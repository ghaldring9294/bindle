# MIGRATION.md — instructions for Claude Code

You (Claude Code) are migrating this machine's existing Claude setup into the
structure defined by this repo. Work incrementally, show the human a plan before
moving anything, and never delete — only move, link, or copy.

## Ground rules

1. **Inventory before action.** Produce a written inventory and a proposed
   mapping table. Get explicit approval before executing.
2. **Nothing is deleted.** Anything replaced is moved to
   `~/.claude/backup-<date>/`, mirroring the installer's behavior.
3. **Respect the privacy boundary.** Two destinations exist:
   - `bindle` (this repo): reusable, domain-free config only — conventions,
     hooks, commands, agents, skills, templates. If a candidate file mentions an
     employer, product, codebase, ticket, schema, or person, it does NOT go here.
   - `bindle-memories` (private repo, default `~/bindle-memories`): all
     project-specific and personal context, under `projects/<name>/`.
   When unsure which side of the line something falls on, ask — do not guess
   toward the shareable side.
4. **Work memories stay in work-approved storage.** If this is a work machine,
   confirm with the human where the memories repo may be hosted before pushing
   anything anywhere.

## Step 1 — Inventory

Examine and summarize:

- `~/.claude/CLAUDE.md` — global conventions (if present)
- `~/.claude/settings.json` and `settings.local.json` — hooks, statusline, permissions
- `~/.claude/commands/`, `~/.claude/agents/`, `~/.claude/skills/`
- Per-project `CLAUDE.md` files and any ad-hoc memory/notes files the human
  points you to (ticket .md files, architecture notes, mermaid docs)

For each item record: path, purpose (one line), and destination:
`setup:<path>` / `memories:projects/<name>/<path>` / `stays put` / `unsure`.

## Step 2 — Propose the mapping

Present the table. Flag every `unsure`. Wait for approval.

## Step 3 — Execute

1. Run `bin/install.sh` if not already run (creates symlinks + backup dir).
2. **Global CLAUDE.md:** merge the human's existing global conventions into
   `global/CLAUDE.md` in this repo — their content takes precedence on conflict;
   preserve this repo's tier rules and `.claude-local` privacy block.
3. **Settings:** merge existing hooks/settings into `global/settings.json` if
   reusable and generic; machine- or auth-specific values go to
   `~/.claude/settings.local.json`.
4. **Commands / agents / skills:** move generic ones into `global/…` here;
   anything domain-specific goes to the memories repo for that project.
5. **Per-project memories:** for each project, run
   `bin/init-project.sh <project-path> --local <project-name>`, then move the
   project's existing ticket files into `.claude-local/tickets/`, architecture
   notes into `.claude-local/docs/`, and build `.claude-local/index.md` from
   what's there. Migrate existing ticket files toward the template shape
   (TL;DR top, append-only decision log) — but do not rewrite historical
   content, just add the structure around it.
6. Commit each repo separately with a summary of what moved where.

## Step 4 — Verify

- Start a fresh session in one migrated project; confirm the tier flow works
  (index → architecture → ticket) and the session orients without grepping.
- Confirm the cost hook wrote a row to `claude-costs.md` after one turn.
- Confirm `git status` in the team repo shows NO new untracked files
  (`.claude-local/` must be invisible via global excludes).

Report results and anything you couldn't classify.
