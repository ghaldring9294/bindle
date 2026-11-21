---
name: bindle-promote
description: Promote a general lesson, skill or command from the current domain's bindle to another bindle (usually personal, or a shared craft bindle) through the source bindle's outbox. Use when the user says something is a general lesson worth keeping elsewhere, asks to promote, or asks what could be promoted.
---

# Promote through the outbox

Material leaves a bindle only as text the person reviewed and approved as general. You do the judgment (drafting); the `bindle` CLI does every write and the checks.

## 1. Find the source and candidates

- The source is the bindle that's writable in this folder (`bindle doctor` shows it). Promote out of it only.
- Candidates: what the person points to, or memories tagged `boundary: craft` or `both` (in `memory/` and `projects/*/`). `context` memories are never promoted.
- Read only the source bindle's memories. Never read another domain's memories to look for candidates.

## 2. Draft a general rewrite of each

- Keep the lesson; drop the domain: no organization, product, repo, system, ticket, people or data names. A reader outside this domain should find it true and useful.
- A memory keeps the memory format (frontmatter `name`, `description`, `type`, `boundary: craft`; body with **Why:** and **How to apply:**).
- A skill or command: rewrite its text the same way into a scratch folder; don't edit the original.
- Write each draft to a scratch file. Never write into the target bindle.

## 3. Show and get approval

Show each draft beside the original, briefly say what you removed, and ask the person to approve, edit or drop each one. Nothing moves without a yes for that item.

## 4. Add approved drafts to the outbox

```
bindle outbox add <source bindle> <draft> --kind memory|skill|command --name <slug> --description "<one line>"
```

It refuses a draft that names a term from the source's `private-terms.txt` or looks like it holds a secret; fix the draft, show the change, and retry. If `private-terms.txt` is empty, suggest terms for the person to add first (organization, products, repos, ticket prefixes).

## 5. Collect, if the person wants it now

```
bindle collect <source bindle> --into <target bindle> --items <slug>[,<slug>]
```

Name the items, so the permission prompt shows exactly what moves. It rechecks, copies into the target, adds memory index lines, marks the items collected, and commits both bindles. Collecting can also wait for a session in the target's folder.
