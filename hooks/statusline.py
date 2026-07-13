#!/usr/bin/env python3
"""Claude Code statusLine: "<model> | <repo> (<branch>) · $<cost>".

Reads the session JSON on stdin. When the branch carries a ticket, the cost is
that ticket's live total: the ledger's total for the ticket, EXCLUDING the
current session's own row, PLUS this session's live cost — current within the
turn and never double-counting the in-progress session. The ticket key isn't
printed: it's derived from the branch, so it's already visible in "(<branch>)".
Note the total is ticket-scoped, so on a stacked series it spans all branches
sharing the ticket, not just the current one.

Fails soft by design: any missing field degrades gracefully and it never
raises — a statusLine command that errors blanks the line.

python3-only (no jq), matching the cost hook. Lives in hooks/ beside
cost-tracker.sh only because that directory is already symlinked into
~/.claude; it is a statusLine command, not a hook.
"""
import json
import os
import re
import subprocess
import sys

# Same pattern lives in cost-tracker.sh (grep -oE) — keep the two in sync.
TICKET_RE = re.compile(r"[A-Z][A-Z0-9]+-[0-9]+")


def git_branch(cwd: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=1,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def ledger_path(cwd: str):
    for rel in (".claude-local/claude-costs.md", "docs/claude-costs.md"):
        p = os.path.join(cwd, rel)
        if os.path.isfile(p):
            return p
    return None


def ledger_sum(path: str, ticket: str, exclude_session: str) -> float:
    """Sum the est-cost column across rows matching `ticket`, skipping the
    current session's row (its live cost is added by the caller)."""
    total = 0.0
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.startswith("| 20"):  # data rows start with a date
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                # updated, session, ticket, in, out, cread, cwrite, hit%, resp, cost
                # (cost stays last, so cells[-1] holds it whether or not resp is present)
                if len(cells) < 9 or cells[2] != ticket:
                    continue
                if exclude_session and cells[1] == exclude_session:
                    continue
                m = re.search(r"[\d.]+", cells[-1])
                if m:
                    total += float(m.group())
    except Exception:
        pass
    return total


def main() -> int:
    try:
        d = json.load(sys.stdin)
    except Exception:
        print("claude")
        return 0

    model = (d.get("model") or {}).get("display_name") or "claude"
    ws = d.get("workspace") or {}
    cwd = ws.get("current_dir") or d.get("cwd") or "."
    repo = os.path.basename(cwd.rstrip("/")) or cwd
    live = float((d.get("cost") or {}).get("total_cost_usd") or 0.0)
    session = str(d.get("session_id") or "")[:8]

    branch = git_branch(cwd)
    line = f"{model} | {repo}" + (f" ({branch})" if branch else "")

    m = TICKET_RE.search(branch)
    if m:
        ticket = m.group()
        path = ledger_path(cwd)
        total = (ledger_sum(path, ticket, session) if path else 0.0) + live
        line += f" · ${total:.2f}"
    elif live:
        line += f" · ${live:.2f}"

    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
