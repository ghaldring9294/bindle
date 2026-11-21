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
bindle detach personal ~/acme
```

On a new machine: clone your bindles, then run `attach` once per folder.

Migrating an existing setup: open Claude Code and say "Read MIGRATION.md in the bindle repo and migrate my setup."

## Tests

```
python3 -m unittest discover -s tests   # fast, uses a fake claude
tests/e2e.sh                            # real Claude Code in a scratch folder (two short sessions)
```
