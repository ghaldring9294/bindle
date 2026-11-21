---
description: Set up or operate bindle: create a bindle, turn bindles on for a folder, check a folder, or migrate an existing setup
---

Help the user with bindle: $ARGUMENTS

`bindle` is on PATH. Commands:
- `bindle new <name> [--at <dir>]`: create a bindle repo (default `./.bindle`).
- `bindle attach <bindle> [<folder>] [--writable]`: turn a bindle on for a folder; `--writable` makes it the one new memories go to.
- `bindle detach <name-or-path> [<folder>]`: turn it off.
- `bindle sync [<folder>]`: pull the bindles that are on; commit and push the writable one's memories.
- `bindle doctor [<folder>]`: what's on, which is writable, unsaved memories, drift.

Rules:
1. **Never add or push remotes.** The user puts each bindle on its own domain's git host.
2. **Migration follows MIGRATION.md in the bindle repo:** inventory, mapping, approval, then secure-first.
3. **Show the plan and get confirmation** before anything that copies, moves or attaches.
