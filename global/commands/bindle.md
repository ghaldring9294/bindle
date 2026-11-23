---
description: Operate bindle, which carries Claude Code memory, rules and skills between machines in git repos ("bindles"). Use when the user asks to attach or detach a bindle, turn one on or off for a folder, make one writable or read-only, check which bindles are on, sync, upgrade, create a bindle, set up private terms, or migrate an existing setup.
---

Help the user with bindle: $ARGUMENTS

## The model

- A **bindle** is a git repo holding one domain's layer (personal, an employer, a client, shared craft): `memory/`, `projects/`, `notes/`, `rules.md`, skills, `private-terms.txt`. It's a Claude Code plugin, so its skills are `/<bindle>:<skill>`.
- A **folder** turns bindles on in its `.claude/settings.local.json`. Every attached bindle is **on** there; **at most one is writable** (new memories go to it). The rest are **read-only**: Claude Code is denied edits inside them.
- Where bindles live: a domain bindle is usually `<domain folder>/.bindle`; bindles used in many folders (personal, craft) are usually in `~/bindles/`, `~/bindles/registry.json` records where the others live. Every command that takes a bindle accepts its name or its path (`craft` means `~/bindles/craft`; `acme` means wherever the registry says); `detach` takes the name of one attached to the folder. Prefer names. Run `bindle` alone for the full command list.
- bindle keeps only that registry. `bindle doctor` reads the folder's settings and reports what's on.

## Commands

`bindle` is on PATH. `<folder>` defaults to the current folder. Any folder works, in a git repo or not; but if it's inside a repo, on macOS and Linux use the repo root, because that's where Claude Code reads settings (`attach` refuses a subfolder and names the root).

- `bindle list [<folder>]`: every bindle bindle can find (in `~/bindles`, in its registry, and attached to the folder), each with whether it's writable or read-only there, and registered ones that are gone. A bindle created or last attached before the registry existed appears once it's attached again; until then, ask the user for its path.
- `bindle doctor [<folder>]`: what's on, which is writable, unsaved memories, warnings and problems, each problem with its fix. In a folder with a writable bindle, it also warns about repos directly inside whose sessions wouldn't load it, with the attach command. **Run this first** when unsure of the current state.
- `bindle attach <bindle> [<folder>] [--writable] [--repos]`: turn a bindle on for a folder (read-only unless `--writable`). A folder has one writable bindle; detach the current one first to switch. `--repos` also attaches it to each git repo directly inside the folder (a session started in a repo reads only that repo's settings); if any of them already has another writable bindle, nothing changes.
- `bindle detach <name-or-path> [<folder>] [--repos]`: turn it off. Takes the bindle's name. `--repos` also turns it off in each repo directly inside the folder that has it.
- `bindle new <name> [--at <dir>] [--sync] [--audience private|shared|public] [--writes implicit|explicit]`: create a bindle repo (default `./.bindle`).
- `bindle terms <bindle> [<folder>]`: suggest private terms from the domain folder's repos (names, remotes, ticket prefixes). Suggestions only; the person picks.
- `bindle sync [<folder> | --all]`: pull the bindles that are on; commit and push the writable one's memories. `--all` does every bindle `bindle list` finds (commit and push only in those that can be writable). Sessions already sync on their own when a bindle has `"sync": true`; this is for catching up by hand.
- `bindle upgrade [<bindle> | --all] [--dry-run]`: bring a bindle's managed files up to this version of bindle; `--all` does every bindle `bindle list` finds. A bindle read-only in this folder is locked to Claude: give the user the command with a `!` prefix instead of running it.
- `bindle promote <source> <draft> --into <target> --name <slug> [--kind memory|skill|command|note] [--description …] [--allow <term>] [--replace] [--dry-run]`: copy an approved, general draft into another bindle on this machine, after the private-terms and secrets checks. A note is appended to the target's `notes/inbox.md`. Without `--replace` it never overwrites; `--replace` updates an existing memory, skill or command, and `--dry-run` prints the diff to show the user first. If it stops on a private term, show the user where; `--allow <term>` lets that term through once they say it's fine (a possible secret can't be allowed). Draft with the `/bindle-promote` skill.
- `bindle outbox add <bindle> <draft> --name <slug> [--kind memory|skill|command|note] [--description …] [--allow <term>]`, `bindle outbox list <bindle> | --all`, `bindle outbox clean <bindle> [--items …] [--dry-run]`, `bindle outbox remove <bindle> --items …`: approved items waiting for a target that's on another machine; `remove` drops named ones, `clean` removes items an older bindle left marked collected.
- `bindle collect <source> --into <target> --items <slugs>`: on the machine where the target lives, deliver waiting outbox items into it and remove them from the outbox.
- `bindle install [--session-check | --no-session-check]`: put `bindle` on PATH and link `/bindle` and `/bindle-promote` into `~/.claude`. `--session-check` adds one user-level SessionStart hook to `~/.claude/settings.json` (the only thing bindle writes there) that warns when a session starts inside a folder attached writable, in a folder with no writable bindle of its own; recommend it when setting someone up. `--no-session-check` removes it.
- `bindle session-check [<folder>]`: what the session check would say for that folder (the installed hook runs it with `--hook`, reading the folder from Claude Code and answering in hook JSON). If a session opens with a "bindle: this session started in …" warning, offer to run the attach command it gives (it takes effect next session).

## Common requests

- **"Attach craft here" / "turn on personal":** `bindle attach <name> <folder>`, read-only unless they say writable. The folder is the one this session was started in (or its repo root, if it's inside a repo on macOS/Linux). Then run `bindle doctor` and tell them it takes effect in their **next** session, since Claude Code reads settings at session start.
- **"Detach craft" / "turn it off here":** `bindle detach <name> <folder>`, then the same note.
- **"Make X writable here":** if another bindle is writable, say which; with their go-ahead, detach it (and attach it again without `--writable` if they want it kept on read-only), then `bindle attach X <folder> --writable`. Attaching the current writable one again without `--writable` doesn't demote it.
- **"What's on?":** `bindle doctor`, summarized. **"What bindles do I have?":** `bindle list`.
- **"Remind me in globex to …" / a todo for another domain:** promote it as a note with `/bindle-promote` (kind `note`); it lands in that bindle's `notes/inbox.md`, and the next session there mentions it. Never write into another bindle directly.
- **Setting up on another machine:** don't use `bindle new`; clone the existing repo into place: `git clone <url> ~/bindles/<name>` for one used in many folders, `git clone <url> <domain folder>/.bindle` for a domain bindle. Then attach it per folder. Plain `git clone <url>` lands in the current folder under the repo's name, which `attach <name>` won't find.
- **"Rename this bindle":** there's no rename command; follow README's "Renaming a bindle" (detach everywhere, change the three names, attach again, `bindle doctor`). Show the plan first.
- **A new domain:** `bindle new <name> --at <domain folder>/.bindle`, then `bindle terms`, have them pick terms and write the chosen ones to its `private-terms.txt`, then attach it writable. Ask before setting `--sync`; it needs a remote they add themselves.

## Rules

1. **Never add, change or push a remote.** Where each bindle lives is the user's call; a work bindle goes only where the employer allows.
2. **Never edit a bindle that's read-only in this folder,** by any means, shell included. Upgrading one is the user's step: give them the command with a `!` prefix.
3. A direct request ("attach craft here") is the go-ahead. **Show the plan and confirm first** when inferring, and before anything that copies or moves material or changes which bindle is writable.
4. **Migration follows MIGRATION.md** in the bindle repo: inventory, mapping, approval, then secure-first.
