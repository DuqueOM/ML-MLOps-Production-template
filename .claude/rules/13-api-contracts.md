---
paths:
  - "**/app/*.py"
  - "**/app/schemas.py"
  - "**/tests/contract/**"
  - "**/scripts/refresh_contract.py"
---

# API Contract Rules (D-28)

## Invariants
- Public request/response schemas live in `app/schemas.py` — **single source of truth**
- `tests/contract/openapi.snapshot.json` is COMMITTED and auto-generated
- Breaking changes require BOTH:
  1. `python scripts/refresh_contract.py` regenerates the snapshot
  2. `app.version` bumped (semver — minor for additive, major for breaking)
- CI job `contract-check` DIFFS the snapshot against the live OpenAPI spec
  and FAILS if they diverge without a version bump

## What counts as a breaking change
- Removing a field from request/response
- Making an optional field required
- Changing a field's type (str → int, etc.)
- Renaming an endpoint or HTTP method
- Changing status codes for existing error cases

## What counts as additive
- Adding optional request/response fields with defaults
- Adding new endpoints
- Adding new HTTP status codes for NEW error cases

## Workflow
```
Edit app/schemas.py → python scripts/refresh_contract.py
  → git diff tests/contract/openapi.snapshot.json
  → if diff > 0:
      bump app.version (minor or major)
      commit both files together
      add CHANGELOG entry
```

## Forbidden
- Committing a snapshot change without a version bump (CI rejects)
- Editing `openapi.snapshot.json` by hand
- Breaking change without ADR if the service has ≥ 1 consumer

See `.windsurf/rules/14-api-contracts.md`, AGENTS.md D-28.
