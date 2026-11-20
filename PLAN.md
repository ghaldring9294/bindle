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
4. **The domain is the unit of sharing.** One sidecar repo per domain: a shared `memory/` that every project in the domain reads and writes (lessons learned in one repo apply in its siblings), plus `projects/<name>/` for repo-specific notes. For example, a work domain holding several repos, and a personal domain holding related side projects. A project that shares nothing with anything else (common for personal projects) is simply its own domain. In practice: two domains cover most needs (work and personal), plus one per standalone project. The native hook is `autoMemoryDirectory`: point each project in a domain at that domain's `memory/` (set in user or local settings, the right side of the boundary). Today's accidental version of this is starting Claude from a parent folder of several repos, which gives them one shared memory.
   - **Launch from the domain root.** Claude Code keys three things to the launch folder: memory (named after the path), sessions (`claude --resume` lists the current folder's sessions) and project permissions. Launching from a domain root aligns all three with the domain: cross-repo work without per-repo permission prompts, one resume list, one shared memory. That's why the habit formed in the first place. Bindle should make the root explicit; when a domain's repos are scattered (personal projects across machines), the root can be a folder of links, or rely on `autoMemoryDirectory`.
5. **Each sidecar lives with its projects' git.** Personal projects on personal git; work projects on the employer's git (a private repo in the work org). The base comes from personal git on every machine, because it holds no context.
6. **Tag every memory `boundary: craft | context | both`** as it's written. `both` means a general lesson learned on a specific problem: on migration, promote a rewritten general rule and leave the specifics behind.
7. **Migrate secure-first.** Move a mixed setup into the professional layer first, then promote craft to personal one piece at a time, reviewed memory by memory.
   - **Rebuild the personal principles from the live setup, not the July copy.** `bindle-personal/CLAUDE.personal.md` duplicates the working principles from July, and the live global `CLAUDE.md` has grown since (summaries of always-on rules, a lessons index, new sections). At migration, derive `CLAUDE.personal.md` from the current live file minus anything domain-specific, then delete the duplicate so there is one source.
   - **Skills can go into `bindle-personal/skills/` now**, hand-linked into `~/.claude/skills/` until the installer runs. First one: `doc-style` (Nov 2026), working through a symlink.

## Open questions

- **Memory transport.** July copied a layer's memory into `~/.claude/projects/<slug>/memory/`. That drifts: Claude writes new memories into that folder and the repo goes stale. Options:
  0. *(test first, found 2026-11-20)* The native **`autoMemoryDirectory`** setting (Claude Code v2.1.74+) moves auto-memory to an absolute path, so a project's memory can live directly in its sidecar checkout: no copy, no symlink, and it's how Claude Code is built. It's honoured in user and local settings, not committed project settings, by design, so a shared repo can't redirect someone's memory. Open bug reports say it's sometimes ignored (the system prompt still names the default path; `settings.local.json` not always read), so confirm on the installed version where a test memory actually lands.
  1. *(preferred if 0 fails)* The memory folder **is** a git checkout of the domain's memory repo: one copy, git is the sync.
  2. Copy, plus a Stop hook that syncs back and commits. Works, more moving parts.
  3. Symlink the folder into the layer repo. July notes say symlinks broke headless detail reads; re-test first, since it's the tidiest if it works now.

  Check what Claude Code currently supports for memory location before choosing.
- **Path-keyed memory.** Claude names a project's memory folder after its path on disk, so the same project at a different path on another machine gets a different folder. Each machine needs a setup step (`init-project`) that maps the sidecar to that machine's path.
- **Where do layer rules live** once memory is its own checkout: in the same repo as the memory, or beside it?
- **Skills first.** New general skills go straight into `bindle-personal/skills/` and get hand-linked until the overlay installer is in use. Candidates: doc style (living versus snapshot docs, one home per fact), a doc registry and drift audit, a QA handoff, PM meeting prep, a single pre-commit review step, a ship checklist.

## Prior art (quick search, 2026-11-20)

The problem is common; the trust-domain boundary is rarely the focus. Not vetted for maturity or security.

- **Claude Code itself** has no built-in memory sync. Feature requests ask for export/import or account sync and note that memory is keyed to absolute paths ([#25739](https://github.com/anthropics/claude-code/issues/25739)). The native lever is `autoMemoryDirectory` ([memory docs](https://code.claude.com/docs/en/memory)).
- **Sync everything to one private repo:** [claude-sync](https://github.com/renefichtmueller/claude-sync) (selective include/exclude), claude-brain ([write-up](https://dev.to/toroleapinc/i-built-a-tool-to-sync-your-claude-code-brain-across-machines-5a1o)), [git-based global memory](https://dev.classmethod.jp/en/articles/claude-code-global-memory-with-git), [hook-based pull/push](https://dev.to/fillip_kosorukov/keeping-claude-code-context-alive-across-a-desktop-a-laptop-and-a-vps-2epa). Portable, but one store: no boundary.
- **Closest to bindle:**
  - [dotai](https://pypi.org/project/dotai-cli): personal context in its own folder, never writes team files, repo-level instructions win over personal ones.
  - [dotagents](https://pkg.go.dev/github.com/yourconscience/dotagents): public tool and private config as separate repos (like base versus layer).
  - [agentic-stack](https://www.skills.sh/aradotso/ai-agent-skills/agentic-stack-portable-agent-memory): a portable `.agent/` folder with layered memory across tools.
  - [skills via chezmoi](https://dev.to/dotwee/one-skills-brain-for-codex-claude-cursor-and-copilot-with-chezmoi-2p3k): one skills source for several agents.
- **Separate config directories per life:** ["One Claude, two lives"](https://dev.to/charlieseay/one-claude-two-lives-1cmp) keeps work and personal on separate machines and data; others use a separate config dir (for example `~/.claude-work`, via `CLAUDE_CONFIG_DIR`). A hard boundary, but nothing carries craft across.
- **Team versus personal inside one repo:** [what's shared versus private on a team](https://medium.com/@binu_thayamkery/claude-code-on-a-team-whats-shared-what-s-private-and-how-not-to-step-on-each-other-11ebcea8d01c): `~/.claude/CLAUDE.md` is personal, the repo holds team rules.

**Review them properly before building** (each solves a slice; a cohesive design looks at all of it). Compare every tool on the same dimensions, borrow what's solved, and keep bindle's effort on what isn't:

| Dimension | Question |
| --- | --- |
| Memory transport | How does accumulated memory move between machines? Copy, sync, checkout, native setting? |
| Craft sharing | How do skills, agents and commands travel? Across agent tools (Claude, Codex, Cursor)? |
| Trust boundary | Is personal versus employer context separated, and is the separation structural or by convention? |
| Multi-machine | What happens with the same project at different paths, or a new machine? |
| Team coexistence | Does it stay out of team repos and shared settings? |
| Lifecycle | How are stale memories reviewed, promoted or retired? |
| Native fit | Does it use Claude Code's own mechanisms or work around them? |

**What bindle adds:** the boundary is structural (one repo per trust domain, so a wrong push can't cross), and craft versus context is decided per memory as it's written (`boundary:` tags), so methods travel while each domain's knowledge stays put. None of the above found does both.

## Next steps

1. Answer the memory transport question: test `autoMemoryDirectory` first (where does a test memory land?), then symlinks.
2. Write the first skills in `bindle-personal/skills/`.
3. Create the professional layer for the current employer on its git host; migrate secure-first.
4. Finish the overlay installer and install on one machine end to end.

## Log

- **2026-07-08 to 07-14:** base, personal layer, memory taxonomy, `bindle` CLI, README framing.
- **2026-11-20:** sidecar model, hosting rule, memory boundary tags, memory transport options (this file). Quick prior-art search: found `autoMemoryDirectory` (native memory location) and related tools; none combine a structural trust boundary with per-memory craft/context tagging.
