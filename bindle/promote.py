"""Promotion: material leaves a bindle only as text the person approved as general.

`outbox add` checks a draft against the source bindle's private terms and for credentials, stores it in the
source's outbox and records a hash of the approved content. `collect` validates each item (approved, hash
unchanged, no paths outside its folder, no symlinks), checks again, and copies it into the target only once
every destination is known to be free.
"""
import hashlib
import os
import re
import shutil
from pathlib import Path

from .core import BindleError, find_bindle, git, hooks, load_bindle, read_json, real, write_json, write_text

KINDS = {"memory": "memory", "skill": "skills", "command": "commands"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
COLLECTABLE = ("approved", "collected")  # "collected" items may be collected into further targets


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


def leak_hits(b, slug, description, src):
    """Reasons a draft can't leave the bindle: a private term in its name, description, file names or contents,
    or content that looks like a credential."""
    terms, hits = private_terms(b), []
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
    return "\n".join(f"  {where}: {what}" for where, what in hits)


def commit(root, message, *paths):
    git(root, "add", "-A", "--", *paths)
    return git(root, "commit", "-q", "-m", message, "--", *paths) is not None


def cmd_outbox_add(args):
    b = load_bindle(args.bindle)
    slug, kind, src = args.name, args.kind, Path(args.path)
    if not SLUG_RE.match(slug):
        raise BindleError("Name must be lowercase letters, digits, hyphens or underscores.")
    if not src.exists():
        raise BindleError(f"{src} doesn't exist.")
    if kind in ("memory", "command") and not (src.is_file() and src.suffix == ".md"):
        raise BindleError(f"A {kind} is a single .md file.")
    if kind == "skill" and not (src.is_dir() and (src / "SKILL.md").is_file()):
        raise BindleError("A skill is a folder with a SKILL.md.")
    hits = leak_hits(b, slug, args.description, src)
    if hits:
        raise BindleError("Not added; the draft still names this domain or looks like it holds a secret:\n" + describe_hits(hits))
    dest = b["root"] / "outbox" / slug
    if dest.exists():
        raise BindleError(f"{dest} already exists; pick another name.")
    dest.mkdir(parents=True)
    stored = "memory.md" if kind == "memory" else ("command.md" if kind == "command" else src.name)
    if src.is_dir():
        shutil.copytree(src, dest / stored)
    else:
        shutil.copy2(src, dest / stored)
    write_json(dest / "item.json", {"kind": kind, "file": stored, "description": args.description, "status": "approved",
                                    "sha256": content_hash(dest / stored), "collected_into": []})
    committed = commit(b["root"], f"Outbox: {slug}", f"outbox/{slug}")
    print(f"Added {kind} {slug} to {b['name']}'s outbox (leak check and secret check passed)."
          + ("" if committed else " Not committed (no git identity here?)."))
    print(f"Collect it: bindle collect {b['root']} --into <target bindle> --items {slug}")


def outbox_items(b):
    box = b["root"] / "outbox"
    return [{**read_json(f), "dir": f.parent, "slug": f.parent.name} for f in sorted(box.glob("*/item.json"))] if box.is_dir() else []


def cmd_outbox_list(args):
    b = load_bindle(args.bindle)
    items = outbox_items(b)
    if not items:
        print(f"{b['name']}'s outbox is empty.")
    for it in items:
        where = f" -> {', '.join(it.get('collected_into') or [])}" if it.get("collected_into") else ""
        print(f"  {it['slug']}: {it.get('kind')}, {it.get('status')}{where}. {it.get('description') or ''}")


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
    if not it.get("sha256") or content_hash(src) != it["sha256"]:
        raise BindleError(f"{slug}: changed since it was approved (or has no recorded hash); add it to the outbox again.")
    return src


def destination(target, it):
    if it["kind"] == "skill":
        return target["root"] / "skills" / it["file"]
    return target["root"] / KINDS[it["kind"]] / f"{it['slug']}.md"


def cmd_collect(args):
    source, target = load_bindle(args.source), load_bindle(args.into)
    if source["root"] == target["root"]:
        raise BindleError("Source and target are the same bindle.")
    items = {it["slug"]: it for it in outbox_items(source)}
    wanted = list(items) if args.all else [s.strip() for s in (args.items or "").split(",") if s.strip()]
    if not wanted:
        raise BindleError("Name the items (--items a,b) or pass --all, so the command shows exactly what moves.")
    unknown = [s for s in wanted if s not in items]
    if unknown:
        raise BindleError(f"Not in {source['name']}'s outbox: {', '.join(unknown)}")
    todo = [items[s] for s in dict.fromkeys(wanted) if target["name"] not in (items[s].get("collected_into") or [])]
    if not todo:
        print(f"Nothing to collect: already in {target['name']}.")
        return 0

    # Check everything before writing anything, so a failure leaves both bindles as they were.
    sources, dests = {}, {}
    for it in todo:
        sources[it["slug"]] = validate_item(it)
        hits = leak_hits(source, it["slug"], it.get("description"), sources[it["slug"]])
        if hits:
            raise BindleError(f"Nothing collected; {it['slug']} names the source domain or looks like it holds a secret:\n" + describe_hits(hits))
        out = destination(target, it)
        if out.resolve().parent != (target["root"] / KINDS[it["kind"]]).resolve():
            raise BindleError(f"{it['slug']}: its destination {out} is outside {target['name']}.")
        if out.exists() or out in dests.values():
            raise BindleError(f"{out} already exists in {target['name']} (or two items want it); nothing collected.")
        dests[it["slug"]] = out

    moved, index_lines = [], []
    for it in todo:
        src, out = sources[it["slug"]], dests[it["slug"]]
        out.parent.mkdir(parents=True, exist_ok=True)
        if it["kind"] == "skill":
            shutil.copytree(src, out)
        else:
            shutil.copy2(src, out)
        if it["kind"] == "memory":
            index_lines.append(f"- [{it['slug']}]({it['slug']}.md) — {it.get('description') or 'promoted from ' + source['name']}\n")
        moved.append(out.relative_to(target["root"]).as_posix())
    if index_lines:
        write_text(target["root"] / "memory" / "MEMORY.md", "".join(index_lines), mode="a")
    for it in todo:
        meta = read_json(it["dir"] / "item.json")
        meta["status"] = "collected"
        meta["collected_into"] = sorted(set(meta.get("collected_into") or []) | {target["name"]})
        write_json(it["dir"] / "item.json", meta)

    names = ", ".join(it["slug"] for it in todo)
    paths = moved + (["memory/MEMORY.md"] if index_lines else [])
    target_ok = commit(target["root"], f"Promote from {source['name']}: {names}", *paths)
    source_ok = commit(source["root"], f"Outbox: collected into {target['name']}: {names}", "outbox")
    print(f"Collected into {target['name']}: " + ", ".join(moved))
    if target_ok and source_ok:
        print(f"Committed in both bindles. Sync pushes memory/ and outbox/; push {target['name']} yourself if it got a skill or command.")
    else:
        failed = [n for n, ok in ((target["name"], target_ok), (source["name"], source_ok)) if not ok]
        print(f"Copied, but not committed in {', '.join(failed)} (no git identity, or a commit hook failed). Commit by hand.")
    return 0
