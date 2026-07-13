# Memory taxonomy (bindle convention)

How to organize a project's **auto-memory** — the per-project directory Claude Code loads
at session start (`~/.claude/projects/<slug>/memory/`, machine-local). This is the memory
Claude *writes and recalls*; it is distinct from `.claude-local/` (private context Claude
*reads*).

## The scheme — organize by type

Group by **type**, the axis Claude's memory system already understands: one folder per
type, with `MEMORY.md` at the root as the always-loaded index.

```
memory/
  MEMORY.md            # Tier-0 index, loaded every session (keep under ~200 lines / 25 KB)
  reference/           # what the system IS — facts, pointers, data models, glossaries
  feedback/            # how I should work — durable rules, review norms, gotchas
  project/             # ongoing work — durable patterns AND in-flight state
  user/                # who the user is — role, preferences
  skill/               # skill addenda (bindle extension; loaded by a specific skill)
```

- `reference / feedback / project / user` are Claude Code's native memory types; `skill`
  is a bindle extension for skill-coupled addenda.
- Each file is one memory. The folder encodes the type, so filenames need no `type_` prefix.
- `MEMORY.md` groups entries by type and links into the folders, one line each:
  `- [Title](reference/foo.md) — one-line hook`. Claude reads this index first, then opens
  individual files on demand. That index/detail split *is* the tiering — Tier 0 is the
  index, the files are Tier 1.

## stable vs volatile

Tag in-flight state `[volatile]` in the index; everything else is stable. `project/` is
where the two mix — durable patterns (stable, cacheable) alongside ticket-scoped state that
expires. Split them in the index:

```
## project — ongoing work
### durable patterns
- [Facade + Fake for services](project/facade_fake_for_services.md) — ...
### in-flight state  [volatile]
- [VAR rollout phase](project/var_rollout_phase.md) — ... delete when it lands
```

Keeping the volatile entries corralled keeps the stable majority of `MEMORY.md`
cache-friendly and makes "what can I prune?" obvious at a glance.

## Keying gotcha (verified)

Auto-memory is keyed **per git repository**: all worktrees of a repo share ONE memory
directory. **Non-git** directories key by their path slug instead. So two worktrees of the
same repo cannot hold different memory — if you need that (e.g. A/B testing two memory
layouts), use separate non-git copies at distinct paths.
