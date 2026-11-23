"""bindle upgrade: bring a bindle's managed files and layout up to this version of bindle."""
import filecmp
import shutil
from pathlib import Path

from .core import (from_newer_bindle, LAYOUT, MANAGED, OBSOLETE, TEMPLATE, VERSION, BindleError, declared_bindles, find_bindle, git, known_bindles, load_bindle,
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
    if args.all:
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
            raise BindleError(f"{b['name']} has layout {layout}, newer than this bindle ({LAYOUT}). git pull bindle first.")
        if from_newer_bindle(b):
            message = (f"{b['name']}'s files are from bindle {b['files_from']}, newer than this copy ({VERSION}); "
                       f"upgrading would put old hooks back. git pull bindle first.")
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
