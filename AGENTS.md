# AGENTS.md

Guidance for AI agents working in this repo (any agent; Claude Code reads it through CLAUDE.md).

## What bindle is

A CLI that carries one person's Claude Code setup between machines while keeping each domain's context in its own place. A **bindle** is one domain's layer (personal, an employer, a client): a git repo shaped as a Claude Code plugin, with `memory/`, `notes/`, `rules.md`, skills and hooks. A folder turns bindles on in its `.claude/settings.local.json`; every attached bindle is on there and **at most one is writable** (new memories go to it). Read `PLAN.md` for the design and why; it's the source of truth, so update it when a decision changes.

## Layout

- `bin/bindle`: the CLI (Python, standard library only, must run on 3.9).
- `templates/bindle/`: what `bindle new` copies. Files listed in `MANAGED` (in `bin/bindle`) are copied byte for byte into every bindle and `bindle doctor` flags drift, so change them only here, deliberately, then update existing bindles.
- `templates/bindle/hooks/lib.sh`: the one implementation of sync, the writable check and the secret check, shared by the hooks and the CLI.
- `tests/`: `python3 -m unittest discover -s tests` (fast, fake `claude`); `tests/e2e.sh` (real Claude Code in a scratch folder; costs a few short sessions).
- `global/skills/bindle-promote/`: the promotion skill (`bindle install` links it into `~/.claude/skills/`). Drafting is judgment; `bindle outbox add` and `bindle collect` do every write and check.
- `MIGRATION.md`: instructions an agent follows to move an existing setup into bindles.
- `CHANGELOG.md` and `VERSION` (in `bin/bindle`): bump the version and add an entry for each release; say "run `bindle upgrade`" when managed files or the layout change. Tag releases `vX.Y.Z`.

## Rules

1. **Never add, change or push a remote** for a bindle. Where a bindle lives is the person's call.
2. **Never write into a bindle that's read-only in the current folder.** Material moves between bindles only through promotion (an outbox the person reviews), never a direct edit.
3. **Keep this repo employer-free:** no employer names, systems or data, in code, docs or examples (use Acme, Globex).
4. **Use Claude Code's native mechanisms** (plugins, `autoMemoryDirectory`, hooks) rather than custom loading.
5. **Tests encode why:** each test says what breaks for a person if it fails. Run the unit tests before committing.
