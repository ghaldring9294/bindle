# Plan

Where bindle stands and what's next. The design and the reasons behind it are in [docs/design.md](docs/design.md); what changed in each version is in [CHANGELOG.md](CHANGELOG.md). Update this when work lands or priorities change.

## Where it stands (2026-11-22, v0.17.1)

- **The tool:** `install`, `new`, `attach`, `detach`, `doctor`, `sync`, `upgrade`, `outbox add|list`, `collect`; one Python implementation shared by the CLI and every bindle's hooks; 104 unit tests in CI (macOS, Linux and Windows) plus an end-to-end test against real Claude Code.
- **In use on three machines:** a personal laptop and a Windows PC with the personal bindle writable; a work machine with its domain bindle writable (notes, memories, rules, skills moved in) and a shared craft bindle read-only. Memories round-trip between machines through git, including from Windows.
- **Docs:** README (usage), docs/design.md (design), `/bindle` (how Claude in any session operates bindle), MIGRATION.md (what Claude follows to move a setup in), AGENTS.md (orientation for agents, including the rule that docs ship with each change), CHANGELOG.md.

## Next steps

**Road to 1.0 (the tool):**
1. **A public demo repo (`bindle-demo`).** Fixtures plus a cross-platform `setup` script that builds everything in `~/bindle-demo/` without touching real bindles: an `acme/` project with a `demo-acme` bindle (fake memories, private terms, a skill naming Acme specifics) and an empty `demo-craft`; names carry `demo-` because bindle names are unique per machine. README walkthrough, one session per domain: recall a memory and run `/demo-acme:release-notes`; save a memory; promote the skill to demo-craft (see the private-terms check catch "Acme"); remove it from demo-acme, attach demo-craft read-only, and see `/demo-craft:release-notes` still work and an edit to craft refused; a second domain (`globex/`) gets the skill but none of acme's memories; send globex a note from acme; improve the skill from globex with `--replace`. A `cleanup` script undoes it all. The contract test reuses the setup, so a change that breaks the walkthrough fails.
2. **Guard against Claude Code changes.** bindle relies on Claude Code behaviour it doesn't control (settings at the repo root or launch folder, `autoMemoryDirectory`, directory marketplaces and `--scope local`, machine-wide marketplace names, hook events, environment and the 10k cap, `Edit(//path/**)` rules, plugin `.mcp.json`, per-folder memory keys).
   - Turn `tests/e2e.sh` into a contract test: one named check per assumption, each failure naming the assumption that broke.
   - `bindle selftest`: run those checks in a scratch folder against the installed Claude Code (a few short sessions), clean up, report pass or fail per assumption. Friends can run it too.
   - `doctor` records the Claude Code version the last passing selftest ran on, and warns when `claude --version` differs.
   - docs/design.md "Claude Code constraints": link each assumption to its check.
   - Later, once public: a scheduled run (needs an API key as a repo secret; the owner's call).
3. **A fresh-user test:** someone follows only the README on a clean machine or account; fix what they trip on.
4. **Go public** (or add collaborators): the owner's step on GitHub. Then tag 1.0.

**Gaps found migrating a real setup (fix before 1.0):**
- Claude Code keeps one memory folder per launch folder, and on macOS each git repo is its own launch root. A domain folder holding several repos therefore has several old memory folders, and the domain-level attach doesn't reach sessions launched inside a repo. Done (2026-11-22): MIGRATION.md inventories every memory folder under the domain, maps per-repo memories to `projects/<repo>/`, treats files CLAUDE.md points Claude at (a lessons folder) as memory, and attaches the bindle to each repo the person launches from; the README explains launching from a repo. Still to do, three sides of the same gap (Claude Code doesn't inherit settings from parent folders, so each repo needs its own attach):
  - `bindle attach <bindle> <domain folder> --repos` (and `detach --repos`): attach to the domain folder and every git repo directly inside it in one command.
  - `doctor`: list repos inside an attached domain folder that have no bindle attached, with the command to fix them.
  - An opt-in session check (`bindle install --session-check`, the one thing that edits `~/.claude/settings.json`, removable): a user-level SessionStart hook that warns only when a session starts in a folder inside a registered domain folder with no bindle attached ("memories from this session won't go to acme; attach it: …"). Folders outside any domain stay silent.

**The owner's own setup (doesn't block 1.0):**
- Write personal's `rules.md` from the live global instructions, minus anything domain-specific, under 9,000 characters, including the boundary rule (work appears in personal only at a high, public level).
- Promotion pass at work: general lessons and `craft`/`both` memories from the work bindle move to craft, rewritten, through the outbox; the general global instructions go into craft's `rules.md` by hand. Craft is private for now (2026-11-22) while the workflow settles; once parts of it are ready to hand to others, make `craft-shared` (`--audience shared --writes explicit`) and promote those over.
- Later: a remote for the work bindle on storage the employer allows; delete the work machine's pre-bindle memory folder once the new setup has run for a while.

**Done:** Windows support (v0.6.0; verified on a real PC, including the read-only lock, 2026-11-22). The smaller gaps (v0.9.0–0.10.0): `doctor` checks the three names agree, `bindle outbox clean` and `remove`, `bindle list`, renaming documented, attach by name; promotion asks for the target. Ideas beyond 1.0 are in docs/design.md, "Later ideas".

## Log

- **2026-07:** first prototype: base plus layers through a symlink farm, copied memory, a memory taxonomy. Archived; the model survived, the mechanics didn't.
- **2026-11-20:** craft versus context as the line; one repo per domain; memory boundary tags; prior-art survey; found `autoMemoryDirectory`.
- **2026-11-21:** spike confirmed native mechanisms (memory location per folder, plugin skills and hooks per folder, read-only memory through a hook). One model for every bindle, attached per folder, all on and one writable. CLI rebuilt (v0.2.0), personal reshaped and migrated from the laptop, round trip verified.
- **2026-11-21:** sync hooks; rules through hooks and read-only locks (v0.3.0); memories organized by project; promotion through a hash-verified outbox, `audience` and `writes`, a craft bindle (v0.4.0); the work setup moved onto bindles; notes support, scratch notes, secret checks for notes, union merge for indexes (v0.4.x).
- **2026-11-21:** CI; README rewritten for a general audience; an independent review (16 findings) led to one Python implementation, a CLI package, hardened promotion and a wider secret check (v0.5.0); trust warnings (v0.5.1); guardrails-not-gates recorded as a principle; MCP servers in a bindle verified; design doc written.
- **2026-11-21:** v0.6.0: Windows support (Python launcher for hooks, POSIX lock paths, install without symlinks, LF everywhere); CI green on macOS, Linux and Windows.
- **2026-11-21:** Windows verified on a real PC (memory written there reached GitHub). v0.6.1: session start commits memories a skipped SessionEnd left (closing the app skipped it); README covers two GitHub accounts on one machine.
- **2026-11-22:** read-only bindle and lock rule verified on Windows; README notes MCP commands on Windows. MIT license added. v0.7.0: `bindle attach <name>` looks in `~/bindles/` (or `$BINDLE_HOME`). v0.8.0: `bindle terms` and a doctor warning for empty private terms; `/bindle` rewritten so Claude handles attach/detach requests in any session; docs-with-every-change rule. v0.8.1: attach re-points a bindle that moved after a detach (found moving craft to `~/bindles/craft`).
- **2026-11-22:** v0.9.0: `doctor` flags bindle names that disagree; `bindle outbox clean`; renaming documented; design doc's open questions became "Later ideas"; PLAN reorganized around 1.0.
- **2026-11-22:** v0.10.0: `bindle list`, `bindle outbox remove`; `/bindle-promote` asks which bindle to collect into.
- **2026-11-22:** v0.11.0: a registry (`~/bindles/registry.json`) so domain bindles are found by name anywhere; bare `bindle` prints help. 
- **2026-11-22:** v0.12.0–0.13.0: `bindle upgrade --all`, `bindle sync --all`.
- **2026-11-22:** v0.14.0: one-step promotion (`bindle promote`); the outbox only holds items waiting for a target on another machine; `outbox list --all`; `/bindle-promote` built around plain-language requests.
- **2026-11-22:** v0.15.0: the `note` kind (reminders for another domain land in its `notes/inbox.md`, mentioned at session start). Next: the demo repo.
- **2026-11-22:** v0.16.0: `promote --replace` and `--dry-run`, so promoted items can be updated from any domain.
- **2026-11-22:** v0.17.0: private terms are a confirmation (`--allow`), secrets a hard stop; promotion skill covers moving, removing elsewhere, rules and craft-to-domain copies.
- **2026-11-22:** v0.17.1: every bindle ignores `.claude/settings.local.json` (found attaching sp read-only to craft's folder); README covers writing craft with a work bindle read-only.
