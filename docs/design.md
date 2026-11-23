# bindle design

bindle keeps one git repo per domain (you, an employer, each client), shaped as a Claude Code plugin, and lets each folder you start Claude Code from turn on the domains it needs, with exactly one of them receiving new memories. This document explains why it works that way. For how to use it, see the [README](../README.md); for what changed in each version, the [CHANGELOG](../CHANGELOG.md).

Contents: [Problem](#the-problem) · [Principles](#principles) · [Model](#the-model) · [How each part loads](#how-each-part-loads) · [Memory and sync](#memory-and-sync) · [Promotion](#promotion) · [Safety and its limits](#safety-and-its-limits) · [Implementation](#implementation-decisions) · [Claude Code constraints](#claude-code-constraints) · [Rejected](#considered-and-rejected) · [Prior art](#prior-art) · [Later ideas](#later-ideas)

## The problem

A Claude Code setup accumulates two kinds of value. **Craft** is how you work: skills, habits, methods, lessons about working with Claude. **Context** is what a domain knows: its systems, data, people and decisions. Craft should travel everywhere you go, in both directions: something learned at a weekend hackathon should help at work on Monday, and a method refined at work should come home. Context must stay in its domain: an employer's internals don't belong in your personal repo, and one client's knowledge never belongs in another client's folder.

Out of the box, Claude Code keeps memory per folder path on one machine, keeps skills and instructions in one global place, and has no notion of domains. Moving to a new machine means rebuilding, and keeping work and personal apart means care rather than structure.

## Principles

1. **Craft versus context is the line.** Craft travels; context stays in its domain. Work may appear in a personal bindle at a high, public level (the job, interests, product ideas), never as internal knowledge.
2. **Work with how Claude Code is built.** Use its own mechanisms (plugins, `autoMemoryDirectory`, hooks, permission rules) rather than a custom loader. bindle should stay a thin layer that would be easy to remove.
3. **Guardrails, not gates.** The person has direct access to every repo, so they're the one truly enforcing the boundary. bindle makes the right thing the default and mistakes visible. It stops hard only where a mistake can't be undone: a pushed secret, or material crossing between bindles without review. Everything recoverable gets a rule or a warning.
4. **One shape for every bindle.** There's no special personal type. Personal is just the bindle that's yours, the way a freelancer has one per client. A bindle's behaviour comes from two properties and from where it's attached, not from its kind.
5. **The tool holds no hidden state.** The facts live in each bindle (`bindle.json`, its manifests), in each folder's settings, and in Claude Code's own plugin state. `bindle` reads them when it runs, and the tool's repo can be public without learning anything about your domains. The one index is `~/bindles/registry.json`, a plain file mapping the names of bindles that live elsewhere (domain bindles) to their paths, so any of them can be found by name from any folder, and recording which folders have a writable bindle (for the session check). It's the single source for where bindles are, `new` and `attach` keep it current, and it's only an index: lose it and attaching each bindle again rebuilds it.
6. **Secure-first migration.** When moving an existing mixed setup, everything goes into the most restrictive domain first; general pieces are promoted out afterwards, one reviewed item at a time.

## The model

**A bindle** is one domain's git repo:

```
bindle.json            name, layout, sync, audience, writes
.claude-plugin/        plugin.json + marketplace.json: the bindle is its own one-plugin marketplace
skills/ commands/ agents/
hooks/                 managed by bindle (bindle_hook.py, hooks.json)
memory/                MEMORY.md index + one file per memory
projects/<project>/    memories and notes about one project, with their own index.md
notes/                 notes; notes/scratch/ is ignored by git
rules.md               standing instructions
private-terms.txt      names that must never leave this bindle
outbox/                approved items waiting for a target on another machine
```

**A folder turns bindles on.** Attaching a bindle to the folder you launch Claude Code from writes that folder's `.claude/settings.local.json`. Every attached bindle is **on** there: its skills, hooks, rules and memory index load. At most one is **writable**: new memories are saved into its `memory/`. The rest are **read-only** and locked against Claude's editing tools. Switching domains means starting Claude Code from a different folder, which also separates session histories and permissions. The folder is the boundary, and nothing toggles mid-session.

**One writable bindle per folder** is the core structural decision. Every new memory has exactly one destination, so a work session can't save work context into your personal bindle by mistake, and nothing has to decide where each memory goes.

**Two properties per bindle**, in `bindle.json`:

| Property | Values | Meaning |
|---|---|---|
| `audience` | `private`, `shared`, `public` | Who the bindle is for (visibility itself is the git host's setting) |
| `writes` | `implicit`, `explicit` | `implicit` bindles can be a folder's writable bindle; `explicit` ones receive material only through promotion |

| Bindle | audience | writes |
|---|---|---|
| Personal | private | implicit |
| An employer or client | private | implicit |
| Craft (finished, general tooling to share) | shared or public | explicit |

**Projects are organization, not boundaries.** A domain usually spans several repos, so memories live at the lowest level that covers everything they're about: only one project means `projects/<project>/`; spanning projects, or domain-wide, means `memory/`. A project's index may point to a domain memory rather than copy it. Projects have no attach, writable flag or lock of their own.

**Collaborators keep their own bindles.** Working with someone, each person has their own bindles, and whatever matters to both goes into the project repo itself (its `CLAUDE.md`, docs), as reviewed commits. bindle stays one person's layers.

## How each part loads

All verified against Claude Code v2.1.329.

| Part | Mechanism |
|---|---|
| Skills, commands, agents | The bindle is a plugin. `attach` runs `claude plugin marketplace add <bindle> --scope local` and `claude plugin install <name>@bindle-<name> --scope local`, which declare and enable it in the folder's settings. Names get the prefix `<name>:`. |
| Hooks | The plugin's `hooks/hooks.json` runs `bindle_hook.py` at SessionStart (twice: session text, and rules, so each has its own output cap) and SessionEnd |
| Writable memory | `autoMemoryDirectory` in the folder's settings points to the bindle's `memory/`; Claude Code loads its `MEMORY.md` and writes new memories there |
| Read-only memory | The bindle's SessionStart hook prints its `MEMORY.md` into the session |
| Rules | The bindle's SessionStart hook prints `rules.md`, framed as standing instructions. Plugins can't carry a `CLAUDE.md`, and imports from outside the launch folder wait for an approval prompt, so a hook is the one mechanism that works for every bindle without prompts or edits to a folder's own `CLAUDE.md` |
| Notes | Not loaded. The writable bindle's session start says where they are |
| MCP servers | The plugin's `.mcp.json`. Claude Code starts the servers where the plugin is on, expands `${ENV_VAR}` from the machine and `${CLAUDE_PLUGIN_ROOT}` to the bindle, and names tools `mcp__plugin_<bindle>_<server>__<tool>`. Secrets stay per machine as environment variables |
| Read-only lock | `permissions.deny` gets `Edit(//<bindle path>/**)`. An Edit rule covers all of Claude's file-editing tools; Claude Code ignores `Write(path)` rules |

A plugin installed from a local directory runs in place: `CLAUDE_PLUGIN_ROOT` is the bindle's own folder, not a cache. Edits take effect at the next session.

## Memory and sync

**Sync** is opt-in per bindle (`"sync": true`) and lives in the bindle's own hooks, so it works on any machine where the bindle is attached, with or without the bindle tool installed.
- **Session start:** in the writable bindle, first commit and push memories an earlier session left (closing the app or killing a terminal can skip SessionEnd); then pull with fast-forward only. A read-only bindle is only pulled, never pushed: its unpushed commits are someone's unfinished work.
- **Session end, in the writable bindle only:** commit `memory/`, `projects/` and `outbox/` and push. Only if the remote moved does it rebase onto it, and never over uncommitted changes to tracked files (an autostash could leave conflict markers in a note); it stops and says so instead. Without a remote it commits locally.
- **Never blocks a session.** Each pull or push gives up after a few seconds (HTTP on a stalled transfer, SSH on a slow connect, unless the repo sets its own `core.sshCommand`). Failures go to the bindle's sync log (`git rev-parse --git-path bindle-sync.log`) marked `problem:`; the next session start shows them in the terminal, and `doctor` reports them, along with unresolved conflicts and a leftover autostash. Sync skips while a merge or rebase is in progress.
- **Indexes merge by union.** Two machines adding memories both append to `MEMORY.md`; `.gitattributes` uses git's union driver for `memory/MEMORY.md` and `projects/*/index.md`, so both lines survive instead of stopping the rebase.
- **Secrets are held back.** A changed file that matches a credential pattern isn't committed, because a pushed secret can't be taken back; the other files still sync, so one false match doesn't stop every memory. Before pushing, sync also checks every file in the outgoing commits, so a secret committed by hand doesn't leave either. The check is case-insensitive, matches keywords inside longer names, knows common token formats, and ignores placeholders like `${VAR}`.
- **Only `memory/`, `projects/` and `outbox/` commit automatically** (`projects/` holds most memories, which are about one project). Skills, rules and notes are deliberate work, so automatic sync never ships something half-finished. The session start reminds the person about uncommitted work, and flags a note that looks like it holds a secret before it's committed.

## Promotion

Promotion is the only way bindle moves material between bindles, and it has to cross as text the person approved as general.

1. **Draft, in the source domain's session.** The `/bindle-promote` skill drafts a general rewrite of a memory tagged `boundary: craft` or `both` (or a skill or command), shows it beside the original, and asks where it should go. The session knows its own domain, so it's the right place to separate the lesson from the specifics.
2. **Place it, which is code with no judgment.** On approval, `bindle promote <source> <draft> --into <target> --name <name>` checks the draft against the source's `private-terms.txt` (in its name, description, file names and contents) and for credentials, refuses symlinks, confirms the destination is free, copies it into the target, adds an index line for a memory and commits the target. It's a shell command, so Claude Code's permission prompt shows exactly what moves. The original stays in the source; a second target is a second promotion. A private term in the draft stops it and shows where; the person can allow that term for that promotion (`--allow`), because the check exists to make crossing intentional, not to forbid it (the person has full access to both bindles anyway). A possible secret can't be allowed: once pushed, git history can't take it back. An update to something already in the target needs `--replace`, so nothing is overwritten by accident; `--dry-run` prints the diff the person approves, and the old version stays in the target's history.

**When the target isn't on this machine,** the approved draft waits instead: `bindle outbox add` runs the same checks, stores it in the source's `outbox/` and records a SHA-256 of the approved content. The outbox syncs with the source, so on the machine where the target lives, `bindle collect` treats it as untrusted input: it refuses anything that isn't approved, has changed since approval (the hash), points outside its own folder, or contains links, runs the checks again, places it like `promote`, and removes it from the outbox. An outbox normally sits empty; anything in it is waiting to go somewhere.

**Notes for another domain.** A reminder or todo for another domain, thought of while working in this one, is promoted as a `note`: the same checks, then appended to the target's `notes/inbox.md` with the date and the source's name, rather than placed in its memory. The target's next session start shows how many are waiting, as a visible message: hook text reaches only Claude, which can't speak before the person does. Notes cross the same way as everything else because they're the likeliest place for this domain's specifics to slip into another.

No session reads another domain's raw memories; only outboxes are read across bindles, and they hold only reviewed text. A craft bindle receives material only this way.

The leak check is only as good as the term list. `bindle terms` suggests candidates from the domain folder (code finds the names its repos reveal; the person judges which are private), and `doctor` warns when the writable bindle has none. It's a warning, not a refusal, because a personal bindle may have nothing private.

## Safety and its limits

| Guard | Covers | Doesn't cover |
|---|---|---|
| One writable bindle per folder | Where new memories go | What a session chooses to write into the writable bindle |
| Read-only lock | Claude's file-editing tools | Shell commands. Claude Code also refuses attempts to work around the lock that way, and bindle doesn't rely on it |
| Promotion (promote, outbox and collect) | Material moved between bindles by bindle | Text a session copies from a read-only bindle's visible memories into its writable bindle's memories |
| Private terms | Names you listed | Names you didn't list. It's a backstop, not a guarantee |
| Secret check | Common credential formats in files that would be committed | Novel formats; anything in ignored files (which never leave the machine) |
| Enclosing-repo exclude | A bindle inside a project repo being committed by `git add -A` there | A bindle deliberately tracked there (`doctor` warns) |
| Trust warnings | Code a read-only bindle runs beyond bindle's own hooks (extra hooks, servers, executables), and pulls that change such code | Instructions in skills and rules, which are trusted like any plugin's |

A read-only bindle is **visible, not sealed**: its rules and memory index are shown in sessions where it's attached. So attach a bindle only to folders whose domain may see it. That's why a personal bindle stays off at work, and a craft bindle holds only general material.

## Implementation decisions

- **Portable by construction.** Hooks run through `hooks/run`, a small bash script that picks a working Python (Claude Code runs hook commands in Git Bash on Windows, which git brings). Lock rules use Claude Code's POSIX path form, where Windows drives become `/c`. Files are always written UTF-8 with LF, and `.gitattributes` keeps them LF on Windows checkouts, since CRLF breaks bash scripts and made git misread `.gitignore`. On Windows, Claude Code reads `settings.local.json` in the launch folder rather than at the repo root.
- **One implementation.** `templates/bindle/hooks/bindle_hook.py` runs the hooks and holds the writable check, sync and the secret check. The CLI imports it from the template, so the two can't disagree. It reads settings as JSON and compares resolved paths. An earlier version had bash hooks beside a Python CLI; they disagreed on paths with accents and on non-ASCII file names.
- **Managed files are byte-identical copies.** Each bindle carries `hooks/bindle_hook.py` and `hooks/hooks.json`, so it works on a machine without the bindle tool. `doctor` flags a copy that differs, and `upgrade` replaces it.
- **`upgrade` never overwrites a bindle's own files.** It replaces managed files, removes obsolete ones, adds template files a bindle lacks, appends missing template lines to `.gitignore` and `.gitattributes`, stamps the layout version, and commits only what it touched.
- **A locked bindle is upgraded by the person.** Where a bindle is read-only, Claude can't change it, including through `bindle upgrade` in the shell. `doctor` prints the exact command to run.
- **`bindle.json` marks a bindle** and carries a layout number, so tools can tell a bindle from any other plugin and migrate old layouts.
- **`attach` refuses a folder inside another git repo,** because Claude Code reads `settings.local.json` at the repo root.
- **`detach` leaves the marketplace declared,** because removing a marketplace in Claude Code is machine-wide and would break other folders.
- **`bindle new` inside a project repo** adds the bindle to that repo's `.git/info/exclude`, never the team's `.gitignore`.
- **`install` only links,** the CLI onto `PATH`, and `/bindle` and `/bindle-promote` into `~/.claude`, unless the person opts into the session check: one user-level SessionStart hook in `~/.claude/settings.json`, added and removed by `install` without touching anything else there. bindle never takes over `CLAUDE.md`.
- **The session check warns only inside domains.** Claude Code doesn't read a parent folder's settings, so a session started in a repo inside a domain folder misses the domain's bindle and writes memories to the default folder. The check warns there and nowhere else: a warning in every folder without a bindle (home, downloads, a cloned project) would be skipped, including the one time it matters. Domain folders are the ones attached writable, recorded under `domains` in the registry by `attach` and removed by `detach`.
- **The session check also says when bindle needs updating,** in any folder, because it appears only while something is due: a newer release tag than this copy (pull, then upgrade), or a bindle whose managed files differ from the template. Nobody pulls a tool unprompted, and after a pull every bindle runs its old hooks until upgraded. Tags are fetched in a detached background process at most once a day, so no session waits on the network; git's own `FETCH_HEAD` records when, so bindle keeps no state for it.
- **Agents are told the rules where they work:** an `AGENTS.md` in the tool's repo and in every bindle, and one line per bindle at session start saying whether it's writable or read-only.

## Claude Code constraints

These shape the design and are worth knowing if you change it:
- **`settings.local.json` is read at the git repo root,** even when launching from a subfolder. A folder of repos works as a domain root; a repo containing other repos doesn't.
- **Only the first 200 lines or 25 KB of `MEMORY.md` load.** Memory files load on demand when the index points to them.
- **Hook output is capped at 10,000 characters per command,** with no setting to raise it. Rules and read-only memory indexes have to fit, and `doctor` warns when they don't.
- **SessionStart hooks run again on resume,** and hooks for the same event run in parallel, which is why pulling and printing happen in one command.
- **A local-scope plugin install is still recorded at machine level.** "Local" decides where it's enabled, so each machine runs `attach` once per folder.
- **Imports in a project's `CLAUDE.md` from outside the launch folder wait for a one-time approval** and don't load headlessly.

## Considered and rejected

- **A symlink farm and copied memory** (the first prototype). Copies drift, symlinks into `~/.claude` fought Claude Code's own layout, and plugins plus `autoMemoryDirectory` now do it natively.
- **Rules through `CLAUDE.md` imports:** these need approval when they come from outside the folder, and they would edit a folder's own `CLAUDE.md`, which may be a team's committed file.
- **A personal bindle installed at user scope** (on everywhere): it's all or nothing, it would load personal memory into every folder including clients', and it skips the lock and the writable setting. Attaching per folder keeps one mechanism.
- **An inbound check that blocks domain terms from entering personal:** it can't tell an allowed "I work at Acme" from internals, so it would either block allowed content or be pruned into uselessness. A work detail in a private repo is recoverable. A rule in personal's `rules.md` addresses it instead.
- **Shared team memory:** several people's sessions writing one bindle makes agents steer each other with unreviewed memories, and it competes with the repo's own docs. Knowledge a team shares belongs in the project repo.
- **Organizing memories into type folders:** an early A/B showed no quality or cost gain over Claude Code's native flat index, and forcing one structure across projects isn't a goal.
- **Hard-blocking extra code in shared bindles:** warnings fit the guardrails principle, since the person may well have written that code.

## Prior art

The problem is common; the domain boundary is rarely the focus. These are surveyed briefly, not vetted.
- **Claude Code** has no built-in memory sync; feature requests note that memory is keyed to absolute paths. `autoMemoryDirectory` is the native lever.
- **Sync everything to one private repo** ([claude-sync](https://github.com/renefichtmueller/claude-sync), git-based global memory, hook-based pull/push): portable, but one store with no boundary.
- **Closest in spirit:** [dotai](https://pypi.org/project/dotai-cli) (personal context in its own folder, never writes team files), [dotagents](https://pkg.go.dev/github.com/yourconscience/dotagents) (public tool and private config as separate repos), agentic-stack (a portable `.agent/` folder with layered memory), skills shared across agents through chezmoi.
- **Separate config directories per life** (`CLAUDE_CONFIG_DIR`, separate machines): a hard boundary, but nothing carries craft across.

What bindle adds: the structure decides where things go (one repo per domain, one writable bindle per folder) and checks what leaves (reviewed, leak-checked promotion), while what goes into a bindle is up to the person and the rules. Craft versus context is decided per memory as it's written (`boundary:` tags), so methods travel and each domain's knowledge stays put.

## Later ideas

Not needed for 1.0; recorded so they aren't lost.

- **Per-repo notes loading automatically** (a repo's `CLAUDE.local.md` importing its `projects/<repo>/` index), with projects identified by their git remote rather than their path, so the same repo at a different path finds the same notes.
- **Skill addendums:** how a domain's short addendum tailors a general skill from craft (a skill that references the base one, or a file the base skill looks for).
- **More guardrails in the same spirit:** warn when a bindle's remote isn't on its domain's host; warn when a project's private files are committed to a team repo.
- **Freshness stamps for derived docs:** record the commit a doc was built from, and use `git diff` to say whether it's stale.
- **Promoting rules:** promotion carries memories, skills and commands; rules move between bindles by hand for now.
- **`bindle rename`:** documented as manual steps instead, since a rename touches every folder a bindle is attached to.
