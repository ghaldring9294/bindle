# MIGRATION.md — instructions for Claude Code

You (Claude Code) are migrating this machine's existing Claude setup into the bindle model.
Bindle is the orchestrator; craft and memory move into private **layer** repos it scaffolds —
never into this public base. Work incrementally, show the human a plan before moving anything,
and never delete — only move, link, or copy.

## Ground rules

1. **Inventory before action.** Produce a written inventory + a proposed mapping table. Get
   explicit approval before executing.
2. **Nothing is deleted.** Anything replaced is moved to `~/.claude/backup-<date>/`, mirroring
   the installer.
3. **Secure-first, promote explicitly.** Three destinations:
   - **base** (`bindle`, public): the frame only — conventions + Claude-native-anchored format
     (tiered retrieval, memory taxonomy), transport machinery, doc templates. NO craft, NO context.
   - **a professional layer** (private, secure; one per employer/client): anything mentioning an
     employer, product, codebase, ticket, schema, or person.
   - **the personal layer** (private, cross-domain): genuinely universal craft only.
   Default to the SECURE side when unsure — migrate everything into the professional layer first,
   then PROMOTE genuinely cross-domain craft into personal as explicit, per-item decisions. Never
   guess toward the broader/shareable side.
4. **Work content stays in work-approved storage.** On a work machine, confirm with the human where
   the professional layer may be hosted before pushing anything anywhere.

## Step 1 — Inventory

Examine and summarize:
- `~/.claude/CLAUDE.md` — global conventions (usually a mix of universal / personal / employer rules)
- `~/.claude/settings.json` + `settings.local.json` — hooks, statusline, permissions
- `~/.claude/commands/`, `agents/`, `skills/` — craft
- `~/.claude/projects/<slug>/memory/` — auto-memory (the big one; usually mixed)
- Per-project `CLAUDE.md` + ad-hoc notes the human points you to

For each item record: path, purpose (one line), destination — `base` / `professional:<company>` /
`personal` / `stays put` / `unsure`. When in doubt, professional.

## Step 2 — Propose the mapping

Present the table. Flag every `unsure`. Wait for approval.

## Step 3 — Execute (secure-first)

1. `bin/install.sh` if not already run (links base config + backup dir).
2. **Create the professional layer and migrate into it FIRST:**
   `bin/init-layer.sh <company> --scope professional --from ~/.claude/projects/<slug>/memory`
   (confirm the warning). Everything lands in its `memory/_incoming/` for sorting into type folders.
   Move employer craft (commands/agents/skills) and the employer parts of the global `CLAUDE.md` here too.
3. **Create the personal layer:** `bin/init-layer.sh me --scope personal`. PROMOTE only genuinely
   cross-domain craft/memory into it, one item at a time — each an explicit "safe everywhere" call.
   Truly-universal global-`CLAUDE.md` rules → the personal layer's `CLAUDE.personal.md`.
4. **Base gets truly-universal, Claude-native-anchored conventions only** → `global/CLAUDE.md`;
   machine/auth specifics → `~/.claude/settings.local.json`. Base ships no craft — do NOT move
   commands/agents/skills here.
5. **Per-project context:** for each project,
   `BINDLE_LAYER_DIR=<layer-repo> bin/init-project.sh <path> --local <name>`, then move that project's
   ticket files / architecture notes under the linked `.claude-local/`, building `.claude-local/index.md`.
   Migrate ticket files toward the template shape (TL;DR top, append-only log) without rewriting history.
6. Commit each repo separately with a summary of what moved where.

## Step 4 — Verify

- Fresh session in one migrated project: tier flow works (index → architecture → ticket), orients without grepping.
- `git status` in the team repo shows NO new untracked files (`.claude-local/` invisible via global excludes).
- The personal layer contains nothing employer-specific.

Report results and anything you couldn't classify.
