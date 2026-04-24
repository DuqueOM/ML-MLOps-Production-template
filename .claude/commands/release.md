---
description: Full multi-cloud release process — build, deploy GCP + AWS, verify, rollback if needed
allowed-tools:
  - Bash(git:*)
  - Bash(gh:*)
  - Bash(kubectl:*)
  - Read
---

# /release

CONSULT for staging, STOP for production. Respects ADR-011 environment
promotion gates (D-26).

## Pre-flight (AUTO)
1. CI green on `main` (all jobs including `contract-check`, `rule-audit`)
2. CHANGELOG has `[unreleased]` → rename to `[vX.Y.Z] - YYYY-MM-DD`
3. Create `releases/vX.Y.Z.md` following v1.8.x pattern
4. Run `skill release-checklist` for the pre-release gate

## Promotion chain (single workflow, reusable deploy-common.yml)
```
build (AUTO) → dev (AUTO) → staging (CONSULT, 1 reviewer)
            → 15min soak
            → prod (STOP, 2 reviewers, tag-only)
```

## Tag + push
```bash
git tag -s vX.Y.Z -m "Release vX.Y.Z"
git push origin main --tags
```

## Verify post-deploy
- Smoke test `/ready` on all regions
- Dashboards show healthy rates
- No rollback alerts in first 30 min

## If rollback needed
→ Invoke `/rollback` immediately (STOP-class)

**Canonical**: `.windsurf/skills/release-checklist/SKILL.md` + `.windsurf/workflows/release.md`.
