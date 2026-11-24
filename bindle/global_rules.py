"""bindle global: a bindle's rules.md in every session and subagent, through an import in the user CLAUDE.md.

Hook output reaches only the main session, while the user CLAUDE.md and its @imports reach every session and its
subagents. The block bindle writes there is marked; everything outside it is the person's and kept byte for byte.
"""
import os
import shutil
import tempfile
from pathlib import Path

from .core import BindleError, declared_bindles, find_bindle, hooks, load_bindle, quote, read_json, real, settings_path

HEADER = ("<!-- bindle global: start. Managed by `bindle global <name>` (`--off` removes one); "
          "edits inside this block are overwritten. -->")
# Every session and subagent pays for a global rules.md. Claude Code warns when its memory files together pass
# 40,000 characters; 12,000 leaves room under that for a project CLAUDE.md and a memory index (up to 25 KB).
GLOBAL_RULES_WARN = 12000


def read_claude_md(path):
    """(lines, BOM, codec, line ending, block) for the user CLAUDE.md; a missing file is empty."""
    h = hooks()
    data = path.read_bytes() if path.exists() else b""
    try:
        text, bom, codec = h.decode_text(data)
        lines = text.splitlines(keepends=True)
        block = h.global_block([l.rstrip("\r\n") for l in lines])
    except ValueError as e:
        reason = "it isn't UTF-8 (or UTF-16 with a BOM)" if isinstance(e, UnicodeDecodeError) else e
        raise BindleError(f"{path}: {reason}; bindle won't rewrite it. Fix it by hand first.")
    eol = "\r\n" if "\r\n" in text else "\n" if "\n" in text else os.linesep
    return lines, bom, codec, eol, block


def imports_in(lines, block):
    return hooks().global_imports("".join(lines[block[0]:block[1] + 1])) if block else []


def same_file(a, b):
    return os.path.normcase(str(real(a))) == os.path.normcase(str(real(b)))


def cmd_global(args):
    h = hooks()
    path = h.user_claude_md()
    target = real(path) if path.exists() else path  # write through a link (dotfiles), never replace it
    lines, bom, codec, eol, block = read_claude_md(target)
    imports = imports_in(lines, block)

    if args.off:
        try:
            gone = [real(find_bindle(args.bindle)["root"] / "rules.md")]
        except BindleError:  # moved or deleted: match the path doctor printed
            given = Path(os.path.expanduser(args.bindle))
            gone = [given, given / "rules.md"]
        keep = [p for p in imports if not any(same_file(p, g) for g in gone)]
        if len(keep) == len(imports):
            print(f"{args.bindle} isn't global; {path} is unchanged.")
            return 0
        write_block(target, lines, bom, codec, eol, block, keep)
        print(f"{args.bindle}'s rules.md no longer loads everywhere; where it's attached, its own hook shows it again. "
              f"Takes effect in the next session.")
        return 0

    b = find_bindle(args.bindle)
    rules = b["root"] / "rules.md"
    if not rules.is_file():
        raise BindleError(f"{b['name']} has no rules.md at {rules}; create it first.")
    if any(same_file(p, rules) for p in imports):
        print(f"{b['name']} is already global; {path} is unchanged.")
        return 0
    write_block(target, lines, bom, codec, eol, block, imports + [rules])
    print(f"{b['name']}'s rules.md now loads in every session and subagent, from the next session (Claude Code reads "
          f"{path} at session start). Where {b['name']} is attached, its hook no longer shows it a second time.")
    size = len(rules.read_text(encoding="utf-8", errors="ignore"))
    if size > GLOBAL_RULES_WARN:
        print(f"  warning: its rules.md is {size:,} characters; every session and subagent loads it, so keep it under "
              f"{GLOBAL_RULES_WARN:,}")
    if not b["sync"]:
        print(f"  note: {b['name']} has sync off, so nothing pulls it; the session check says when it's behind its remote")
    return 0


def write_block(path, lines, bom, codec, eol, block, imports):
    """Put the block (or, with no imports, nothing) where it was, or at the end, keeping every other line as is.
    A block bindle appends gets one blank line before it, and removing the block takes that line away again."""
    before, after = (lines[:block[0]], lines[block[1] + 1:]) if block else (list(lines), [])
    if imports:
        new = [HEADER + eol] + [hooks().import_line(p) + eol for p in imports] + [hooks().GLOBAL_END + eol]
        if not block and before:
            if not before[-1].endswith("\n"):
                before[-1] += eol
            before.append(eol)
    else:
        new = []
        if not after and before and not before[-1].strip():
            before = before[:-1]
    text = "".join(before + new + after)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A temporary file and a rename, so a failure halfway never leaves the person's CLAUDE.md cut short.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".CLAUDE.md.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(bom + text.encode(codec))
        if path.exists():
            shutil.copymode(str(path), tmp)
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def global_bindles():
    """(rules.md path, bindle or None) for each import in the user CLAUDE.md's block."""
    out = []
    for p in hooks().user_global_imports():
        try:
            out.append((p, load_bindle(p.parent)))
        except BindleError:
            out.append((p, None))
    return out


def doctor_report():
    """(lines, warnings, problems) about global bindles, for doctor."""
    path = hooks().user_claude_md()
    lines, warnings, problems = [], [], []
    try:
        read_claude_md(real(path) if path.exists() else path)
    except BindleError as e:
        return lines, warnings, [str(e)]
    for rules, b in global_bindles():
        folder = quote(str(rules.parent))
        if b is None or not rules.is_file():
            problems.append(f"{path} imports {rules}, which isn't there (the bindle moved, was renamed or deleted), so "
                            f"those rules load nowhere: bindle global --off {folder}, then `bindle global <name>` "
                            f"where it is now")
            continue
        lines.append(f"  {b['name']}: global, its rules.md loads in every session ({rules})")
        try:
            by_name = find_bindle(b["name"])["root"] == b["root"]
        except BindleError:
            by_name = False
        if not by_name:
            problems.append(f"{b['name']} is global from {b['root']}, but the name {b['name']} doesn't find it there "
                            f"(renamed, or no longer registered): bindle global --off {folder}, then "
                            f"`bindle global <name>` for the bindle you mean")
        size = len(rules.read_text(encoding="utf-8", errors="ignore"))
        if size > GLOBAL_RULES_WARN:
            warnings.append(f"{b['name']}: its global rules.md is {size:,} characters, and every session and subagent "
                            f"loads it; keep it under {GLOBAL_RULES_WARN:,}")
        behind = hooks().git_out(b["root"], "rev-list", "--count", "HEAD..@{upstream}")
        if behind and behind != "0":
            warnings.append(f"{b['name']} is {behind} commit(s) behind its remote (as of its last fetch), so its "
                            f"global rules are out of date: git -C {quote(str(b['root']))} pull --ff-only")
    return lines, warnings, problems


def session_lines(root):
    """What the session check says about global bindles, after pulling each that has sync on (pull only: nothing is
    committed or pushed). A global bindle's own hook runs only where it's attached, so nothing else keeps it current.
    One attached in this session's folder is left to its own hook, which pulls it now too."""
    h, out = hooks(), []
    settings = read_json(settings_path(root))
    enabled = settings.get("enabledPlugins", {})
    attached = {str(b["root"]) for b in declared_bindles(settings) if enabled.get(f"{b['name']}@{b['market']}")}
    for rules, b in global_bindles():
        if b is None or not rules.is_file():
            out.append(f"bindle: global rules from {rules} aren't loading: it isn't there; bindle doctor")
            continue
        if str(b["root"]) in attached:
            continue
        name = f"{b['name']} (global)"
        if not b["sync"]:
            behind = h.git_out(b["root"], "rev-list", "--count", "HEAD..@{upstream}")
            if behind and behind != "0":
                out.append(f"bindle: {name} is {behind} commit(s) behind its remote, so its rules are out of date: "
                           f"git -C {quote(str(b['root']))} pull --ff-only")
            continue
        log = h.Log(b["root"])
        log.path = None  # keep the bindle's sync log for its own hooks' runs, whose problems it reports
        before = h.git_out(b["root"], "rev-parse", "HEAD")
        h.sync_pull(b["root"], log)
        after = h.git_out(b["root"], "rev-parse", "HEAD")
        out += [f"bindle: {name} sync problem: {l[len('problem: '):]}" for l in log.lines if l.startswith("problem: ")]
        if before and after and before != after:
            changed = h.git_out(b["root"], "diff", "--name-only", f"{before}..{after}", "--", *h.CODE_PATHS) or ""
            if changed:
                out.append(f"bindle: {name} pulled changes to code that runs on this machine where it's attached "
                           f"({', '.join(changed.splitlines())}); review them before your next session there: "
                           f"git -C {b['root']} diff {before[:12]}..{after[:12]} -- {' '.join(h.CODE_PATHS)}")
    return out
