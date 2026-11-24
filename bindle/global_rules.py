"""bindle global: a bindle's rules.md and memory index in every session and subagent, through imports in the user
CLAUDE.md.

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
# Every session and subagent pays for a global bindle's rules.md and memory index. Claude Code warns when its
# memory files together pass 40,000 characters; 12,000 leaves room under that for a project CLAUDE.md and the
# writable bindle's index (up to 25 KB).
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


def block_text(lines, block):
    return "".join(lines[block[0]:block[1] + 1]) if block else ""


def render(roots, eol):
    """The block for these bindle folders: each one's rules.md and memory index, so links in the index resolve."""
    h = hooks()
    imports = [h.import_line(Path(root) / rel) for root in roots for rel in h.GLOBAL_FILES]
    return [HEADER + eol] + [line + eol for line in imports] + [h.GLOBAL_END + eol]


def same_file(a, b):
    return os.path.normcase(str(real(a))) == os.path.normcase(str(real(b)))


def cmd_global(args):
    h = hooks()
    path = h.user_claude_md()
    target = real(path) if path.exists() else path  # write through a link (dotfiles), never replace it
    lines, bom, codec, eol, block = read_claude_md(target)
    roots = h.global_roots(block_text(lines, block))

    if args.off:
        try:
            gone = real(find_bindle(args.bindle)["root"])
        except BindleError:  # moved or deleted: match the path doctor printed
            given = Path(os.path.expanduser(args.bindle))
            gone = h.import_root(given) or given
        keep = [r for r in roots if not same_file(r, gone)]
        if len(keep) == len(roots):
            print(f"{args.bindle} isn't global; {path} is unchanged.")
            return 0
        write_block(target, lines, bom, codec, eol, block, keep)
        print(f"{args.bindle}'s rules and memory index no longer load everywhere; where it's attached, its own hook "
              f"shows them again. Takes effect in the next session.")
        return 0

    b = find_bindle(args.bindle)
    rules = b["root"] / "rules.md"
    if not rules.is_file():
        raise BindleError(f"{b['name']} has no rules.md at {rules}; create it first.")
    new_roots = roots if any(same_file(r, b["root"]) for r in roots) else roots + [b["root"]]
    if block and block_text(lines, block) == "".join(render(new_roots, eol)):
        print(f"{b['name']} is already global; {path} is unchanged.")
        return 0
    write_block(target, lines, bom, codec, eol, block, new_roots)
    print(f"{b['name']}'s rules.md and memory index now load in every session and subagent, from the next session "
          f"(Claude Code reads {path} at session start). Where {b['name']} is attached, its hook no longer shows them "
          f"a second time.")
    size = global_size(b["root"])
    if size > GLOBAL_RULES_WARN:
        print(f"  warning: its rules.md and memory index are {size:,} characters; every session and subagent loads "
              f"them, so keep them under {GLOBAL_RULES_WARN:,}")
    if not b["sync"]:
        print(f"  note: {b['name']} has sync off, so nothing pulls it; the session check says when it's behind its remote")
    return 0


def global_size(root):
    files = [Path(root) / rel for rel in hooks().GLOBAL_FILES]
    return sum(len(f.read_text(encoding="utf-8", errors="ignore")) for f in files if f.is_file())


def write_block(path, lines, bom, codec, eol, block, roots):
    """Put the block (or, with no bindles, nothing) where it was, or at the end, keeping every other line as is.
    A block bindle appends gets one blank line before it, and removing the block takes that line away again."""
    before, after = (lines[:block[0]], lines[block[1] + 1:]) if block else (list(lines), [])
    if roots:
        new = render(roots, eol)
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
    """(folder, bindle or None) for each global bindle the user CLAUDE.md's block names."""
    h, out = hooks(), []
    try:
        text = h.decode_text(h.user_claude_md().read_bytes())[0]
        roots = h.global_roots(text)
    except (OSError, ValueError):
        return []
    for root in roots:
        try:
            out.append((root, load_bindle(root)))
        except BindleError:
            out.append((root, None))
    return out


def doctor_report():
    """(lines, warnings, problems) about global bindles, for doctor."""
    path = hooks().user_claude_md()
    lines, warnings, problems = [], [], []
    try:
        text_lines, _, _, eol, block = read_claude_md(real(path) if path.exists() else path)
    except BindleError as e:
        return lines, warnings, [str(e)]
    found = global_bindles()
    for root, b in found:
        folder = quote(str(root))
        if b is None or not (root / "rules.md").is_file():
            problems.append(f"{path} imports from {root}, which isn't a bindle with a rules.md any more (it moved, was "
                            f"renamed or deleted), so its rules load nowhere: bindle global --off {folder}, then "
                            f"`bindle global <name>` where it is now")
            continue
        lines.append(f"  {b['name']}: global, its rules.md and memory index load in every session ({root})")
        try:
            by_name = find_bindle(b["name"])["root"] == b["root"]
        except BindleError:
            by_name = False
        if not by_name:
            problems.append(f"{b['name']} is global from {b['root']}, but the name {b['name']} doesn't find it there "
                            f"(renamed, or no longer registered): bindle global --off {folder}, then "
                            f"`bindle global <name>` for the bindle you mean")
        size = global_size(root)
        if size > GLOBAL_RULES_WARN:
            warnings.append(f"{b['name']}: its global rules.md and memory index are {size:,} characters, and every "
                            f"session and subagent loads them; keep them under {GLOBAL_RULES_WARN:,}")
        behind = hooks().git_out(b["root"], "rev-list", "--count", "HEAD..@{upstream}")
        if behind and behind != "0":
            warnings.append(f"{b['name']} is {behind} commit(s) behind its remote (as of its last fetch), so its "
                            f"global rules are out of date: git -C {quote(str(b['root']))} pull --ff-only")
    current = [b for _, b in found if b is not None]
    if current and block_text(text_lines, block) != "".join(render([r for r, _ in found], eol)):
        # Written by an older bindle (0.29 imported rules.md only), or edited by hand.
        problems.append(f"the bindle global block in {path} isn't what this bindle writes (an older version, or "
                        f"edited by hand), so some global files may not load: "
                        + " && ".join(f"bindle global {b['name']}" for b in current))
    return lines, warnings, problems


def session_lines(root):
    """What the session check says about global bindles, after pulling each that has sync on (pull only: nothing is
    committed or pushed). A global bindle's own hook runs only where it's attached, so nothing else keeps it current.
    One attached in this session's folder is left to its own hook, which pulls it now too."""
    h, out = hooks(), []
    settings = read_json(settings_path(root))
    enabled = settings.get("enabledPlugins", {})
    attached = {str(b["root"]) for b in declared_bindles(settings) if enabled.get(f"{b['name']}@{b['market']}")}
    for folder, b in global_bindles():
        if b is None or not (folder / "rules.md").is_file():
            out.append(f"bindle: global rules from {folder} aren't loading: no bindle with a rules.md is there; bindle doctor")
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
