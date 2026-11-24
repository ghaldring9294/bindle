# AGENTS.md

Guidance for AI agents working in this repo (any agent; Claude Code reads it through CLAUDE.md).

## What bindle is

A CLI that carries one person's Claude Code setup between machines while keeping each domain's context in its own place. A **bindle** is one domain's layer (personal, an employer, a client): a git repo shaped as a Claude Code plugin, with `memory/`, `notes/`, `rules.md`, skills and hooks. A folder turns bindles on in its `.claude/settings.local.json`; every attached bindle is on there and **at most one is writable** (new memories go to it). Read `docs/design.md` for the design and why; update it when a decision changes. `PLAN.md` has the status and next steps.

## Layout

- `bin/bindle`: the CLI entry point (`bin/py` finds a working Python for hooks); the CLI is the `bindle/` package (`core.py` shared helpers, `commands.py`, `upgrade.py`, `promote.py`, `cli.py`). Python standard library only; must run on 3.9.
- `bin/bindle-server`: the MCP server; exposes bindle operations as tools over JSON-RPC 2.0 / stdio. The plugin's `.mcp.json` starts it; Claude Code calls the tools directly instead of running CLI commands.
- `templates/bindle/`: what `bindle new` copies. Files listed in `MANAGED` (in `bindle/core.py`) are copied byte for byte into every bindle and `bindle doctor` flags drift, so change them only here, deliberately, then update existing bindles.
- `templates/bindle/hooks/bindle_hook.py`: the one implementation of the hooks, sync, the writable check and the secret check. The CLI imports it from the template (`core.hooks()`), so never reimplement that logic in the CLI.
- `tests/`: `python3 -m unittest discover -s tests` (fast, fake `claude`); `tests/e2e.sh` (real Claude Code in a scratch folder; costs a few short sessions).
- `.claude-plugin/`: the plugin manifest (`plugin.json`, `marketplace.json`); bindle itself is a Claude Code plugin, installable with `/plugin marketplace add`.
- `.mcp.json`: declares the MCP server the plugin provides; Claude Code starts `bin/bindle-server` when the plugin loads.
- `commands/bindle.md`: the `/bindle` command, provided by the plugin. It's how Claude in **any** session understands bindle and handles requests like "attach craft here", so it must describe every tool and when to use it.
- `skills/bindle-promote/`: the promotion skill, provided by the plugin. Drafting is judgment; the `promote` tool (or `outbox_add` then `collect`, for a target on another machine) does every write and check.
- `hooks/hooks.json`: the plugin's session-check hook (warns when a session starts inside a domain folder without its bindle, and when bindle or a bindle needs updating).
- `MIGRATION.md`: instructions an agent follows to move an existing setup into bindles.
- `CHANGELOG.md` and `VERSION` (in `bindle/core.py`): bump the version and add an entry for each release; say "run `bindle upgrade`" when managed files or the layout change. Tag releases `vX.Y.Z`.

## Rules

1. **Never add, change or push a remote** for a bindle. Where a bindle lives is the person's call.
2. **Never write into a bindle that's read-only in the current folder.** Material moves between bindles only through promotion (an outbox the person reviews), never a direct edit.
3. **Keep this repo employer-free:** no employer names, systems or data, in code, docs or examples (use Acme, Globex).
4. **Use Claude Code's native mechanisms** (plugins, `autoMemoryDirectory`, hooks) rather than custom loading.
5. **Tests encode why:** each test says what breaks for a person if it fails. Run the unit tests before committing.
6. **Docs ship with the change, in the same commit.** A change to a command, a behaviour or a decision updates every place that describes it:
   - `README.md` (people using bindle) and `commands/bindle.md` (Claude operating bindle): tests check that both name every command and option, and that every `bindle …` line in a code block in the README and MIGRATION.md parses
   - `skills/bindle-promote/SKILL.md` and `MIGRATION.md`, when promotion or setup changes
   - `docs/design.md`, when a decision or its reason changes
   - `templates/bindle/AGENTS.md`, when the bindle layout changes
   - this file's Layout, when a module or script is added, renamed or removed (a test checks it names every one, and only paths that exist)
   - `CHANGELOG.md` for each release (a test checks its newest entry is `VERSION`), and `PLAN.md` (status, next steps, log)

   Before committing, check that nothing in these contradicts the change (grep for the command or term). Docs are written for a general audience.
