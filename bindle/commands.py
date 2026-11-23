"""install, new, attach, detach, sync and doctor."""
import filecmp
import os
import shlex
import shutil
import sys
from pathlib import Path

from .promote import private_terms
from .core import (BASE, WINDOWS, HOOK_OUTPUT_LIMIT, LAYOUT, MANAGED, NAME_RE, RULES_LIMIT, TEMPLATE, BindleError, check_folder,
                   claude, declared_bindles, directory_marketplaces, enclosing_repo_problems,
                   exclude_from_enclosing_repo, bindles_home, extra_code, find_bindle, known_bindles, register, git, git_health, name_problems, hooks, is_writable, last_sync, load_bindle,
                   lock_is_exact, lock_rules, missing_bindles, plugin_id, read_json, real, secret_hits, set_lock,
                   settings_path, write_json, write_text)


INSTALLED_MARK = "Installed by bindle install"


def quote(path):
    """Quote a path for copy-and-paste: POSIX shells on macOS and Linux; PowerShell and cmd on Windows."""
    s = str(path)
    if WINDOWS:
        return f'"{s}"' if any(c in s for c in ' &()[]{}^=;!\'+,`~') else s
    return shlex.quote(s)


def cmd_install(args):
    """Puts the bindle command on PATH and links /bindle and /bindle-promote into ~/.claude. Nothing else:
    bindle never takes over ~/.claude's settings or CLAUDE.md. Where symlinks aren't allowed (Windows without
    developer mode) it copies instead, and on Windows it writes a bindle.cmd launcher."""
    home = Path.home()
    bindir = home / ".local" / "bin"
    items = [(home / ".claude" / "commands" / "bindle.md", BASE / "global" / "commands" / "bindle.md"),
             (home / ".claude" / "skills" / "bindle-promote", BASE / "global" / "skills" / "bindle-promote")]
    launchers = launcher_files(bindir)
    for dest, _ in items + [(p, None) for p in launchers]:
        if dest.exists() and not dest.is_symlink() and not installed_by_bindle(dest):
            raise BindleError(f"{dest} exists and wasn't installed by bindle; move it aside first.")
    for path, content in launchers.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            path.unlink()
        if content is None:
            path.symlink_to(BASE / "bin" / "bindle")
            print(f"Linked {path} -> {BASE / 'bin' / 'bindle'}")
        else:
            write_text(path, content)
            path.chmod(0o755)
            print(f"Wrote {path}")
    for dest, src in items:
        dest.parent.mkdir(parents=True, exist_ok=True)
        remove(dest)
        try:
            dest.symlink_to(src, target_is_directory=src.is_dir())
            print(f"Linked {dest} -> {src}")
        except OSError:
            if src.is_dir():
                shutil.copytree(src, dest)
                write_text(dest / ".bindle-installed", INSTALLED_MARK + "\n")
            else:
                write_text(dest, src.read_text(encoding="utf-8") + f"\n<!-- {INSTALLED_MARK} -->\n")
            print(f"Copied {src} -> {dest} (symlinks aren't available; run bindle install again after updating bindle)")
    if str(bindir) not in os.environ.get("PATH", "").split(os.pathsep):
        if WINDOWS:
            print(f"Add {bindir} to your PATH (System settings > Environment Variables), then open a new terminal.")
        else:
            print(f'Add {bindir} to PATH: export PATH="$HOME/.local/bin:$PATH"')


def launcher_files(bindir):
    """The bindle command on PATH: a symlink on macOS and Linux; on Windows, a .cmd for cmd and PowerShell and a
    shell script for Git Bash, both calling the Python that ran install."""
    if not WINDOWS:
        return {bindir / "bindle": None}
    script = BASE / "bin" / "bindle"
    return {bindir / "bindle.cmd": f'@echo off\r\nrem {INSTALLED_MARK}\r\n"{sys.executable}" "{script}" %*\r\n',
            bindir / "bindle": f'#!/usr/bin/env bash\n# {INSTALLED_MARK}\nexec "{Path(sys.executable).as_posix()}" "{script.as_posix()}" "$@"\n'}


def installed_by_bindle(path):
    try:
        if path.is_dir():
            return (path / ".bindle-installed").exists()
        return INSTALLED_MARK in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy_template(dest, name):
    for src in sorted(TEMPLATE.rglob("*")):
        rel = src.relative_to(TEMPLATE).as_posix()
        out = dest / rel
        if src.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if "__pycache__" in rel:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if rel in MANAGED:
            shutil.copy2(src, out)  # managed files stay byte-identical to the template
        else:
            write_text(out, src.read_text(encoding="utf-8").replace("{{name}}", name))
            shutil.copymode(src, out)


def cmd_new(args):
    name = args.name
    if not NAME_RE.match(name):
        raise BindleError("Name must be lowercase letters, digits and hyphens, e.g. acme or personal.")
    dest = real(args.at) if args.at else Path.cwd() / ".bindle"
    if dest.exists() and any(dest.iterdir()):
        raise BindleError(f"{dest} already exists and isn't empty.")
    copy_template(dest, name)
    meta = read_json(dest / "bindle.json")
    meta.update({"sync": bool(args.sync), "audience": args.audience, "writes": args.writes})
    write_json(dest / "bindle.json", meta)

    excluded = exclude_from_enclosing_repo(dest)
    git(dest, "init", "-q")
    git(dest, "add", "-A")
    committed = git(dest, "commit", "-q", "-m", f"Create the {name} bindle") is not None
    print(f"Created the {name} bindle at {dest}")
    print("  committed" if committed else "  files staged, not committed (no git identity here)")
    print("  no remote set. To add one later: git remote add origin <url> && git push -u origin HEAD")
    if excluded:
        print(f"  inside the repo {excluded[0]}: added {excluded[1]} to its .git/info/exclude (local, never committed)")
    print("  sync: " + ("on (memories pull at session start and push at session end, once a remote is set)"
                        if args.sync else "off (turn on with \"sync\": true in bindle.json)"))
    warning = register(load_bindle(dest))
    if warning:
        print(f"  warning: {warning}")
    print(f"Turn it on for a folder: bindle attach {name if not warning else quote(str(dest))} <folder> [--writable]")


def repos_in(folder):
    """The git repos directly inside a folder (a `.git` folder, or a file for a worktree). Skips bindles, which
    hold their own domain's memory, and folders it can't read."""
    repos = []
    for p in folder.iterdir():
        try:
            if p.is_dir() and not p.is_symlink() and not p.name.startswith(".") and (p / ".git").exists() \
                    and not (p / "bindle.json").exists():
                repos.append(p)
        except OSError:
            pass
    return sorted(repos)


def targets(args):
    """The folder, plus with --repos each repo directly inside it: Claude Code doesn't read a parent folder's
    settings, so a session started in a repo needs its own attach."""
    folder = check_folder(args.folder or Path.cwd())
    if not args.repos:
        return [folder]
    repos = repos_in(folder)
    if not repos:
        print(f"note: no git repos directly inside {folder}")
    return [folder, *repos]


def cmd_attach(args):
    b = find_bindle(args.bindle)
    folders = targets(args)

    if args.writable and b["writes"] == "explicit":
        raise BindleError(
            f"{b['name']} takes explicit writes only (things arrive through `bindle collect`), so it can't be "
            f"a folder's writable bindle. Attach it without --writable.")
    for folder in folders:  # check every folder first, so a refusal changes none of them
        current = read_json(settings_path(folder)).get("autoMemoryDirectory")  # also fails on unreadable settings
        if args.writable and current and real(current) != real(b["memory"]):
            raise BindleError(
                f"{folder} already writes memories to {current}. A folder has one writable bindle: "
                f"detach that one first, or attach {b['name']} without --writable.")

    read_only = [folder for folder in folders if not attach_to(b, folder, args.writable)]
    # Once, not per folder: these depend only on the bindle, and a repeated warning gets skimmed.
    code = extra_code(b) if read_only else []
    if code:
        print(f"  warning: {b['name']} runs code on this machine beyond bindle's own hooks: {', '.join(code)}. "
              f"Attach it only if you trust whoever can push to it.")
    if read_only and not lock_is_exact(b["root"]):
        print(f"  note: {b['root']} contains * ? [ or ], which permission rules read as patterns; the lock may not match exactly")
    warning = register(b)
    if warning:
        print(f"  warning: {warning}")
    print("Takes effect in the next session started from " + ("those folders." if len(folders) > 1 else "that folder."))


def attach_to(b, folder, writable_flag):
    sp = settings_path(folder)
    settings = read_json(sp)
    # Add the marketplace, or add it again if it was declared at another path (the bindle moved after a
    # detach, which keeps the declaration); Claude Code then re-points it.
    declared = dict(directory_marketplaces(settings)).get(b["market"])
    if not declared or real(declared) != b["root"]:
        claude(folder, "plugin", "marketplace", "add", str(b["root"]), "--scope", "local")
    if not read_json(sp).get("enabledPlugins", {}).get(plugin_id(b)):
        claude(folder, "plugin", "install", plugin_id(b), "--scope", "local")

    settings = read_json(sp)  # claude rewrote it
    if writable_flag:
        settings["autoMemoryDirectory"] = str(b["memory"])
        b["memory"].mkdir(exist_ok=True)
    writable = is_writable(settings, b)
    # Read-only bindles are locked; the writable one must stay editable for memory writes.
    set_lock(settings, b["root"], locked=not writable)
    write_json(sp, settings)

    print(f"{b['name']} is on in {folder}" + (", and writable" if writable else ", read-only (locked against Claude's file-editing tools)"))
    return writable


def find_attached(settings, ref):
    """A bindle by name or marketplace among those the folder declares, or by path."""
    for b in declared_bindles(settings):
        if ref in (b["name"], b["market"]):
            return b
    looks_like_path = os.sep in ref or ref.startswith(("~", ".")) or (Path(os.path.expanduser(ref)) / "bindle.json").exists()
    if looks_like_path and Path(os.path.expanduser(ref)).exists():
        return load_bindle(ref)
    return None


def cmd_list(args):
    """The bindles bindle can find: those in bindles_home(), those in its registry, and those attached to a
    folder (a bindle attached before the registry existed is registered the next time it's attached)."""
    folder = real(args.folder or Path.cwd())
    settings = read_json(settings_path(folder))
    attached = {str(b["root"]): b for b in declared_bindles(settings)}
    found, missing = known_bindles()
    home = bindles_home()
    found.update(attached)
    if not found and not missing:
        print(f"No bindles in {home} or attached to {folder}.")
        return 0
    width = max((len(b["name"]) for b in found.values()), default=0)
    for key, b in sorted(found.items(), key=lambda kv: kv[1]["name"]):
        here = ("writable here" if is_writable(settings, b) else "read-only here") if key in attached else "not on here"
        print(f"  {b['name'].ljust(width)}  {b['audience']}, {b['writes']} writes; {here}  {b['root']}")
    for name, path in missing:
        print(f"  {name}: registered at {path}, but nothing is there now (attach it from its new path)")
    print(f"(bindles in {home} and its registry.json, plus those attached to {folder})")
    return 0


def cmd_detach(args):
    folder, *repos = targets(args)
    detached = 0
    for repo in repos:
        settings = read_json(settings_path(repo))
        b = find_attached(settings, args.bindle)
        # A path finds the bindle whether or not this repo has it; act only where it's declared.
        if b is not None and str(b["root"]) in {str(d["root"]) for d in declared_bindles(settings)}:
            detach_from(b, repo)
            detached += 1
        elif b is None:
            try:
                detach_missing(repo, settings, args.bindle)  # it moved or was deleted
                detached += 1
            except BindleError:
                pass  # not attached to this repo
    settings = read_json(settings_path(folder))
    b = find_attached(settings, args.bindle)
    if b is None:
        try:
            return detach_missing(folder, settings, args.bindle)
        except BindleError:
            if not detached:
                raise
            return 0
    detach_from(b, folder)


def detach_from(b, folder):
    sp = settings_path(folder)
    settings = read_json(sp)

    if settings.get("enabledPlugins", {}).get(plugin_id(b)):
        claude(folder, "plugin", "uninstall", plugin_id(b), "--scope", "local")
    # The marketplace declaration stays: removing a marketplace is machine-wide in Claude Code.
    settings = read_json(sp)
    if is_writable(settings, b):
        del settings["autoMemoryDirectory"]
        print(f"{folder} no longer writes memories to {b['name']}; it uses Claude Code's default memory folder.")
    if settings.get("permissions"):
        set_lock(settings, b["root"], locked=False)
    write_json(sp, settings)
    print(f"{b['name']} is off in {folder}.")


def detach_missing(folder, settings, ref):
    """Clean up a bindle whose folder is gone (it moved or was deleted), by name, marketplace or old path."""
    for market, path in directory_marketplaces(settings):
        if Path(path).exists() or ref not in (market, market.removeprefix("bindle-"), path):
            continue
        for pid in [k for k in settings.get("enabledPlugins", {}) if k.endswith(f"@{market}")]:
            try:
                claude(folder, "plugin", "uninstall", pid, "--scope", "local")
            except BindleError:
                pass
        settings = read_json(settings_path(folder))
        settings.get("extraKnownMarketplaces", {}).pop(market, None)
        for pid in [k for k in settings.get("enabledPlugins", {}) if k.endswith(f"@{market}")]:
            settings["enabledPlugins"].pop(pid)
        memory_dir = settings.get("autoMemoryDirectory")
        if memory_dir and Path(memory_dir) == Path(path) / "memory":
            del settings["autoMemoryDirectory"]
        if settings.get("permissions"):
            set_lock(settings, path, locked=False)
        write_json(settings_path(folder), settings)
        print(f"Removed {market} (nothing was left at {path}) from {folder}.")
        return 0
    raise BindleError(f"No bindle named {ref} is attached to {folder}.")


def cmd_sync(args):
    if args.all:
        if args.folder:
            raise BindleError("Pass a folder or --all, not both.")
        return sync_all()
    folder = real(args.folder or Path.cwd())
    settings = read_json(settings_path(folder))
    enabled = settings.get("enabledPlugins", {})
    bindles = [b for b in declared_bindles(settings) if enabled.get(plugin_id(b))]
    if not bindles:
        print(f"No bindles are on in {folder}.")
        return 0
    h = hooks()
    for b in bindles:
        # The same steps as the hooks, by hand and whether or not sync is on: pull every bindle that's on;
        # commit and push the writable one.
        print(f"{b['name']}:")
        log = h.Log(b["root"], echo=False)
        h.sync_pull(b["root"], log)
        if is_writable(settings, b):
            h.sync_push(b["root"], log)
        for line in log.lines:
            print(f"  {line}")
    return 0


def sync_all():
    """Every bindle bindle can find: pull each; commit and push memory/ and outbox/ in those that can be a
    folder's writable bindle. Explicit-writes bindles get no session writes (collect commits for them)."""
    found, missing = known_bindles()
    for name, path in missing:
        print(f"{name}: skipped, registered at {path} but nothing is there now")
    if not found:
        raise BindleError("No bindles found in ~/bindles or its registry.")
    h = hooks()
    for b in sorted(found.values(), key=lambda b: b["name"]):
        print(f"{b['name']}:")
        log = h.Log(b["root"], echo=False)
        h.sync_pull(b["root"], log)
        if b["writes"] == "implicit":
            h.sync_push(b["root"], log)
        for line in log.lines or ["up to date"]:
            print(f"  {line}")
    return 0


def unattached_repos(folder, b):
    """Repos inside a domain folder whose sessions would save memories to Claude Code's default folder,
    since a session started in a repo reads only that repo's settings."""
    memory = {r: read_json(settings_path(r)).get("autoMemoryDirectory") for r in repos_in(folder)}
    repos = [r for r, m in memory.items() if not m]
    if not repos:
        return []
    others = [r for r, m in memory.items() if m and real(m) != real(b["memory"])]
    # --repos refuses when any repo writes to another bindle, so name each repo instead.
    fixes = ([f"bindle attach {quote(str(b['root']))} {quote(str(r))} --writable" for r in repos] if others
             else [f"bindle attach {quote(str(b['root']))} {quote(str(folder))} --writable --repos"])
    return [f"sessions started in {', '.join(r.name for r in repos)} won't load {b['name']} or save memories to it "
            f"(a repo reads only its own settings). If you start Claude there, run:\n      " + "\n      ".join(fixes)]


def cmd_doctor(args):
    folder = real(args.folder or Path.cwd())
    problems, warnings, needs_upgrade = [], [], []
    print(f"Folder: {folder}")

    top = None if WINDOWS else git(folder, "rev-parse", "--show-toplevel")
    if top and real(top) != folder:
        problems.append(f"inside the git repo {top}: Claude Code reads settings from there, not here")

    settings = read_json(settings_path(folder))
    enabled = settings.get("enabledPlugins", {})
    memory_dir = settings.get("autoMemoryDirectory")
    bindles = declared_bindles(settings)
    missing = missing_bindles(settings)
    writable = None

    if not bindles and not missing:
        print("  No bindles attached.")
    for market, path in missing:
        state = "was on" if any(k.endswith(f"@{market}") and v for k, v in enabled.items()) else "declared"
        print(f"  {market}: {state}, but nothing is at {path}")
        problems.append(f"{market}: no bindle at {path}. If it moved, attach it from its new path; "
                        f"to remove it, run `bindle detach {quote(market)} {quote(str(folder))}`.")
    if memory_dir and not real(memory_dir).is_dir():
        problems.append(f"memories are set to go to {memory_dir}, which doesn't exist")
    deny = settings.get("permissions", {}).get("deny", [])

    for b in bindles:
        on = bool(enabled.get(plugin_id(b)))
        writable_here = is_writable(settings, b)
        writable = b if writable_here else writable
        state = ("on, writable" if writable_here else "on, read-only") if on else "off (declared, not enabled)"
        if b["audience"] != "private" or b["writes"] != "implicit":
            state += f", {b['audience']}, {b['writes']} writes"
        if writable_here and not on:
            problems.append(f"{b['name']} is writable but its plugin isn't enabled")
        memories = len([p for p in b["memory"].glob("*.md") if p.name != "MEMORY.md"]) if b["memory"].is_dir() else 0
        print(f"  {b['name']}: {state}, sync {'on' if b['sync'] else 'off'}")
        print(f"    {b['root']}  ({memories} memories)")
        last = last_sync(b["root"])
        if last:
            print(f"    last sync: {last}")
        lines, git_problems = git_health(b["root"])
        for line in lines:
            print(f"    {line}")
        problems += git_problems
        for hit in secret_hits(b):
            if hit.startswith("notes/"):
                problems.append(f"{b['name']}: {hit} may hold a secret; move it to secure storage (e.g. a password manager) and leave a pointer in the note")
            else:
                problems.append(f"{b['name']}: {hit} may hold a secret; sync won't commit it until it's removed")
        for rel in MANAGED:
            copy = b["root"] / rel
            if not copy.exists():
                problems.append(f"{b['name']}: {rel} is missing")
                needs_upgrade.append(b)
            elif not filecmp.cmp(copy, TEMPLATE / rel, shallow=False):
                problems.append(f"{b['name']}: {rel} differs from bindle's template")
                needs_upgrade.append(b)
        problems += enclosing_repo_problems(b)
        problems += name_problems(b)
        if writable_here and not private_terms(b):
            warnings.append(f"{b['name']}: private-terms.txt lists no terms, so promotion can't check drafts for names "
                            f"that identify this domain; `bindle terms {quote(str(b['root']))}` suggests some")
        code = extra_code(b) if on and not writable_here else []
        if code:
            warnings.append(f"{b['name']} (read-only here) runs code on this machine beyond bindle's own hooks: "
                            f"{', '.join(code)}. Fine if it's yours; otherwise trust whoever can push to it.")
        locked = all(r in deny for r in lock_rules(b["root"]))
        if on and not writable_here and not locked:
            problems.append(f"{b['name']} is read-only here but not locked against edits; "
                            f"run `bindle attach {quote(str(b['root']))} {quote(str(folder))}` again")
        if writable_here and any(r in deny for r in lock_rules(b["root"])):
            problems.append(f"{b['name']} is writable but locked, so memories can't be saved; "
                            f"run `bindle attach {quote(str(b['root']))} {quote(str(folder))} --writable` again")
        rules = b["root"] / "rules.md"
        if rules.exists() and len(rules.read_text(encoding="utf-8", errors="ignore")) > RULES_LIMIT:
            problems.append(f"{b['name']}: rules.md is over {RULES_LIMIT} characters; the session-start hook can show only {HOOK_OUTPUT_LIMIT:,}")
        index = b["memory"] / "MEMORY.md"
        if on and not writable_here and index.exists() and len(index.read_text(encoding="utf-8", errors="ignore")) > HOOK_OUTPUT_LIMIT - 500:
            problems.append(f"{b['name']}: its MEMORY.md is too long to show in full where it's read-only (the hook shows "
                            f"up to {HOOK_OUTPUT_LIMIT:,} characters); move project memories into projects/")
        layout = b["layout"] or 1
        if layout > LAYOUT:
            problems.append(f"{b['name']}: layout {layout} is newer than this bindle ({LAYOUT}); git pull bindle")
        elif b["layout"] != LAYOUT:
            problems.append(f"{b['name']}: bindle.json has no current layout number")
            needs_upgrade.append(b)

    if writable:
        warnings += unattached_repos(folder, writable)

    if memory_dir and not writable:
        print(f"  Memory: {memory_dir} (not a bindle attached here)")
    elif not memory_dir:
        print("  Memory: Claude Code's default folder (no writable bindle)")

    fixes = []
    for b in {str(b["root"]): b for b in needs_upgrade}.values():
        root = quote(str(b["root"]))
        # Push too when the bindle has an upstream, so other machines get the upgrade with their next pull.
        push = f" && git -C {root} push" if hooks().has_upstream(b["root"]) else ""
        fixes.append(f"bindle upgrade {root}{push}")
    if fixes:
        problems.append("to fix, run (in Claude Code, prefix it with ! so it runs as you; a read-only bindle is locked to Claude):\n      "
                        + "\n      ".join(fixes))
    if warnings:
        print("Warnings (worth a look; nothing is broken):")
        for w in warnings:
            print(f"  - {w}")
    if problems:
        print("Problems:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("No problems found.")
    return 0
