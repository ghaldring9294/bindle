---
name: promote
description: Promote a memory, skill or command from the current domain's bindle into another bindle (a craft bindle, personal, another client), as a general rewrite the user approves; or send another domain a note (a reminder or todo). Use when the user asks to put something from here into another bindle, in any words: "promote the doc-style skill to my craft", "add this to my personal bindle too", "move this skill to my craft", "copy that memory to globex", "keep this lesson in craft", "save this for my personal setup as well"; when they say a lesson is worth keeping elsewhere, asks what could be promoted, or wants a reminder in another domain ("remind me in globex to send the invoice"). Also use for any change to a bindle that's read-only here, craft above all (add, edit or remove its rules.md, an agent, a memory or any file): when the user asks ("change X in my craft", "update my craft rules") or a task would write into one, even when that bindle's own file says where things go.
---

# Promote into another bindle

The user asks in plain words; you do the judgment (finding, drafting, asking), and the bindle MCP tools do every write and check. They should never need to type a bindle command.

**Ask choices as a select.** When the person picks from a few options (yes or no, which bindle, which kind, approve or edit or drop), ask with the AskUserQuestion tool so they can arrow through them: recommended option first, and the question names the item, since the dialog can hide what you wrote before it. Answers they have to type (a path, a name, private terms) stay plain questions, as does everything when that tool isn't available.

## 1. Work out what and where

- **Source:** usually the bindle that's writable in this folder (call the `doctor` tool). To make a domain-specific version of a craft skill, the source can be craft and the target this folder's writable bindle; then customize the copy here.
- **What:** the memory, skill or command they named, any other file in the target (kind `file`, named by its path there: `rules.md`, `agents/<name>.md`, `memory/machines/<name>.md`; no index line), a **removal** (remove=true), or a **note**: a reminder or todo for the other domain, which you write from what they said. Memories are in the source's `memory/` and `projects/*/`, skills in `skills/<name>/`, commands in `commands/`. If they ask what could be promoted, judge from the content: offer lessons that would hold outside this domain, never ones that only make sense inside it.
- **Where:** call the `list` tool and match what they said ("my craft" → `craft`). If it's ambiguous or not listed, ask; never choose for them. A domain bindle that isn't listed: ask for its path.
- Read only the source's own files. Never read another domain's memories.
- If the source's `private-terms.txt` is empty, call the `terms` tool first and have them pick terms to add, so the check below means something.

## 2. Draft a general version

- Keep the lesson; drop the domain: no organization, product, repo, system, ticket, people or data names. A reader outside this domain should find it true and useful.
- A memory keeps Claude Code's memory format (frontmatter `name`, `description`, `type`; body with **Why:** and **How to apply:**).
- A note: a short `.md` file with the reminder, written for when they're working in that domain. Keep this domain's specifics out of it; it's checked like everything else.
- A skill: copy its folder to a scratch folder and rewrite the copy; a command: the same with its file. Never edit the original, and never write into the target yourself.

## 3. Check with them

If the target already has it (an update, such as improving a craft skill you're using here, or editing craft's `rules.md`), call the `promote` tool with dry_run=true and show them that diff; on approval, call it with replace=true. For a removal, call it with remove=true and dry_run=true, show what would go, and remove on their yes. Otherwise show the draft beside the original, say briefly what you removed, and name the target. Nothing moves without a yes for that item.

Ask with the AskUserQuestion tool (a select they arrow through), one question per item: "Send small-prs to craft as a memory?" with options **Approve**, **Edit** and **Drop**, and the draft (or the diff) as Approve's preview, since the dialog can hide what you wrote before it. On Edit, ask what to change, redraft, and ask again. Without that tool, ask in plain text: "Approve, edit, or drop?"

## 4. Move it

If the target is on this machine (it's in the `list` output, even marked "not attached here", which only means it isn't on in this folder):

Call the `promote` tool with the source, draft path, target, kind, name, and description.

It checks the draft against the source's private terms and for secrets, refuses to overwrite anything, places it (a note is appended to the target's `notes/inbox.md`), adds a memory index line for a memory, and commits the target. If it refuses on a private term, that's a prompt to check, not a wall: show them the term in context and ask whether to reword or keep it. If they say it's fine (a public name, a target that's theirs alone), call the tool again with the term in allow. A possible secret can't be allowed: take it out of the draft, and suggest a password manager or vault for it.

If the target lives on another machine, the draft waits in the source's outbox instead:

Call the `outbox_add` tool with the source, draft path, kind, name, and description.

Tell them to collect it there (or in a session there) with the `collect` tool (or `bindle collect` from the terminal): source, target, items, plus the terms they allowed. Run it with dry_run=true first, show them the content it prints, and collect on their yes.

## 5. Finish

- Say where it landed, and how to use it there (a skill is `/<target>:<skill>` from the next session where the target is on).
- If the target has a remote, offer to push it (`git -C <target path> push`). For a bindle that takes explicit writes (like craft) with sync on, the next session start pushes it anyway; otherwise sync pushes a bindle only from a session where it's writable, so this push is what gets it to other machines. Ask first.
- If they're moving it rather than copying, offer to remove the original from the source (it's writable here).
- A rule goes in as kind `file` with name `rules.md` and replace=true: draft the whole new file from the target's current `rules.md`. General instructions belong in a craft bindle's `rules.md`, which loads wherever craft is on, or in every session and subagent once craft is global (`bindle global craft`). `~/.claude/CLAUDE.md` isn't in a bindle; edit it only when they ask.
- Sending it to a second bindle is a second promotion. To drop a waiting outbox item: call the `outbox_remove` tool.
