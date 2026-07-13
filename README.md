# bindle

Portable, opinionated Claude Code configuration. Clone on any machine, run the
installer, and your conventions, hooks, agents, and context architecture follow you.

Bindle is the **orchestrator**: install it once, and it scaffolds and manages your **private
layer repos** — a personal layer plus one professional layer per employer/client — so every
piece of craft and memory is born in the right place. The layers are separate private repos;
nothing employer-specific ever lives in this public base. (Already have a tangled `~/.claude`?
Migration below is a one-time on-ramp; new work is born clean.)

## Quick start

```bash
git clone <this-repo> ~/bindle
cd ~/bindle
./bin/install.sh                                 # symlink base config into ~/.claude
./bin/init-layer.sh acme --scope professional    # scaffold a secure domain layer (its own private repo)
./bin/init-project.sh ~/code/some-repo           # link a project to your context
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
3. **Measure everything.** Optimizations without numbers are vibes. Pair this with a
   per-session cost ledger — the companion [`claude-cost-ledger`](https://github.com/ghaldring9294/claude-cost-ledger)
   repo is a drop-in `Stop` hook that writes one row per session to `claude-costs.md`.

## Layout

```
global/          → CLAUDE.md + settings.json, symlinked into ~/.claude
templates/       → tiered doc templates dropped into projects by init-project.sh
bin/             → install.sh, init-project.sh
MIGRATION.md     → instructions for Claude Code to migrate an existing setup into this structure
```

## What's optional (and what isn't)

Two kinds of thing live here, and they aren't equal:

- **Boundaries are the frame — mandatory and structural.** The trust-domain separation,
  the `.claude-local` privacy convention, and the craft/context split are the *point* of
  the toolkit. Don't remove them.
- **Opinionated *craft* lives in a layer, not here.** Base ships and farms **no** commands, agents,
  or skills — those are craft, farmed into `~/.claude` by a layer's own installer (your personal layer,
  or a professional layer). The `/ticket` workflow moved to the personal layer; cost tracking and the
  statusline became their own repos. Base stays opinion-free except for conventions anchored to a
  Claude-native default (memory taxonomy, tiered retrieval).
- **Conventions are format, not features.** Tiered retrieval and the memory taxonomy are how context is
  shaped for transport; they're base because a shared format is what makes transported context portable.

There's no plugin system: the substrate is files, so "add a feature" means keep its files and
"remove it" means delete them. Keep what you use.

| Convention | Lives in | Opt out by |
|---|---|---|
| Tiered retrieval | tier rules in `global/CLAUDE.md`, `templates/docs-index.md` + `architecture.md` | stop maintaining `docs/index.md` |
| Memory taxonomy | `templates/memory-taxonomy.md` + the *Memory taxonomy* section of `global/CLAUDE.md` | organize memory however you like |

## Personal per-project context (`.claude-local/`)

Team repos stay pristine. Personal context lives in `.claude-local/`, which is:

- ignored **globally** via `git config core.excludesFile` (no team .gitignore edits)
- a **symlink** into a professional layer's `projects/<name>/`, so it's versioned and portable
- taught to Claude via the global CLAUDE.md: read it first, never reference it in
  code, commits, or PR descriptions

## Security boundaries

- No secrets in this repo. Ever. Machine/auth specifics live in `settings.local.json`.
- Employer/project knowledge lives in a **professional layer** repo (private), not here.
- Keep separate layer repos per trust domain (personal vs. each employer/client) so a wrong
  `git push` can't cross the boundary.

## Layers, and migrating into them

Craft and memory live in **layer** repos, scaffolded with `bin/init-layer.sh` — each its own
private git repo, stored locally or on the appropriate (personal vs. company) git host:

- **personal** — cross-domain craft; loads on every machine (always-on). This is what you carry
  between your own machines, or onto a work box.
- **professional** — a secure employer/client domain; loads only inside that domain's projects
  (scoped). One per company; never overlaps personal or another professional layer.

### Migrating an existing setup

Most people adopting bindle start where its author did: a **mixed** `~/.claude` — personal craft and
employer/client context tangled together. The recommended path for that (the common case):

1. **Create the professional (secure) layer and migrate everything into it:**
   `init-layer <company> --scope professional --from ~/.claude/projects/<slug>/memory`. Everything
   lands in that layer's `memory/_incoming/` for sorting — secure-by-default, nothing leaks to a
   broader layer by omission.
2. **Promote genuinely cross-domain craft into a personal layer, piece by piece** — each move a
   deliberate "yes, this is safe to carry everywhere."

Already have *clean, personal-only* craft — e.g. carrying it between your own machines or onto a work
box? Skip step 1 and migrate straight into a **personal** layer; that's exactly what it's for.

```bash
./bin/init-layer.sh acme --scope professional --from ~/.claude/projects/<slug>/memory   # common: mixed → secure first
./bin/init-layer.sh me   --scope personal                                               # then promote cross-domain craft
```

Either way, `init-layer --from` **warns and asks you to confirm before copying** — the destination is
a trust decision, and nothing is copied until you confirm.
