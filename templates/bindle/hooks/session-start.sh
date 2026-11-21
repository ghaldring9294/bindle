#!/usr/bin/env bash
# SessionStart: pull this bindle's latest (if sync is on), tell the session whether this bindle is
# writable or read-only here, and show its memory index where it's read-only (where it's writable,
# Claude Code loads the index itself).
# One script, because hooks for the same event run in parallel and the print must see the pull.
# Managed by bindle: `bindle doctor` flags a copy that differs from the base template.
set -uo pipefail
. "$(dirname "$0")/lib.sh"

sync_enabled && sync_pull

name="$(bindle_name)"
if writable_here; then
  echo "Bindle ${name} is on and writable in this folder: new memories are saved to ${memory}."
  exit 0
fi
echo "Bindle ${name} is on and read-only in this folder (${root}): use its skills and memories, but don't edit its files. Material moves into it only through promotion (its outbox), never a direct edit."
index="${memory}/MEMORY.md"
[ -s "$index" ] || exit 0
echo "Memory index from the ${name} bindle (files are in ${memory}):"
cat "$index"
