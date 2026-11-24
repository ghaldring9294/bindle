# bindle

bindle carries your Claude Code setup (skills, hooks, memory, notes and rules) between machines in git, while keeping each part of your life, such as personal projects, an employer or each client, in its own repo that never mixes with the others.

You keep one repo per domain, called a **bindle**. Each folder you launch Claude Code from turns on the bindles it needs. A work session can use your general tooling, but it can't write work context into your personal repo, and a client's knowledge never reaches another client's folder.

Contents: [How it works](#how-it-works) · [Install](#install) · [Quick start](#quick-start) · [Everyday use](#everyday-use) · [Scenarios](#scenarios) · [Commands](#commands) · [Configuration](#configuration) · [Safety](#safety-and-boundaries) · [Updating](#updating) · [Troubleshooting](#troubleshooting) · [Limits](#limits)

## How it works

| Term | Meaning |
|---|---|
| **Bindle** | A git repo for one domain: its skills, commands, hooks, memory, notes and rules. Technically, a Claude Code plugin with a few extra folders. |
| **Domain** | A boundary you want to keep: you, an employer, one client. One bindle per domain. |
| **Attach** | Turn a bindle on for a folder. Every session started from that folder loads it. |
| **Writable** | The one attached bindle that new memories are saved to. A folder has at most one. |
| **Read-only** | Any other attached bindle. Its skills, rules and memories load, but sessions can't edit it. |
| **Promotion** | The only way material moves between bindles: a general rewrite you approve, checked for domain names and secrets on the way out. |

A typical setup at work, launching Claude Code from `~/acme`:

```mermaid
flowchart LR
    F["~/acme<br/>(the folder you launch Claude from)"]
    A["acme bindle<br/>~/acme/.bindle"]
    C["craft bindle<br/>your general tooling"]
    F -- "on, writable:<br/>new memories go here" --> A
    F -- "on, read-only:<br/>skills and rules only" --> C
```

Your personal bindle isn't attached at `~/acme` at all, so nothing personal loads there. At home, `~/projects` attaches your personal bindle as writable instead.

bindle uses Claude Code's own mechanisms rather than replacing them: plugins for skills and hooks, the `autoMemoryDirectory` setting for memory, and permission rules for the read-only lock. The `bindle` command writes a folder's `.claude/settings.local.json` and reads it back; the only thing it keeps is `~/bindles/registry.json`, a plain list of where your bindles live, so you can name them from any folder.

## Install

You need Claude Code 2.1.74 or later, git, and Python 3.9 or later. It runs on macOS, Linux and Windows.

**As a plugin (recommended):**
```
/plugin marketplace add https://github.com/ghaldring9294/bindle.git
/plugin install bindle@bindle --scope user
```
Adding the marketplace only makes the plugin available; the install turns it on, and user scope turns it on in every folder (your bindles still load only where you attach them). This gives you the `/bindle` command, the `/bindle-promote` skill, MCP tools that Claude calls directly (attach, detach, doctor, sync and so on — no shell commands needed), and the session-check hook that warns when a session starts inside a domain folder without its bindle, and when bindle or a bindle needs updating. Nothing else to do.

**For terminal access** (optional — lets you run `bindle` commands outside Claude Code):
```
git clone https://github.com/ghaldring9294/bindle.git
bindle/bin/bindle install
```
`install` puts the `bindle` command in `~/.local/bin`. If `~/.local/bin` isn't on your `PATH`, it tells you how to add it.

The session check warns inside folders you've attached a bindle to as writable; everywhere else it stays silent. In any folder, it also says when bindle has a new release (it checks for new tags in the background, at most once a day; set `BINDLE_UPDATE_CHECK=off` to stop that) or when a bindle needs `bindle upgrade`.

**On Windows:** install [Git for Windows](https://git-scm.com/download/win) (Claude Code runs hooks in its Git Bash) and Python from [python.org](https://www.python.org/downloads/). For the plugin, the same `/plugin marketplace add` works. For terminal access, run `python bindle\bin\bindle install` after cloning. Without developer mode, Windows doesn't allow symlinks, so `install` copies files instead and writes a `bindle.cmd` launcher; run `bindle install` again after updating bindle. Add `%USERPROFILE%\.local\bin` to your `PATH`.

## Quick start

Create a personal bindle and turn it on for the folder you keep side projects in. These examples keep bindles in `~/bindles/`; any folder works. Commands find a bindle in `~/bindles/` by its folder name, and one elsewhere (like a domain bindle in its project folder) by the name it was created or attached with (set `BINDLE_HOME` to use another home folder). Run `bindle` alone to see every command.

1. **Create the bindle.** It's a local git repo; bindle never sets a remote.
   ```
   bindle new personal --at ~/bindles/personal --sync
   ```
2. **Give it a private remote** so it can travel between machines (any git host):
   ```
   cd ~/bindles/personal
   git remote add origin git@github.com:you/bindle-personal.git
   git push -u origin HEAD
   ```
3. **Attach it** to the folder you launch Claude Code from, as the writable bindle:
   ```
   bindle attach personal ~/projects --writable
   ```
   `personal` is short for `~/bindles/personal`; a path works too.
4. **Check it:**
   ```
   bindle doctor ~/projects
   ```
   You should see `personal: on, writable, sync on` and `No problems found.`
   If you installed from a git clone rather than the plugin, turn on the session check (`bindle install --session-check`, see [Install](#install)).
5. **Start Claude Code from `~/projects`.** The first lines of the session name the bindle and say it's writable. Ask Claude to remember something; it lands in `~/bindles/personal/memory/`, and with sync on, it's committed and pushed when the session ends.

On another machine: install the plugin (`/plugin marketplace add <bindle-repo-url>`), clone the bindle to the same kind of place (`git clone <url> ~/bindles/personal`; plain `git clone <url>` would put it in the current folder as `bindle-personal`), and `bindle attach` once per folder.

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

**Sync.** With `"sync": true` in `bindle.json`, each session start pulls the latest from the bindle's remote, and each session end commits changes under `memory/`, `projects/` and `outbox/` and pushes them. A bindle that's read-only in the folder is only pulled, never pushed. Without a remote, it commits locally. Everything else (skills, rules, notes) you commit yourself; the session start reminds you when something's waiting. `bindle sync` does the same on demand.

**Notes.** Each bindle has a `notes/` folder for anything you want to keep: ticket notes, plans, research. Notes aren't loaded automatically; the session is told where they are. `notes/scratch/` is ignored by git, for things that should never leave the machine.

**Rules.** A bindle's `rules.md` is shown at every session start where it's attached, as standing instructions. Keep it short (it must stay under 9,000 characters) and put detail in memory or notes.

## Scenarios

Each scenario uses made-up names. Replace the paths with your own.

**An employee.** Your employer's bindle lives in your work folder and is writable there; your general tooling (a craft bindle) is on read-only.
```
bindle new acme --at ~/acme/.bindle
bindle terms acme                    # names to keep inside it; add the ones that apply to private-terms.txt
bindle attach acme ~/acme --writable
bindle attach craft ~/acme           # craft = ~/bindles/craft
```

**Launching from a repo inside the domain folder.** Claude Code treats each git repo as its own starting point: a session started in `~/acme/web` reads `~/acme/web/.claude/settings.local.json`, not `~/acme`'s, and keeps its own memory folder. Either start Claude from `~/acme` (it sees every repo, and the bindle is on), or also attach the bindle to each repo you start from for narrow work. `--repos` does the folder and every git repo directly inside it in one go (run it again after cloning a new repo; `bindle doctor` in the domain folder lists repos still missing it):
```
bindle attach acme ~/acme --writable --repos
```
If you used Claude Code in those repos before bindle, each has its own old memory folder under `~/.claude/projects/`; migrate those too (MIGRATION.md).

**A freelancer with two clients.** Each client gets a folder and a bindle. Switching clients means starting Claude Code from the other folder, which also gives you separate session histories and permissions.
```
bindle attach ~/clients/acme/.bindle ~/clients/acme --writable
bindle attach ~/clients/globex/.bindle ~/clients/globex --writable
bindle attach ~/bindles/craft ~/clients/acme
bindle attach ~/bindles/craft ~/clients/globex
```

**A client that allows no outside tooling.** Attach only that client's bindle to its folder.

**A new machine.** Install the plugin (`/plugin marketplace add <bindle-repo-url>`), clone each bindle into place (a bindle used in many folders to `~/bindles/<name>`, a domain bindle to `<domain folder>/.bindle`), then `bindle attach` once per folder. Use `bindle new` only to create a bindle the first time. A folder's attach settings stay on that machine, so this is the only setup step.

**Promoting a lesson.** In the session where you learned it, ask Claude to promote it (the `/bindle-promote` skill). It drafts a general rewrite, asks where it should go, and once you approve, puts it there in one step, after a check against the source bindle's private terms:
```
bindle promote acme draft.md --into craft --name small-prs --description "keep PRs small"
```
The original stays where it was. To send it to a second bindle, promote it again. If a draft names one of the source's private terms, the promotion stops and shows where; that's a prompt to check, not a wall. If the term is fine to share (a public name, or a target that's yours alone), allow it for that promotion (`--allow <term>`). A possible secret is the one hard stop: take it out, and keep it in a password manager or vault. Rules (`rules.md`) aren't promoted; move a rule by hand in a session in the target's folder. To improve something already promoted (say, a craft skill you noticed was wrong while using it at work), ask Claude to update it: you see a diff against the current version, and on approval it's replaced with `--replace` (git history keeps the old one). Nothing is ever replaced without that flag.

**A reminder for another domain.** Working in one client's folder and remember something for another? Ask Claude to send it ("remind me in globex to send the March invoice"). It's promoted as a note (`--kind note`): checked against this domain's private terms like anything else, then added to the other bindle's `notes/inbox.md` with the date and where it came from. The next session there shows how many notes are waiting as it starts, and Claude brings them up. When the target isn't on this machine (personal, from a work laptop), the approved draft waits in the source's outbox (`bindle outbox add`) until you run `bindle collect` where the target lives.

**Sharing your craft.** Keep finished, general skills in a craft bindle that only takes promoted material, and share its repo. Anyone with access can install it as an ordinary plugin, with no bindle needed:
```
bindle new craft --at ~/bindles/craft --audience shared --writes explicit
```
```
/plugin marketplace add git@github.com:you/bindle-craft.git
```

**Writing craft with real history at hand.** Work on craft in its own folder, where its files are editable. To draw on what actually happened at work while keeping the skills general, attach the work bindle there read-only: its memories are listed at session start and readable, and locked against edits.
```
bindle attach acme ~/bindles/craft
```
What you write in craft isn't checked against acme's private terms (only promotion is), so keep acme's specifics out of craft's files yourself; craft's `rules.md` is a good place to say so.

**The same tools on every machine.** Put the domain's MCP servers in its bindle's `.mcp.json` (see [Configuration](#configuration)), with secrets as environment variables. On each machine, set the variables once; every folder the bindle is attached to then has the same tools.

**Working with a friend on a project.** You each keep your own bindles. Anything you both need goes into the project's repo itself (its `CLAUDE.md` and docs), where it's reviewed like code.

## Commands

| Command | What it does |
|---|---|
| `bindle install [--cleanup] [--session-check \| --no-session-check]` | Put `bindle` on your `PATH` for terminal use (optional when installed as a plugin); `--cleanup` removes old-style command/skill links and user-level hook left by an earlier install; `--session-check` and `--no-session-check` add or remove a legacy user-level hook (the plugin provides this now) |
| `bindle session-check [<folder>]` | Show what the session check would say for a session started in that folder (the installed hook runs it with `--hook`) |
| `bindle new <name> [--at <dir>] [--sync] [--audience …] [--writes …]` | Create a bindle repo (default location `./.bindle`) |
| `bindle attach <bindle> [<folder>] [--writable] [--repos]` | Turn a bindle on for a folder; `--writable` makes it the one new memories go to; `--repos` also does each git repo directly inside the folder |
| `bindle detach <name-or-path> [<folder>] [--repos]` | Turn a bindle off for a folder; `--repos` also each git repo directly inside it that has it |
| `bindle terms <bindle> [<folder>]` | Suggest private terms from the domain folder's repos, for you to pick from |
| `bindle list [<folder>]` | List your bindles: those in `~/bindles`, those in its registry and those on in the folder, with whether each is writable, read-only or not attached there |
| `bindle doctor [<folder>]` | Show what's on, what's writable, unsaved work, warnings and problems, with the command that fixes each problem |
| `bindle sync [<folder> \| --all]` | Commit and push the writable bindle's memories, then pull the bindles that are on. `--all`: every bindle `bindle list` finds |
| `bindle update [--push]` | Pull bindle itself, refresh its install and upgrade every bindle; `--push` also pushes each upgraded bindle |
| `bindle upgrade [<bindle> \| --all] [--dry-run]` | Bring a bindle's managed files up to this version of bindle |
| `bindle promote <source> <draft> --into <target> --name <slug> [--kind …] [--description …] [--allow <term>] [--replace] [--dry-run]` | Copy an approved, general draft into another bindle on this machine, after the private-terms and secrets checks. `--replace` updates what's there; `--dry-run` shows the diff |
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
| `sync` | `true` / `false` | Pull at session start; commit and push `memory/`, `projects/` and `outbox/` at session end |
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

- **One writable bindle per folder.** Every new memory has exactly one destination, so a session can't save work context into your personal bindle by mistake.
- **Read-only bindles are locked against Claude's file-editing tools.** `attach` adds a permission rule, so Claude can't edit them. It isn't a sandbox: it doesn't cover shell commands, though Claude Code refuses attempts to work around the lock that way.
- **Promotion is the only way bindle moves material between bindles.** Material crosses as a general rewrite you approved. `promote` (and `outbox add`) check it against the source's private terms (in its name, description, file names and contents) and for credentials, and Claude Code's permission prompt shows exactly what moves. An item that waits in an outbox gets a hash, and `collect` refuses it if it changed since you approved it. The private terms are a backstop for names you've listed, not a guarantee.
- **A read-only bindle is visible, not sealed.** Its rules and memory index are shown in sessions where it's attached, so what a session sees there could end up in the writable bindle's memories. Attach a bindle to a folder only if that domain may see it, which is why personal stays off at work and craft holds only general material.
- **Secrets are never pushed by sync.** A memory, project or outbox file that looks like it holds a credential is held back (the rest still sync), the next session start says so, and `doctor` reports it. Sync also checks everything it's about to push that the remote doesn't already have, so a secret committed by hand stays local too, even if a later commit removed it; `doctor` says how to take it out of those commits. `doctor` also checks notes and suggests moving a secret to a password manager, leaving a pointer in the note.
- **A bindle inside a project repo is excluded there.** `bindle new` adds it to that repo's `.git/info/exclude`, so a `git add -A` in the project can't commit your bindle. `doctor` warns if a repo would commit or already tracks one.
- **bindle never adds or pushes a remote.** Where each bindle lives is your decision. A work bindle belongs only on storage your employer allows.
- **Trust what you attach.** A bindle's hooks and servers run with your permissions, and its skills and rules are instructions to Claude. Attach only bindles you control or trust. `attach` and `doctor` warn when a read-only bindle runs code beyond bindle's own hooks, and if a sync pulls changes to such code, the session start says so in the terminal before it next runs. These are warnings, not blocks: you decide.

## Updating

**When installed as a plugin:** update bindle through Claude Code (`/plugin` → Installed → bindle → Update, or `claude plugin update bindle@bindle` from the terminal). Then upgrade your bindles:
```
bindle update --push     # upgrade every bindle; --push pushes each one it upgrades
```

**When installed from a git clone:**
```
bindle update            # pull bindle, upgrade every bindle
bindle update --push     # the same, then push each bindle it upgraded
```
`update` fast-forwards bindle's own clone (it stops if you've changed files there), then upgrades every bindle in `~/bindles` and its registry. It lists a push command for each bindle it upgraded that has a remote; `--push` runs them.

The session check tells you when an update is available. `doctor` prints a ready-to-run `bindle upgrade` for each bindle that's behind. A bindle that's read-only in the folder is locked to Claude, so run that upgrade yourself (in Claude Code, prefix it with `!`). [CHANGELOG.md](CHANGELOG.md) lists what changed in each version, and says when an upgrade is needed.

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
| A skill shows up twice | An old copy is still in `~/.claude/skills/`. Remove it; the bindle provides it now. |
| Memories didn't reach the other machine | Closing the app or killing the terminal can skip the end-of-session sync; the next session start in that folder commits and pushes them. `bindle sync` does it now. `doctor` shows the last sync result. |
| Sync says "push failed" | Usually credentials. With two GitHub accounts on one machine (say work and personal), the credential manager may offer the wrong one. Put the account in the remote URL so git asks for it once and remembers it per repo: `git -C <bindle> remote set-url origin https://<user>@github.com/<user>/<repo>.git`, then `git -C <bindle> push` by hand. Over SSH, use a host alias per account. |
| Sync refused to commit | A memory looks like it holds a credential. `doctor` names the file; remove the secret. |
| "attach refuses a folder inside a git repo" | Claude Code reads settings at the repo root. Attach the repo root, or a folder that isn't inside a repo. |
| "read-only but not locked" | The bindle was attached before locks existed. Run the same `bindle attach` again. |
| Rules seem ignored | `doctor` warns when `rules.md` is over 9,000 characters; the hook can show only 10,000. |

## Limits

- **Windows needs Git for Windows and Python.** Hooks run through Git Bash and find Python as `python3`, `python` or `py`. On Windows, Claude Code reads a folder's settings in that folder, so `attach` accepts a folder inside a repo there.
- **Claude Code shows only the first 200 lines or 25 KB of `MEMORY.md`.** Keep the index short; put project memories in `projects/`.
- **A read-only bindle's memory index is shown through a hook, capped at 10,000 characters.**
- **A repo's notes don't load automatically when you work inside that repo.** Launch from the folder that holds your repos, and the session is told where the notes are.
- **Attach settings are per machine.** Each machine runs `bindle attach` once per folder.

## For contributors

- `python3 -m unittest discover -s tests` runs the unit tests (a fake `claude`, fast); `tests/e2e.sh` runs the main flow against the real Claude Code. CI runs the unit tests on macOS, Linux and Windows.
- [docs/design.md](docs/design.md) explains the design and why it works this way; [PLAN.md](PLAN.md) has the status and next steps; [AGENTS.md](AGENTS.md) orients AI agents working on this repo; [MIGRATION.md](MIGRATION.md) is what Claude follows to move an existing setup into bindles.

## License

MIT. See [LICENSE](LICENSE).
