#!/usr/bin/env bash
# Stop hook: after each turn, parse the session transcript and record the
# session's cumulative cost as ONE row in the project cost ledger.
#
# Upsert, not append: the Stop hook fires per turn and parse_usage.py sums the
# whole transcript, so appending every turn would write cumulative snapshots
# that overcount when summed. Instead we keep exactly one row per session_id,
# rewriting it each turn. (Decision logs are append-only; this machine-owned
# ledger is not.)
#
# Receives hook JSON on stdin (transcript_path, cwd, session_id).
# Single dependency: python3. Fails silent by design — tooling must never
# block real work.
set -u
exec 2>/dev/null

INPUT="$(cat)"
command -v python3 >/dev/null || exit 0

# Resolve our own dir portably. python3 is already required above; `readlink -f`
# is GNU-only and absent on BSD / older macOS, so don't depend on it.
LIB_DIR="$(python3 -c 'import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$0")/lib"

# Extract fields from hook input (tab-separated: transcript, cwd, session)
FIELDS="$(printf '%s' "$INPUT" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
print("\t".join([
    str(d.get("transcript_path") or ""),
    str(d.get("cwd") or ""),
    str(d.get("session_id") or "unknown")[:8],
]))
')" || exit 0

IFS=$'\t' read -r TRANSCRIPT CWD SESSION <<< "$FIELDS"

[ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] || exit 0
[ -n "$CWD" ] && [ -d "$CWD" ] || exit 0

# Where to write: prefer personal .claude-local, else docs/, else skip quietly.
if [ -d "$CWD/.claude-local" ]; then
  OUT_FILE="$CWD/.claude-local/claude-costs.md"
elif [ -d "$CWD/docs" ]; then
  OUT_FILE="$CWD/docs/claude-costs.md"
else
  exit 0
fi

# Ticket detection from git branch (e.g. feature/ABC-123-thing -> ABC-123).
# Same pattern lives in statusline.py (TICKET_RE) — keep the two in sync.
TICKET="$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null \
  | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | head -n1)"
TICKET="${TICKET:--}"

SUMMARY="$(python3 "$LIB_DIR/parse_usage.py" "$TRANSCRIPT")" || exit 0
[ -n "$SUMMARY" ] || exit 0

if [ ! -f "$OUT_FILE" ]; then
  {
    echo "# Claude Code session costs"
    echo ""
    echo "One row per session (upserted by the Stop hook). Cost estimates use the"
    echo "pricing table in hooks/lib/parse_usage.py — update it when prices change."
    echo ""
    echo "| updated | session | ticket | in | out | cache read | cache write | hit% | est. cost |"
    echo "|---|---|---|---|---|---|---|---|---|"
  } >> "$OUT_FILE"
fi

ROW="| $(date +%Y-%m-%d\ %H:%M) | $SESSION | $TICKET | $SUMMARY |"

# Upsert: drop any existing row for this session, then append the fresh one.
# -F: match the session marker literally, no regex interpretation.
if grep -qF "| $SESSION |" "$OUT_FILE"; then
  TMP="$(mktemp)" || exit 0
  grep -vF "| $SESSION |" "$OUT_FILE" > "$TMP" \
    && printf '%s\n' "$ROW" >> "$TMP" \
    && mv "$TMP" "$OUT_FILE"
else
  printf '%s\n' "$ROW" >> "$OUT_FILE"
fi
exit 0
