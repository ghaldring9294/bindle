# AGENTS.md

This repo is the **{{name}} bindle**: one domain's Claude Code layer, made by [bindle](https://github.com/ghaldring9294/bindle). It's a plugin (skills, commands, agents, hooks) plus this domain's memory, notes and rules.

- `memory/`: auto-memory, in Claude Code's own memory format. `MEMORY.md` is the index, loaded at every session start, so keep it short. How memories are organized is Claude's call; a default that works: memories about only one project in `projects/<project>/` with their own `index.md` and one pointer line in `MEMORY.md`, and anything spanning projects in `memory/`.
- `rules.md`: standing instructions for this domain. `notes/`: notes (sync commits them, except `notes/scratch/`, which stays on this machine). `projects/<repo>/`: private notes about one repo.
- `.mcp.json` (optional): MCP servers that start wherever this bindle is on. Secrets only as `${ENV_VAR}` references, never values; files inside the bindle as `${CLAUDE_PLUGIN_ROOT}/…`.
- `hooks/` holds files managed by bindle (`bindle doctor` flags edits): change them in bindle's template, not here.
- `private-terms.txt`: words that identify this domain; anything promoted out of this bindle is checked against them. `outbox/`: reviewed, general items waiting for a target bindle on another machine (promotion to a bindle on this machine is one step, `bindle promote`).
- Everything here belongs to the {{name}} domain. Don't copy it into another bindle; material moves between bindles only through promotion (an outbox the person reviews).
- Memories sync to every machine: save what's true everywhere, and name the machine (the user `CLAUDE.md` says which one this is) for a fact true on only one.
- Never add, change or push a remote.
