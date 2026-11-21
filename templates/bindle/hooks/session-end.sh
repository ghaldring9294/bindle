#!/usr/bin/env bash
# SessionEnd: where this bindle is writable and sync is on, commit memory/ changes and push them.
# Never blocks: failures are logged in .git/bindle-sync.log and reported by `bindle doctor`.
# Managed by bindle: `bindle doctor` flags a copy that differs from the base template.
set -uo pipefail
. "$(dirname "$0")/lib.sh"

sync_enabled && writable_here && sync_push
exit 0
