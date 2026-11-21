#!/usr/bin/env bash
# SessionStart: give the session this bindle's standing rules (rules.md). A separate hook command from
# session-start.sh so each gets its own 10,000-character output cap.
# Managed by bindle: `bindle doctor` flags a copy that differs from the base template.
set -uo pipefail
. "$(dirname "$0")/lib.sh"

rules="${root}/rules.md"
[ -s "$rules" ] || exit 0
echo "Standing instructions from the $(bindle_name) bindle (${rules}). Follow them as you would CLAUDE.md:"
cat "$rules"
