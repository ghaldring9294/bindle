# bindle-{{name}}

The {{name}} bindle: one domain's skills, commands, hooks, memory and notes, made by [bindle](https://github.com/ghaldring9294/bindle).

| Path | What it is |
|---|---|
| `bindle.json` | Marks this repo as a bindle |
| `.claude-plugin/` | Plugin manifest, plus a one-plugin marketplace so the repo installs directly |
| `skills/`, `commands/`, `agents/`, `hooks/` | Tooling, namespaced `{{name}}:<name>` |
| `memory/` | Auto-memory: writable in folders where this bindle is writable, shown read-only elsewhere |
| `rules.md` | Standing instructions for this domain |
| `notes/` | Notes for this domain |
| `projects/<repo>/` | Private notes about one repo |

Turn it on for a folder with `bindle attach <path-to-this-repo> <folder>`; add `--writable` to make it the folder's writable bindle. `bindle doctor` shows what's on.
