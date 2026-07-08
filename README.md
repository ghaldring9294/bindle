# bindle

Portable, opinionated Claude Code configuration. Clone on any machine, run the
installer, and your conventions, hooks, agents, and context architecture follow you.

Pairs with a **private** `bindle-memories` repo that holds per-project context
(never committed to team repos, never public).

## Quick start

```bash
git clone <this-repo> ~/bindle
cd ~/bindle
./bin/install.sh          # symlinks config into ~/.claude, sets global git excludes
./bin/init-project.sh ~/code/some-repo   # drop tiered doc templates into a project
```

Machine-specific settings go in `~/.claude/settings.local.json` (created by the
installer, never committed here).

## The methodology: context is a database problem

Claude Code's context window is a scarce, priced resource. Treat it like one.
This setup applies database engineering to agent context:

| Database concept | Context equivalent |
|---|---|
| Index | `docs/index.md` — one line per doc; agent scans 30 lines instead of grepping |
| Materialized view | `architecture.md`, mermaid ERDs — maintained summaries, refreshed on change |
| Query planner | Tier rules in CLAUDE.md — read cheap maps first, open source files surgically |
| Cache invalidation | Stable/volatile split — prompt caching rewards unchanged prefixes |
| Append-only log | Ticket decision logs — append, don't rewrite, so the prefix stays cached |

### The tiers

- **Tier 0 — Index.** `docs/index.md`: table of contents for all project docs.
- **Tier 1 — Summaries.** `architecture.md` (stable: data model mermaid, conventions,
  system boundaries), module one-pagers, ticket TL;DRs.
- **Tier 2 — Source.** Opened only after tiers 0–1 say where to look.

### Cache-aware rules

1. **Stable before volatile.** Architecture docs change rarely → load early, stay cached.
   Ticket files churn → load late. The always-loaded layer (the `CLAUDE.md` `@import` chain)
   is the highest-value cache surface — never interpolate dynamic values (dates, IDs, counts)
   into it, or the whole session's cached prefix invalidates.
2. **Append, don't rewrite.** Ticket updates go to the end of a `## Decision log`
   section. Editing the top of a file invalidates everything after it.
3. **Measure everything.** The cost-tracker hook records one cost row per session
   (upserted after each turn) in a central ledger. Optimizations without numbers are vibes.

## Layout

```
global/          → symlinked into ~/.claude (CLAUDE.md, settings, commands, agents, skills)
hooks/           → Stop-hook cost tracker + statusline + shared JSONL parsing lib
templates/       → tiered doc templates dropped into projects by init-project.sh
test/            → regression tests for the cost loop (bash + python3)
bin/             → install.sh, init-project.sh
MIGRATION.md     → instructions for Claude Code to migrate an existing setup into this structure
```

## What's optional (and what isn't)

Two kinds of thing live here, and they aren't equal:

- **Boundaries are the frame — mandatory and structural.** The trust-domain separation,
  the `.claude-local` privacy convention, and the craft/context split are the *point* of
  the toolkit. Don't remove them.
- **Features are furniture — opinionated defaults you can rip out.** The ticket workflow,
  cost tracking, and tiered retrieval are independent and opt-in. They don't depend on each
  other — e.g. cost tracking detects the ticket from the git branch and degrades to `-` when
  there's none, so it works fine with the ticket workflow deleted entirely.

There's no plugin system: the substrate is files, so "add a feature" means keep its files and
"remove it" means delete them. Keep what you use.

| Feature | Lives in | Remove by |
|---|---|---|
| Ticket workflow | `global/commands/ticket.md`, the *Ticket workflow* section of `global/CLAUDE.md`, `templates/ticket.md` | delete those |
| Cost ledger | `Stop` hook in `global/settings.json`, `hooks/cost-tracker.sh`, `hooks/lib/parse_usage.py` | remove the `Stop` hook entry |
| Statusline cost | `statusLine` in `global/settings.json`, `hooks/statusline.py` | remove the `statusLine` entry |
| Tiered retrieval | tier rules in `global/CLAUDE.md`, `templates/docs-index.md` + `architecture.md` | stop maintaining `docs/index.md` |

## Personal per-project context (`.claude-local/`)

Team repos stay pristine. Personal context lives in `.claude-local/`, which is:

- ignored **globally** via `git config core.excludesFile` (no team .gitignore edits)
- a **symlink** into your private `bindle-memories` repo, so it's versioned and portable
- taught to Claude via the global CLAUDE.md: read it first, never reference it in
  code, commits, or PR descriptions

## Security boundaries

- No secrets in this repo. Ever. Machine/auth specifics live in `settings.local.json`.
- Employer/project knowledge lives in `bindle-memories` (private), not here.
- Keep separate memories repos per trust domain (personal vs. work) so a wrong
  `git push` can't cross the boundary.
