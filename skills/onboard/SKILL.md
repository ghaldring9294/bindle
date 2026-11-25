---
name: onboard
description: Set up bindle for the first time — create or clone bindles, attach them, and see them work. Offered by the session check when no bindles exist.
---

# Onboard

Walk the person through their first bindle setup. They should never need to type a bindle command — you call the MCP tools.

**Ask choices as a select.** When the person picks from a few options (approve / decline, which path, yes / no), ask with the AskUserQuestion tool so they can arrow through them: recommended option first, and the question names the item, since the dialog can hide what you wrote before it. Answers they have to type (a path, a name, a remote URL) stay plain questions, as does everything when that tool isn't available.

## 1. Already have bindles?

Ask first: "Do you already have bindles on another machine, or is this a fresh start?"

- **Clone flow:** for each bindle they name, get its git URL and ask which kind it is (Options: **Craft**: rules and skills that follow them everywhere; **Domain**: one context kept to its own folder, such as a job, a client, or their personal projects). Clone it to where that kind lives (`~/bindles/<name>` for craft; `<domain folder>/.bindle` for a domain, asking which folder):
  ```
  git clone <url> <destination>
  ```
  Then attach it by kind:
  - **Craft:** call `global` so its rules load everywhere, and `attach` it read-only to the folders they work in. Read its `bindle.json` first: one with `"writes": "explicit"` only takes promoted material and can't be writable anywhere.
  - **Domain:** `attach` it writable to the domain folder with repos=true, since a session started in a repo inside the folder reads only that repo's settings.

  Call `doctor` at the end. Done — skip to step 6 (remotes are already set by the clone).

- **Fresh start:** continue to step 2.

## 2. Create craft — your portable rules

Explain what craft is in terms of what it does for them, not the mechanics:

> "This creates a place for instructions that follow you everywhere — your preferences for how Claude works, your workflow rules, skills you build up over time. Think of it as a portable CLAUDE.md that loads in every session, every subagent, in any folder, on any machine where you clone it."

1. Call the `new` tool: name=`craft`, at=`~/bindles/craft`, sync=false (no remote yet).
2. Call `global` with bindle=`craft` — this imports craft's `rules.md` and memory index into the user `CLAUDE.md`, so they load everywhere.

Tell them: "Created your craft bindle and set it global. Let's put something in it so you can see it working."

## 3. Write your first rule

Make the loop tangible right now — don't just say "you'll see it next session."

1. Ask: "What's one instruction you'd want Claude to follow in every session? Something like 'prefer concise responses' or 'always use TypeScript' — or I can add a starter for you." (Options: **I'll pick one**, **Add a starter for me**, **Skip**)

2. If they pick one or want a starter: write it into `rules.md` in the craft bindle. For a starter, use something lightweight and useful:
   ```
   Keep responses concise. Lead with the answer, then explain if needed.
   ```

3. Tell them: "That rule is now in craft's rules.md. Because craft is global, it'll load in every session from now on — this folder, other folders, subagents, everywhere. You can edit it any time."

This is the moment they understand what craft does. Make it concrete.

## 4. Create a demo domain — context isolation

This is the other half of what bindle does: a domain bindle keeps its context — memories, notes, private terms — isolated to where it belongs. Craft's rules still apply (they're global), but the domain's own context stays separate.

Explain the contrast:

> "Craft follows you everywhere. But when you work for a company or a client, that context — their systems, their data, your notes about their codebase — should stay in its own place, not leak into personal projects or other clients. A domain bindle is that place."

1. Create a demo domain folder: `mkdir -p ~/onboard-demo` (or use the current folder if it's a reasonable project folder — ask).
2. Call the `new` tool: name=`demo`, at=`~/onboard-demo/.bindle`, sync=false.
3. Call `attach` with bindle=`demo`, folder=`~/onboard-demo`, writable=true. Also attach craft there read-only: call `attach` with bindle=`craft`, folder=`~/onboard-demo`.

Tell them: "Now ~/onboard-demo has its own domain bindle. Memories saved there stay in the demo bindle — they won't show up in craft or anywhere else. But craft's rules still load, because they're global."

Point out what this means in practice:
- "In a session in ~/onboard-demo: craft's rules apply, but memories go to the demo bindle."
- "In a session anywhere else: craft's rules apply, but the demo bindle's context is invisible."
- "If the demo bindle had private terms (company names, internal systems), promotion would catch them before anything leaves."

Then: "This demo folder is yours to delete any time — it's just to show how the pieces fit. When you start a real project or job, `bindle new` creates the real one."

## 5. Migration

Check quickly whether they have existing Claude Code memories. Look for `~/.claude/memory/` or the default memory folder for the current project directory.

- If memories exist, mention it briefly: "I see some existing Claude Code memories. Want to bring them into craft? I'll show you what's there and you pick what to keep." (Options: **Yes, let's look**, **Skip for now**)
- If yes: follow MIGRATION.md in the bindle repo. Inventory, show them, go step by step with approval.
- If skip or nothing found: move on without ceremony.

## 6. Remotes

For each bindle created (not cloned):

Ask: "Want to back up craft to a git remote so it syncs across machines? (A private repo on GitHub, GitLab, etc.)" (Options: **Yes — I'll set one up**, **Not now**)

- If yes: tell them to create a private repo, then give the commands. Bindle never adds a remote itself — give the commands and let them run them:
  ```
  git -C ~/bindles/craft remote add origin <their-url>
  git -C ~/bindles/craft push -u origin HEAD
  ```
  Once the remote is set, offer to enable sync (update `bindle.json` to set `"sync": true`) so memories auto-push.
- If not now: "No problem — you can add a remote any time. On another machine, clone it into place and attach it."

Don't ask about a remote for the demo bindle — it's disposable.

## 7. Wrap up

Call `doctor` to show the final state. Then give them something concrete to try — settings take effect next session, so this is how they see it all working:

> "Everything's set up. Here's how to see both pieces in action:
>
> 1. Start a new session in ~/onboard-demo — you'll see craft's rules load (they're global) and the demo bindle receiving memories.
> 2. Ask Claude to remember something ('remember that I prefer dark mode') — it goes into the demo bindle.
> 3. Start a session somewhere else — craft's rules still load, but the demo memory isn't there. That's context isolation: the demo's context stays in its domain.
>
> The demo folder is safe to delete when you're done. To create a real domain bindle for a job or client: `bindle new`."

End with: "As you work, lessons worth keeping across projects go into craft with `/bindle:promote`. Craft becomes your toolkit; domain bindles keep each context in its own place."

Link to the docs: "For the full picture — how promotion works, private terms, syncing across machines, migration — type `/bindle:docs`."
