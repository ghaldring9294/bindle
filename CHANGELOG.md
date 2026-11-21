# Changelog

One entry per release. "Run `bindle upgrade`" means the files bindle manages inside every bindle changed: after `git pull` here, run `bindle upgrade <bindle>` (or `bindle upgrade` in a folder to upgrade every bindle attached there), then push each bindle. `bindle doctor` tells you when one is due.

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
