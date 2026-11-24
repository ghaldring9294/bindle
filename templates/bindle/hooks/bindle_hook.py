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
import signal
import socket
import subprocess
import sys
from pathlib import Path

# A value that looks like a credential: a keyword (case-insensitive, inside longer names such as
# AWS_SECRET_ACCESS_KEY) assigned something long, or a well-known token format. Placeholders like
# ${VAR} or <redacted> don't count.
LEAK_SHAPES = [re.compile(p) for p in [
    r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d|credential|private[_-]?key)[A-Za-z0-9_]*"
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

SYNCED = ("memory", "projects", "outbox")  # what sync commits by itself; everything else is committed by hand
NETWORK_TIMEOUT = 5  # seconds per network call; a session start makes at most two, within its 20s hook
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

def git(root, *args, network=False):
    """Run git in root. A network call fails fast instead of holding up a session: HTTP gives up on a stalled
    transfer, SSH on a slow connect (unless the repo or person set their own SSH command), and either is cut
    off after NETWORK_TIMEOUT seconds."""
    env, cmd = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}, ["git", "-C", str(root), "-c", "core.quotePath=false"]
    text = {"text": True, "encoding": "utf-8", "errors": "replace"}
    if not network:
        return subprocess.run(cmd + list(args), capture_output=True, env=env, **text)
    cmd += ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=4"]
    own_ssh = subprocess.run(["git", "-C", str(root), "config", "core.sshCommand"], capture_output=True, text=True)
    if not {"GIT_SSH_COMMAND", "GIT_SSH"} & env.keys() and not own_ssh.stdout.strip():
        env["GIT_SSH_COMMAND"] = "ssh -o ConnectTimeout=5 -o BatchMode=yes"
    # Its own process group, so a timeout ends git's helpers (ssh, git-remote-https) too, not just git.
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(cmd + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, **text, **group)
    try:
        out, err = proc.communicate(timeout=NETWORK_TIMEOUT)
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        try:
            proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        return subprocess.CompletedProcess(cmd, 124, "", "timed out")


OFFLINE = ("Could not resolve host", "Could not resolve hostname", "Resolving timed out", "Temporary failure in name",
           "Connection refused", "Connection timed out", "Connection reset", "Connection closed by", "Operation timed out",
           "Operation too slow", "Network is unreachable", "No route to host", "Failed to connect", "SSL_ERROR_SYSCALL",
           "returned error: 502", "returned error: 503", "returned error: 504")


def unreachable(r):
    """A failed network call that means this machine can't reach the remote right now (no network, DNS, a
    refused or timed-out connection). Anything else, such as a rejected key or a missing repository, is a
    problem the person has to fix, so it mustn't be filed as offline."""
    return r.returncode == 124 or any(m in r.stderr for m in OFFLINE)


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
    """Paths with uncommitted changes (modified, staged or untracked, not ignored), NUL-safe. The output isn't
    stripped: each entry starts with a two-letter status, and an unstaged change's first letter is a space."""
    r = git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", *pathspec)
    out = r.stdout if r.returncode == 0 else ""
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


def unmerged_paths(root):
    """Files left mid-conflict (conflict markers in them); committing them would push the markers."""
    out = git_out(root, "diff", "--name-only", "-z", "--diff-filter=U") or ""
    return [p for p in out.split("\0") if p]


def committable_files(root, *pathspec):
    """Tracked and untracked files git would commit (ignored files never leave the machine), NUL-safe."""
    out = git_out(root, "ls-files", "-z", "-co", "--exclude-standard", "--", *pathspec) or ""
    return [p for p in out.split("\0") if p]


# ---------- checks ----------

def looks_secret(text):
    return any(p.search(text) for p in LEAK_SHAPES)


def as_text(data):
    """File bytes as text for the secret check; UTF-16 (with its byte-order mark) would otherwise never match."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="ignore")
    return data.decode("utf-8", errors="ignore")


def secret_hits(root, rel_paths):
    """The given files (relative to root) that look like they hold a credential."""
    hits = []
    for rel in rel_paths:
        f = Path(root) / rel
        if f.is_file() and not f.is_symlink():
            try:
                text = as_text(f.read_bytes())
            except OSError:
                continue
            if looks_secret(text):
                hits.append(rel)
    return hits


def read_objects(root, shas):
    """{sha: (type, bytes)} for the given objects, read in one git process."""
    shas = list(dict.fromkeys(x for x in shas if x))
    if not shas:
        return {}
    r = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"], input=("\n".join(shas) + "\n").encode(),
                       capture_output=True)
    if r.returncode != 0:
        raise OSError("git cat-file failed")
    out, found, i = r.stdout, {}, 0
    while i < len(out):
        nl = out.index(b"\n", i)
        head = out[i:nl].split()
        if len(head) == 3:
            size = int(head[2])
            found[head[0].decode()] = (head[1].decode(), out[nl + 1:nl + 1 + size])
            i = nl + 1 + size + 1
        else:  # "<sha> missing"
            i = nl + 1
    return found


def outgoing_secret_hits(root):
    """Files whose new content looks like it holds a credential, in exactly what a push would send: every file
    version the remote doesn't have yet (so a secret added and later removed counts, and so do binary files and
    odd names, whatever the diff settings), checking only lines the remote's copy of that file doesn't already
    have (a remote file merged in, or a line already there, isn't new)."""
    listed = git(root, "rev-list", "--objects", "@{upstream}..HEAD")
    if listed.returncode != 0:
        return ["(the check couldn't run: git rev-list failed)"]
    new = [(sha, path) for sha, _, path in (l.partition(" ") for l in listed.stdout.splitlines()) if path]
    remote = {}
    for entry in git(root, "ls-tree", "-r", "-z", "@{upstream}").stdout.split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            remote[path] = parts[2]
    try:
        objects = read_objects(root, [sha for sha, _ in new] + [remote.get(path) for _, path in new])
    except OSError:
        return ["(the check couldn't run: git cat-file failed)"]
    hits = []
    for sha, path in new:
        kind, data = objects.get(sha, ("", b""))
        if kind != "blob" or path in hits:
            continue
        old = set(as_text(objects.get(remote.get(path), ("", b""))[1]).splitlines())
        added = [l for l in as_text(data).splitlines() if l not in old]
        if looks_secret("\n".join(added)):
            hits.append(path)
    return hits


def last_run_problems(root, label=None):
    """Every problem the latest sync run logged (or None when that run wasn't `label`): a run can fail early
    and still end with a line like "pulled"."""
    log = git_path(root, "bindle-sync.log")
    lines = log.read_text(encoding="utf-8", errors="ignore").splitlines() if log and log.exists() else []
    marks = [i for i, l in enumerate(lines) if l.startswith(Log.RUN)]
    if label is not None and (not marks or lines[marks[-1]] != f"{Log.RUN} {label}"):
        return None
    run = lines[marks[-1] + 1:] if marks else lines[-1:]
    return [l.split(" problem: ", 1)[1] for l in run if " problem: " in l]


# ---------- sync ----------

class Log:
    RUN = "--- sync"  # starts each run's lines, so doctor can report every problem of the latest run

    def __init__(self, root, echo=False, label=""):
        self.path, self.echo, self.lines, self.label = git_path(root, "bindle-sync.log"), echo, [], label
        self.up_to_date = False  # set once this run has fetched, so the pull needs no second network call

    def say(self, msg, problem=False):
        """Record a sync step. Problems start with "problem:", which doctor and the session start look for."""
        msg = f"problem: {msg}" if problem else msg
        line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        if not self.lines:
            line = f"{self.RUN} {self.label}".rstrip() + f"\n{line}"
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
    """Pull the bindle's latest, fast-forward only; never push (only sync_push does, in the writable bindle)."""
    if operation_in_progress(root):
        return log.say("pull: a merge or rebase is in progress; skipped", problem=True)
    if not has_upstream(root):
        return log.say(no_upstream_message(root, "pull"))
    if log.up_to_date:  # this run already fetched: catch up locally, no second network call
        r = git(root, "merge", "-q", "--ff-only", "@{upstream}")
        if r.returncode == 0:
            log.say("pulled")
        elif (git_out(root, "rev-list", "--count", "HEAD..@{upstream}") or "0") != "0":
            log.say("couldn't catch up with the remote: " + (r.stderr.strip().splitlines() or ["no detail"])[0], problem=True)
        return
    r = git(root, "pull", "-q", "--ff-only", network=True)
    if r.returncode == 0:
        return log.say("pulled")
    if unreachable(r):
        return log.say("offline or the remote is unreachable; not pulled")
    gone = removed_from_remote(root)
    if gone:
        return log.say(rewritten_message(root, gone), problem=True)
    ahead = git_out(root, "rev-list", "--count", "@{upstream}..HEAD") or "0"
    if ahead != "0" and ("fast-forward" in r.stderr or "diverg" in r.stderr):
        return log.say(f"not pulled: this copy has {ahead} commit(s) the remote doesn't, and the remote moved on; "
                       f"put them on top of it and push (git -C {root} pull --rebase && git -C {root} push)", problem=True)
    log.say("pull failed; left as is: " + (r.stderr.strip().splitlines() or ["no detail"])[0], problem=True)


def sync_push(root, log):
    """Commit changes in memory/, projects/ and outbox/ and push them. A file that looks like it holds a secret
    is held back (the rest still sync), so it can't reach the remote; the session start and doctor report it."""
    if operation_in_progress(root):
        return log.say("commit: a merge or rebase is in progress; skipped", problem=True)
    paths = [p for p in SYNCED if (Path(root) / p).exists()]
    changed = changed_paths(root, *paths) if paths else []
    hits = secret_hits(root, changed)
    if hits:
        log.say("held back, may hold a secret: " + ", ".join(hits), problem=True)
    ready = [p for p in changed if p not in hits]
    if ready:
        message = f"Memories from {socket.gethostname().split('.')[0]} on {datetime.date.today()}"
        if git(root, "add", "-A", "--", *ready).returncode != 0 or git(root, "commit", "-q", "-m", message, "--", *ready).returncode != 0:
            return log.say("commit failed", problem=True)
        log.say("committed memory changes")
    push_leftovers(root, log)


def no_upstream_message(root, step):
    if git_out(root, "remote"):
        return f"{step}: a remote is set but the branch has no upstream; run `git -C {root} push -u origin HEAD` once"
    return f"{step}: no remote, kept local"


def removed_from_remote(root):
    """Commits this copy has that the remote once had and no longer does: its history was rewritten, usually to
    remove something. Read from the tracking ref's reflog, so it stays true after later fetches move the ref."""
    ref = git_out(root, "rev-parse", "--symbolic-full-name", "@{upstream}")
    olds = (git_out(root, "reflog", "show", "--format=%H", "-n", "200", ref) or "").split() if ref else []
    if not olds:
        return []
    gone = set((git_out(root, "rev-list", *dict.fromkeys(olds), "--not", "@{upstream}") or "").split())
    mine = set((git_out(root, "rev-list", "HEAD", "--not", "@{upstream}") or "").split()) if gone else set()
    return sorted(gone & mine)


def rewritten_message(root, gone):
    return (f"the remote's history was rewritten and no longer has {len(gone)} commit(s) this copy still has "
            f"(perhaps removed on purpose), so sync won't push or replay them. Look at git -C {root} log "
            f"@{{upstream}}..HEAD, drop what should stay gone (git -C {root} rebase -i @{{upstream}}), then run bindle sync")


def push_checked(root):
    """Push HEAD to its upstream branch only: exactly the range outgoing_secret_hits checked."""
    branch = git_out(root, "symbolic-ref", "--short", "HEAD") or ""
    remote = git_out(root, "config", f"branch.{branch}.remote") or "origin"
    merge = git_out(root, "config", f"branch.{branch}.merge") or f"refs/heads/{branch}"
    return git(root, "push", "-q", "--no-follow-tags", remote, f"HEAD:{merge}", network=True)


def push_leftovers(root, log):
    """Push local commits. It fetches first, so it can see a remote whose history was rewritten (to remove a
    leaked secret, say) and check for secrets against what the remote really has. If the remote moved, it
    rebases onto it, but only when no uncommitted file here is one the remote changed (stashing such a file
    could leave conflict markers in it)."""
    if not has_upstream(root):
        return log.say(no_upstream_message(root, "push"))
    if (git_out(root, "rev-list", "--count", "@{upstream}..HEAD") or "0") == "0":
        return
    r = git(root, "fetch", "-q", network=True)
    if r.returncode != 0:
        if unreachable(r):
            return log.say("offline or the remote is unreachable; commits kept local until next time")
        return log.say("couldn't fetch the remote; commits kept local: "
                       + (r.stderr.strip().splitlines() or ["no detail"])[0], problem=True)
    log.up_to_date = True
    gone = removed_from_remote(root)
    if gone:
        return log.say(rewritten_message(root, gone), problem=True)
    if (git_out(root, "rev-list", "--count", "@{upstream}..HEAD") or "0") == "0":
        return
    if git(root, "merge-base", "--is-ancestor", "@{upstream}", "HEAD").returncode != 0:  # the remote moved
        # Without rename detection a renamed file lists both names, so an uncommitted edit to the old one is caught.
        incoming = set((git_out(root, "diff", "--name-only", "--no-renames", "HEAD...@{upstream}") or "").splitlines())
        clash = sorted(incoming & set(changed_paths(root)))
        if clash:
            return log.say(f"the remote changed {', '.join(clash)}, which have uncommitted changes here; commit or "
                           f"discard them, then run bindle sync", problem=True)
        stashes = len((git_out(root, "stash", "list") or "").splitlines())
        r = git(root, "rebase", "-q", "--autostash", "@{upstream}")
        if r.returncode != 0:
            if operation_in_progress(root):
                git(root, "rebase", "--abort")
            return log.say("couldn't rebase onto the remote; commits kept local: "
                           + (r.stderr.strip().splitlines() or ["no detail"])[0], problem=True)
        if unmerged_paths(root) or len((git_out(root, "stash", "list") or "").splitlines()) > stashes:
            log.say(f"your uncommitted changes didn't apply cleanly over the remote's; they're in git stash and "
                    f"{', '.join(unmerged_paths(root)) or 'the stash'} needs resolving (git -C {root} status)", problem=True)
    hits = outgoing_secret_hits(root)
    if hits:
        return log.say(f"not pushing: unpushed commits add what looks like a secret to {', '.join(hits)}. Take it out "
                       f"of those commits (git -C {root} reset --soft @{{upstream}}, remove it, commit again), then "
                       f"run bindle sync", problem=True)
    r = push_checked(root)
    if r.returncode == 0:
        return log.say("pushed")
    if unreachable(r):
        return log.say("offline or the remote is unreachable; commits kept local until next time")
    if "[rejected]" in r.stderr:  # another machine pushed between our fetch and our push
        return log.say("the remote moved during sync; commits kept local, pushed next time")
    log.say("push failed; commits kept local: " + (r.stderr.strip().splitlines() or ["no detail"])[0], problem=True)


# ---------- session text ----------

def has_notes(root):
    notes = Path(root) / "notes"
    return notes.is_dir() and any(
        f.is_file() and f.name != ".gitkeep" and f.relative_to(notes).as_posix() != "scratch/README.md"
        for f in notes.rglob("*"))


def inbox_notes(root):
    inbox = Path(root) / "notes" / "inbox.md"
    return sum(1 for l in inbox.read_text(encoding="utf-8", errors="ignore").splitlines()
               if l.startswith("## ")) if inbox.is_file() else 0


def session_start_text(root, project_dir):
    root = Path(root)
    name, memory = bindle_name(root), root / "memory"
    out = []
    if writable_here(root, project_dir):
        out.append(f"Bindle {name} is on and writable in this folder: new memories are saved to {memory}. "
                   f"Organize memories as you judge best; a default that keeps the index short: a memory about only "
                   f"one project in {root}/projects/<project>/, listed in that folder's index.md, with one pointer "
                   f"line per project in MEMORY.md. To put something into another bindle (\"add this to my personal "
                   f"bindle too\", \"move this skill to my craft\"), use the /bindle-promote skill; never write into "
                   f"another bindle's folder directly.")
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
        inbox, waiting = root / "notes" / "inbox.md", inbox_notes(root)
        if waiting:
            out.append(f"{inbox} has {waiting} note(s) sent from other domains (reminders, todos). Mention them to the "
                       f"person early in the session, and remove each one once they've handled it.")
        if has_notes(root):
            readme = root / "notes" / "README.md"
            out.append(f"Notes for this domain are in {root}/notes (read them when relevant; they aren't loaded "
                       f"automatically)." + (f" Start at {readme}." if readme.is_file() else ""))
        return "\n".join(out)
    out.append(f"Bindle {name} is on and read-only in this folder ({root}): use its skills and memories, but don't "
               f"edit its files. Material moves into it only through promotion (bindle promote, which the user approves), never a direct edit.")
    index = memory / "MEMORY.md"
    if index.is_file() and index.stat().st_size:
        out.append(f"Memory index from the {name} bindle (files are in {memory}):")
        out.append(index.read_text(encoding="utf-8", errors="ignore").rstrip("\n"))
    return "\n".join(out)


# ---------- global rules (an import in the user CLAUDE.md) ----------

GLOBAL_START = "<!-- bindle global: start"
GLOBAL_END = "<!-- bindle global: end -->"


def user_claude_md():
    """The user CLAUDE.md where Claude Code reads it: in $CLAUDE_CONFIG_DIR when set, else ~/.claude."""
    base = (os.environ.get("CLAUDE_CONFIG_DIR") or "").strip()
    return (Path(base) if base else Path.home() / ".claude") / "CLAUDE.md"


def decode_text(data):
    """A CLAUDE.md's bytes as (text, BOM, codec), so a rewrite keeps its encoding. Raises ValueError for anything but
    UTF-8 or a UTF-16 file with a BOM (Windows editors can save that)."""
    for bom, codec in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if data.startswith(bom):
            return data[len(bom):].decode(codec), bom, codec
    return data.decode("utf-8"), b"", "utf-8"


def global_block(lines):
    """The indexes of the bindle-global block's start and end lines, or None. Raises ValueError when a marker is
    missing or repeated: rewriting then could eat the person's own text."""
    starts = [i for i, l in enumerate(lines) if l.strip().startswith(GLOBAL_START)]
    ends = [i for i, l in enumerate(lines) if l.strip() == GLOBAL_END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise ValueError("its bindle global block has a missing or repeated marker line")
    return starts[0], ends[0]


def import_line(path):
    """How the block imports a file: absolute, forward slashes on every OS (a backslash escapes), spaces escaped."""
    return "@" + Path(path).as_posix().replace(" ", "\\ ")


def global_imports(text):
    """The files the bindle-global block of a CLAUDE.md's text imports."""
    lines = text.splitlines()
    block = global_block(lines)
    if not block:
        return []
    return [Path(l.strip()[1:].replace("\\ ", " ")) for l in lines[block[0] + 1:block[1]] if l.strip().startswith("@")]


def user_global_imports():
    try:
        return global_imports(decode_text(user_claude_md().read_bytes())[0])
    except (OSError, ValueError):
        return []


def imported_globally(root):
    """True when the user CLAUDE.md imports this bindle's rules.md, so every session already has it."""
    rules = real(Path(root) / "rules.md")
    return any(real(p) == rules for p in user_global_imports())


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
    log = Log(root, label=command)
    try:
        if command == "session-start":
            # Problems the last session's end ran into (it can't show anything itself), shown before this run's.
            ended = (last_run_problems(root, label="session-end") or []) if sync_enabled(root) else []
            changed_code, before = [], git_out(root, "rev-parse", "HEAD")
            if sync_enabled(root):
                if writable_here(root, project_dir):
                    # A session that ended without SessionEnd (a closed app, a killed terminal) leaves memories
                    # uncommitted; commit and push them before anything else.
                    sync_push(root, log)
                sync_pull(root, log)
            after = git_out(root, "rev-parse", "HEAD")
            if before and after and before != after:  # code the remote brought in, by a pull or a rebase
                changed = git_out(root, "diff", "--name-only", f"{before}..{after}", "--", *CODE_PATHS) or ""
                changed_code = [c for c in changed.splitlines() if c]
            review = f"git -C {root} diff {(before or '')[:12]}..{(after or '')[:12]} -- {' '.join(CODE_PATHS)}"
            out = []
            if changed_code:
                out.append(f"Warning: bindle {bindle_name(root)} just pulled changes to files that run code on this machine "
                           f"({', '.join(changed_code)}). They take effect from the next session. Tell the person, so they "
                           f"can review them ({review}) before starting another session.")
            out.append(session_start_text(root, project_dir))
            text = "\n".join(t for t in out if t)
            visible = []
            if changed_code:
                visible.append(f"bindle: {bindle_name(root)} pulled changes to code that runs on this machine "
                               f"({', '.join(changed_code)}); review them before your next session: "
                               f"{review}")
            now = [l[len("problem: "):] for l in log.lines if l.startswith("problem: ")]
            visible += [f"bindle: {bindle_name(root)} sync at the last session's end: problem: {l}" for l in ended if l not in now]
            visible += [f"bindle: {bindle_name(root)} sync problem: {l}" for l in now]
            conflicted = unmerged_paths(root)
            if conflicted:
                visible.append(f"bindle: {bindle_name(root)} has unresolved conflicts in {', '.join(conflicted)}; "
                               f"resolve them before committing (git -C {root} status)")
            waiting = inbox_notes(root) if writable_here(root, project_dir) else 0
            if waiting:
                visible.append(f"bindle: {waiting} note(s) from other domains waiting in {Path(root) / 'notes' / 'inbox.md'}")
            if visible:  # plain output reaches only Claude, which can't speak first; systemMessage shows in the terminal
                print(json.dumps({"systemMessage": "\n".join(visible),
                                  "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
            elif text:
                print(text)
        elif command == "rules":
            # Imported by the user CLAUDE.md (bindle global): printing it too would load it twice.
            text = "" if imported_globally(root) else rules_text(root)
            if text:
                print(text)
        elif command == "session-end":
            if sync_enabled(root) and writable_here(root, project_dir):
                before = git_out(root, "rev-parse", "HEAD")
                sync_push(root, log)
                after = git_out(root, "rev-parse", "HEAD")
                changed = git_out(root, "diff", "--name-only", f"{before}..{after}", "--", *CODE_PATHS) if before and after and before != after else ""
                if changed:  # a rebase brought in code; the next session start shows this
                    log.say(f"pulled changes to code that runs on this machine ({', '.join(changed.splitlines())}); "
                            f"review them before your next session: git -C {root} diff {before[:12]}..{after[:12]} -- "
                            f"{' '.join(CODE_PATHS)}", problem=True)
    except Exception as e:  # a hook must never break a session
        log.say(f"{command} error: {e!r}", problem=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
