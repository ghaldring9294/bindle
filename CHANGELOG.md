# Changelog

One entry per release. "Run `bindle upgrade`" means the files bindle manages inside every bindle changed: after `git pull` here, run `bindle upgrade <bindle>` (or `bindle upgrade` in a folder to upgrade every bindle attached there), then push each bindle. `bindle doctor` tells you when one is due.

## 0.32.2 (2026-11-25)

No upgrade needed.

- **`"demo": true` in `bindle.json` no longer silences doctor.** It let the retired bindle-demo repo keep its bindle inside the repo's own history; `/bindle:onboard` replaces that demo and keeps its demo bindle as its own repo. A bindle tracked by its enclosing repo is now always reported, since its memories get pushed with that repo.

## 0.32.1 (2026-11-24)

No upgrade needed. Run `/plugin update bindle` (or `bindle update`), then restart Claude Code.

- **The MCP server starts on Windows.** The plugin started it as `bash bin/py …`, but Claude Code starts MCP servers from the Windows PATH, where Git for Windows doesn't put `bash`, so the bindle tools never loaded and `/bindle:onboard` couldn't call them. `.mcp.json` now runs `bin/py` directly; on Windows that finds the new `bin/py.cmd`, which picks a working Python the same way (skipping the Microsoft Store `python3` stub).

## 0.32.0 (2026-11-24)

No upgrade needed.

- **`/bindle:onboard` skill:** walks a new user through first-time setup — creating or cloning a craft bindle, making it global (so its `rules.md` loads in every session), attaching it, and setting up a remote. The session check offers it when no bindles exist on the machine.
- **Skills and commands renamed** to drop the redundant `bindle-` prefix: `/bindle:promote` (was `bindle:bindle-promote`), `/bindle:onboard`, `/bindle:docs`. The `install --cleanup` step covers the old skill links too.

## 0.31.0 (2026-11-24)

No upgrade needed.

- `bindle update` pulls every bindle (fast-forward only) before upgrading it, so `bindle update --push` is the whole routine on each machine. A bindle it can't bring up to date (offline, diverged, or an uncommitted change the pull would overwrite) is left as it was and not upgraded, with the reason; upgrading a stale copy made a commit that competed with the same upgrade from another machine.

## 0.30.0 (2026-11-24)

Run `bindle update` (the hooks changed), then `bindle global <name>` again for each global bindle (`doctor` names them).

- `bindle global` also imports the bindle's memory index (`memory/MEMORY.md`), so its memories are reachable from every session and subagent, not only its rules. A global craft is now a portable `CLAUDE.md`: rules that always load, lessons that load when relevant.
- Where a global bindle is attached read-only, its hook no longer shows its memory index a second time.
- `doctor` flags a global block written by 0.29 (rules only), and counts the index in the 12,000-character warning.

## 0.29.1 (2026-11-24)

No upgrade needed.

- Tests only: two unit tests failed on Windows (a file name with `"`, which Windows doesn't allow, and a lock-rule check that expected the wrong path form). CI is green on every OS again.

## 0.29.0 (2026-11-24)

Run `bindle update` (the rules hook changed, so every bindle needs an upgrade).

- `bindle global <name>` makes a bindle's `rules.md` load in every session, every subagent and every folder: it adds an import of it to a marked block in your user `CLAUDE.md` (`~/.claude/CLAUDE.md`, or in `$CLAUDE_CONFIG_DIR`). The rest of that file is untouched, in its own encoding and line endings; running it twice changes nothing. `--off` removes it. Also an MCP tool (`global`).
- Where a global bindle is also attached, its hook no longer shows `rules.md`, so the rules don't load twice.
- The session check pulls each global bindle that has sync on (pull only) and says in the terminal when a pull fails or a global bindle is behind its remote. Its hook timeout is now 30 seconds, to leave room for those pulls.
- `doctor` lists global bindles and flags an import whose bindle moved or was renamed, a global `rules.md` over 12,000 characters, and a global bindle behind its remote. The 9,000-character limit for attached rules no longer applies to a global bindle.

## 0.28.0 (2026-11-24)

Run `bindle upgrade` (the session hook's wording changed).

- Memory organization is Claude's call: the session hook, the bindle template's `AGENTS.md`, the README and the design describe the `projects/<project>/` layout as a default, not a rule.
- Memories no longer need a `boundary:` tag. `/bindle-promote` picks candidates by content, and promoted memories keep Claude Code's own frontmatter.
- Existing bindles keep their copied `AGENTS.md`; edit its `memory/` line to match if you like.

## 0.27.2 (2026-11-24)

No upgrade needed.

- Install: the README now includes `/plugin install bindle@bindle --scope user`; adding the marketplace alone doesn't install the plugin.
- `bindle install --cleanup` removes the old `/bindle` and `/bindle-promote` links even though their target (`global/`) is gone.
- `doctor` warns when bindle's own plugin isn't enabled, and when old-install links remain.

## 0.27.1 (2026-11-23)

No upgrade needed.

- `bindle update` says whether bindle itself changed first, not after the upgrade output.

## 0.27.0 (2026-11-23)

No upgrade needed. From now on, `bindle update` does the whole update.

- `bindle update [--push]`: pulls bindle itself, refreshes `/bindle` and `/bindle-promote`, and upgrades every bindle; `--push` also pushes each bindle it upgraded. The session check and `doctor` now point to it.

## 0.26.0 (2026-11-23)

Run `bindle upgrade` (the hook changed), then push each bindle. On Windows, `bindle install` again (`/bindle` and the promotion skill changed). Fixes from a whole-repo adversarial review.

- Sync commits and pushes `projects/` (project memories) too, and secret-checks it. Before every push it checks exactly what the push would send that the remote doesn't already have (binary files, odd names and diff settings included), so a secret committed by hand is never pushed, even if a later commit removed it; `doctor` says how to take it out.
- A file that looks like a secret is held back and the rest still sync; the session start says so in the terminal.
- A bindle that's read-only in a folder is pulled (fast-forward only) and never pushed.
- Sync fetches before it pushes: a remote whose history was rewritten (to remove a leaked secret, say) never gets the removed commits back from another machine, in that session or any later one, and the secret check compares against what the remote really has. It rebases only when the remote moved, stashing uncommitted work only when the remote didn't change the same files (no conflict markers in your notes), and pushes only the checked branch. Sync problems show at the next session start and in `doctor` (every problem of the latest run), with unresolved conflicts and a leftover autostash. Being offline isn't flagged, but a rejected key or a missing remote is, and so are commits that haven't reached the remote for a day. Problems from a session's end, including code a rebase brought in, show at the next session start.
- An edited `MEMORY.md` no longer stops sync (a status-parsing bug this release would otherwise have made worse).
- Network calls give up after a few seconds on a stalled network and end git's helper processes too, and respect a repo's own `core.sshCommand` and `GIT_SSH`. `bindle sync` pushes before it pulls, like the hooks.
- The code-change warning's review command covers every commit the pull brought.
- `upgrade` never goes backwards: `bindle.json` records the bindle version that wrote a bindle's files, and an older copy says to pull bindle instead (`upgrade --all` skips it, upgrades the rest and exits with an error). It also leaves deleted template files deleted.
- `collect` shows each item's content (`--dry-run` shows it and moves nothing), takes allowed terms only from its own `--allow` (an item's record isn't trusted), and rejects multi-line descriptions. Promote and collect always print the push command, and `doctor` warns about unpushed commits in a bindle no session pushes.
- The read-only lock also covers a bindle's path through a linked `~/bindles`.
- Claude recognizes plain requests to put something in another bindle ("add this to my personal bindle too", "move this skill to my craft") as promotions: the promote skill, `/bindle` and the writable bindle's session-start text name them.
- Docs: the README quick start pushes `HEAD` (works where git's default branch is `master`); MIGRATION.md no longer attaches personal in work folders.

## 0.25.0 (2026-11-23)

No upgrade needed. On Windows, `bindle install` again (`/bindle` changed).

- The session check also says when bindle has a new release to pull, or a bindle needs `bindle upgrade`. New tags are fetched in the background at most once a day; `BINDLE_UPDATE_CHECK=off` turns that off.

## 0.24.0 (2026-11-23)

Run `bindle upgrade` (the hook changed).

- When a sync pulls changes to a bindle's code (hooks, servers, `bin/`), the session start says so in the terminal, not only to Claude.

## 0.23.0 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (`/bindle` and the promotion skill changed).

- `bindle list` says "not attached here" instead of "not on here", which read as "not on this machine" and sent a note for a bindle on this machine to the outbox.

## 0.22.0 (2026-11-22)

Run `bindle upgrade` (the hook changed). On Windows, `bindle install` again (`/bindle` and the promotion skill changed).

- A session start with notes waiting in the inbox says so in the terminal, not only to Claude.
- `/bindle`, the promotion skill and MIGRATION.md ask choices (yes or no, which bindle, approve or edit or drop) as a select.

## 0.21.3 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (the promotion skill changed).

- `/bindle-promote`: approving a draft is a select (Approve, Edit, Drop) with the draft as its preview, instead of a typed answer.

## 0.21.2 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (`/bindle` changed).

- `/bindle`: setting up a new domain attaches with `--repos`, suggests the session check, and offers to migrate old memories.

## 0.21.1 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (`/bindle` changed).

- `/bindle`: when asked to make a bindle, Claude always passes `--at`, asking whether it's a domain bindle (`<domain folder>/.bindle`) or one for many folders (`~/bindles/<name>`), instead of relying on the `./.bindle` default.

## 0.21.0 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (`/bindle` changed).

- Every command that takes a bindle accepts its name or its path: `promote`'s source, `collect`, the `outbox` commands and `upgrade` took only a path before (found writing the demo walkthrough).
- `doctor`'s suggested commands, and the hint after `outbox add`, name the bindle when its name finds it, instead of printing its path.

## 0.20.1 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (`/bindle` changed).

- `/bindle` now tells Claude about `--allow` (letting a private term through a promotion once you've approved it) and that `outbox add` takes notes too; the README lists `outbox add --allow` and the session check's `--hook`.
- Tests catch documentation drift: every command option must appear in the README and `/bindle`, every `bindle …` example in a code block must parse, AGENTS.md must name every module and script (and only paths that exist), and the newest changelog entry must be the current version.

## 0.20.0 (2026-11-22)

No upgrade needed. Recommended: `bindle install --session-check`, then `bindle attach <bindle> <folder> --writable` again in each folder with a writable bindle, so the check knows it (`bindle doctor` reminds you).

- The session check (opt-in): `bindle install --session-check` adds one SessionStart hook to `~/.claude/settings.json` that warns when a session starts inside a folder attached writable, in a folder (usually a repo) with no writable bindle of its own, and gives the attach command. Silent everywhere else. `--no-session-check` removes it.
- `bindle session-check [<folder>]` shows what it would say.
- The registry records folders attached writable (`domains`); `detach` removes them.

## 0.19.0 (2026-11-22)

No upgrade needed.

- `bindle doctor` warns, in a folder with a writable bindle, about each repo directly inside it whose sessions wouldn't load that bindle or save memories to it, and gives the attach command. Repos that write to another bindle on purpose are left alone.

## 0.18.0 (2026-11-22)

No upgrade needed.

- `bindle attach --repos` and `bindle detach --repos`: act on a domain folder and every git repo directly inside it, since a session started in a repo reads only that repo's settings. Other bindles inside the folder are skipped. A writable conflict or an unreadable settings file in any of them changes none; `detach --repos` also clears a bindle that moved from every repo.

## 0.17.1 (2026-11-22)

**Run `bindle upgrade --all`** (adds a line to each bindle's `.gitignore`); for a bindle that's read-only where you are, run it yourself.

- Every bindle ignores `.claude/settings.local.json`, so attaching another bindle to a bindle's own folder (for example a work bindle read-only in craft's folder, to draw on real patterns while writing general skills) never commits that bindle's paths and name. Before, this relied on a global gitignore.
- README: attaching a domain bindle read-only to craft's folder.

## 0.17.0 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (the promotion skill changed).

- A private term in a draft is now a confirmation, not a wall: `--allow <term>` (on `promote` and `outbox add`, honored by `collect`) lets through a term you've decided is fine. Possible secrets stay a hard stop.
- `/bindle-promote`: offers to remove the original when you're moving rather than copying; says to remove things from another bindle in that bindle's own folder; explains that rules move by hand; covers customizing a craft skill for a domain (craft as the source).

## 0.16.0 (2026-11-22)

No upgrade needed. On Windows, `bindle install` again (the promotion skill changed).

- `bindle promote --replace` updates a memory, skill or command already in the target, such as improving a craft skill from a session in another domain. It's checked like any promotion; without the flag nothing is overwritten. A replaced skill folder loses files the new version dropped.
- `bindle promote --dry-run` prints what would change, as a diff when replacing, so you approve the exact change.

## 0.15.0 (2026-11-22)

**Run `bindle upgrade --all`** (changed `hooks/bindle_hook.py`); for a bindle that's read-only where you are, run it yourself. On Windows, also `bindle install`.

- A `note` promotion kind: a reminder or todo for another domain ("remind me in globex to send the invoice"), checked like any promotion and appended to the target's `notes/inbox.md` with the date and where it came from.
- Session start in a writable bindle mentions notes waiting in its inbox.

## 0.14.0 (2026-11-22)

No upgrade needed. Run `bindle install` again on Windows (the promotion skill changed).

- Promotion is one step: `bindle promote <source> <draft> --into <target>` checks an approved draft (private terms, secrets, nothing overwritten) and places it in the target, which can be named. The original stays; a second target is a second promotion.
- The outbox is now only for targets on another machine: `outbox add` there, then `bindle collect` where the target lives, which delivers the item and removes it from the outbox. `bindle outbox list --all` shows what's waiting anywhere. `outbox clean` removes items an older version left marked "collected".
- `/bindle-promote` rewritten around asking in plain words ("promote the doc-style skill to my craft"): it finds the item and the target, drafts a general version, checks with you, promotes, and offers to push the target.

## 0.13.0 (2026-11-22)

No upgrade needed.

- `bindle sync --all` pulls every bindle `bindle list` finds, and commits and pushes `memory/` and `outbox/` in those that can be writable (the same secret check applies).

## 0.12.0 (2026-11-22)

No upgrade needed.

- `bindle upgrade --all` upgrades every bindle `bindle list` finds (in `~/bindles` and its registry), so a bindle release is one command on each machine.

## 0.11.0 (2026-11-22)

No upgrade needed. Bindles attached before this version join the registry the next time you attach them (`bindle attach <path> <folder>` again is safe).

- A registry, `~/bindles/registry.json`: where bindles outside `~/bindles` live, by name. `new` and `attach` keep it current, so a domain bindle can be named from any folder (`bindle attach acme`, `bindle list`). Duplicate names are warned about, since Claude Code's marketplace names are machine-wide.
- `bindle list` includes registered bindles, and registered ones whose folder is gone.
- `bindle` with no arguments prints every command.

## 0.10.0 (2026-11-22)

No upgrade needed.

- `bindle list [<folder>]` lists your bindles: those in `$BINDLE_HOME` (default `~/bindles`) plus those attached to the folder, each with its audience, writes and whether it's writable there.
- `bindle outbox remove <bindle> --items …` drops named outbox items whatever their status, for an approval you changed your mind about.
- `/bindle-promote` asks which bindle to collect into, offering what `bindle list` shows; it never chooses.

## 0.9.0 (2026-11-22)

No upgrade needed.

- `doctor` flags a bindle whose three names (bindle.json, plugin.json, marketplace.json) disagree, as after a half-done rename.
- `bindle outbox clean <bindle>` removes outbox items already collected, and commits the removal; items not yet collected stay.
- README: "Renaming a bindle" (manual steps; there's no rename command).

## 0.8.1 (2026-11-22)

No upgrade needed.

- Fix: attaching a bindle that moved after it was detached failed ("Plugin not found in marketplace"), because detach keeps the folder's marketplace entry at the old path. `attach` now re-points it.

## 0.8.0 (2026-11-22)

No upgrade needed. Run `bindle install` again only if you installed by copying (Windows); links pick up the new `/bindle` on their own.

- `bindle terms <bindle>` suggests private terms from the domain folder: its name, its repos' names, their remotes' owners and names, and ticket prefixes seen in recent commits. It never writes the file; you pick.
- `doctor` warns when the writable bindle's `private-terms.txt` is empty, since promotion's leak check then passes everything.
- `/bindle` rewritten so Claude in any session understands the model and handles requests like "attach craft here" or "make acme writable".
- MIGRATION.md and `/bindle-promote` use `bindle terms` when a bindle has no terms. AGENTS.md: docs ship with every change, and tests check that README and `/bindle` list every command.

## 0.7.0 (2026-11-22)

No upgrade needed.

- `bindle attach craft` finds a bindle by name in `~/bindles/`, or in `$BINDLE_HOME` if set. A path that exists still means that path.
- README: MCP server commands must exist under the same name on every machine (`python3` opens the Microsoft Store on Windows).

## 0.6.1 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/bindle_hook.py`); for a bindle that's read-only where it's attached, run it yourself.

- Session start in the writable bindle commits and pushes memories a previous session left uncommitted. Closing the Claude app can skip SessionEnd (seen on Windows), so this no longer leaves memories behind.
- README: troubleshooting for two GitHub accounts on one machine.

## 0.6.0 (2026-11-21)

**Run `bindle upgrade`** (new managed `hooks/run`, changed `hooks/hooks.json`, `.gitattributes` gains an LF rule); for a bindle that's read-only where it's attached, run it yourself. Windows support.

- Windows: hooks run through `hooks/run`, which finds a working Python 3.9+ (`python3`, `python` or `py`; on Windows `python3` is often a Store stub). Lock rules use Claude Code's POSIX path form (`C:\\x` becomes `//c/x`). `install` falls back to copying where symlinks aren't allowed and writes a `bindle.cmd` launcher. `attach` accepts a folder inside a repo on Windows, where Claude Code reads settings in the launch folder. `doctor` quotes paths for PowerShell and cmd.
- bindle always writes UTF-8 with LF line endings, and `.gitattributes` keeps a bindle's text files LF on every OS (CRLF made git misread a bindle's `.gitignore` on Windows, and breaks shell scripts).
- Git output is read as UTF-8 on every OS.
- CI runs on Windows too.

## 0.5.1 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/bindle_hook.py`); for a bindle that's read-only where it's attached, run it yourself.

- Trust warnings (warnings, not refusals): `attach` and `doctor` list what a read-only bindle runs on the machine beyond bindle's own hooks (extra hook files, hooks or servers declared in `plugin.json`, `.mcp.json`, `.lsp.json`, `bin/`). `doctor` has a Warnings section that doesn't fail the check.
- When a session-start pull changes any of those files, the session is told right away, before they run in the next session.

## 0.5.0 (2026-11-21)

**Run `bindle upgrade`** (the hooks are now one Python file; the bash scripts are removed); for a bindle that's read-only where it's attached, run it yourself. Hardening from an independent review.

- **One implementation:** `hooks/bindle_hook.py` runs the hooks and is imported by the CLI, so the writable check, sync and the secret check can't disagree. Settings are parsed as JSON, and paths are compared properly (accents, brackets and spaces in paths work).
- **The CLI is a package** (`bindle/`), with `bin/bindle` as its entry point.
- **Promotion hardened:** `outbox add` records a hash of the approved content; `collect` refuses an item that isn't approved, changed since approval, points outside its folder, or contains symlinks. The leak check now covers the item's name, description and file names, not just contents. `collect` checks every destination before writing, so a failure leaves both bindles untouched, and it reports commits that failed.
- **Wider secret check:** case-insensitive, matches keywords inside longer names (`AWS_SECRET_ACCESS_KEY`), more token formats (`github_pat_`, `AIza…`, `sk-ant-`, `xapp-`), ignores placeholders like `${VAR}`, and handles file names with non-ASCII characters.
- **Fixes:** `doctor` flags a remote with no upstream (sync was silently keeping commits local); memories sync when `outbox/` is missing; the sync log works in worktrees; sync skips while a merge or rebase is in progress; `upgrade` stamps a missing layout instead of crashing; `detach` matches attached names before paths and can remove a bindle that moved; `doctor`'s fix commands quote paths; `doctor` warns when a read-only bindle's memory index is too long to show.

## 0.4.6 (2026-11-21)

**Run `bindle upgrade`** (adds `.gitattributes`); for a bindle that's read-only where it's attached, run it yourself.

- Fix: two machines adding memories between syncs both append to `MEMORY.md`, which stopped the rebase and left one machine's memory unpushed. `.gitattributes` now merges `memory/MEMORY.md` and `projects/*/index.md` with git's union driver, keeping both sides' lines.
- `bindle upgrade` appends missing template lines to `.gitattributes` as well as `.gitignore`.

## 0.4.5 (2026-11-21)

- `doctor` ends with a copy-and-paste command for each bindle that needs upgrading (`bindle upgrade <path>`, plus `&& git -C <path> push` when it has a remote), noting that in Claude Code it's prefixed with `!` because a read-only bindle is locked to Claude.

## 0.4.4 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`; adds `notes/scratch/` and its ignore rules); for a bindle that's read-only where it's attached, run it yourself.

- `notes/scratch/`: machine-local notes, ignored by git (its README is kept), never carried to other machines.
- Secrets in notes: `doctor` checks committable notes (and memory and outbox) for credentials and suggests moving them to secure storage with a pointer; the session start flags an uncommitted note that looks like it holds one. Files git ignores aren't checked.
- `bindle upgrade` appends template ignore rules a bindle's `.gitignore` lacks, never rewriting its own rules.

## 0.4.3 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`); for a bindle that's read-only where it's attached, run it yourself.

- Where a bindle is writable, the session start mentions uncommitted changes (and how many are in notes), so the session can remind the person to commit. With sync on, `memory/` and `outbox/` aren't counted, since sync commits them. Sync works without a remote too: it commits locally and skips the push.

## 0.4.2 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/rules.sh`). A read-only bindle is locked in folders where it's attached, so upgrade it yourself or from a folder where it isn't attached.

- A bindle's rules arrive framed as standing instructions to follow like CLAUDE.md, not as plain hook output.

## 0.4.1 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`).

- Where a bindle is writable, the session is told where its notes are (and to start at `notes/README.md` if there is one). Notes still aren't loaded automatically.
- MIGRATION.md: move an existing notes folder into the bindle and leave a symlink at the old path.

## 0.4.0 (2026-11-21)

**Run `bindle install` again** (it now links the `/bindle-promote` skill) and **`bindle upgrade`** (sync includes `outbox/`; new template files `private-terms.txt` and `outbox/`).

- Promotion through an outbox: `/bindle-promote` drafts general rewrites in the source domain's session; `bindle outbox add` stores an approved draft after a leak check (the source's `private-terms.txt`, whole words; a term ending in punctuation, like a ticket prefix `ACME-`, matches what follows) and the secret check; `bindle collect <source> --into <target> --items …` rechecks, copies memories (with an index line), skills or commands into the target, marks them collected, and commits both bindles. Naming the items puts them in Claude Code's permission prompt.
- Bindles have an `audience` (private, shared, public) and `writes` (implicit, explicit): `bindle new --audience shared --writes explicit` makes a craft bindle; `attach --writable` refuses an explicit bindle.
- `outbox/` syncs along with `memory/`, so items prepared on one machine can be collected on another.

## 0.3.2 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`).

- A memory goes at the lowest level that covers everything it's about: only one project → `projects/<project>/`; spanning projects (how two repos interact, domain-wide conventions) → `memory/`.

## 0.3.1 (2026-11-21)

**Run `bindle upgrade`** (changed `hooks/session-start.sh`).

- The writable bindle's session-start line tells the session to file a memory about one project in `projects/<project>/` (listed in that folder's `index.md`), with one pointer line per project in `MEMORY.md`, so the always-loaded index stays short.

## 0.3.0 (2026-11-21)

**Run `bindle upgrade`** (new managed hook `rules.sh`, changed `hooks.json`), then **re-run `bindle attach`** for each read-only bindle so it gets locked (`bindle doctor` lists them).

- Rules load: each bindle's `rules.md` reaches every session where the bindle is on, through its own SessionStart hook (no CLAUDE.md edits, no import prompts). `doctor` warns when `rules.md` nears the hook's 10,000-character cap.
- Read-only bindles are locked: `attach` adds an `Edit(//<bindle>/**)` deny rule for a bindle that isn't writable in that folder, so a session can't edit it; `detach` and `attach --writable` remove it. `doctor` flags a read-only bindle that isn't locked, and a writable one that is.

## 0.2.0 (2026-11-21)

A rebuild around one model: every bindle has the same shape, folders turn bindles on, and one is writable. **Bindles from 0.1.0 aren't compatible; create new ones and migrate (MIGRATION.md).**

- CLI rewritten in Python: `install`, `new`, `attach`, `detach`, `doctor`, `sync`, `upgrade`, `--version`.
- A bindle is a Claude Code plugin with `bindle.json`, `memory/`, `notes/`, `rules.md`, `projects/` and managed hooks.
- Memory sync through each bindle's hooks (opt-in, `"sync": true`): pull at session start, commit `memory/` and push at session end; a memory that looks like a secret is never committed.
- `bindle new` inside a git repo excludes the bindle there; `doctor` flags a bindle a repo would commit.
- `AGENTS.md` in the base and in every bindle; each bindle tells the session whether it's writable or read-only.

## 0.1.0 (2026-07)

The first attempt: layers installed by a symlink farm, memory copied into place, `init-layer` and `init-project`. Replaced by 0.2.0.
