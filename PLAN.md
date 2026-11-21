# Plan

Where bindle stands and what's next. The design and the reasons behind it are in [docs/design.md](docs/design.md); what changed in each version is in [CHANGELOG.md](CHANGELOG.md). Update this when work lands or priorities change.

## Where it stands (2026-11-21, v0.5.1)

- **The tool:** `install`, `new`, `attach`, `detach`, `doctor`, `sync`, `upgrade`, `outbox add|list`, `collect`; one Python implementation shared by the CLI and every bindle's hooks; 104 unit tests in CI (macOS, Linux and Windows) plus an end-to-end test against real Claude Code.
- **In use on two machines:** a personal laptop with the personal bindle writable; a work machine with its domain bindle writable (notes, memories, rules, skills moved in) and a shared craft bindle read-only. Memories round-trip between machines through git.
- **Docs:** README (usage), docs/design.md (design), MIGRATION.md (what Claude follows to move a setup in), AGENTS.md (orientation for agents), CHANGELOG.md.

## Next steps

1. **Write personal's `rules.md`** from the live global instructions, minus anything domain-specific, under 9,000 characters, including the boundary rule (work appears in personal only at a high, public level).
2. ~~**Windows support.**~~ Done in v0.6.0, and verified on a Windows PC with Claude Code (in the desktop app): install, attach, detach after a move, skills, hooks through Git Bash, `autoMemoryDirectory` with a `C:\\` path, and a memory synced to GitHub. Not yet seen on Windows: the `//c/` lock rule (needs a read-only bindle there).
3. **Promotion pass at work:** general rules, lessons and `craft`/`both` memories from the work bindle and the machine's global instructions move to craft, rewritten, through the outbox.
4. **A public demo repo (`bindle-demo`).** A toy project laid out like a domain root, with its `.bindle/` folded in (`"demo": true`, sync off) and a README walkthrough: clone, attach, see a memory recalled and a skill run, watch a new memory land, try detach and a second read-only bindle. It doubles as the end-to-end test fixture, so a change that breaks the walkthrough fails the test.
5. **Smaller gaps, as needed:** `bindle rename`, a `doctor` check that the three names (bindle.json, plugin.json, marketplace.json) agree, cleaning up collected outbox items, the `~/bindles/` collective view, and the open questions in the design doc (per-repo notes, skill addendums, remote allowlist, freshness stamps).
6. **Later:** a remote for the work bindle on storage the employer allows; delete the work machine's pre-bindle memory folder once the new setup has run for a while.

## Log

- **2026-07:** first prototype: base plus layers through a symlink farm, copied memory, a memory taxonomy. Archived; the model survived, the mechanics didn't.
- **2026-11-20:** craft versus context as the line; one repo per domain; memory boundary tags; prior-art survey; found `autoMemoryDirectory`.
- **2026-11-21:** spike confirmed native mechanisms (memory location per folder, plugin skills and hooks per folder, read-only memory through a hook). One model for every bindle, attached per folder, all on and one writable. CLI rebuilt (v0.2.0), personal reshaped and migrated from the laptop, round trip verified.
- **2026-11-21:** sync hooks; rules through hooks and read-only locks (v0.3.0); memories organized by project; promotion through a hash-verified outbox, `audience` and `writes`, a craft bindle (v0.4.0); the work setup moved onto bindles; notes support, scratch notes, secret checks for notes, union merge for indexes (v0.4.x).
- **2026-11-21:** CI; README rewritten for a general audience; an independent review (16 findings) led to one Python implementation, a CLI package, hardened promotion and a wider secret check (v0.5.0); trust warnings (v0.5.1); guardrails-not-gates recorded as a principle; MCP servers in a bindle verified; design doc written.
- **2026-11-21:** v0.6.0: Windows support (Python launcher for hooks, POSIX lock paths, install without symlinks, LF everywhere); CI green on macOS, Linux and Windows.
- **2026-11-21:** Windows verified on a real PC (memory written there reached GitHub). v0.6.1: session start commits memories a skipped SessionEnd left (closing the app skipped it); README covers two GitHub accounts on one machine.
