# Operating manual (base)

Generic conventions for every project using this toolkit. Personal and
project/employer layers extend these; they never relax the privacy rules below.

## Context discipline — tiered retrieval

Read cheap maps before expensive files. Progressive disclosure: pay for depth
only when the map says to.

1. **Tier 0 — Index.** If `docs/index.md` exists, read it FIRST: one line per doc.
   Use it to decide what to open.
2. **Tier 1 — Summaries.** Prefer `docs/architecture.md`, module one-pagers, and a
   ticket file's top section over reading source to build understanding.
3. **Tier 2 — Source.** Open surgically, only where Tiers 0–1 point. Don't grep the
   whole tree when a map answers the question.

When broad exploration is unavoidable, dispatch a subagent and take back only its
distilled summary — keep this session's context lean.

## Doc maintenance

- After changes to the data model, module boundaries, or conventions, update
  `docs/architecture.md` and `docs/index.md` in the same session.
- Prefer mermaid (ERD / sequence / flow) for structural information — token-dense and
  unambiguous.
- Keep `architecture.md` STABLE: no ticket-specific or fast-changing content. Volatile
  detail belongs in ticket files.
- Long-lived reference material (data dictionaries, API contracts, mermaid diagram sets) is
  Tier 1 too: keep it in `docs/` (team-visible) or `.claude-local/docs/` (private, per the
  privacy rule), list it in `docs/index.md`, and keep it stable — not in ticket files.

## Memory taxonomy

Organize a project's auto-memory (`~/.claude/projects/<slug>/memory/`) by **type** — one
folder per Claude-native type: `reference/` (what is), `feedback/` (how to work), `project/`
(ongoing work + state), `user/` (who), plus `skill/` (skill addenda). `MEMORY.md` is the
Tier-0 index, grouped by type, one line per memory, linking into the folders. Tag in-flight
state `[volatile]`; keep the stable majority cache-friendly. Full scheme + the per-repo
keying gotcha: `templates/memory-taxonomy.md`.

## Personal context — `.claude-local/`

If `.claude-local/` exists, it is private personal context, authoritative for this project.

- Read `.claude-local/index.md` (if present) as part of Tier 0.
- NEVER reference `.claude-local` or its contents in code, comments, commit messages, PR
  descriptions, or any output other people will see.
- Never suggest committing it; it is intentionally excluded from version control.

## General

- Ask before destructive or outward-facing actions (dropping data, force-push, rewriting
  history, publishing).
- Record non-obvious design decisions in the active ticket's decision log with a one-line
  rationale.

## Personal layer

Your personal layer, if installed, loads at the end here; if absent, the import below is silently
ignored. Keep this base file employer-agnostic — personal preferences belong in the personal layer,
employer/client context in that domain's professional layer (loaded per-project via `.claude-local/`).

@~/.claude/CLAUDE.personal.md
