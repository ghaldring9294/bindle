---
name: bindle-promote
description: Promote a memory, skill or command from the current domain's bindle into another bindle (a craft bindle, personal, another client), as a general rewrite the user approves; or send another domain a note (a reminder or todo). Use when the user asks to promote something ("promote the doc-style skill to my craft"), says a lesson is worth keeping elsewhere, asks what could be promoted, or wants a reminder in another domain ("remind me in globex to send the invoice").
---

# Promote into another bindle

The user asks in plain words; you do the judgment (finding, drafting, asking), and the `bindle` CLI does every write and check. They should never need to type a bindle command.

## 1. Work out what and where

- **Source:** usually the bindle that's writable in this folder (`bindle doctor`). To make a domain-specific version of a craft skill, the source can be craft and the target this folder's writable bindle; then customize the copy here.
- **What:** the memory, skill or command they named, or a **note**: a reminder or todo for the other domain, which you write from what they said. Memories are in the source's `memory/` and `projects/*/`, skills in `skills/<name>/`, commands in `commands/`. If they ask what could be promoted, offer memories tagged `boundary: craft` or `both`; `context` memories are never promoted.
- **Where:** run `bindle list` and match what they said ("my craft" → `craft`). If it's ambiguous or not listed, ask; never choose for them. A domain bindle that isn't listed: ask for its path.
- Read only the source's own files. Never read another domain's memories.
- If the source's `private-terms.txt` is empty, run `bindle terms <source>` first and have them pick terms to add, so the check below means something.

## 2. Draft a general version

- Keep the lesson; drop the domain: no organization, product, repo, system, ticket, people or data names. A reader outside this domain should find it true and useful.
- A memory keeps the memory format (frontmatter `name`, `description`, `type`, `boundary: craft`; body with **Why:** and **How to apply:**).
- A note: a short `.md` file with the reminder, written for when they're working in that domain. Keep this domain's specifics out of it; it's checked like everything else.
- A skill: copy its folder to a scratch folder and rewrite the copy; a command: the same with its file. Never edit the original, and never write into the target yourself.

## 3. Check with them

If the target already has it (an update, such as improving a craft skill you're using here), run the promote command below with `--dry-run` and show them that diff; on approval, run it with `--replace`. Otherwise show the draft beside the original, say briefly what you removed, and name the target: "This goes to craft as a memory named small-prs. Approve, edit, or drop?" Nothing moves without a yes for that item.

## 4. Move it

If the target is on this machine (it's in `bindle list`):
```
bindle promote <source path> <draft> --into <target> --kind memory|skill|command|note --name <slug> --description "<one line>"
```
It checks the draft against the source's private terms and for secrets, refuses to overwrite anything, places it (a note is appended to the target's `notes/inbox.md`), adds a memory index line for a memory, and commits the target. If it refuses on a private term, that's a prompt to check, not a wall: show them the term in context and ask whether to reword or keep it. If they say it's fine (a public name, a target that's theirs alone), run the same command with `--allow <term>`. A possible secret can't be allowed: take it out of the draft, and suggest a password manager or vault for it.

If the target lives on another machine, the draft waits in the source's outbox instead:
```
bindle outbox add <source path> <draft> --kind … --name <slug> --description "…"
```
Tell them to collect it there (or in a session there): `bindle collect <source> --into <target> --items <slug>`.

## 5. Finish

- Say where it landed, and how to use it there (a skill is `/<target>:<skill>` from the next session where the target is on).
- If the target has a remote, offer to push it (`git -C <target path> push`). Sync pushes only a writable bindle's memories, so a skill, a command, or anything in an explicit-writes bindle like craft needs this push to reach other machines. Ask first.
- If they're moving it rather than copying, offer to remove the original from the source (it's writable here). Removing something from another bindle can't happen from here, since that bindle is read-only: tell them to open a session in that bindle's own folder (for craft, `~/bindles/craft`) and remove it there.
- Rules (`rules.md`, `~/.claude/CLAUDE.md`) aren't promoted. To move a rule, show them the text and where it goes; they add it in a session in the target bindle's folder. General instructions belong in a craft bindle's `rules.md`, which loads wherever craft is on.
- Sending it to a second bindle is a second promotion. To drop a waiting outbox item: `bindle outbox remove <source> --items <slug>`.
