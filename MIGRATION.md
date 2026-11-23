# MIGRATION.md: instructions for Claude Code

You (Claude Code) are moving this machine's existing Claude setup into bindles. Read docs/design.md's "The model" first. Show the person a plan before moving anything, and never delete: move, copy, or leave in place.

## Ground rules

1. **Inventory before action.** Produce an inventory and a proposed mapping table, then wait for approval.
2. **Nothing is deleted.** The old memory folders stay where they are until the person says they can go.
3. **Secure-first.** Each item goes to exactly one bindle. When unsure, choose the domain bindle (employer or client), never personal. Personal receives only craft (methods, skills, habits), one item at a time, each the person's explicit call, rewritten without the domain's specifics.
4. **Remotes are the person's call.** Never add or push a remote. A work bindle goes only to storage the employer allows.

## Step 1: Inventory

**Find every old memory folder, not just one.** Claude Code keeps a separate auto-memory folder for each folder a session was started from, named after its path with `/` replaced by `-` (`~/acme/web` → `~/.claude/projects/-Users-you-acme-web/memory/`). On macOS and Linux each git repo is its own starting point, so a domain folder holding several repos usually has one memory folder for the domain plus one per repo someone started Claude in:
```
ls -d ~/.claude/projects/-Users-you-acme*/memory
```
Count the memories in each and note which repos the person still starts sessions from (for narrow work, say). Ignore folders under temporary paths (`-private-tmp-…`, `-private-var-folders-…`); they're from scratch sessions.

Then, for the domain:
- each memory folder found above: usually mixed, and the per-repo ones are mostly about that repo
- `~/.claude/CLAUDE.md`: global rules, usually universal plus some domain rules
- files `CLAUDE.md` tells Claude to read or write (a lessons folder, a notes index): they're memory in all but name and need a destination like any memory
- `~/.claude/skills/`, `commands/`, `agents/`: tooling
- `~/.claude/settings.json` hooks: note which are personal tools and which are domain ones
- Notes folders the person points to

Record, per item: path, one-line purpose, destination (`<domain bindle>`, `personal`, `stays put`, or `unsure`).

## Step 2: Propose the mapping

Present the table. Flag every `unsure`. Wait for approval.

## Step 3: Execute

1. Create each bindle: `bindle new <name> --at <path>` (a domain bindle defaults to `<domain root>/.bindle`). For a domain bindle, run `bindle terms <bindle>`, show the suggestions, add the names that identify the domain (plus people, products and internal systems the person names) to its `private-terms.txt`, and confirm the list with the person. Promotion checks drafts against it.
2. Copy memories into the destination bindle and rebuild its `MEMORY.md` index from the files. Memories about only one repo (most of a per-repo folder) go in `projects/<repo>/` with that folder's `index.md`, and `MEMORY.md` gets one pointer line per project; memories that span repos go in `memory/`. Check each per-repo memory against the domain-level ones first: the same lesson is often in both. Keep each memory's frontmatter; add `boundary: craft | context | both` if missing.
2a. If `CLAUDE.md` tells Claude to save lessons or notes somewhere outside the bindles, update that rule to save into the writable bindle instead, or new material keeps landing outside it.
3. Move tooling into the bindle's `skills/`, `commands/`, `agents/`. Remove the old hand-made link in `~/.claude/skills/` once the bindle is attached, or the skill shows up twice.
3a. Move an existing notes folder into the bindle's `notes/` and leave a symlink at the old path, so every reference to the old path keeps working. Before committing, ignore anything that shouldn't be in git (query results that may hold real customer data, large exports) in the bindle's `.gitignore`, and run the secret check.
4. Attach: `bindle attach <bindle> <folder> --writable` for the folder's own domain, and `bindle attach <personal bindle> <folder>` to have personal on too. Also attach the domain's bindle, writable, to each repo inside it that the person starts sessions from: a session started in a repo reads that repo's settings, not the domain folder's, so without this it gets none of the bindle and keeps writing to the old memory folder.
5. Commit each bindle separately with a summary of what moved.

## Step 4: Verify

- `bindle doctor <folder>`: the right bindles are on, the right one is writable, no problems.
- A fresh session started from the folder recalls a known memory and lists the bindle's skills (`<bindle>:<skill>`). So does one started from a repo inside it, if the person starts sessions there.
- Every old memory folder found in step 1 is accounted for in the mapping: moved, merged into an existing memory, or left out on purpose.
- The personal bindle contains nothing domain-specific.

Report results and anything you couldn't classify.
