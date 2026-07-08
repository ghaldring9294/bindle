---
description: Start or resume a ticket using the tiered-context workflow
---

Work on ticket: $ARGUMENTS

1. If a tracker MCP (Jira/Linear/etc.) is connected and $ARGUMENTS looks like an ID or
   URL, fetch the ticket (and any linked design) for context.
2. Find or create the ticket file per the operating manual: `.claude-local/tickets/<ID>.md`
   if `.claude-local/` exists, else `docs/tickets/<ID>.md`. Use the standard shape —
   Status/TL;DR/links at the top, append-only `## Decision log`, working notes at the bottom.
3. Orient via the tiers: the ticket file's top section, then `docs/index.md`, then only the
   docs it points to. Do not grep broadly.
4. Restate the goal and current status in one short paragraph, then propose the next step.

Throughout the session: append dated decisions to the log as they are made, and refresh the
TL;DR/status before finishing.
