#!/usr/bin/env bash
# Regression tests for the cost loop. bash + python3 only, matching the toolkit.
# These lock the two behaviours whose bugs were silent in review: the pricing
# math (parse_usage.py) and the ticket-scoped, current-session-excluding ledger
# sum (statusline.py). Run: ./test/run.sh  (exits nonzero on any failure).
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS="$DIR/../hooks"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0

check() {  # check <label> <got> <want>
  if [ "$2" = "$3" ]; then
    echo "PASS $1"
  else
    echo "FAIL $1: got [$2] want [$3]"
    fail=1
  fi
}

# --- parse_usage.py: token sums, dedup on (id,requestId), Opus 4.8 pricing ---
# Two unique assistant records + one duplicate of the first (must be ignored).
# in=1500 out=2100 cread=5000 cwrite=8000; cost @ $5/$25/$0.50/$6.25 = $0.1125.
cat > "$TMP/transcript.jsonl" <<'EOF'
{"message":{"id":"m1","model":"claude-opus-4-8","usage":{"input_tokens":1000,"output_tokens":2000,"cache_read_input_tokens":4000,"cache_creation_input_tokens":8000}},"requestId":"r1"}
{"message":{"id":"m2","model":"claude-opus-4-8","usage":{"input_tokens":500,"output_tokens":100,"cache_read_input_tokens":1000,"cache_creation_input_tokens":0}},"requestId":"r2"}
{"message":{"id":"m1","model":"claude-opus-4-8","usage":{"input_tokens":1000,"output_tokens":2000,"cache_read_input_tokens":4000,"cache_creation_input_tokens":8000}},"requestId":"r1"}
EOF
# resp=2: two unique (id,requestId) records; the m1/r1 duplicate is not counted.
got="$(python3 "$HOOKS/lib/parse_usage.py" "$TMP/transcript.jsonl")"
check "parse_usage" "$got" "1.5k | 2.1k | 5.0k | 8.0k | 77% | 2 | \$0.11"

# --- statusline.ledger_sum: sum a ticket, exclude current session + other tickets ---
# Ledger carries the resp column (cost stays last) — guards cells[-1] cost lookup.
cat > "$TMP/ledger.md" <<'EOF'
| updated | session | ticket | in | out | cache read | cache write | hit% | resp | est. cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-08 10:00 | OTHER1 | ACME-1234 | 1k | 1k | 1k | 1k | 90% | 10 | $1.00 |
| 2026-07-08 10:05 | OTHER2 | ACME-1234 | 1k | 1k | 1k | 1k | 90% | 20 | $2.00 |
| 2026-07-08 10:10 | CURRENTX | ACME-1234 | 1k | 1k | 1k | 1k | 90% | 30 | $5.00 |
| 2026-07-08 09:00 | ZZZZ | ACME-9999 | 1k | 1k | 1k | 1k | 90% | 40 | $99.00 |
EOF
got="$(python3 -c "import sys;sys.path.insert(0,'$HOOKS');import statusline;print(round(statusline.ledger_sum('$TMP/ledger.md','ACME-1234','CURRENTX'),2))")"
check "statusline.ledger_sum" "$got" "3.0"

[ "$fail" -eq 0 ] && echo "ALL PASS" || echo "FAILURES"
exit "$fail"
