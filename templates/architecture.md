# Architecture (Tier 1 — STABLE)

Rules for this file:
- STABLE content only: data model, boundaries, conventions. No ticket-specific
  or fast-changing detail — that belongs in ticket files. Stability keeps this
  doc cache-friendly and trustworthy.
- Update it in the same session as any change to the data model or boundaries.
- Prefer mermaid: token-dense, unambiguous.

## System overview

<!-- 3-6 sentences: what this system does, for whom, key external dependencies. -->

## Data model

```mermaid
erDiagram
    %% Core entities and relationships. Attributes only where they carry
    %% design meaning (keys, discriminators, soft-delete flags).
    USER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
```

## Module boundaries

```mermaid
flowchart LR
    %% Who talks to whom, and through what (API, queue, job).
    API[Public API] --> SVC[Domain services]
    SVC --> DB[(Primary DB)]
    SVC --> Q[[Job queue]]
```

## Conventions

- <!-- naming, error handling, migration policy, testing expectations -->

## Key decisions (long-lived)

| decision | rationale | date |
|---|---|---|
| <!-- e.g. soft deletes everywhere --> | <!-- audit requirements --> | |
