# MIGRATION.md: instructions for Claude Code

You (Claude Code) are moving this machine's existing Claude setup into bindles. Read PLAN.md's "The model" first. Show the person a plan before moving anything, and never delete: move, copy, or leave in place.

## Ground rules

1. **Inventory before action.** Produce an inventory and a proposed mapping table, then wait for approval.
2. **Nothing is deleted.** The old memory folder stays where it is until the person says it can go.
3. **Secure-first.** Each item goes to exactly one bindle. When unsure, choose the domain bindle (employer or client), never personal. Personal receives only craft (methods, skills, habits), one item at a time, each the person's explicit call, rewritten without the domain's specifics.
4. **Remotes are the person's call.** Never add or push a remote. A work bindle goes only to storage the employer allows.

## Step 1: Inventory

For each launch folder the person uses (often a parent of several repos, like `~/acme`):
- `~/.claude/projects/<slug>/memory/`: auto-memory for that folder, usually mixed
- `~/.claude/CLAUDE.md`: global rules, usually universal plus some domain rules
- `~/.claude/skills/`, `commands/`, `agents/`: tooling
- `~/.claude/settings.json` hooks: note which are personal tools and which are domain ones
- Notes folders the person points to

Record, per item: path, one-line purpose, destination (`<domain bindle>`, `personal`, `stays put`, or `unsure`).

## Step 2: Propose the mapping

Present the table. Flag every `unsure`. Wait for approval.

## Step 3: Execute

1. Create each bindle: `bindle new <name> --at <path>` (a domain bindle defaults to `<domain root>/.bindle`).
2. Copy memories into the destination bindle's `memory/` and rebuild its `MEMORY.md` index from the files. Keep each memory's frontmatter; add `boundary: craft | context | both` if missing.
3. Move tooling into the bindle's `skills/`, `commands/`, `agents/`. Remove the old hand-made link in `~/.claude/skills/` once the bindle is attached, or the skill shows up twice.
3a. Move an existing notes folder into the bindle's `notes/` and leave a symlink at the old path, so every reference to the old path keeps working. Before committing, ignore anything that shouldn't be in git (query results that may hold real customer data, large exports) in the bindle's `.gitignore`, and run the secret check.
4. Attach: `bindle attach <bindle> <folder> --writable` for the folder's own domain, and `bindle attach <personal bindle> <folder>` to have personal on too.
5. Commit each bindle separately with a summary of what moved.

## Step 4: Verify

- `bindle doctor <folder>`: the right bindles are on, the right one is writable, no problems.
- A fresh session started from the folder recalls a known memory and lists the bindle's skills (`<bindle>:<skill>`).
- The personal bindle contains nothing domain-specific.

Report results and anything you couldn't classify.
