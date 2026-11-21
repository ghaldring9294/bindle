#!/usr/bin/env bash
# Shows this bindle's memory index in folders where the bindle is on but not writable.
# Where it's writable, Claude Code loads the index itself, so printing it again would duplicate it.
# Managed by bindle: `bindle doctor` flags a copy that differs from the base template.
set -euo pipefail

root="${CLAUDE_PLUGIN_ROOT:?}"
memory="${root}/memory"
index="${memory}/MEMORY.md"
[ -s "$index" ] || exit 0

settings="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/settings.local.json"
if [ -f "$settings" ] && grep -q "\"autoMemoryDirectory\"[[:space:]]*:[[:space:]]*\"${memory}/\{0,1\}\"" "$settings"; then
  exit 0
fi

name="$(sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${root}/bindle.json" | head -1)"
echo "Memory index from the ${name:-unnamed} bindle (read-only in this folder; files are in ${memory}):"
cat "$index"
