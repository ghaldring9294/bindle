#!/usr/bin/env python3
"""Hooks for a bindle, and the one implementation of the logic the bindle CLI shares with them.

Managed by bindle: copied byte for byte into every bindle (`bindle doctor` flags a copy that differs).
Claude Code runs it as `bindle_hook.py session-start|rules|session-end` with CLAUDE_PLUGIN_ROOT set to
the bindle's folder and CLAUDE_PROJECT_DIR set to the folder the session started in. Standard library
only, Python 3.9+. A hook must never fail or block a session, so every entry point swallows errors.
"""
import datetime
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

# A value that looks like a credential: a keyword (case-insensitive, inside longer names such as
# AWS_SECRET_ACCESS_KEY) assigned something long, or a well-known token format. Placeholders like
# ${VAR} or <redacted> don't count.
SECRET_PATTERNS = [re.compile(p) for p in [
    r"(?i)[A-Za-z0-9_]*(?:api[_-]?key|secret|token|passw(?:or)?d|credential|private[_-]?key)[A-Za-z0-9_]*"
    r"[\"']?\s*[:=]\s*[\"']?(?![$<{(])[^\s\"'`]{12,}",
    r"Bearer\s+[A-Za-z0-9._~+/-]{20,}",
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"\bxapp-[A-Za-z0-9-]{10,}",
    r"\bsk-ant-[A-Za-z0-9_-]{20,}",
    r"\bsk-[A-Za-z0-9_-]{20,}",
    r"\bAIza[0-9A-Za-z_-]{35}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]]

SYNCED = ("memory", "outbox")  # what sync commits by itself; everything else is committed by hand
# Parts of a plugin that run code on the person's machine (hooks, servers, executables).
CODE_PATHS = ("hooks", ".claude-plugin/plugin.json", ".mcp.json", ".lsp.json", "bin")


def real(path):
    return Path(os.path.realpath(os.path.expanduser(str(path))))


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}


def bindle_name(root):
    return read_json(Path(root) / "bindle.json").get("name") or "unnamed"


def sync_enabled(root):
    return read_json(Path(root) / "bindle.json").get("sync") is True


def writable_here(root, project_dir):
    """True when the folder the session started in writes its memories into this bindle."""
    memory_dir = read_json(Path(project_dir) / ".claude" / "settings.local.json").get("autoMemoryDirectory")
    return bool(memory_dir) and real(memory_dir) == real(Path(root) / "memory")


# ---------- git ----------

def git(root, *args):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    env.setdefault("GIT_SSH_COMMAND", "ssh -o ConnectTimeout=5 -o BatchMode=yes")
    return subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def git_out(root, *args):
    r = git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else None


def git_path(root, name):
    """A path inside the repo's git directory, correct for worktrees and separate git dirs too."""
    p = git_out(root, "rev-parse", "--git-path", name)
    if not p:
        return None
    p = Path(p)
    return p if p.is_absolute() else Path(root) / p


def has_upstream(root):
    return git_out(root, "rev-parse", "--abbrev-ref", "@{upstream}") is not None


def operation_in_progress(root):
    """A merge or rebase the person is in the middle of; sync must not commit into it."""
    for name in ("MERGE_HEAD", "rebase-merge", "rebase-apply"):
        p = git_path(root, name)
        if p is not None and p.exists():
            return True
    return False


def changed_paths(root, *pathspec):
    """Paths with uncommitted changes (modified, staged or untracked, not ignored), NUL-safe."""
    out = git_out(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", *pathspec) or ""
    paths, entries = [], out.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        if len(e) > 3:
            paths.append(e[3:])
            if e[0] in "RC":  # renames carry the old path as the next entry
                i += 1
        i += 1
    return paths


def committable_files(root, *pathspec):
    """Tracked and untracked files git would commit (ignored files never leave the machine), NUL-safe."""
    out = git_out(root, "ls-files", "-z", "-co", "--exclude-standard", "--", *pathspec) or ""
    return [p for p in out.split("\0") if p]


# ---------- checks ----------

def looks_secret(text):
    return any(p.search(text) for p in SECRET_PATTERNS)


def secret_hits(root, rel_paths):
    """The given files (relative to root) that look like they hold a credential."""
    hits = []
    for rel in rel_paths:
        f = Path(root) / rel
        if f.is_file() and not f.is_symlink():
            try:
                text = f.read_bytes().decode("utf-8", errors="ignore")
            except OSError:
                continue
            if looks_secret(text):
                hits.append(rel)
    return hits


# ---------- sync ----------

class Log:
    def __init__(self, root, echo=False):
        self.path, self.echo, self.lines = git_path(root, "bindle-sync.log"), echo, []

    def say(self, msg):
        line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        self.lines.append(msg)
        if self.echo:
            print(msg)
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


def sync_pull(root, log):
    """Pull the bindle's latest, and push commits an earlier session left behind. Returns the files that run
    code (hooks, servers, executables) the pull changed, so the session can be warned before they next run."""
    if operation_in_progress(root):
        log.say("pull: a merge or rebase is in progress; skipped")
        return []
    if not has_upstream(root):
        log.say(no_upstream_message(root, "pull"))
        return []
    push_leftovers(root, log)
    before = git_out(root, "rev-parse", "HEAD")
    r = git(root, "pull", "-q", "--ff-only")
    log.say("pulled" if r.returncode == 0 else "pull failed or not fast-forward; left as is")
    after = git_out(root, "rev-parse", "HEAD")
    if not before or before == after:
        return []
    changed = git_out(root, "diff", "--name-only", f"{before}..{after}", "--", *CODE_PATHS) or ""
    return [p for p in changed.splitlines() if p]


def sync_push(root, log):
    """Commit memory/ and outbox/ changes and push them. Refuses when a file looks like it holds a secret:
    nothing is committed, so nothing can reach the remote, and `bindle doctor` reports it."""
    if operation_in_progress(root):
        return log.say("commit: a merge or rebase is in progress; skipped")
    paths = [p for p in SYNCED if (Path(root) / p).exists()]
    changed = changed_paths(root, *paths) if paths else []
    if changed:
        hits = secret_hits(root, changed)
        if hits:
            log.say("refused: possible secret in " + ", ".join(hits))
            print(f"bindle: not syncing {bindle_name(root)}; possible secret in: {', '.join(hits)}", file=sys.stderr)
            return
        message = f"Memories from {socket.gethostname().split('.')[0]} on {datetime.date.today()}"
        if git(root, "add", "-A", "--", *paths).returncode != 0 or git(root, "commit", "-q", "-m", message, "--", *paths).returncode != 0:
            return log.say("commit failed")
        log.say("committed memory changes")
    push_leftovers(root, log)


def no_upstream_message(root, step):
    if git_out(root, "remote"):
        return f"{step}: a remote is set but the branch has no upstream; run `git -C {root} push -u origin HEAD` once"
    return f"{step}: no remote, kept local"


def push_leftovers(root, log):
    if not has_upstream(root):
        return log.say(no_upstream_message(root, "push"))
    ahead = git_out(root, "rev-list", "--count", "@{upstream}..HEAD") or "0"
    if ahead == "0":
        return
    if git(root, "pull", "-q", "--rebase", "--autostash").returncode != 0:
        git(root, "rebase", "--abort")
        return log.say("rebase conflict; commits kept local")
    log.say("pushed" if git(root, "push", "-q").returncode == 0 else "push failed; commits kept local")


# ---------- session text ----------

def has_notes(root):
    notes = Path(root) / "notes"
    return notes.is_dir() and any(
        f.is_file() and f.name != ".gitkeep" and f.relative_to(notes).as_posix() != "scratch/README.md"
        for f in notes.rglob("*"))


def session_start_text(root, project_dir):
    root = Path(root)
    name, memory = bindle_name(root), root / "memory"
    out = []
    if writable_here(root, project_dir):
        out.append(f"Bindle {name} is on and writable in this folder: new memories are saved to {memory}. "
                   f"A memory about only one project goes in {root}/projects/<project>/ instead, listed in that "
                   f"folder's index.md, with one pointer line per project in MEMORY.md; a memory that spans "
                   f"projects stays in {memory}.")
        pending = changed_paths(root)
        if sync_enabled(root):
            pending = [p for p in pending if p.split("/")[0] not in SYNCED]
        if pending:
            in_notes = [p for p in pending if p.startswith("notes/")]
            out.append(f"Bindle {name} has {len(pending)} uncommitted change(s) ({len(in_notes)} in notes). Remind the "
                       f"person to commit what's ready: git -C {root} add -A && git -C {root} commit.")
            risky = secret_hits(root, in_notes)
            if risky:
                out.append(f"Before committing: {', '.join(risky)} may hold a secret. Suggest moving it to secure "
                           f"storage (a password manager) and leaving a pointer in the note.")
        if has_notes(root):
            readme = root / "notes" / "README.md"
            out.append(f"Notes for this domain are in {root}/notes (read them when relevant; they aren't loaded "
                       f"automatically)." + (f" Start at {readme}." if readme.is_file() else ""))
        return "\n".join(out)
    out.append(f"Bindle {name} is on and read-only in this folder ({root}): use its skills and memories, but don't "
               f"edit its files. Material moves into it only through promotion (its outbox), never a direct edit.")
    index = memory / "MEMORY.md"
    if index.is_file() and index.stat().st_size:
        out.append(f"Memory index from the {name} bindle (files are in {memory}):")
        out.append(index.read_text(encoding="utf-8", errors="ignore").rstrip("\n"))
    return "\n".join(out)


def rules_text(root):
    rules = Path(root) / "rules.md"
    if not rules.is_file() or not rules.stat().st_size:
        return ""
    return (f"Standing instructions from the {bindle_name(root)} bindle ({rules}). Follow them as you would CLAUDE.md:\n"
            + rules.read_text(encoding="utf-8", errors="ignore").rstrip("\n"))


# ---------- entry point ----------

def main(argv):
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or str(Path(__file__).resolve().parent.parent)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    command = argv[1] if len(argv) > 1 else ""
    try:
        if command == "session-start":
            changed_code = []
            if sync_enabled(root):
                if writable_here(root, project_dir):
                    # A session that ended without SessionEnd (a closed app, a killed terminal) leaves memories
                    # uncommitted; commit and push them before anything else.
                    sync_push(root, Log(root))
                changed_code = sync_pull(root, Log(root))
            if changed_code:
                print(f"Warning: bindle {bindle_name(root)} just pulled changes to files that run code on this machine "
                      f"({', '.join(changed_code)}). They take effect from the next session. Tell the person, so they "
                      f"can review them (git -C {root} log -p -1 -- {' '.join(CODE_PATHS)}) before starting another session.")
            text = session_start_text(root, project_dir)
            if text:
                print(text)
        elif command == "rules":
            text = rules_text(root)
            if text:
                print(text)
        elif command == "session-end":
            if sync_enabled(root) and writable_here(root, project_dir):
                sync_push(root, Log(root))
    except Exception as e:  # a hook must never break a session
        Log(root).say(f"{command} error: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
