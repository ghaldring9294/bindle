---
description: Operate bindle, which carries Claude Code memory, rules and skills between machines in git repos ("bindles"). Use when the user asks to attach or detach a bindle, turn one on or off for a folder, make one writable or read-only, check which bindles are on, sync, upgrade, create a bindle, set up private terms, or migrate an existing setup.
---

Help the user with bindle: $ARGUMENTS

## The model

- A **bindle** is a git repo holding one domain's layer (personal, an employer, a client, shared craft): `memory/`, `projects/`, `notes/`, `rules.md`, skills, `private-terms.txt`. It's a Claude Code plugin, so its skills are `/<bindle>:<skill>`.
- A **folder** turns bindles on in its `.claude/settings.local.json`. Every attached bindle is **on** there; **at most one is writable** (new memories go to it). The rest are **read-only**: Claude Code is denied edits inside them.
- Where bindles live: a domain bindle is usually `<domain folder>/.bindle`; bindles used in many folders (personal, craft) are usually in `~/bindles/`, `~/bindles/registry.json` records where the others live. Every tool that takes a bindle accepts its name or its path (`craft` means `~/bindles/craft`; `acme` means wherever the registry says); `detach` takes the name of one attached to the folder. Prefer names.
- bindle keeps only that registry. The `doctor` tool reads the folder's settings and reports what's on.

## Tools

Bindle operations are MCP tools. Call them directly — no shell command needed. `folder` defaults to the current working directory. Any folder works, in a git repo or not; but if it's inside a repo, on macOS and Linux use the repo root, because that's where Claude Code reads settings (`attach` refuses a subfolder and names the root).

- **list**(folder?): every bindle bindle can find (in `~/bindles`, in its registry, and attached to the folder), each with whether it's writable, read-only or not attached there (all of them are on this machine), and registered ones that are gone. A bindle created or last attached before the registry existed appears once it's attached again; until then, ask the user for its path.
- **doctor**(folder?): what's on, which is writable, unsaved memories, warnings and problems, each problem with its fix. In a folder with a writable bindle, it also warns about repos directly inside whose sessions wouldn't load it, with the attach command. **Run this first** when unsure of the current state.
- **attach**(bindle, folder?, writable?, repos?): turn a bindle on for a folder (read-only unless writable=true). A folder has one writable bindle; detach the current one first to switch. repos=true also attaches it to each git repo directly inside the folder (a session started in a repo reads only that repo's settings); if any of them already has another writable bindle, nothing changes.
- **detach**(bindle, folder?, repos?): turn it off. Takes the bindle's name. repos=true also turns it off in each repo directly inside the folder that has it.
- **new**(name, at?, sync?, audience?, writes?): create a bindle repo (default `./.bindle`).
- **terms**(bindle, folder?): suggest private terms from the domain folder's repos (names, remotes, ticket prefixes). Suggestions only; the person picks.
- **sync**(folder?, all?): commit and push the writable bindle's memories, then pull the bindles that are on. all=true does every bindle `list` finds (commit and push only in those that can be writable). Sessions already sync on their own when a bindle has `"sync": true`; this is for catching up by hand.
- **update**(push?): upgrade every bindle's managed files, and list a push command for each one it upgrades; pass push=true only when the user asks to push. When bindle is installed as a plugin, the plugin is updated through Claude Code (`/plugin` → Installed → bindle → Update, or `claude plugin update bindle@bindle`). Run it when the session check says an update is available, or the user asks to update bindle.
- **upgrade**(bindle?, all?, dry_run?): bring a bindle's managed files up to this version of bindle; all=true does every bindle `list` finds. A bindle read-only in this folder is locked to Claude: give the user the command with a `!` prefix instead of running it.
- **promote**(source, path, into, name, kind?, description?, allow?, replace?, dry_run?): copy an approved, general draft into another bindle on this machine, after the private-terms and secrets checks. A note is appended to the target's `notes/inbox.md`. Without replace=true it never overwrites; replace=true updates an existing memory, skill or command, and dry_run=true prints the diff to show the user first. If it stops on a private term, show the user where; pass the term in allow to let it through once they say it's fine (a possible secret can't be allowed). Draft with the `/bindle-promote` skill.
- **outbox_add**(bindle, path, name, kind?, description?, allow?), **outbox_list**(bindle?, all?), **outbox_clean**(bindle, items?, dry_run?), **outbox_remove**(bindle, items, dry_run?): approved items waiting for a target that's on another machine; `outbox_remove` drops named ones, `outbox_clean` removes items an older bindle left marked collected.
- **collect**(source, into, items?, all?, allow?, dry_run?): on the machine where the target lives, deliver waiting outbox items into it and remove them from the outbox. Run it with dry_run=true first: it prints each item's content and moves nothing; show that to the user and collect on their yes. An item's own record of allowed terms isn't trusted, so a term allowed at approval needs allow again (outbox_add's output prints the full command).

### CLI-only (not MCP tools)

For terminal use, `bindle` is available on PATH when installed with `bindle install`. The CLI has the same operations as the tools above plus:

- `bindle install [--cleanup] [--session-check | --no-session-check]`: put `bindle` on PATH for terminal use. Optional when bindle is installed as a plugin (the plugin provides the command, skill and session-check hook). `--cleanup` removes the old-style links and user-level hook left by an earlier install. `--session-check` and `--no-session-check` add or remove a legacy user-level hook (the plugin provides this now).
- `bindle session-check [<folder>]`: what the session check would say for that folder (the installed hook runs it with `--hook`, reading the folder from Claude Code and answering in hook JSON). If a session opens with a "bindle: this session started in …" warning, offer to run the attach command it gives (it takes effect next session). For "bindle: … is available" or "… need(s) an upgrade", offer to run the `update` tool.

## Common requests

- **"Attach craft here" / "turn on personal":** call `attach` with the bindle name, read-only unless they say writable. The folder is the one this session was started in (or its repo root, if it's inside a repo on macOS/Linux). Then call `doctor` and tell them it takes effect in their **next** session, since Claude Code reads settings at session start.
- **"Detach craft" / "turn it off here":** call `detach`, then the same note.
- **"Make X writable here":** if another bindle is writable, say which; with their go-ahead, detach it (and attach it again without writable if they want it kept on read-only), then call `attach` with writable=true. Attaching the current writable one again without writable doesn't demote it.
- **"What's on?":** call `doctor`, summarized. **"What bindles do I have?":** call `list`.
- **"Add this to my personal bindle too" / "move this skill to my craft" / "copy that memory to globex":** use the `/bindle-promote` skill, never a direct write into the other bindle. "Move" means promote it, then offer to remove the original here.
- **"Remind me in globex to …" / a todo for another domain:** promote it as a note with `/bindle-promote` (kind `note`); it lands in that bindle's `notes/inbox.md`, and the next session there mentions it. Never write into another bindle directly.
- **Setting up on another machine:** don't use `new`; clone the existing repo into place: `git clone <url> ~/bindles/<name>` for one used in many folders, `git clone <url> <domain folder>/.bindle` for a domain bindle. Then attach it per folder. Plain `git clone <url>` lands in the current folder under the repo's name, which attach by name won't find.
- **"Rename this bindle":** there's no rename tool; follow README's "Renaming a bindle" (detach everywhere, change the three names, attach again, `doctor`). Show the plan first.
- **"Make a bindle" / "new X":** always pass `at`; the default (`./.bindle` in the current folder) is right only for a domain bindle created in its domain folder. Unless it's clear, ask which kind: a domain bindle (an employer, a client) goes in `<domain folder>/.bindle`; one used in many folders (personal, craft) goes in `~/bindles/<name>`. The name becomes the skill prefix (`/<name>:…`), so suggest a short one without "bindle" in it.
- **A new domain** ("make a bindle for ~/acme"): call `new` with at=`<domain folder>/.bindle`, then `terms`, have them pick terms and write the chosen ones to its `private-terms.txt`, then `attach` with writable=true and repos=true (repos so sessions started in its repos get it too) and `doctor`. Ask before setting sync; it needs a remote they add themselves. If they used Claude Code there before, offer to move the old memories in (MIGRATION.md).

## Rules

1. **Never add, change or push a remote.** Where each bindle lives is the user's call; a work bindle goes only where the employer allows.
2. **Never edit a bindle that's read-only in this folder,** by any means, shell included. Upgrading one is the user's step: give them the command with a `!` prefix.
3. A direct request ("attach craft here") is the go-ahead. **Show the plan and confirm first** when inferring, and before anything that copies or moves material or changes which bindle is writable.
4. **Migration follows MIGRATION.md** in the bindle repo: inventory, mapping, approval, then secure-first.
5. **Ask choices as a select.** When the person picks from a few options (yes or no, which bindle, which kind, approve or edit or drop), ask with the AskUserQuestion tool so they can arrow through them: recommended option first, and the question names the item, since the dialog can hide what you wrote before it. Answers they have to type (a path, a name, private terms) stay plain questions, as does everything when that tool isn't available.
