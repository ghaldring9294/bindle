# AGENTS.md

This repo is the **{{name}} bindle**: one domain's Claude Code layer, made by [bindle](https://github.com/ghaldring9294/bindle). It's a plugin (skills, commands, agents, hooks) plus this domain's memory, notes and rules.

- `memory/`: auto-memory. `MEMORY.md` is the index, loaded at every session start, so keep it short: general memories get a line each; memories about only one project live in `projects/<project>/` with their own `index.md`, and `MEMORY.md` has one pointer line per project. A memory that spans projects (how two repos interact, domain-wide conventions) stays in `memory/`; a project's index can point to it with a "see also" line instead of copying it. Each memory is a file with frontmatter (`name`, `description`, `type`, and `boundary: craft | context | both`).
- `rules.md`: standing instructions for this domain. `notes/`: notes. `projects/<repo>/`: private notes about one repo.
- `.mcp.json` (optional): MCP servers that start wherever this bindle is on. Secrets only as `${ENV_VAR}` references, never values; files inside the bindle as `${CLAUDE_PLUGIN_ROOT}/…`.
- `hooks/` holds files managed by bindle (`bindle doctor` flags edits): change them in bindle's template, not here.
- `private-terms.txt`: words that identify this domain; anything promoted out of this bindle is checked against them. `outbox/`: reviewed, general items waiting to be collected into another bindle.
- Everything here belongs to the {{name}} domain. Don't copy it into another bindle; material moves between bindles only through promotion (an outbox the person reviews).
- Never add, change or push a remote.
