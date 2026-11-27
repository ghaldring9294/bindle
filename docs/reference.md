# Reference

Full documentation for bindle. See the [README](../README.md) for what bindle is, how to install it and common scenarios.

Contents: [Everyday use](#everyday-use) · [Using the terminal](#using-the-terminal) · [Configuration](#configuration) · [Safety](#safety-and-boundaries) · [Updating](#updating) · [Renaming](#renaming-a-bindle) · [Troubleshooting](#troubleshooting) · [Limits](#limits)

## Everyday use

**What loads when you start Claude Code in a folder:**

| From each attached bindle | Writable bindle | Read-only bindle |
|---|---|---|
| Skills, commands, agents, hooks (named `<bindle>:<name>`) | yes | yes |
| `rules.md` (standing instructions) | yes | yes |
| `memory/MEMORY.md` (the memory index) | yes, by Claude Code | yes, shown by the bindle's hook |
| Where its notes are, and uncommitted work to commit | yes | no |

Bindles not attached to the folder contribute nothing. Individual memory files load on demand when the index points to something relevant.

**Memory.** Claude saves new memories into the writable bindle's `memory/` and organizes them as it judges best. The suggested default: a memory about only one project goes in `projects/<project>/` with that folder's own `index.md`, and `MEMORY.md` keeps one pointer line per project, so the index loaded at every start stays short.

**Sync.** With `"sync": true` in `bindle.json`, each session start pulls the latest from the bindle's remote, and each session end commits changes under `memory/`, `projects/`, `outbox/` and `notes/` (except `notes/scratch/`) and pushes them. A bindle that's read-only in the folder is only pulled, never pushed, except one that takes explicit writes (craft): sync pushes commits already made in it (a promotion) but never commits there, and says in the terminal when it has uncommitted edits, so you commit them on purpose. Without a remote, it commits locally. Everything else (skills, rules) you commit yourself; the session start reminds you when something's waiting. `bindle sync` does the same on demand.

**Notes.** Each bindle has a `notes/` folder for anything you want to keep, such as plans and research. Notes aren't loaded automatically; the session is told where they are. `notes/scratch/` is ignored by git, for things that should never leave the machine.

**Rules.** A bindle's `rules.md` is shown at every session start where it's attached, as standing instructions. Keep it short (it must stay under 9,000 characters) and put detail in memory or notes.

**A bindle everywhere (`bindle global`).** Rules shown by a hook reach the main session only, not subagents, and a bindle's agents and skills load only in folders where it's attached. For a bindle you want in every session, every subagent and every folder (craft: how you work, and the agents and skills you build up), make it global:
```
bindle global craft        # craft's rules, memory index, agents, skills and hooks are on everywhere, from the next session
bindle global craft --off  # back to loading only where it's attached
```
This adds imports of the bindle's `rules.md` and its memory index (`memory/MEMORY.md`) to a marked block in your user `CLAUDE.md` (`~/.claude/CLAUDE.md`, or in `$CLAUDE_CONFIG_DIR` when that's set), which Claude Code reads in every session and passes to subagents. Everything else in that file stays exactly as it was, including its line endings; running it twice changes nothing. So a global craft works as a portable `CLAUDE.md`: its rules always load, and its memories load when their index line is relevant. Global also installs the bindle's plugin at user scope, so its agents, skills and commands are on in every folder (as `craft:<name>`), and its hooks run in every session; where it's also attached, Claude Code loads it once. A bindle that takes explicit writes (craft) is locked against Claude's edit tools everywhere, as it is where it's attached; promotion still changes it, since bindle writes those changes itself. A bindle made global before 0.37.0 has only the imports: run `bindle global <name>` again (`doctor` says when). Where a global bindle is also attached, its hook stops showing `rules.md` and the index, so they don't load twice. Changes apply from the next session. With its plugin on everywhere, a global bindle's own hook keeps it current in every session; for one without the plugin, the session check pulls it at every session start when sync is on (never a commit; for one that takes explicit writes, it pushes commits already made and names uncommitted edits), and says in the terminal when one is behind its remote or the pull fails. `doctor` flags an import whose bindle moved or was renamed, a global `rules.md` and index together over 12,000 characters (every session and subagent pays for them), and a block written by an older bindle (run `bindle global <name>` again). If you set `CLAUDE_CONFIG_DIR` in a settings file's `env` rather than your shell, set it in your shell too, so bindle finds the same file.

**Which machine (`bindle machine`).** Memories reach every machine, but some facts hold on only one ("this laptop is slow; use pre-built tools"). Name each machine once, and every session and subagent knows where it runs:
```
bindle machine work-mac    # writes "This machine: work-mac (MacBookPro18,3, arm64, macOS 26.3)" into the block
bindle machine             # shows the name and what's detected
```
The name stays on this machine (in `~/bindles/registry.json`); model, architecture and OS are detected, and the session check updates the line when they change. Onboarding asks for a name, and the session check asks once if none is set. Claude then saves what's true everywhere as is, and names the machine in a memory that holds on only one.

## Using the terminal

Everything above works through Claude. To run bindle yourself, or script it, the same operations are a `bindle` command.

### Install the command

```
git clone https://github.com/ghaldring9294/bindle.git
bindle/bin/bindle install
```
`install` puts the `bindle` command in `~/.local/bin`. If `~/.local/bin` isn't on your `PATH`, it tells you how to add it.

**On Windows,** run `python bindle\bin\bindle install` after cloning. Without developer mode, Windows doesn't allow symlinks, so `install` copies files instead and writes a `bindle.cmd` launcher; run `bindle install` again after updating bindle. Add `%USERPROFILE%\.local\bin` to your `PATH`.

### Quick start

Create a craft bindle for your general rules and skills, and a domain bindle for one folder of work (here `~/acme`), then turn both on there. Commands find a bindle in `~/bindles/` by its folder name, and one elsewhere (like a domain bindle in its folder) by the name it was created or attached with (set `BINDLE_HOME` to use another home folder). Run `bindle` alone to see every command.

1. **Create the bindles.** Each is a local git repo; bindle never sets a remote.
   ```
   bindle new craft --at ~/bindles/craft --sync
   bindle new acme --at ~/acme/.bindle --sync
   ```
2. **Give each a private remote** so it can travel between machines (any git host):
   ```
   cd ~/bindles/craft
   git remote add origin git@github.com:you/bindle-craft.git
   git push -u origin HEAD
   ```
   and the same in `~/acme/.bindle`.
3. **Turn them on.** Make craft's rules load everywhere, and attach both to the folder you launch Claude Code from, with acme as the writable bindle:
   ```
   bindle global craft
   bindle attach acme ~/acme --writable
   bindle attach craft ~/acme
   ```
   `craft` is short for `~/bindles/craft`; a path works too.
4. **Check it:**
   ```
   bindle doctor ~/acme
   ```
   You should see `acme: on, writable, sync on`, `craft: on, read-only, sync on` and `No problems found.`
   If you installed from a git clone rather than the plugin, turn on the session check (`bindle install --session-check`).
5. **Start Claude Code from `~/acme`.** The first lines of the session name the bindles and say which is writable. Ask Claude to remember something; it lands in `~/acme/.bindle/memory/`, and with sync on, it's committed and pushed when the session ends.

On another machine: install the plugin (`/plugin marketplace add <bindle-repo-url>`), clone each bindle to the same kind of place (`git clone <url> ~/bindles/craft`; plain `git clone <url>` would put it in the current folder as `bindle-craft`), and `bindle attach` once per folder.

### Commands

| Command | What it does |
|---|---|
| `bindle install [--cleanup] [--session-check \| --no-session-check]` | Put `bindle` on your `PATH` for terminal use (optional when installed as a plugin); `--cleanup` removes old-style command/skill links and user-level hook left by an earlier install; `--session-check` and `--no-session-check` add or remove a legacy user-level hook (the plugin provides this now) |
| `bindle session-check [<folder>]` | Show what the session check would say for a session started in that folder (the installed hook runs it with `--hook`) |
| `bindle new <name> [--at <dir>] [--sync] [--audience …] [--writes …]` | Create a bindle repo (default location `./.bindle`) |
| `bindle attach <bindle> [<folder>] [--writable] [--repos] [--dry-run]` | Turn a bindle on for a folder, and say what loads there (rules and memory index size, skills, agents and commands by name, code such as MCP servers by name); `--writable` makes it the one new memories go to; `--repos` also does each git repo directly inside the folder; `--dry-run` shows what would load and changes nothing |
| `bindle detach <name-or-path> [<folder>] [--repos]` | Turn a bindle off for a folder; `--repos` also each git repo directly inside it that has it |
| `bindle terms <bindle> [<folder>]` | Suggest private terms from the domain folder's repos, for you to pick from |
| `bindle machine [<name>]` | Show or set this machine's name; bindle writes it with the detected model, architecture and OS into its block in your user `CLAUDE.md` |
| `bindle global <bindle> [--off] [--dry-run]` | Turn a whole bindle on in every session and subagent, in every folder: its `rules.md` and memory index (imports in your user `CLAUDE.md`) and its plugin at user scope, and say what that brings, as `attach` does; `--dry-run` shows it and changes nothing; `--off` removes both, by name or by the path `doctor` shows for one that moved |
| `bindle list [<folder>]` | List your bindles: those in `~/bindles`, those in its registry and those on in the folder, with whether each is writable, read-only or not attached there |
| `bindle doctor [<folder>]` | Show what's on, what's writable, unsaved work, warnings and problems, with the command that fixes each problem |
| `bindle sync [<folder> \| --all]` | Commit and push the writable bindle's memories and notes, then pull the bindles that are on. `--all`: every bindle `bindle list` finds |
| `bindle update [--push]` | Pull bindle itself, refresh its install and its plugin, then pull every bindle and upgrade each one that's current, and bring each global bindle's plugin and the machine line up to date; `--push` also pushes each upgraded bindle |
| `bindle upgrade [<bindle> \| --all] [--dry-run]` | Bring a bindle's managed files up to this version of bindle |
| `bindle promote <source> <draft> --into <target> --name <slug> [--kind …] [--description …] [--allow <term>] [--replace] [--remove] [--dry-run]` | Copy an approved, general draft into another bindle on this machine, after the private-terms and secrets checks. `--kind file` places any other file by its path (`--name rules.md`, `--name .gitignore`; `.claude/`, `.claude-plugin/` and `.mcp.json` need `--allow <path>`); `--replace` updates what's there; `--remove` (no draft) takes the item out; `--dry-run` shows the diff |
| `bindle outbox add <bindle> <draft> --name <slug> [--kind …] [--description …] [--allow <term>]` | Store an approved draft for promotion, after the leak and secret checks |
| `bindle outbox list <bindle> \| --all` | Show a bindle's outbox, or every outbox that has items |
| `bindle outbox clean <bindle> [--items …] [--dry-run]` | Remove items already collected (they're in the target and in git history) |
| `bindle outbox remove <bindle> --items … [--dry-run]` | Drop named items, collected or not (an approval you changed your mind about) |
| `bindle collect <source> --into <target> --items <slugs> [--allow <term>] [--dry-run]` | Move approved outbox items into another bindle, showing each one's content (`--dry-run`: show it, move nothing); a private term allowed at approval needs `--allow` again |

`<bindle>`, `<source>` and `<target>` take a bindle's name (a folder in `~/bindles`, or a bindle in its registry) or its path. `<folder>` always means the folder you start Claude Code from; it defaults to the current one. Run `bindle <command> --help` for every option.

## Configuration

**A bindle's layout:**

```
bindle.json            name, layout version, sync, audience, writes
.claude-plugin/        the plugin manifest (its name is the prefix: acme:<skill>)
skills/ commands/ agents/
hooks/                 managed by bindle; don't edit (doctor flags changes)
memory/                MEMORY.md plus one file per memory
projects/<project>/    memories and notes about one project
notes/                 your notes; notes/scratch/ is never committed
rules.md               standing instructions for this domain
private-terms.txt      names that must never leave this bindle
outbox/                approved items waiting for a target on another machine
AGENTS.md              orientation for AI agents working in the bindle
```

**`bindle.json`:**

| Field | Values | Effect |
|---|---|---|
| `name` | lowercase letters, digits, hyphens | The bindle's name, and the prefix of its skills. Pick it for how you'll type it. |
| `sync` | `true` / `false` | Pull at session start; commit and push `memory/`, `projects/`, `outbox/` and `notes/` at session end |
| `audience` | `private` / `shared` / `public` | Who the bindle is for. Visibility itself is your git host's setting. |
| `writes` | `implicit` / `explicit` | `explicit` bindles take material only through promotion and can't be writable |
| `bindle_version` | set by `new` and `upgrade` | The bindle version that last wrote its managed files. An older copy of bindle refuses to upgrade it and asks you to pull bindle instead. |

**`~/bindles/registry.json`:** where bindles outside `~/bindles` live, by name (`{"bindles": {"acme": "/Users/you/acme/.bindle"}}`). `new` and `attach` keep it current; you can edit it. It also records, under `domains`, each folder a bindle was attached to as writable, which is where the session check looks; `detach` removes the entry. Names must be unique on a machine, because Claude Code's marketplace names are machine-wide; `new` and `attach` warn about a duplicate.

**`private-terms.txt`:** one name per line (organization, products, repos, ticket prefixes, people). Matching ignores case and whole words only; a term ending in punctuation, like the ticket prefix `ACME-`, also matches what follows it. Anything promoted out of the bindle is checked against these. `bindle terms <bindle>` suggests candidates from the domain folder: its name, its repos' names and remotes, and ticket prefixes in their commits. You choose which to add; it never writes the file. `doctor` warns when the writable bindle has none.

**What `attach` writes** into the folder's `.claude/settings.local.json` (shown for a writable bindle; nothing is copied or linked):

```json
{
  "extraKnownMarketplaces": {
    "bindle-acme": { "source": { "source": "directory", "path": "/Users/you/acme/.bindle" } }
  },
  "enabledPlugins": { "acme@bindle-acme": true },
  "autoMemoryDirectory": "/Users/you/acme/.bindle/memory"
}
```

A read-only bindle gets a permission rule instead of `autoMemoryDirectory`: `"permissions": { "deny": ["Edit(//Users/you/bindles/craft/**)"] }`.

**MCP servers.** To have the same tools on every machine where a domain is attached, put its MCP servers in the bindle's `.mcp.json`. Claude Code starts them in every session where the bindle is on, and their tools are named `mcp__plugin_<bindle>_<server>__<tool>`. Keep secrets out of the file: refer to environment variables, which each machine sets (from a password manager or your shell profile), and use `${CLAUDE_PLUGIN_ROOT}` for files inside the bindle.

```json
{
  "mcpServers": {
    "tracker": {
      "command": "npx",
      "args": ["-y", "some-tracker-mcp"],
      "env": { "TRACKER_TOKEN": "${ACME_TRACKER_TOKEN}" }
    },
    "helper": {
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/helper.py"]
    }
  }
}
```

Claude Code runs a server's `command` directly, not through bindle's hook launcher, so the command has to exist under that name on every machine. On Windows, `python3` usually opens the Microsoft Store instead of Python, so the `helper` example above would fail there. For a server that must run everywhere, prefer `npx` or `node`, or give each machine a command with the same name.

A server that only exists on one machine (a local path, a tool installed in one place) stays in that machine's own setup (`claude mcp add --scope user`), with a line in the bindle's `notes/` saying how to add it. Connectors that come with your Claude account follow your login and need no setup. A read-only bindle's servers run code on your machine, so `doctor` lists them under Warnings.

**What's in git, and what isn't:**

| In git (carried to every machine) | Not in git (stays on the machine) |
|---|---|
| Each bindle's memories (committed at session end with sync on) | Uncommitted edits in a bindle (`doctor` shows them) |
| A bindle's MCP server definitions (`.mcp.json`) | The secrets they read from environment variables |
| Everything else you commit in a bindle | `notes/scratch/` and anything else a bindle ignores |
| The bindle tool itself | Your Claude Code setup outside bindles: `~/.claude/CLAUDE.md`, `settings.json`, skills not in a bindle, MCP servers, session history |
| | A folder's attach settings (recreated with `bindle attach`) |

## Safety and boundaries

- **One writable bindle per folder.** Every new memory has exactly one destination, so a session can't save one client's context into craft or another client's bindle by mistake.
- **Read-only bindles are locked against Claude's file-editing tools.** `attach` adds a permission rule, so Claude can't edit them. It isn't a sandbox: it doesn't cover shell commands, though Claude Code refuses attempts to work around the lock that way.
- **Promotion is the only way bindle moves material between bindles.** Material crosses as a general rewrite you approved. `promote` (and `outbox add`) check it against the source's private terms (in its name, description, file names and contents) and for credentials, and Claude Code's permission prompt shows exactly what moves. An item that waits in an outbox gets a hash, and `collect` refuses it if it changed since you approved it. The private terms are a backstop for names you've listed, not a guarantee.
- **A read-only bindle is visible, not sealed.** Its rules and memory index are shown in sessions where it's attached, so what a session sees there could end up in the writable bindle's memories. Attach a bindle to a folder only if that domain may see it, which is why a client's bindle stays off in other clients' folders and craft holds only general material.
- **Secrets are never pushed by sync.** A memory, project, outbox or note file that looks like it holds a credential is held back (the rest still sync), the next session start says so, and `doctor` reports it. Sync also checks everything it's about to push that the remote doesn't already have, so a secret committed by hand stays local too, even if a later commit removed it; `doctor` says how to take it out of those commits. `doctor` also checks notes and suggests moving a secret to a password manager, leaving a pointer in the note.
- **A bindle inside a project repo is excluded there.** `bindle new` adds it to that repo's `.git/info/exclude`, so a `git add -A` in the project can't commit your bindle. `doctor` warns if a repo would commit or already tracks one.
- **bindle never adds or pushes a remote.** Where each bindle lives is your decision. A work bindle belongs only on storage your employer allows.
- **Trust what you attach.** A bindle's hooks and servers run with your permissions, and its skills and rules are instructions to Claude. Attach only bindles you control or trust. `attach` and `global` list what a bindle loads (`--dry-run` to see it first) and warn when a read-only bindle runs code beyond bindle's own hooks, naming its MCP servers; `doctor` warns too, and if a sync pulls changes to such code, the session start says so in the terminal before it next runs. These are warnings, not blocks: you decide.

## Updating

**When installed as a plugin:** update bindle through Claude Code (`/plugin` → Installed → bindle → Update, or `claude plugin update bindle@bindle` from the terminal). Then upgrade your bindles:
```
bindle update --push     # pull and upgrade every bindle; --push pushes each one it upgrades
```

**When installed from a git clone:**
```
bindle update            # pull bindle, then pull and upgrade every bindle
bindle update --push     # the same, then push each bindle it upgraded
```
`update` fast-forwards bindle's own clone (it stops if you've changed files there). Then, for every bindle in `~/bindles` and its registry, it pulls (fast-forward only) and upgrades it. So on each machine `bindle update --push` is the whole routine: no pulling each bindle by hand first. A bindle it can't bring up to date (offline, diverged from its remote, or an uncommitted change the pull would overwrite) is left exactly as it was and not upgraded, and update says why: upgrading a copy that's behind would make a commit that competes with the same upgrade pushed from another machine. Commit or stash, then run it again. Uncommitted changes the pull doesn't touch are kept. It lists a push command for each bindle it upgraded that has a remote; `--push` runs them. Finally it takes care of the parts that live in Claude Code rather than git: it updates bindle's plugin, installs each global bindle's plugin at user scope if a newer `bindle global` would have, and refreshes the machine line (and says so if the machine has no name yet: `bindle machine <name>`). Restart Claude Code afterwards.

The session check tells you when an update is available. `doctor` prints a ready-to-run `bindle upgrade` for each bindle that's behind. A bindle that's read-only in the folder is locked to Claude, so run that upgrade yourself (in Claude Code, prefix it with `!`). [CHANGELOG.md](../CHANGELOG.md) lists what changed in each version, and says when an upgrade is needed.

## Renaming a bindle

A bindle's name appears in three files, and Claude Code knows it by those names in every folder it's attached to, so rename in this order:

1. `bindle detach <old name> <folder>` in every folder it's attached to.
2. Change the name in all three files: `bindle.json` (`"name"`), `.claude-plugin/plugin.json` (`"name"`) and `.claude-plugin/marketplace.json` (`"name": "bindle-<new>"`, and the plugin entry's `"name"`). Commit.
3. Optionally rename its folder (and its GitHub repo).
4. `bindle attach` it again in each folder, then `bindle doctor`, which flags names that still disagree.

Its skills are then `/<new name>:<skill>`; update anything that refers to the old names.

## Troubleshooting

Start with `bindle doctor <folder>`; it explains most problems and prints the fix.

| Symptom | Cause and fix |
|---|---|
| `doctor` says nothing is at a bindle's path | The bindle moved. Attach it again from its new path. |
| `doctor` says a global import isn't there | A global bindle moved or was renamed, so its rules load nowhere. Run the `bindle global --off <old path>` it prints, then `bindle global <name>`. |
| A skill shows up twice | An old copy is still in `~/.claude/skills/`. Remove it; the bindle provides it now. |
| Memories didn't reach the other machine | Closing the app or killing the terminal can skip the end-of-session sync; the next session start in that folder commits and pushes them. `bindle sync` does it now. `doctor` shows the last sync result. |
| Sync says "push failed" | Usually credentials. With two GitHub accounts on one machine (say work and personal), the credential manager may offer the wrong one. Put the account in the remote URL so git asks for it once and remembers it per repo: `git -C <bindle> remote set-url origin https://<user>@github.com/<user>/<repo>.git`, then `git -C <bindle> push` by hand. Over SSH, use a host alias per account. |
| Sync refused to commit | A memory looks like it holds a credential. `doctor` names the file; remove the secret. |
| "attach refuses a folder inside a git repo" | Claude Code reads settings at the repo root. Attach the repo root, or a folder that isn't inside a repo. |
| "read-only but not locked" | The bindle was attached before locks existed. Run the same `bindle attach` again. |
| Rules seem ignored | `doctor` warns when `rules.md` is over 9,000 characters; the hook can show only 10,000. In a subagent, only global rules load (`bindle global`). |

## Limits

- **Windows needs Git for Windows and Python.** Hooks run through Git Bash and find Python as `python3`, `python` or `py`. On Windows, Claude Code reads a folder's settings in that folder, so `attach` accepts a folder inside a repo there.
- **Claude Code shows only the first 200 lines or 25 KB of `MEMORY.md`.** Keep the index short; put project memories in `projects/`.
- **A read-only bindle's memory index is shown through a hook, capped at 10,000 characters.**
- **A repo's notes don't load automatically when you work inside that repo.** Launch from the folder that holds your repos, and the session is told where the notes are.
- **Attach settings are per machine.** Each machine runs `bindle attach` once per folder.
