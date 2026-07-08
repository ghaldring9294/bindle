#!/usr/bin/env python3
"""Sum token usage from a Claude Code transcript JSONL.

Prints one pipe-separated summary row (no leading/trailing pipes):
    in | out | cache_read | cache_write | hit% | $cost

Each transcript line is self-contained JSON; assistant messages carry a
`usage` object. We dedupe on message id + request id so streamed duplicates
aren't double counted. The whole transcript is summed each call, so the
result is the session's cumulative total — the Stop hook upserts it as one
row per session (see cost-tracker.sh).

PRICING is USD per million tokens. Verified 2026-07-08 against the claude-api
skill catalog (cached 2026-06-24). It WILL go stale — re-check at
https://platform.claude.com/docs/en/pricing when accuracy matters.
Cache-read = 0.1x input, cache-write = 1.25x input (5-minute TTL). Two known
simplifications: (1) cache writes are assumed 5-minute TTL; 1-hour writes cost
2x and would be undercounted; (2) no long-context (>200K) tier — Opus 4.8 has
no long-context premium, but other models may. Unknown models fall back to
DEFAULT_PRICE so the pipeline never breaks.
"""
import json
import sys

# model substring: (input, output, cache_read, cache_write) per MTok
PRICING = {
    "fable":  (10.0, 50.0, 1.00, 12.50),
    "opus":   (5.0,  25.0, 0.50, 6.25),
    "sonnet": (3.0,  15.0, 0.30, 3.75),
    "haiku":  (1.0,  5.0,  0.10, 1.25),
}
DEFAULT_PRICE = PRICING["sonnet"]


def price_for(model: str):
    m = (model or "").lower()
    for key, p in PRICING.items():
        if key in m:
            return p
    return DEFAULT_PRICE


def main(path: str) -> int:
    tin = tout = cread = cwrite = 0
    cost = 0.0
    seen = set()

    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return 1

    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = rec.get("message") or {}
            usage = msg.get("usage") or rec.get("usage")
            if not isinstance(usage, dict):
                continue

            key = (msg.get("id"), rec.get("requestId") or rec.get("uuid"))
            if key in seen:
                continue
            seen.add(key)

            i = int(usage.get("input_tokens") or 0)
            o = int(usage.get("output_tokens") or 0)
            cr = int(usage.get("cache_read_input_tokens") or 0)
            cw = int(usage.get("cache_creation_input_tokens") or 0)

            tin += i
            tout += o
            cread += cr
            cwrite += cw

            pi, po, pcr, pcw = price_for(msg.get("model") or rec.get("model") or "")
            cost += (i * pi + o * po + cr * pcr + cw * pcw) / 1_000_000

    denom = tin + cread
    hit = (100.0 * cread / denom) if denom else 0.0

    def k(n: int) -> str:
        return f"{n/1000:.1f}k" if n >= 1000 else str(n)

    print(f"{k(tin)} | {k(tout)} | {k(cread)} | {k(cwrite)} | {hit:.0f}% | ${cost:.2f}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
