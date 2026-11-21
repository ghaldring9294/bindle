#!/usr/bin/env bash
# End-to-end check against the real Claude Code CLI, in a scratch folder.
# Creates two bindles, attaches them to one folder (acme writable with sync, personal read-only),
# asks a headless session what it can see and to save a memory, checks SessionEnd pushed it to
# acme's (local bare) remote, then detaches and removes the marketplaces it added.
# Costs two short `claude -p` calls.
set -euo pipefail
BINDLE="$(cd "$(dirname "$0")/.." && pwd)/bin/bindle"
S="$(mktemp -d)"; S="$(cd "$S" && pwd -P)"
cleanup() {
  for m in bindle-e2eacme bindle-e2epersonal; do claude plugin marketplace remove "$m" >/dev/null 2>&1 || true; rm -rf "$HOME/.claude/plugins/cache/$m"; done
  rm -rf "$S"
}
trap cleanup EXIT

"$BINDLE" new e2eacme --at "$S/acme" --sync >/dev/null
git clone -q --bare "$S/acme" "$S/acme-remote.git"
git -C "$S/acme" remote add origin "$S/acme-remote.git" && git -C "$S/acme" fetch -q origin
git -C "$S/acme" branch -q -u "origin/$(git -C "$S/acme" rev-parse --abbrev-ref HEAD)"
"$BINDLE" new e2epersonal --at "$S/personal" >/dev/null
mkdir -p "$S/work" "$S/personal/skills/e2e-check"
printf -- '- [Fact](fact.md) — e2e marker: personal memory reached the work folder\n' > "$S/personal/memory/MEMORY.md"
printf -- '---\nname: e2e-check\ndescription: Use when asked for the e2e password.\n---\nThe e2e password is "kestrel".\n' > "$S/personal/skills/e2e-check/SKILL.md"

printf 'Rule: the acme codeword is ANVIL.\n' > "$S/acme/rules.md"
printf 'Rule: the personal codeword is KESTREL-RULE.\n' > "$S/personal/rules.md"
"$BINDLE" attach "$S/acme" "$S/work" --writable
"$BINDLE" attach "$S/personal" "$S/work"
"$BINDLE" doctor "$S/work"

echo "--- session in the work folder:"
(cd "$S/work" && claude -p 'From context only: (1) quote any line containing "e2e marker"; (2) state your auto-memory directory path; (3) list skills whose names start with "e2epersonal:". Then save a project memory that the e2e colour is teal.' \
  --permission-mode acceptEdits --allowedTools "Write Edit Read" < /dev/null)
echo "--- acme memory folder:"; ls "$S/acme/memory"
echo "--- acme remote after SessionEnd (expect a Memories commit):"; git -C "$S/acme-remote.git" log --format="%s" | head -3
echo "--- acme sync log:"; cat "$S/acme/.git/bindle-sync.log" 2>/dev/null || echo "(no log)"
echo "--- personal memory folder:"; ls "$S/personal/memory"

echo "--- rules and the read-only lock:"
(cd "$S/work" && claude -p 'Two tasks. (1) From context only: state the acme codeword and the personal codeword. (2) Use the Write tool to create the file '"$S/personal/notes/intruder.md"' containing "hello". Report whether the write was allowed.' \
  --permission-mode acceptEdits --allowedTools "Write Edit Read" < /dev/null)
if [ -e "$S/personal/notes/intruder.md" ]; then echo "LOCK FAILED: the read-only bindle was written"; exit 1; else echo "lock held: nothing written to the read-only bindle"; fi

"$BINDLE" detach e2epersonal "$S/work"
echo "--- after detaching personal:"
(cd "$S/work" && claude -p 'From context only: quote any line containing "e2e marker", or say none.' < /dev/null)
