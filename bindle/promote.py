"""Promotion: material leaves a bindle only as text the person approved as general.

`outbox add` checks a draft against the source bindle's private terms and for credentials, stores it in the
source's outbox and records a hash of the approved content. `collect` validates each item (approved, hash
unchanged, no paths outside its folder, no symlinks), checks again, and copies it into the target only once
every destination is known to be free.
"""
import datetime
import difflib
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

from .core import BindleError, find_bindle, quote, ref, git, hooks, known_bindles, load_bindle, read_json, real, write_json, write_text

KINDS = {"memory": "memory", "skill": "skills", "command": "commands", "note": "notes"}
INBOX_HEADER = "# Inbox\n\nNotes sent from other domains, oldest first. Remove each one once it's handled.\n"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
COLLECTABLE = ("approved",)  # items collected before 0.14 kept status "collected"; outbox clean removes them


def private_terms(b):
    """Words that identify the bindle's domain; anything leaving the bindle is checked against them."""
    f = b["root"] / "private-terms.txt"
    if not f.exists():
        return []
    return [t.strip() for t in f.read_text(encoding="utf-8").splitlines() if t.strip() and not t.strip().startswith("#")]


def terms_in(text, terms):
    found = []
    for t in terms:
        # Whole words, except a term ending in punctuation (a ticket prefix like "ACME-") matches what follows it.
        start = r"(?<![A-Za-z0-9])" if t[0].isalnum() else ""
        end = r"(?![A-Za-z0-9])" if t[-1].isalnum() else ""
        if re.search(start + re.escape(t) + end, text, re.I):
            found.append(t)
    return found


TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b")
REMOTE_RE = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")


def domain_folder(b, folder):
    """The folder a bindle serves: given, or the folder a `.bindle` sits in, or here."""
    if folder:
        return real(folder)
    return b["root"].parent if b["root"].name == ".bindle" else real(Path.cwd())


def suggest_terms(b, folder):
    """Candidate private terms, each with where it was found: the domain folder's name, and for the git repos
    in it (the folder and its immediate subfolders) their names, their remotes' owners and repo names, and
    ticket prefixes seen at least twice in recent commit subjects. The person decides which are private."""
    found = {}

    def add(term, source):
        if term and term.lower() not in (t.lower() for t in found):
            found[term] = source

    if folder != real(Path.home()):
        add(folder.name, "the domain folder's name")
    repos = [d for d in [folder, *sorted(p for p in folder.iterdir() if p.is_dir())]
             if (d / ".git").exists() and d != b["root"]]
    for repo in repos:
        if repo != folder:
            add(repo.name, f"a repo in {folder}")
        for url in (git(repo, "remote", "-v") or "").split():
            m = REMOTE_RE.search(url)
            if m and ("@" in url or "://" in url):
                add(m.group(1), f"the owner of {repo.name}'s remote")
                add(m.group(2), f"{repo.name}'s remote")
        counts = {}
        for prefix in TICKET_RE.findall(git(repo, "log", "-200", "--format=%s") or ""):
            counts[prefix] = counts.get(prefix, 0) + 1
        for prefix, n in counts.items():
            if n >= 2:
                add(prefix + "-", f"ticket prefix in {repo.name}'s commits")
    have = {t.lower() for t in private_terms(b)}
    return {t: src for t, src in found.items() if t.lower() not in have}


def cmd_terms(args):
    b = find_bindle(args.bindle)
    folder = domain_folder(b, args.folder)
    suggestions = suggest_terms(b, folder)
    if not suggestions:
        print(f"No new terms found in {folder}. Add any by hand to {b['root'] / 'private-terms.txt'}.")
        return 0
    print(f"Possible private terms for {b['name']}, from {folder} (not yet in private-terms.txt).")
    print("Keep the ones that identify the domain; add people, products and internal systems this can't see.")
    width = max(len(t) for t in suggestions)
    for t, src in suggestions.items():
        print(f"  {t.ljust(width)}  {src}")
    return 0


def draft_files(src):
    """Every file in a draft (a file, or a folder walked without following links). Refuses symlinks: a link
    could carry content from anywhere into the target without being checked."""
    src = Path(src)
    if src.is_symlink():
        raise BindleError(f"{src} is a symlink; promote the real file or folder.")
    if src.is_file():
        return [src]
    files = []
    for dirpath, dirnames, filenames in os.walk(src):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if p.is_symlink():
                raise BindleError(f"{p} is a symlink; drafts can't contain links.")
            if p.is_file():
                files.append(p)
    return sorted(files)


def content_hash(src):
    """A hash of a draft's relative paths and contents, so collect can tell it's what the person approved."""
    src = Path(src)
    h = hashlib.sha256()
    for f in draft_files(src):
        rel = f.name if src.is_file() else f.relative_to(src).as_posix()
        h.update(rel.encode("utf-8") + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def leak_hits(b, slug, description, src, allowed=()):
    """Reasons a draft can't leave the bindle: a private term in its name, description, file names or contents,
    or content that looks like a credential. Terms the person allowed for this promotion are skipped; a possible
    secret never is, since git history can't un-leak it."""
    ok = {a.lower() for a in allowed}
    terms, hits = [t for t in private_terms(b) if t.lower() not in ok], []
    src = Path(src)
    for label, text in (("name", slug), ("description", description or "")):
        hits += [(label, t) for t in terms_in(text, terms)]
    for f in draft_files(src):
        rel = src.name if src.is_file() else f"{src.name}/{f.relative_to(src).as_posix()}"
        hits += [(f"file name {rel}", t) for t in terms_in(rel, terms)]
        text = f.read_bytes().decode("utf-8", errors="ignore")
        hits += [(rel, t) for t in terms_in(text, terms)]
        if hooks().looks_secret(text):
            hits.append((rel, "possible secret"))
    return hits


def describe_hits(hits):
    lines = [f"  {where}: {what}" for where, what in hits]
    if any(what != "possible secret" for _, what in hits):
        lines.append("A private term is a prompt to check, not a wall: if it's fine here (a public name, or a target "
                     "that's yours alone), run the same command with --allow <term> for each one.")
    if any(what == "possible secret" for _, what in hits):
        lines.append("A possible secret can't be promoted: take it out, and keep it in a password manager or vault.")
    return "\n".join(lines)


def commit(root, message, *paths):
    git(root, "add", "-A", "--", *paths)
    return git(root, "commit", "-q", "-m", message, "--", *paths) is not None


def check_draft(b, slug, kind, src, description, verb, allowed=()):
    """A draft is fit to leave bindle b: a valid name, the right shape for its kind, and nothing that names
    b's domain or looks like a secret."""
    if not SLUG_RE.match(slug):
        raise BindleError("Name must be lowercase letters, digits, hyphens or underscores.")
    if not src.exists():
        raise BindleError(f"{src} doesn't exist.")
    if kind in ("memory", "command", "note") and not (src.is_file() and src.suffix == ".md"):
        raise BindleError(f"A {kind} is a single .md file.")
    if kind == "skill" and not (src.is_dir() and (src / "SKILL.md").is_file()):
        raise BindleError("A skill is a folder with a SKILL.md.")
    hits = leak_hits(b, slug, description, src, allowed)
    if hits:
        raise BindleError(f"Not {verb}; the draft still names this domain or looks like it holds a secret:\n" + describe_hits(hits))


def destination(target, slug, kind, src):
    out = target["root"] / "skills" / src.name if kind == "skill" else target["root"] / KINDS[kind] / f"{slug}.md"
    if out.resolve().parent != (target["root"] / KINDS[kind]).resolve():
        raise BindleError(f"{slug}: its destination {out} is outside {target['name']}.")
    return out


def place(source, target, items, replace=False):
    """Copy items [(slug, kind, src, description)] into target, add memory index lines and commit there.
    Every destination is checked before anything is written, so a failure leaves the target as it was.
    Something already in the target is replaced only when asked; git history keeps the old version.
    Returns (paths written, committed)."""
    dests, inbox = {}, target["root"] / "notes" / "inbox.md"
    for slug, kind, src, _ in items:
        if kind == "note":
            continue  # notes are appended to the inbox, never placed as files
        out = destination(target, slug, kind, src)
        if out in dests.values() or (out.exists() and not replace):
            raise BindleError(f"{out} already exists in {target['name']} (or two items want it); nothing written. "
                              f"To update it, promote with --replace.")
        dests[slug] = out
    index = target["root"] / "memory" / "MEMORY.md"
    indexed = index.read_text(encoding="utf-8") if index.exists() else ""
    moved, index_lines, notes = [], [], []
    for slug, kind, src, description in items:
        if kind == "note":
            body = src.read_text(encoding="utf-8").strip()
            notes.append(f"\n## {datetime.date.today().isoformat()} · from {source['name']} · {slug}\n\n{body}\n")
            continue
        out = dests[slug]
        out.parent.mkdir(parents=True, exist_ok=True)
        if kind == "skill":
            if out.exists():
                shutil.rmtree(out)  # replacing: files the new version dropped must go too
            shutil.copytree(src, out)
        else:
            shutil.copy2(src, out)
        if kind == "memory" and f"({slug}.md)" not in indexed:
            index_lines.append(f"- [{slug}]({slug}.md) — {description or 'promoted from ' + source['name']}\n")
        moved.append(out.relative_to(target["root"]).as_posix())
    if index_lines:
        write_text(target["root"] / "memory" / "MEMORY.md", "".join(index_lines), mode="a")
    if notes:
        inbox.parent.mkdir(parents=True, exist_ok=True)
        write_text(inbox, ("" if inbox.exists() else INBOX_HEADER) + "".join(notes), mode="a")
        moved.append("notes/inbox.md")
    names = ", ".join(i[0] for i in items)
    committed = commit(target["root"], f"Promote from {source['name']}: {names}", *moved, *(["memory/MEMORY.md"] if index_lines else []))
    return moved, committed


def cmd_promote(args):
    """One step: check the approved draft and place it in the target, which must be on this machine. When it
    isn't, the draft waits in the source's outbox instead (`bindle outbox add`)."""
    source, target = find_bindle(args.source), find_bindle(args.into)
    if source["root"] == target["root"]:
        raise BindleError("Source and target are the same bindle.")
    src = Path(args.path)
    check_draft(source, args.name, args.kind, src, args.description, "promoted", args.allow)
    if args.replace and args.kind == "note":
        raise BindleError("Notes are added to the inbox, never replaced; drop --replace.")
    if args.dry_run:
        return show_change(target, args.name, args.kind, src)
    moved, committed = place(source, target, [(args.name, args.kind, src, args.description)], replace=args.replace)
    print(f"{'Replaced' if args.replace else 'Promoted'} {args.kind} {args.name} from {source['name']} into {target['name']}: {', '.join(moved)} "
          f"(leak check and secret check passed)." + ("" if committed else f" Not committed in {target['name']}; commit by hand."))
    if args.kind != "memory" or target["writes"] == "explicit":
        print(f"Push {target['name']} when ready (sync pushes only memory/, projects/ and outbox/ of a writable bindle).")
    return 0


def show_change(target, slug, kind, src):
    """Print what promoting would change in the target: a new item, or a diff against what's there."""
    if kind == "note":
        print(f"Would add to {target['name']}'s notes/inbox.md:\n{src.read_text(encoding='utf-8').strip()}")
        return 0
    out = destination(target, slug, kind, src)
    if not out.exists():
        print(f"Would add {out.relative_to(target['root']).as_posix()} to {target['name']} (nothing there yet).")
        return 0
    pairs = ([(f, out / f.relative_to(src)) for f in sorted(src.rglob("*")) if f.is_file()]
             + [(src / f.relative_to(out), f) for f in sorted(out.rglob("*")) if f.is_file() and not (src / f.relative_to(out)).exists()]
             if kind == "skill" else [(src, out)])
    changed = False
    for new, old in pairs:
        before = old.read_text(encoding="utf-8").splitlines(keepends=True) if old.exists() else []
        after = new.read_text(encoding="utf-8").splitlines(keepends=True) if new.exists() else []
        rel = old.relative_to(target["root"]).as_posix()
        diff = list(difflib.unified_diff(before, after, f"{target['name']}/{rel}", f"draft/{rel}"))
        if diff:
            changed = True
            sys.stdout.writelines(diff)
    if not changed:
        print(f"No change: {target['name']} already has exactly this.")
    else:
        print(f"\nPromote again with --replace to apply this to {target['name']}.")
    return 0


def cmd_outbox_add(args):
    b = find_bindle(args.bindle)
    slug, kind, src = args.name, args.kind, Path(args.path)
    check_draft(b, slug, kind, src, args.description, "added", args.allow)
    dest = b["root"] / "outbox" / slug
    if dest.exists():
        raise BindleError(f"{dest} already exists; pick another name.")
    dest.mkdir(parents=True)
    stored = {"memory": "memory.md", "command": "command.md", "note": "note.md"}.get(kind, src.name)
    if src.is_dir():
        shutil.copytree(src, dest / stored)
    else:
        shutil.copy2(src, dest / stored)
    write_json(dest / "item.json", {"kind": kind, "file": stored, "description": args.description, "status": "approved",
                                    "allowed_terms": list(args.allow),
                                    "sha256": content_hash(dest / stored), "collected_into": []})
    committed = commit(b["root"], f"Outbox: {slug}", f"outbox/{slug}")
    print(f"Added {kind} {slug} to {b['name']}'s outbox (leak check and secret check passed)."
          + ("" if committed else " Not committed (no git identity here?)."))
    allow = "".join(f" --allow {quote(t)}" for t in args.allow)
    print(f"It waits there until collected, on the machine where the target lives: "
          f"bindle collect {ref(b)} --into <target bindle> --items {slug}{allow}")


def outbox_items(b):
    box = b["root"] / "outbox"
    return [{**read_json(f), "dir": f.parent, "slug": f.parent.name} for f in sorted(box.glob("*/item.json"))] if box.is_dir() else []


def print_outbox(b, items):
    for it in items:
        where = f" -> {', '.join(it.get('collected_into') or [])}" if it.get("collected_into") else ""
        print(f"  {it['slug']}: {it.get('kind')}, {it.get('status')}{where}. {it.get('description') or ''}")


def cmd_outbox_list(args):
    if args.all == bool(args.bindle):
        raise BindleError("Pass a bindle or --all.")
    if args.bindle:
        b = find_bindle(args.bindle)
        items = outbox_items(b)
        if not items:
            print(f"{b['name']}'s outbox is empty.")
        print_outbox(b, items)
        return 0
    # Across every bindle bindle can find; only outboxes are read, never memories.
    found, _ = known_bindles()
    shown = 0
    for b in sorted(found.values(), key=lambda b: b["name"]):
        items = outbox_items(b)
        if items:
            print(f"{b['name']} ({b['root']}):")
            print_outbox(b, items)
            shown += 1
    if not shown:
        print("Every outbox is empty.")
    return 0


def cmd_outbox_clean(args):
    """Remove outbox items already collected; uncollected ones are waiting for review or a target, so stay."""
    b = find_bindle(args.bindle)
    items = outbox_items(b)
    if args.items:
        wanted = [s.strip() for s in args.items.split(",") if s.strip()]
        by_slug = {it["slug"]: it for it in items}
        for slug in wanted:
            if slug not in by_slug:
                raise BindleError(f"{b['name']}'s outbox has no item {slug}.")
            if not by_slug[slug].get("collected_into"):
                raise BindleError(f"{slug} hasn't been collected yet; clean removes only collected items.")
        items = [by_slug[s] for s in dict.fromkeys(wanted)]
    items = [it for it in items if it.get("collected_into") and not it["dir"].is_symlink()]
    if not items:
        print(f"Nothing to clean: no collected items in {b['name']}'s outbox.")
        return 0
    return remove_items(b, items, args.dry_run, "removed collected items")


def cmd_outbox_remove(args):
    """Drop named items whatever their status, e.g. an approved draft you changed your mind about."""
    b = find_bindle(args.bindle)
    by_slug = {it["slug"]: it for it in outbox_items(b)}
    wanted = list(dict.fromkeys(s.strip() for s in args.items.split(",") if s.strip()))
    missing = [s for s in wanted if s not in by_slug]
    if missing:
        raise BindleError(f"{b['name']}'s outbox has no item {', '.join(missing)}.")
    return remove_items(b, [by_slug[s] for s in wanted], args.dry_run, "removed")


def remove_items(b, items, dry_run, what):
    for it in items:
        if it["dir"].is_symlink():
            raise BindleError(f"{it['slug']} is a link, not a folder; remove it by hand.")
        where = f"collected into {', '.join(it['collected_into'])}" if it.get("collected_into") else "not collected"
        print(f"  {'would remove' if dry_run else 'removing'} {it['slug']} ({where})")
    if dry_run:
        return 0
    for it in items:
        shutil.rmtree(it["dir"])
    names = ", ".join(it["slug"] for it in items)
    if not commit(b["root"], f"Outbox: {what}: {names}", "outbox"):
        print("Removed, but not committed (no git identity here?). Commit by hand.")
    return 0


def validate_item(it):
    """An outbox item collect may trust: a known kind, approved, its file inside its own folder, unchanged since
    approval. The outbox syncs from other machines, so its item.json is treated as untrusted input."""
    slug = it["slug"]
    if not SLUG_RE.match(slug):
        raise BindleError(f"{slug}: not a valid item name.")
    if it.get("kind") not in KINDS:
        raise BindleError(f"{slug}: unknown kind {it.get('kind')!r}.")
    if it.get("status") not in COLLECTABLE:
        raise BindleError(f"{slug}: status is {it.get('status')!r}, not approved.")
    name = it.get("file")
    if not isinstance(name, str) or not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith("."):
        raise BindleError(f"{slug}: its file {name!r} isn't a plain name inside the item's folder.")
    src = it["dir"] / name
    if src.is_symlink() or not src.exists() or src.resolve().parent != it["dir"].resolve():
        raise BindleError(f"{slug}: {name} is missing, a link, or outside the item's folder.")
    if it["kind"] == "skill" and not src.is_dir():
        raise BindleError(f"{slug}: a skill must be a folder.")
    if it["kind"] != "skill" and not src.is_file():
        raise BindleError(f"{slug}: a {it['kind']} must be a single file.")
    description = it.get("description")
    if description is not None and (not isinstance(description, str) or "\n" in description or "\r" in description):
        raise BindleError(f"{slug}: its description isn't a single line of text.")
    if not it.get("sha256") or content_hash(src) != it["sha256"]:
        raise BindleError(f"{slug}: changed since it was approved (or has no recorded hash); add it to the outbox again.")
    return src


def cmd_collect(args):
    """Deliver waiting outbox items into the target, then remove them from the outbox: an item goes to one
    target, and git history keeps the record."""
    source, target = find_bindle(args.source), find_bindle(args.into)
    if source["root"] == target["root"]:
        raise BindleError("Source and target are the same bindle.")
    items = {it["slug"]: it for it in outbox_items(source)}
    wanted = list(items) if args.all else [s.strip() for s in (args.items or "").split(",") if s.strip()]
    if not wanted:
        raise BindleError("Name the items (--items a,b) or pass --all, so the command shows exactly what moves.")
    unknown = [s for s in wanted if s not in items]
    if unknown:
        raise BindleError(f"Not in {source['name']}'s outbox: {', '.join(unknown)}")
    todo = [items[s] for s in dict.fromkeys(wanted) if items[s].get("status") != "collected"]
    if not todo:
        print("Nothing to collect: those items were already collected (bindle outbox clean removes them).")
        return 0

    # The outbox syncs from other machines, and anything that can write files can write an item that claims to be
    # approved, so each one is validated and checked again, allowed terms come only from this command line, and
    # its full content is shown before anything moves.
    ready = []
    for it in todo:
        src = validate_item(it)
        hits = leak_hits(source, it["slug"], it.get("description"), src, args.allow)
        if hits:
            raise BindleError(f"Nothing collected; {it['slug']} names the source domain or looks like it holds a secret:\n"
                              + describe_hits(hits) + "\nIf a term is fine to share, run collect again with --allow <term>.")
        ready.append((it["slug"], it["kind"], src, it.get("description")))
    for slug, kind, src, description in ready:
        print(f"--- {slug} ({kind}){': ' + description if description else ''} ---")
        for f in draft_files(src):
            if src.is_dir():
                print(f"[{f.relative_to(src).as_posix()}]")
            print(f.read_bytes().decode("utf-8", errors="replace").rstrip("\n"))
    moved, target_ok = place(source, target, ready)
    for it in todo:
        shutil.rmtree(it["dir"])
    names = ", ".join(it["slug"] for it in todo)
    source_ok = commit(source["root"], f"Outbox: delivered to {target['name']}: {names}", "outbox")
    print(f"Collected into {target['name']}: " + ", ".join(moved) + f"; removed from {source['name']}'s outbox.")
    if not (target_ok and source_ok):
        failed = [n for n, ok in ((target["name"], target_ok), (source["name"], source_ok)) if not ok]
        print(f"Not committed in {', '.join(failed)} (no git identity, or a commit hook failed). Commit by hand.")
    return 0

