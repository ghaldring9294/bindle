# AGENTS.md

This repo is the **{{name}} bindle**: one domain's Claude Code layer, made by [bindle](https://github.com/ghaldring9294/bindle). It's a plugin (skills, commands, agents, hooks) plus this domain's memory, notes and rules.

- `memory/`: auto-memory. `MEMORY.md` is the index (one line per memory); each memory is a file with frontmatter (`name`, `description`, `type`, and `boundary: craft | context | both`).
- `rules.md`: standing instructions for this domain. `notes/`: notes. `projects/<repo>/`: private notes about one repo.
- `hooks/` holds files managed by bindle (`bindle doctor` flags edits): change them in bindle's template, not here.
- Everything here belongs to the {{name}} domain. Don't copy it into another bindle; material moves between bindles only through promotion (an outbox the person reviews).
- Never add, change or push a remote.
