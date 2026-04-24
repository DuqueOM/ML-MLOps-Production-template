---
description: Create a new Architecture Decision Record with proper structure and numbering
allowed-tools:
  - Read
  - Edit
  - Bash(ls:*)
---

# /new-adr

Create an ADR whenever a decision involves trade-offs, alternatives
considered, or a posture that might be revisited later.

## When to use
- Architectural choice (framework, pattern, topology)
- "Buy vs build" decision
- Rejected option worth recording (CarVision removal, Airflow not adopted)
- Deferred decision with explicit revisit triggers (like ADR-013)

## Format
```
docs/decisions/ADR-NNN-short-slug.md

## Status
Accepted | Proposed | Superseded by ADR-XXX

## Date
YYYY-MM-DD

## Context
What problem? What constraints? What measurements justified this?

## Options considered
- Option A (pros, cons)
- Option B (pros, cons)
- Option C (why rejected)

## Decision
Chosen option + WHY the others don't fit TODAY.

## Revisit triggers
Measurable signals that would cause re-evaluation.

## Consequences
- Positive
- Negative
- Mitigations

## Related
ADRs, skills, workflows that depend on or reference this.
```

## Numbering
Next number = last ADR + 1. As of v1.9.0: next is **ADR-014**.
```bash
ls docs/decisions/ADR-*.md | sort | tail -1
```

**Canonical**: `.windsurf/workflows/new-adr.md`. Examples: ADR-010 (dynamic
behavior), ADR-013 (GitOps deferred).
