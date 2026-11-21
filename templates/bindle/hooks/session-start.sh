#!/usr/bin/env bash
# SessionStart: pull this bindle's latest (if sync is on), then show its memory index where the
# bindle is on but not writable. Where it's writable, Claude Code loads the index itself.
# One script, because hooks for the same event run in parallel and the print must see the pull.
# Managed by bindle: `bindle doctor` flags a copy that differs from the base template.
set -uo pipefail
. "$(dirname "$0")/lib.sh"

sync_enabled && sync_pull

index="${memory}/MEMORY.md"
[ -s "$index" ] || exit 0
writable_here && exit 0
echo "Memory index from the $(bindle_name) bindle (read-only in this folder; files are in ${memory}):"
cat "$index"
