"""What every command shares: bindles, a folder's settings, git, locks and the hook module.

A bindle is one domain's layer in its own git repo, shaped as a Claude Code plugin. A folder turns
bindles on in its .claude/settings.local.json: every attached bindle is on there, and at most one is
writable (new memories land in its memory/ folder). bindle keeps only an index of where bindles live (~/bindles/registry.json); it reads and writes
those settings. Standard library only; Python 3.9+.
"""
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path, PureWindowsPath

WINDOWS = os.name == "nt"

BASE = Path(os.path.realpath(__file__)).parent.parent
TEMPLATE = BASE / "templates" / "bindle"
LAYOUT = 1
VERSION = "0.31.0"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# Files bindle owns inside every bindle; doctor flags copies that drifted from the template.
MANAGED = ["hooks/bindle_hook.py", "hooks/run", "hooks/hooks.json"]
# Managed files from earlier versions; `bindle upgrade` removes them.
OBSOLETE = ["hooks/print-memory.sh", "hooks/lib.sh", "hooks/session-start.sh", "hooks/session-end.sh", "hooks/rules.sh"]
# SessionStart hook output is capped at 10,000 characters; leave room for the header line.
RULES_LIMIT = 9000
HOOK_OUTPUT_LIMIT = 10000


class BindleError(Exception):
    pass


def hooks():
    """The template's bindle_hook.py, imported, so the CLI and every bindle's hooks share one implementation."""
    if not hasattr(hooks, "module"):
        spec = importlib.util.spec_from_file_location("bindle_hook", TEMPLATE / "hooks" / "bindle_hook.py")
        hooks.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks.module)
    return hooks.module


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise BindleError(f"{path} isn't valid JSON ({e}); fix it by hand first.")


def write_text(path, text, mode="w"):
    """Write UTF-8 with LF line endings on every OS. Windows' default CRLF made git read a bindle's .gitignore
    oddly, and a CRLF shell script fails in bash."""
    with open(path, mode, encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def real(path):
    return Path(os.path.realpath(os.path.expanduser(str(path))))


def settings_path(folder):
    return Path(folder) / ".claude" / "settings.local.json"


def load_bindle(path):
    """The bindle at path: its name, marketplace name and paths. Raises if path isn't a bindle."""
    root = real(path)
    meta = read_json(root / "bindle.json")
    if not meta.get("name"):
        raise BindleError(f"{root} isn't a bindle (no bindle.json with a name).")
    market = read_json(root / ".claude-plugin" / "marketplace.json").get("name")
    if not market:
        raise BindleError(f"{root} has no .claude-plugin/marketplace.json name.")
    return {"name": meta["name"], "market": market, "root": root, "memory": root / "memory",
            "layout": meta.get("layout"), "sync": meta.get("sync") is True, "files_from": meta.get("bindle_version"),
            "audience": meta.get("audience", "private"), "writes": meta.get("writes", "implicit")}


def version_tuple(text):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    return tuple(int(n) for n in m.groups()) if m else None


def from_newer_bindle(b):
    """True when a newer bindle (on another machine) last wrote this bindle's files: upgrading from this copy
    would put old hooks back, and sync would spread them."""
    files_from = version_tuple(b["files_from"])
    return bool(files_from) and files_from > version_tuple(VERSION)


def bindles_home():
    """Where bindles used by many folders live: $BINDLE_HOME, or ~/bindles."""
    return real(os.environ.get("BINDLE_HOME") or Path.home() / "bindles")


def registry_path():
    return bindles_home() / "registry.json"


def registry():
    """Bindles that live outside bindles_home() (domain bindles, usually), by name: {name: path}. A plain file
    the person can read and edit; `new` and `attach` keep it current. Bindles in bindles_home() need no entry."""
    entries = read_json(registry_path()).get("bindles", {})
    return entries if isinstance(entries, dict) else {}


def register(b):
    """Record where a bindle lives, so it can be found by name from any folder. Returns a warning, or None.
    Names must be unique on a machine: Claude Code's marketplace names (bindle-<name>) are machine-wide."""
    name, root, home = b["name"], b["root"], bindles_home()
    in_home = home / name
    if in_home.exists() and real(in_home) != root:
        return f"another bindle named {name} is at {in_home}; names must be unique on a machine, so rename one"
    entries = registry()
    if real(root.parent) == real(home) and root.name == name:
        if name in entries:  # it moved into the home folder; its folder name finds it now
            del entries[name]
            save_registry("bindles", entries)
        return None
    other = entries.get(name)
    if other and real(other) != root and (Path(other) / "bindle.json").exists():
        return (f"another bindle named {name} is registered at {other}; names must be unique on a machine, "
                f"so rename one (README: Renaming a bindle)")
    if other and real(other) == root:
        return None
    entries[name] = str(root)
    save_registry("bindles", entries)
    return None


def save_registry(key, entries):
    """Rewrite one section of registry.json, keeping the others."""
    data = read_json(registry_path())
    data[key] = dict(sorted(entries.items()))
    write_json(registry_path(), data)


def domains():
    """Folders a bindle was attached to as writable: {folder: bindle name}. The session check warns when a
    session starts inside one of them with no writable bindle, since its memories would miss the domain."""
    entries = read_json(registry_path()).get("domains", {})
    return entries if isinstance(entries, dict) else {}


def set_domain(folder, name):
    """Record (or with name None, forget) a folder's writable bindle."""
    entries = domains()
    if name:
        entries[str(folder)] = name
    elif entries.pop(str(folder), None) is None:
        return
    save_registry("domains", entries)


def known_bindles():
    """Every bindle bindle can find without a folder: those in bindles_home() and those registered.
    Returns ({root: bindle}, [(name, path) of registered bindles that are gone])."""
    found, missing, home = {}, [], bindles_home()
    candidates = [d for d in sorted(home.iterdir()) if d.is_dir()] if home.is_dir() else []
    for name, path in registry().items():
        if (Path(path) / "bindle.json").exists():
            candidates.append(Path(path))
        else:
            missing.append((name, path))
    for d in candidates:
        if (d / "bindle.json").exists():
            try:
                b = load_bindle(d)
            except BindleError:
                continue
            found[str(b["root"])] = b
    return found, missing


def find_bindle(arg):
    """A bindle given as a path, or by name: a folder in bindles_home(), or a registered bindle."""
    if Path(os.path.expanduser(arg)).exists() or not NAME_RE.match(arg):
        return load_bindle(arg)
    if (bindles_home() / arg).exists():
        return load_bindle(bindles_home() / arg)
    path = registry().get(arg)
    if path and Path(path).exists():
        return load_bindle(path)
    if path:
        raise BindleError(f"{arg} is registered at {path}, but nothing is there now. Pass its new path.")
    raise BindleError(f"No bindle named {arg} in {bindles_home()} or its registry. Pass the bindle's path "
                      f"(attaching it once registers it), or set BINDLE_HOME to the folder your bindles live in.")


def quote(path):
    """Quote a path for copy-and-paste: POSIX shells on macOS and Linux; PowerShell and cmd on Windows."""
    s = str(path)
    if WINDOWS:
        return f'"{s}"' if any(c in s for c in ' &()[]{}^=;!\'+,`~') else s
    return shlex.quote(s)


def ref(b):
    """How a suggested command names a bindle: by name when that finds this same bindle, else by path."""
    try:
        if find_bindle(b["name"])["root"] == b["root"]:
            return b["name"]
    except BindleError:
        pass
    return quote(str(b["root"]))


def name_problems(b):
    """A bindle's name appears in three files; renaming one by hand and not the others breaks attach and
    detach in confusing ways."""
    root, name = b["root"], b["name"]
    plugin = read_json(root / ".claude-plugin" / "plugin.json").get("name")
    market = read_json(root / ".claude-plugin" / "marketplace.json")
    listed = [p.get("name") for p in market.get("plugins", []) if isinstance(p, dict)]
    found = []
    if plugin != name:
        found.append(f".claude-plugin/plugin.json has name {plugin!r}")
    if market.get("name") != f"bindle-{name}":
        found.append(f".claude-plugin/marketplace.json has name {market.get('name')!r}, not 'bindle-{name}'")
    if listed != [name]:
        found.append(f".claude-plugin/marketplace.json lists plugins {listed}, not ['{name}']")
    return [f"{name}: bindle.json says {name!r} but {f}; make the names agree (README: Renaming a bindle)" for f in found]


def plugin_id(b):
    return f"{b['name']}@{b['market']}"


def git(folder, *args):
    return hooks().git_out(folder, *args)


def check_folder(folder):
    """Claude Code reads settings.local.json at the git repo root, so a folder inside a repo it
    isn't the root of would get its settings written somewhere else."""
    folder = real(folder)
    if not folder.is_dir():
        raise BindleError(f"{folder} isn't a folder.")
    if WINDOWS:
        return folder  # on Windows, Claude Code reads settings.local.json in the launch folder itself
    top = git(folder, "rev-parse", "--show-toplevel")
    if top and real(top) != folder:
        raise BindleError(
            f"{folder} is inside the git repo {top}. Claude Code reads settings at the repo root, "
            f"so attach to {top} instead, or to a folder that isn't inside a repo.")
    return folder


def claude(folder, *args):
    exe = os.environ.get("BINDLE_CLAUDE", "claude")
    # Windows can't execute a script directly; run a Python stand-in (the tests' fake claude) with Python.
    cmd = [sys.executable, exe] if WINDOWS and exe.endswith(("fake_claude", ".py")) else [exe]
    r = subprocess.run([*cmd, *args], cwd=str(folder), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise BindleError(f"`claude {' '.join(args)}` failed:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout


# ---------- the read-only lock ----------

GLOB_CHARS = set("*?[]")


def lock_rules(root):
    """Permission rules that stop Claude's file-editing tools changing a bindle that's read-only in a folder.
    `//` makes the path absolute; an Edit rule covers every file-editing tool (Claude Code ignores Write(path)
    rules). It doesn't cover shell commands."""
    paths, root = [Path(root)], Path(root)
    # When ~/bindles (or $BINDLE_HOME) is a link, Claude may see a bindle's files by the link's path; lock both.
    link_home = Path(os.path.abspath(os.path.expanduser(str(os.environ.get("BINDLE_HOME") or Path.home() / "bindles"))))
    if link_home != real(link_home) and real(link_home) in root.parents:
        paths.append(link_home / root.relative_to(real(link_home)))
    return [f"Edit(/{rule_path(p)}/**)" for p in paths]


def rule_path(root):
    """A path in Claude Code's permission-rule form: POSIX, and on Windows the drive as /c (C:\\x -> /c/x)."""
    s = str(root)
    p = PureWindowsPath(s).as_posix() if re.match(r"^[A-Za-z]:[\\/]", s) else Path(s).as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else p


def lock_is_exact(root):
    """Permission paths are patterns, so a bindle path containing pattern characters may not match exactly."""
    return not (GLOB_CHARS & set(str(root)))


def set_lock(settings, root, locked):
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    rules = lock_rules(root)
    if locked:
        deny.extend(r for r in rules if r not in deny)
    else:
        deny[:] = [r for r in deny if r not in rules]
    if not deny:
        del settings["permissions"]["deny"]
    if not settings["permissions"]:
        del settings["permissions"]


# ---------- the bindles a folder declares ----------

def directory_marketplaces(settings):
    for market, entry in settings.get("extraKnownMarketplaces", {}).items():
        source = entry.get("source", {}) if isinstance(entry, dict) else {}
        if source.get("source") == "directory" and source.get("path"):
            yield market, source["path"]


def declared_bindles(settings):
    out = []
    for market, path in directory_marketplaces(settings):
        try:
            b = load_bindle(path)
        except BindleError:
            continue
        if b["market"] == market:
            out.append(b)
    return out


def missing_bindles(settings):
    """Local marketplaces this folder declares whose folder is gone, usually a bindle that moved."""
    return [(market, path) for market, path in directory_marketplaces(settings) if not Path(path).exists()]


def is_writable(settings, b):
    memory_dir = settings.get("autoMemoryDirectory")
    return bool(memory_dir) and real(memory_dir) == real(b["memory"])


# ---------- a bindle inside another repo ----------

def enclosing_repo(path):
    """The git repo a path sits inside (not counting a repo at the path itself), and the path relative to it."""
    top = git(Path(path).parent, "rev-parse", "--show-toplevel")
    if not top:
        return None
    return real(top), real(path).relative_to(real(top)).as_posix()


def exclude_pattern(rel):
    """A .gitignore-style line matching exactly this folder, with pattern characters escaped."""
    escaped = re.sub(r"([*?\[\]\\])", r"\\\1", rel)
    if escaped[:1] in ("!", "#"):
        escaped = "\\" + escaped
    return f"/{escaped}/"


def exclude_from_enclosing_repo(dest):
    """A bindle inside a project repo would show up as untracked there, and one `git add -A` would push
    private memories into that repo. Exclude it locally (.git/info/exclude), leaving the team's .gitignore alone."""
    found = enclosing_repo(dest)
    if not found:
        return None
    top, rel = found
    if git(top, "check-ignore", "-q", rel + "/") is not None:
        return None  # already ignored
    exclude = hooks().git_path(top, "info/exclude")
    exclude.parent.mkdir(parents=True, exist_ok=True)
    pattern = exclude_pattern(rel)
    write_text(exclude, f"\n# bindle: a private bindle lives here\n{pattern}\n", mode="a")
    return top, pattern


def enclosing_repo_problems(b):
    found = enclosing_repo(b["root"])
    if not found:
        return []
    top, rel = found
    if git(top, "ls-files", "--", rel):
        if read_json(b["root"] / "bindle.json").get("demo") is True:
            return []  # a demo bindle is folded into its repo on purpose
        return [f"{b['name']}: tracked by the repo {top}, so its memories get pushed with that repo. "
                f"Remove it from that repo (git rm -r --cached {rel}) and exclude it."]
    if git(top, "check-ignore", "-q", rel + "/") is None:
        return [f"{b['name']}: inside the repo {top} and not ignored there, so `git add -A` would commit it. "
                f"Add {exclude_pattern(rel)} to {top}/.git/info/exclude."]
    return []


# ---------- git health ----------

def git_health(root):
    """Lines describing work that isn't safely in git yet. Returns (lines, problems)."""
    if git(root, "rev-parse", "--git-dir") is None:
        return ["not a git repo"], [f"{root} isn't a git repo"]
    lines, problems = [], []
    dirty = hooks().changed_paths(root)
    if dirty:
        lines.append(f"{len(dirty)} uncommitted change(s)")
    if not git(root, "remote"):
        lines.append("no remote (local only)")
    elif not hooks().has_upstream(root):
        lines.append("remote set, but the branch has no upstream")
        problems.append(f"{root}: a remote is set but nothing is pushed to it, so sync keeps commits local; "
                        f"run `git -C {root} push -u origin HEAD` once")
    else:
        ahead = git(root, "rev-list", "--count", "@{upstream}..HEAD")
        if ahead and ahead != "0":
            lines.append(f"{ahead} commit(s) not pushed")
    conflicted = hooks().unmerged_paths(root)
    if conflicted:
        problems.append(f"{root}: unresolved conflicts in {', '.join(conflicted)}; resolve them before committing, "
                        f"or sync stays stuck (git -C {root} status)")
    if "autostash" in (git(root, "stash", "list") or ""):
        problems.append(f"{root}: a leftover autostash holds uncommitted changes from an old sync; "
                        f"see `git -C {root} stash list` and apply or drop it")
    for problem in last_run_problems(root):
        if not problem.startswith("not pushing:"):  # the live check below says it, and stays current
            problems.append(f"{root}: the last sync didn't finish: {problem}")
    if hooks().has_upstream(root):
        hits = hooks().outgoing_secret_hits(root)
        if hits:
            problems.append(f"{root}: unpushed commits add what looks like a secret to {', '.join(hits)}, so sync won't "
                            f"push; take it out of those commits (git -C {root} reset --soft @{{upstream}}, remove it, "
                            f"commit again)")
    return lines, problems


def sync_log(root):
    log = hooks().git_path(root, "bindle-sync.log")
    return log.read_text(encoding="utf-8", errors="ignore").splitlines() if log and log.exists() else []


def last_sync(root):
    lines = [l for l in sync_log(root) if not l.startswith(hooks().Log.RUN)]
    return lines[-1] if lines else None


def last_run_problems(root):
    return hooks().last_run_problems(root)


def extra_code(b):
    """What a bindle runs on this machine beyond bindle's own hooks: more hook files, hooks or servers declared
    in plugin.json, MCP/LSP servers, executables. Its skills and rules are instructions, not code, so they're
    not listed, but they're trusted the same way."""
    root, found = b["root"], []
    hooks_dir = root / "hooks"
    if hooks_dir.is_dir():
        found += [f"hooks/{p.relative_to(hooks_dir).as_posix()}" for p in sorted(hooks_dir.rglob("*"))
                  if p.is_file() and "__pycache__" not in p.parts and f"hooks/{p.relative_to(hooks_dir).as_posix()}" not in MANAGED]
    manifest = read_json(root / ".claude-plugin" / "plugin.json")
    found += [f"plugin.json declares {key}" for key in ("hooks", "mcpServers", "lspServers") if key in manifest]
    found += [name for name in (".mcp.json", ".lsp.json") if (root / name).exists()]
    if (root / "bin").is_dir() and any((root / "bin").iterdir()):
        found.append("bin/ (executables)")
    return found


def secret_hits(b):
    """Committable files in what sync commits (memory/, projects/, outbox/) and in notes/ that look like they hold
    a credential. Files git ignores (scratch notes, local query outputs) never leave the machine, so they aren't checked."""
    h = hooks()
    return h.secret_hits(b["root"], h.committable_files(b["root"], *h.SYNCED, "notes"))
