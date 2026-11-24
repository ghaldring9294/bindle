"""bindle upgrade: bring a bindle's managed files and layout up to this version of bindle."""
import argparse
import filecmp
import shutil
import subprocess
import sys
from pathlib import Path

from .core import (BASE, from_newer_bindle, hooks, LAYOUT, MANAGED, OBSOLETE, TEMPLATE, VERSION, BindleError, declared_bindles, find_bindle, git, known_bindles, load_bindle,
                   read_json, real, settings_path, write_json, write_text)

# A bindle's .gitignore and .gitattributes are its own, so upgrade only appends template lines they lack.
LINE_MERGED = [".gitignore", ".gitattributes"]

# Layout migrations: {from_layout: function(bindle_root)}, each moving a bindle up one layout.
# A bindle.json without a layout predates layout numbers; it needs only the number stamped in.
MIGRATIONS = {0: lambda root: None}


def missing_lines(root, name):
    own = (root / name).read_text(encoding="utf-8").splitlines() if (root / name).exists() else []
    return [l for l in (TEMPLATE / name).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#") and l not in own]


def upgrade_plan(b):
    """What upgrade would change: managed files that differ or are missing, obsolete managed files to remove,
    template files the bindle has never had (never overwriting its own), and template lines to append."""
    root, plan = b["root"], []
    # Whether a missing template file was deleted on purpose is read from history; without full history, assume so.
    full_history = git(root, "rev-parse", "--is-shallow-repository") == "false"
    for rel in MANAGED:
        copy = root / rel
        if not copy.exists():
            plan.append(("add", rel))
        elif not filecmp.cmp(copy, TEMPLATE / rel, shallow=False):
            plan.append(("update", rel))
    for rel in OBSOLETE:
        if (root / rel).exists():
            plan.append(("remove", rel))
    for src in sorted(TEMPLATE.rglob("*")):
        rel = src.relative_to(TEMPLATE).as_posix()
        # A file the bindle's history already had was deleted on purpose; don't bring it back.
        if (src.is_file() and "__pycache__" not in rel and rel not in MANAGED and not (root / rel).exists()
                and full_history and not git(root, "log", "-1", "--format=%H", "--", rel)):
            plan.append(("add", rel))
    for name in LINE_MERGED:
        if (root / name).exists() and missing_lines(root, name):
            plan.append(("lines", name))
    return plan


def describe(b, action, rel):
    if action == "lines":
        return f"add lines to {rel}: {', '.join(missing_lines(b['root'], rel))}"
    return f"{action} {rel}"


def cmd_upgrade(args):
    if args.all and args.bindle:
        raise BindleError("Pass a bindle or --all, not both.")
    if getattr(args, "bindles", None) is not None:  # update passes the ones it could bring up to date first
        bindles = args.bindles
    elif args.all:
        found, missing = known_bindles()
        for name, path in missing:
            print(f"{name}: skipped, registered at {path} but nothing is there now")
        bindles = sorted(found.values(), key=lambda b: b["name"])
        if not bindles:
            raise BindleError("No bindles found in ~/bindles or its registry.")
    elif args.bindle:
        bindles = [find_bindle(args.bindle)]
    else:
        folder = real(Path.cwd())
        bindles = declared_bindles(read_json(settings_path(folder)))
        if not bindles:
            raise BindleError(f"No bindles are attached to {folder}; pass a bindle's path.")
    skipped = []
    for b in bindles:
        layout = b["layout"] if isinstance(b["layout"], int) else 0
        if layout > LAYOUT:
            raise BindleError(f"{b['name']} has layout {layout}, newer than this bindle ({LAYOUT}). Run bindle update.")
        if from_newer_bindle(b):
            message = (f"{b['name']}'s files are from bindle {b['files_from']}, newer than this copy ({VERSION}); "
                       f"upgrading would put old hooks back. Run bindle update.")
            if not args.all:
                raise BindleError(message)
            print(f"{b['name']}: skipped; {message}")
            skipped.append(b["name"])
            continue
        plan = upgrade_plan(b)
        steps = list(range(layout, LAYOUT))
        if not plan and not steps:
            print(f"{b['name']}: up to date (bindle {VERSION})")
            continue
        print(f"{b['name']}: {'would change' if args.dry_run else 'upgrading'} ({b['root']})")
        for n in steps:
            print(f"  set layout {n + 1}" if n == 0 else f"  migrate layout {n} -> {n + 1}")
        for action, rel in plan:
            print(f"  {describe(b, action, rel)}")
        if args.dry_run:
            continue

        touched = []
        for n in steps:
            MIGRATIONS[n](b["root"])
        for action, rel in plan:
            out = b["root"] / rel
            if action == "lines":
                write_text(out, "\n# Added by bindle upgrade\n" + "\n".join(missing_lines(b["root"], rel)) + "\n", mode="a")
            elif action == "remove":
                out.unlink()
            elif rel in MANAGED:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(TEMPLATE / rel, out)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                write_text(out, (TEMPLATE / rel).read_text(encoding="utf-8").replace("{{name}}", b["name"]))
                shutil.copymode(TEMPLATE / rel, out)
            touched.append(rel)
        meta = read_json(b["root"] / "bindle.json")
        meta["bindle_version"] = VERSION  # so an older copy of bindle elsewhere won't undo this upgrade
        if steps:
            meta["layout"] = LAYOUT
        write_json(b["root"] / "bindle.json", meta)
        touched.append("bindle.json")
        # Commit only what upgrade touched, so a person's own uncommitted work stays theirs.
        git(b["root"], "add", "-A", "--", *touched)
        if git(b["root"], "commit", "-q", "-m", f"Upgrade bindle files to bindle {VERSION}", "--", *touched) is not None:
            print(f"  committed; push it so other machines get it: git -C {b['root']} push (sync pushes it from the "
                  f"next session where this bindle is writable)")
        else:
            print("  changed, not committed (no git identity here?)")
    return 1 if skipped else 0


def pull_bindle(repo):
    """Fast-forward bindle's own clone. Refuses rather than merge: a clone with local changes is someone's work."""
    if git(repo, "rev-parse", "--git-dir") is None:
        raise BindleError(f"{repo} isn't a git clone; update bindle the way you installed it.")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise BindleError(f"{repo} has uncommitted changes; commit or discard them, then run bindle update again.")
    before = git(repo, "rev-parse", "HEAD")
    if subprocess.run(["git", "-C", str(repo), "pull", "-q", "--ff-only"]).returncode != 0:
        raise BindleError(f"Couldn't fast-forward {repo} (see above); nothing was changed.")
    return before != git(repo, "rev-parse", "HEAD")


def pull_bindles(found):
    """Pull each bindle (fast-forward only) before upgrading it, and return the ones that are current. Upgrading a
    copy that's behind makes a commit that competes with the same upgrade pushed from another machine, and then
    neither pulls cleanly. So a bindle whose pull didn't succeed (offline, diverged, a conflict) isn't upgraded."""
    h, ready = hooks(), []
    for b in sorted(found.values(), key=lambda b: b["name"]):
        if not h.has_upstream(b["root"]):
            ready.append(b)  # local only: nothing to compete with
            continue
        log = h.Log(b["root"])
        log.path = None  # the sync log reports the bindle's own hook runs
        h.sync_pull(b["root"], log)
        if "pulled" in log.lines:
            ready.append(b)
            continue
        why = (log.lines or ["not pulled"])[-1]
        why = why[len("problem: "):] if why.startswith("problem: ") else why
        print(f"{b['name']}: not upgraded, since it couldn't be brought up to date first ({why}); "
              f"pull it, then run bindle update again")
    return ready


def cmd_update(args):
    """Update bindle and every bindle. When running from a git clone, it pulls bindle's own repo, then hands over
    to the pulled copy so upgrading each bindle runs the new code and templates. When running from a plugin cache
    (no .git), it skips the pull and tells the user to update the plugin through Claude Code."""
    is_git_clone = (BASE / ".git").exists()
    if not args.after_pull:
        if is_git_clone:
            changed = pull_bindle(BASE)
            print(f"bindle: {'updated' if changed else 'already up to date'} ({BASE})", flush=True)
            return subprocess.call([sys.executable, str(BASE / "bin" / "bindle"), "update", "--after-pull"]
                                   + (["--push"] if args.push else []))
        else:
            print(f"bindle {VERSION} (installed as a plugin). To update bindle itself, use Claude Code: "
                  "/plugin → Installed → bindle → Update, or: claude plugin update bindle@bindle")
            args.after_pull = True
    if is_git_clone:
        from .commands import cmd_install  # commands imports this module
        print(f"bindle {VERSION}: refreshing the install")
        cmd_install(argparse.Namespace(session_check=None, cleanup=False))
    found, missing = known_bindles()
    for name, path in missing:
        print(f"{name}: skipped, registered at {path} but nothing is there now")
    if not found:
        raise BindleError("No bindles found in ~/bindles or its registry.")
    ready = pull_bindles(found)
    heads = {root: git(b["root"], "rev-parse", "HEAD") for root, b in found.items()}
    code = cmd_upgrade(argparse.Namespace(all=True, bindle=None, dry_run=False, bindles=ready)) if ready else 0
    if len(ready) < len(found):
        code = 1
    h = hooks()
    for root, b in sorted(found.items(), key=lambda kv: kv[1]["name"]):
        if git(b["root"], "rev-parse", "HEAD") == heads[root] or not h.has_upstream(b["root"]):
            continue
        if not args.push:
            print(f"Push {b['name']} so other machines get the upgrade: git -C {b['root']} push")
        elif subprocess.run(["git", "-C", str(b["root"]), "push", "-q"]).returncode == 0:
            print(f"{b['name']}: pushed")
        else:
            print(f"{b['name']}: push failed (see above); push it by hand: git -C {b['root']} push")
            code = 1
    return code
