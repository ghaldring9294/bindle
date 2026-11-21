# Plan

Where bindle stands, what's decided, and what's open. Update this when a decision changes; append to the log at the bottom.

## Where it stands (2026-11-21)

- **Base (this repo):** the `bindle` CLI in Python (standard library, 3.9+): `install`, `new`, `attach`, `detach`, `doctor`. A bindle template in `templates/bindle/`. 22 unit tests with a fake `claude`, plus `tests/e2e.sh` against the real CLI (passed: read-only personal memory and skill visible in a work folder, new memories written to the writable bindle only, gone after detach). July's `init-layer`, `init-project`, overlay installer, global CLAUDE.md/settings and memory taxonomy are removed (git history keeps them).
- **Personal (`bindle-personal`):** in the bindle layout, matching the template; `doc-style` skill and `/ticket` command. Memory empty until migration.
- **Personal laptop done (2026-11-21):** both repos cloned, personal attached writable, the laptop's memories migrated and pulled on the work machine. Sync now automatic for personal. Not attached on the work machine yet; the Acme bindle waits for a new work laptop.

## Goal

Carry craft between personal and work, in both directions, without crossing the context boundary. Build skills anywhere (hackathons, meetups, side projects), sync them to the personal layer, and use them at work next to work context. Never rebuild a setup from scratch on a new machine.

## The model (2026-11-21)

One tool, many bindles. This supersedes decision 3's sidecar wording below.

- **The base (`bindle`)** is tooling only: create a bindle, attach it to a folder, promote craft between bindles. No context; lives on personal git.
- **A bindle** is one domain's layer, in its own repo on that domain's git. Every bindle has the same shape; there is no special "personal" type. Personal is just the bindle that's mine, the way a freelancer would have one per client.
  ```
  <bindle>/
    .claude-plugin/        plugin.json + marketplace.json (the bindle is its own marketplace)
    skills/ agents/ commands/ hooks/
    rules.md               the domain's standing instructions
    memory/                auto-memory: MEMORY.md index + one file per memory
    notes/                 tickets, artifact index, TODO
    projects/<repo>/       per-project sidecar (later)
  ```
- **Toggling happens per launch folder,** not mid-session. A folder (a domain root, such as `~/acme`) attaches bindles in its `.claude/settings.local.json`. Switching clients means launching from another folder, which also separates session lists and permissions. That's a feature: the boundary is the folder.
- **Every attached bindle is on; exactly one is writable.** Attaching a bindle to a folder (once, with `bindle attach <bindle> <folder>`) turns it on whenever Claude launches from that folder: its skills, hooks and memory all load. The **writable** bindle is the one new memories are written to, and its notes and rules are this folder's. The others are read-only there. At `~/acme`, both bindles are on and Acme is writable; in personal projects, personal is writable.
- **One writable memory per session enforces the boundary.** A work session can't write into the personal repo. Craft moves between bindles only through promotion: a reviewed step, run from a folder where the *target* bindle is writable, that reads the source's `boundary: craft | both` memories and proposes general rewrites one by one. It's a skill (`bindle:promote`), with the CLI for the deterministic parts.

### Build decisions (2026-11-21)

- **A bindle is marked by `bindle.json`** (`name`, `layout`), so tools can tell a bindle from any other plugin and migrate old layouts later.
- **Each bindle carries its own copy of the managed files** (`hooks/print-memory.sh`, `hooks/hooks.json`), byte-identical to the base template, so a bindle works on a machine without the base. `bindle doctor` flags a copy that drifted.
- **A local plugin runs in place:** `CLAUDE_PLUGIN_ROOT` is the bindle's own folder, not a cache (verified), so edits take effect at the next session and the hook can compare paths directly.
- **`detach` leaves the marketplace declared** in the folder's settings; removing a marketplace in Claude Code is machine-wide and would break other folders.
- **`attach` refuses a folder inside another git repo**, since Claude Code would write the settings at that repo's root.
- **Sync lives in each bindle's hooks** (opt-in, `"sync": true`). SessionStart pulls (and pushes commits a killed session left behind), then prints the memory index: one script, because hooks for the same event run in parallel. SessionEnd commits only `memory/`, and only in the writable bindle, then rebases and pushes. It never blocks a session; failures go to `.git/bindle-sync.log` and `doctor`. A memory matching a credential pattern is never committed (a pushed secret can't be taken back). `notes/` doesn't sync automatically. Verified end to end: a headless session's memory reached the remote at SessionEnd.
- **`install` only links** the CLI onto PATH and `/bindle` into `~/.claude/commands`. bindle never takes over `~/.claude`'s settings or CLAUDE.md.

### How each part loads (verified 2026-11-21, Claude Code v2.1.329)

| Part | Native mechanism | How it's toggled | Verified |
|---|---|---|---|
| Skills, agents, commands, hooks, MCP servers | The bindle is a **plugin**, installed from its own repo used as a marketplace (local directory or private git URL) | `claude plugin install <b>@<b> --scope local` writes `enabledPlugins` (and the marketplace) into the folder's `settings.local.json`; personal can be user scope if it should be on everywhere | Spike: the skill and SessionStart hook were active in the attached folder and absent in a sibling. Skills are namespaced (`<bindle>:<skill>`) |
| Writable memory | `autoMemoryDirectory` (absolute or `~/`) | Folder's `settings.local.json` | Spike: the session reported that path as its memory dir, wrote there, nothing in the default location; a fresh session recalled it |
| Read-only memory (other bindles that are on) | The bindle plugin's own SessionStart hook prints `${CLAUDE_PLUGIN_ROOT}/memory/MEMORY.md` | Comes with the plugin | Spike: recalled in the attached folder. Hook output is capped at **10,000 characters** (today's work index is ~15.6k), so read-only indexes stay small or the hook prints only `boundary: craft` lines |
| Rules | Plugins can't carry a CLAUDE.md. Personal rules: `~/.claude/CLAUDE.md` (user scope, loads everywhere). Domain rules: the domain root's `CLAUDE.md`, importing `@<bindle>/rules.md` | Which folder you launch from | Docs: imports outside the working directory show a one-time approval dialog. In the spike (headless) a project CLAUDE.md with an external import loaded nothing; recheck interactively |
| Notes | Plain folders | Inside the launch folder, or `--add-dir` | Not tested; nothing special needed |
| Per-project sidecar | `CLAUDE.local.md` (supported, gitignored) importing `@<bindle>/projects/<repo>/…` | Per repo | Docs only |

**Constraints found:**
- `settings.local.json` is read at the **git repo root** even when launching from a subfolder. A domain root must not itself be a git repo that contains the project repos as subfolders, or every repo needs its own attach. (`~/acme` isn't a git repo, so it works as a root.)
- A local-scope install still records the plugin at machine level (`~/.claude/plugins/`); "local" decides where it's enabled, not where it's cached. Each machine runs the attach once (the path-keyed setup step).
- MEMORY.md loads only its first 200 lines or 25 KB. Topic files load on demand.
- SessionStart hooks run again on resume. Output is capped at 10,000 characters with no setting to raise it.

**Where bindles live on disk:** by default inside the domain root (`<root>/.bindle/`), so its rules import and notes sit inside the working directory with no external-import dialog. Overridable (`bindle attach --at <path>`). An optional `~/bindles/` folder of symlinks gives a collective view; `bindle doctor` lists them. Roots are just paths: bindle requires no folder layout. Here, `~/acme` and `~/Projects` are already the two domain roots. Kept local first; push the work bindle to the work org later.

**Don't move existing folders.** Path-keyed today: Claude's memory folder and session history, trust in `~/.claude.json`, Docker/Sail mounts, git worktrees, symlinks into `~/Projects`. Migrating memory into `<root>/.bindle/memory/` removes the biggest of these, so migrate first and reorganize later, if ever.

**Read-only memory cap:** 10,000 characters is fine for now; revisit if an index outgrows it.

**Notes cross boundaries the way memories do.** Most notes are domain context and stay in the domain bindle. A note that's really craft (process ideas, a workflow roadmap) is promoted to personal like a memory: rewritten without the domain's specifics.

## Decisions (2026-11-20)

1. **Craft versus context is the line.** Craft is how I work: methods, skills, habits, lessons about working with Claude. Context is what an employer or project knows: its systems, data, people, decisions. Craft travels both ways; context stays in its domain. Work may appear in personal only at a high, public level (the job, interests, product ideas); never code-heavy or internal knowledge (repos, systems, data, internal decisions, people). Promotion and migration apply this test.
2. **Work with how Claude Code is built, not against it.** Plain Claude Code underneath; no custom loading mechanism where a native one exists.
3. *(Superseded by "The model", 2026-11-21.)* **The model is sidecars.** Plain Claude Code, plus a personal sidecar (craft, always on), plus a project sidecar per project (that project's memory and private `.claude-local` notes, git-versioned). Any machine with access to a project pulls its setup.
4. **The domain is the unit of sharing.** One sidecar repo per domain: a shared `memory/` that every project in the domain reads and writes (lessons learned in one repo apply in its siblings), plus `projects/<name>/` for repo-specific notes. For example, a work domain holding several repos, and a personal domain holding related side projects. A project that shares nothing with anything else (common for personal projects) is simply its own domain. In practice: two domains cover most needs (work and personal), plus one per standalone project. The native hook is `autoMemoryDirectory`: point each project in a domain at that domain's `memory/` (set in user or local settings, the right side of the boundary). Today's accidental version of this is starting Claude from a parent folder of several repos, which gives them one shared memory.
   - **Launch from the domain root.** Claude Code keys three things to the launch folder: memory (named after the path), sessions (`claude --resume` lists the current folder's sessions) and project permissions. Launching from a domain root aligns all three with the domain: cross-repo work without per-repo permission prompts, one resume list, one shared memory. That's why the habit formed in the first place. Bindle should make the root explicit; when a domain's repos are scattered (personal projects across machines), the root can be a folder of links, or rely on `autoMemoryDirectory`.
5. **Each sidecar lives with its projects' git.** Personal projects on personal git; work projects on the employer's git (a private repo in the work org). The base comes from personal git on every machine, because it holds no context.
6. **Tag every memory `boundary: craft | context | both`** as it's written. `both` means a general lesson learned on a specific problem: on migration, promote a rewritten general rule and leave the specifics behind.
7. **Migrate secure-first.** Move a mixed setup into the professional layer first, then promote craft to personal one piece at a time, reviewed memory by memory.
   - **Rebuild the personal principles from the live setup, not the July copy.** `bindle-personal/CLAUDE.personal.md` duplicates the working principles from July, and the live global `CLAUDE.md` has grown since (summaries of always-on rules, a lessons index, new sections). At migration, derive `CLAUDE.personal.md` from the current live file minus anything domain-specific, then delete the duplicate so there is one source.
   - **Skills can go into `bindle-personal/skills/` now**, hand-linked into `~/.claude/skills/` until the installer runs. First one: `doc-style` (Nov 2026), working through a symlink.

## Open questions

- **Memory transport.** *(Answered 2026-11-21: option 0 works on v2.1.329; see "How each part loads". The bindle's `memory/` is a git checkout, so git is the sync.)* July copied a layer's memory into `~/.claude/projects/<slug>/memory/`. That drifts: Claude writes new memories into that folder and the repo goes stale. Options:
  0. *(test first, found 2026-11-20)* The native **`autoMemoryDirectory`** setting (Claude Code v2.1.74+) moves auto-memory to an absolute path, so a project's memory can live directly in its sidecar checkout: no copy, no symlink, and it's how Claude Code is built. It's honoured in user and local settings, not committed project settings, by design, so a shared repo can't redirect someone's memory. Open bug reports say it's sometimes ignored (the system prompt still names the default path; `settings.local.json` not always read), so confirm on the installed version where a test memory actually lands.
  1. *(preferred if 0 fails)* The memory folder **is** a git checkout of the domain's memory repo: one copy, git is the sync.
  2. Copy, plus a Stop hook that syncs back and commits. Works, more moving parts.
  3. Symlink the folder into the layer repo. July notes say symlinks broke headless detail reads; re-test first, since it's the tidiest if it works now.

  Check what Claude Code currently supports for memory location before choosing.
- **Path-keyed memory.** Claude names a project's memory folder after its path on disk, so the same project at a different path on another machine gets a different folder. Each machine needs a setup step (`init-project`) that maps the sidecar to that machine's path.
- **Where do layer rules live** once memory is its own checkout: in the same repo as the memory, or beside it?
- **Skills first.** New general skills go straight into `bindle-personal/skills/` and get hand-linked until the overlay installer is in use. Candidates: doc style (living versus snapshot docs, one home per fact), a doc registry and drift audit, a QA handoff, PM meeting prep, a single pre-commit review step, a ship checklist.

## Adopted from July

July's tracker (kept locally as an archive) reached the same model: every layer the same shape, personal just the always-on one. What it couldn't do natively, it built (a symlink farm, per-layer installers, memory copying); plugins and `autoMemoryDirectory` now replace those. These July ideas still hold:

- **Identify a project by its git remote, not its path.** The remote (`host/owner/name`) picks the project's notes folder in `projects/`, so the same repo at a different path or on another machine finds the same notes. The path stays only for what Claude Code itself keys to it (sessions, trust).
- **Enforce the boundary in code, not by care.** A pre-push check in each bindle that refuses content from another domain (a denylist of domain terms, kept in machine-local settings, never in the base), a remote allowlist so a bindle can only push to its own domain's git host, and a pre-commit check that blocks committing a project's private files (`CLAUDE.local.md`, sidecar links) into a team repo.
- **A skill plus a domain addendum.** A general skill lives in personal; a short addendum in a domain bindle tailors it with that domain's specifics (for example, `doc-style` in personal and SP's doc registry as an SP addendum). Craft stays general; context stays home. Decide how an addendum loads (a skill that references the base one, or a file the base skill looks for).
- **Freshness stamps for derived docs.** Record the commit a doc was built from and the sources it read; `git diff --name-only <commit>..HEAD -- <sources>` says whether it's stale and which part to recheck. Same idea as doc-style's registry and drift audit, found twice.
- **Use Claude Code's native memory format.** Flat `MEMORY.md` index plus one file per memory with `type:` frontmatter, plus bindle's `boundary:` tag. Retire the base's July taxonomy template (type folders): the July A/B showed no quality or cost win, and forcing one structure across projects isn't a goal. A different view of the memories is a derived doc, made on request.
- **Practical craft to carry** (candidates for personal, as needed): an idempotent MCP bootstrap script (`claude mcp add --scope user`, no secrets), secrets handling (`${VAR}` from a gitignored `secrets.env`, which is still how this machine works), and an adversarial review skill.

Left behind: the memory A/B harness and its results; the cost ledger and statusline already live in their own repos.

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

1. ~~Answer the memory transport question.~~ Done 2026-11-21 (spike).
2. Settle the open design points in "The model" (rules loading interactively, the read-only memory cap, where bindles live).
3. ~~Reshape `bindle-personal` into the bindle layout.~~ Done 2026-11-21.
4. ~~Base CLI: `new`, `attach`, `detach`, `doctor`.~~ Done 2026-11-21. `sync` and automatic sync hooks done too. Still to build: the `promote` skill, the `~/bindles/` collective view, and a cleanup pass on personal's migrated memories (keep, move to `projects/<name>/`, archive, or delete).
4a. ~~**Test on the personal laptop.**~~ Done 2026-11-21. clone `bindle` and `bindle-personal`, `bindle install`, attach personal to a projects folder as writable, migrate that laptop's own memories into it (MIGRATION.md), check `bindle doctor` and a fresh session.
5. Create the Acme bindle and migrate secure-first: on the next work laptop (no rush on this one).
6. **Scenario docs with practical examples** (`docs/scenarios.md`), written as the CLI lands so they describe real behaviour. Made-up companies; each scenario shows the folders, what's on, what's writable, and the commands:
   - **Employee:** personal and Acme both on at `~/acme`, Acme writable.
   - **Freelancer:** clients Acme and Globex in separate folders. Personal is on in both, the client is writable, and switching clients means launching from the other folder.
   - **Side project:** personal on and writable, nothing else.
   - **A client that allows no outside tooling:** Initech's folder has only Initech on.
   - **Promoting a lesson:** learned at Acme, carried into personal with `bindle:promote` from a folder where personal is writable.
   - **Hackathon skill:** built in personal on Saturday, used at Acme on Monday.
   - **New machine:** clone the bindles, run `attach` once per folder.
   - **Per-project notes:** private notes about Acme's `api` repo, loaded through its `CLAUDE.local.md`.

## Log

- **2026-07-08 to 07-14:** base, personal layer, memory taxonomy, `bindle` CLI, README framing.
- **2026-11-20:** sidecar model, hosting rule, memory boundary tags, memory transport options (this file). Quick prior-art search: found `autoMemoryDirectory` (native memory location) and related tools; none combine a structural trust boundary with per-memory craft/context tagging.
- **2026-11-21:** one model for all bindles (personal is just mine), attached per folder as home (one, writable memory) or companion (tooling plus read-only memory); promotion as a skill. Spike on v2.1.329 confirmed `autoMemoryDirectory` in local settings, plugin skills and hooks enabled per folder, and companion memory via the plugin's SessionStart hook (10k-character cap). External `@imports` from a project CLAUDE.md didn't load headless; recheck interactively.
- **2026-11-21:** renamed home/companion to on/writable: every attached bindle is on, one is writable. Attach per folder rather than user scope, so a bindle can be off in a folder that doesn't want it.
- **2026-11-21:** reshaped `bindle-personal` into the bindle layout (plugin, memory hook, `rules.md`). Reviewed July's PROJECT.md (archived locally): adopted git-remote identity, code-enforced boundary guards, skill addendums, freshness stamps and the native memory format; left the A/B behind.
- **2026-11-21:** built the CLI (`install`, `new`, `attach`, `detach`, `doctor`) and the bindle template; removed July's commands and templates; personal brought in line with the template. Unit and end-to-end tests pass.
- **2026-11-21:** memory sync: session hooks in each bindle (pull at start, commit `memory/` and push at end, secret check), `bindle sync`, `bindle new --sync`. Personal on sync. Tests: 31 unit, end to end with real Claude Code.
