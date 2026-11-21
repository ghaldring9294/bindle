# Changelog

One entry per release. "Run `bindle upgrade`" means the files bindle manages inside every bindle changed: after `git pull` here, run `bindle upgrade <bindle>` (or `bindle upgrade` in a folder to upgrade every bindle attached there), then push each bindle. `bindle doctor` tells you when one is due.

## 0.5.0 (2026-11-21)

**Run `bindle upgrade`** (the hooks are now one Python file; the bash scripts are removed); for a bindle that's read-only where it's attached, run it yourself. Hardening from an independent review.

- **One implementation:** `hooks/bindle_hook.py` runs the hooks and is imported by the CLI, so the writable check, sync and the secret check can't disagree. Settings are parsed as JSON, and paths are compared properly (accents, brackets and spaces in paths work).
- **The CLI is a package** (`bindle/`), with `bin/bindle` as its entry point.
- **Promotion hardened:** `outbox add` records a hash of the approved content; `collect` refuses an item that isn't approved, changed since approval, points outside its folder, or contains symlinks. The leak check now covers the item's name, description and file names, not just contents. `collect` checks every destination before writing, so a failure leaves both bindles untouched, and it reports commits that failed.
- **Wider secret check:** case-insensitive, matches keywords inside longer names (`AWS_SECRET_ACCESS_KEY`), more token formats (`github_pat_`, `AIza…`, `sk-ant-`, `xapp-`), ignores placeholders like `${VAR}`, and handles file names with non-ASCII characters.
- **Fixes:** `doctor` flags a remote with no upstream (sync was silently keeping commits local); memories sync when `outbox/` is missing; the sync log works in worktrees; sync skips while a merge or rebase is in progress; `upgrade` stamps a missing layout instead of crashing; `detach` matches attached names before paths and can remove a bindle that moved; `doctor`'s fix commands quote paths; `doctor` warns when a read-only bindle's memory index is too long to show.

## 0.4.6 (2026-11-21)

**Run `bindle upgrade`** (adds `.gitattributes`); for a bindle that's read-only where it's attached, run it yourself.

- Fix: two machines adding memories between syncs both append to `MEMORY.md`, which stopped the rebase and left one machine's memory unpushed. `.gitattributes` now merges `memory/MEMORY.md` and `projects/*/index.md` with git's union driver, keeping both sides' lines.
- `bindle upgrade` appends missing template lines to `.gitattributes` as well as `.gitignore`.

## 0.4.5 (2026-11-21)

- `doctor` ends with a copy-and-paste command for each bindle that needs upgrading (`bindle upgrade <path>`, plus `&& git -C <path> push` when it has a remote), noting that in Claude Code it's prefixed with `!` because a read-only bindle is locked to Claude.

## 0.4.4 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`; adds `notes/scratch/` and its ignore rules); for a bindle that's read-only where it's attached, run it yourself.

- `notes/scratch/`: machine-local notes, ignored by git (its README is kept), never carried to other machines.
- Secrets in notes: `doctor` checks committable notes (and memory and outbox) for credentials and suggests moving them to secure storage with a pointer; the session start flags an uncommitted note that looks like it holds one. Files git ignores aren't checked.
- `bindle upgrade` appends template ignore rules a bindle's `.gitignore` lacks, never rewriting its own rules.

## 0.4.3 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`); for a bindle that's read-only where it's attached, run it yourself.

- Where a bindle is writable, the session start mentions uncommitted changes (and how many are in notes), so the session can remind the person to commit. With sync on, `memory/` and `outbox/` aren't counted, since sync commits them. Sync works without a remote too: it commits locally and skips the push.

## 0.4.2 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/rules.sh`). A read-only bindle is locked in folders where it's attached, so upgrade it yourself or from a folder where it isn't attached.

- A bindle's rules arrive framed as standing instructions to follow like CLAUDE.md, not as plain hook output.

## 0.4.1 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`).

- Where a bindle is writable, the session is told where its notes are (and to start at `notes/README.md` if there is one). Notes still aren't loaded automatically.
- MIGRATION.md: move an existing notes folder into the bindle and leave a symlink at the old path.

## 0.4.0 (2026-11-21)

**Run `bindle install` again** (it now links the `/bindle-promote` skill) and **`bindle upgrade`** (sync includes `outbox/`; new template files `private-terms.txt` and `outbox/`).

- Promotion through an outbox: `/bindle-promote` drafts general rewrites in the source domain's session; `bindle outbox add` stores an approved draft after a leak check (the source's `private-terms.txt`, whole words; a term ending in punctuation, like a ticket prefix `ACME-`, matches what follows) and the secret check; `bindle collect <source> --into <target> --items …` rechecks, copies memories (with an index line), skills or commands into the target, marks them collected, and commits both bindles. Naming the items puts them in Claude Code's permission prompt.
- Bindles have an `audience` (private, shared, public) and `writes` (implicit, explicit): `bindle new --audience shared --writes explicit` makes a craft bindle; `attach --writable` refuses an explicit bindle.
- `outbox/` syncs along with `memory/`, so items prepared on one machine can be collected on another.

## 0.3.2 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`).

- A memory goes at the lowest level that covers everything it's about: only one project → `projects/<project>/`; spanning projects (how two repos interact, domain-wide conventions) → `memory/`.

## 0.3.1 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`).

- The writable bindle's session-start line tells the session to file a memory about one project in `projects/<project>/` (listed in that folder's `index.md`), with one pointer line per project in `MEMORY.md`, so the always-loaded index stays short.

## 0.3.0 (2026-11-21)

**Run `bindle upgrade`** (new managed hook `rules.sh`, changed `hooks.json`), then **re-run `bindle attach`** for each read-only bindle so it gets locked (`bindle doctor` lists them).

- Rules load: each bindle's `rules.md` reaches every session where the bindle is on, through its own SessionStart hook (no CLAUDE.md edits, no import prompts). `doctor` warns when `rules.md` nears the hook's 10,000-character cap.
- Read-only bindles are locked: `attach` adds an `Edit(//<bindle>/**)` deny rule for a bindle that isn't writable in that folder, so a session can't edit it; `detach` and `attach --writable` remove it. `doctor` flags a read-only bindle that isn't locked, and a writable one that is.

## 0.2.0 (2026-11-21)

A rebuild around one model: every bindle has the same shape, folders turn bindles on, and one is writable. **Bindles from 0.1.0 aren't compatible; create new ones and migrate (MIGRATION.md).**

- CLI rewritten in Python: `install`, `new`, `attach`, `detach`, `doctor`, `sync`, `upgrade`, `--version`.
- A bindle is a Claude Code plugin with `bindle.json`, `memory/`, `notes/`, `rules.md`, `projects/` and managed hooks.
- Memory sync through each bindle's hooks (opt-in, `"sync": true`): pull at session start, commit `memory/` and push at session end; a memory that looks like a secret is never committed.
- `bindle new` inside a git repo excludes the bindle there; `doctor` flags a bindle a repo would commit.
- `AGENTS.md` in the base and in every bindle; each bindle tells the session whether it's writable or read-only.

## 0.1.0 (2026-07)

The first attempt: layers installed by a symlink farm, memory copied into place, `init-layer` and `init-project`. Replaced by 0.2.0.
