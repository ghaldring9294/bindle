# Plan

Where bindle stands, what's decided, and what's open. Update this when a decision changes; append to the log at the bottom.

## Where it stopped (July 2026)

- **Base (this repo):** installer, the `bindle` CLI (`init-layer`, `init-project`), tiered retrieval and the memory taxonomy. Largely done.
- **Personal layer (`bindle-personal`):** scaffolded, with an overlay installer and the `/ticket` workflow. `skills/` and `agents/` are empty.
- **Professional layers:** designed (`init-layer <name> --scope professional`), never created for a real employer.
- **Not installed** on the main work machine; `~/.claude` there is still the "mixed" setup MIGRATION.md describes.

## Goal

Carry craft between personal and work, in both directions, without crossing the context boundary. Build skills anywhere (hackathons, meetups, side projects), sync them to the personal layer, and use them at work next to work context. Never rebuild a setup from scratch on a new machine.

## Decisions (2026-11-20)

1. **Craft versus context is the line.** Craft is how I work: methods, skills, habits, lessons about working with Claude. Context is what an employer or project knows: its systems, data, people, decisions. Craft travels both ways; context stays in its domain.
2. **Work with how Claude Code is built, not against it.** Plain Claude Code underneath; no custom loading mechanism where a native one exists.
3. **The model is sidecars.** Plain Claude Code, plus a personal sidecar (craft, always on), plus a project sidecar per project (that project's memory and private `.claude-local` notes, git-versioned). Any machine with access to a project pulls its setup.
4. **One sidecar repo per trust domain, with a folder per project** (the `projects/<name>/` layout). A repo per project only when that project's access differs from the rest of its domain.
5. **Each sidecar lives with its projects' git.** Personal projects on personal git; work projects on the employer's git (a private repo in the work org). The base comes from personal git on every machine, because it holds no context.
6. **Tag every memory `boundary: craft | context | both`** as it's written. `both` means a general lesson learned on a specific problem: on migration, promote a rewritten general rule and leave the specifics behind.
7. **Migrate secure-first.** Move a mixed setup into the professional layer first, then promote craft to personal one piece at a time, reviewed memory by memory.

## Open questions

- **Memory transport.** July copied a layer's memory into `~/.claude/projects/<slug>/memory/`. That drifts: Claude writes new memories into that folder and the repo goes stale. Options:
  1. *(preferred)* The memory folder **is** a git checkout of the domain's memory repo: one copy, git is the sync.
  2. Copy, plus a Stop hook that syncs back and commits. Works, more moving parts.
  3. Symlink the folder into the layer repo. July notes say symlinks broke headless detail reads; re-test first, since it's the tidiest if it works now.

  Check what Claude Code currently supports for memory location before choosing.
- **Path-keyed memory.** Claude names a project's memory folder after its path on disk, so the same project at a different path on another machine gets a different folder. Each machine needs a setup step (`init-project`) that maps the sidecar to that machine's path.
- **Where do layer rules live** once memory is its own checkout: in the same repo as the memory, or beside it?
- **Skills first.** New general skills go straight into `bindle-personal/skills/` and get hand-linked until the overlay installer is in use. Candidates: doc style (living versus snapshot docs, one home per fact), a doc registry and drift audit, a QA handoff, PM meeting prep, a single pre-commit review step, a ship checklist.

## Next steps

1. Answer the memory transport question (test symlinks, check Claude Code's current options).
2. Write the first skills in `bindle-personal/skills/`.
3. Create the professional layer for the current employer on its git host; migrate secure-first.
4. Finish the overlay installer and install on one machine end to end.

## Log

- **2026-07-08 to 07-14:** base, personal layer, memory taxonomy, `bindle` CLI, README framing.
- **2026-11-20:** sidecar model, hosting rule, memory boundary tags, memory transport options (this file).
