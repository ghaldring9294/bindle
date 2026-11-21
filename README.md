# bindle

Carry your Claude Code setup (skills, hooks, memory, notes) between machines, while keeping each domain's context in its own place.

- **A bindle** is one domain's layer: a git repo shaped as a Claude Code plugin, with its own `memory/`, `notes/` and `rules.md`. Your personal bindle is just the one that's yours; an employer or each client gets their own, on their own git.
- **Folders turn bindles on.** Attach bindles to the folder you launch Claude from. Every attached bindle is on there (its skills, hooks and memory load), and **one is writable**: new memories land in its `memory/`. A work session can't write into your personal bindle.
- **Craft moves deliberately.** A lesson learned in one domain reaches another only through promotion, rewritten without the specifics.

It uses Claude Code's own mechanisms: plugins for tooling, `autoMemoryDirectory` for memory, a SessionStart hook for read-only memory. See [PLAN.md](PLAN.md) for the design and what was verified.

## Install

```
git clone git@github.com:ghaldring9294/bindle.git
bindle/bin/bindle install        # links bindle into ~/.local/bin
```

Requires Claude Code v2.1.74+, git and Python 3.9+.

## Use

```
bindle new acme --at ~/acme/.bindle          # create a bindle (no remote is set)
bindle attach ~/acme/.bindle ~/acme --writable
bindle attach ~/bindle-personal ~/acme       # personal on too, read-only
bindle doctor ~/acme
bindle sync ~/acme                           # pull, and push the writable bindle's memories
bindle detach personal ~/acme
```

`attach` takes two paths: **the bindle, and the folder it's for** (the folder you launch Claude from). It writes one file in that folder, `.claude/settings.local.json`, pointing back at the bindle. Nothing is copied or linked:

```json
{
  "extraKnownMarketplaces": {
    "bindle-acme": { "source": { "source": "directory", "path": "/Users/you/acme/.bindle" } }
  },
  "enabledPlugins": { "acme@bindle-acme": true },
  "autoMemoryDirectory": "/Users/you/acme/.bindle/memory"
}
```

The first two entries turn on the bindle's skills, commands and hooks; `autoMemoryDirectory` (only with `--writable`) sends new memories into the bindle. Because the bindle's path is recorded, moving a bindle means attaching it again; `bindle doctor` points it out.

**Sync.** A bindle with `"sync": true` in `bindle.json` (or created with `bindle new --sync`) keeps itself in sync through its own hooks: every session start pulls the latest from its remote; every session end commits changes under `memory/` in the writable bindle and pushes them. Only `memory/` is committed automatically; skills, rules and notes stay deliberate commits. A memory that looks like it holds a secret is never committed, and `bindle doctor` reports it. Offline or conflicted, the hooks give up quietly and `doctor` shows what's waiting. `bindle sync [<folder>]` does the same by hand, whether or not sync is on.

On a new machine: clone your bindles, then run `attach` once per folder.

Migrating an existing setup: open Claude Code and say "Read MIGRATION.md in the bindle repo and migrate my setup."

## Tests

```
python3 -m unittest discover -s tests   # fast, uses a fake claude
tests/e2e.sh                            # real Claude Code in a scratch folder (two short sessions)
```
