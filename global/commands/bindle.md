---
description: Set up or operate bindle — install, create a layer, or migrate an existing setup
---

Help the user with bindle: $ARGUMENTS

bindle is the orchestrator. Its commands are on PATH as `bindle` (and in this repo's `bin/`):
- `bindle install` — link base config into `~/.claude` (once per machine).
- `bindle init-layer <name> --scope personal|professional [--from <memory-dir>]` — scaffold a private layer repo.
- `bindle init-project <repo> --local <name>` — link a project's private context into a layer.

From `$ARGUMENTS`, figure out what they want (fresh setup / new layer / migrate an existing `~/.claude`)
and run the right command. Rules:
1. **Never automate remotes.** Layers are LOCAL private repos; the user pushes them where they belong —
   a professional layer only to local or an *approved secure* host, never a personal/public one.
2. **Migration is secure-first** (see MIGRATION.md). For a mixed/existing setup: create the professional
   layer and migrate everything there first (`init-layer --from`, confirm the warning), then help PROMOTE
   genuinely cross-domain craft into the personal layer one item at a time — their explicit call each time.
   Migrating clean, personal-only craft straight into a personal layer is fine.
3. **Show the plan and get confirmation** before running anything that copies or moves files.
