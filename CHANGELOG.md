# Changelog

One entry per release. "Run `bindle upgrade`" means the files bindle manages inside every bindle changed: after `git pull` here, run `bindle upgrade <bindle>` (or `bindle upgrade` in a folder to upgrade every bindle attached there), then push each bindle. `bindle doctor` tells you when one is due.

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
