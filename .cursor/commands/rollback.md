---
description: Emergency rollback of a production ML service (STOP-class)
allowed-tools:
  - Bash(kubectl:*)
  - Bash(argo:*)
  - Bash(mlflow:*)
  - Read
  - Edit
---

# /rollback

Invoke when an incident is active and the decision has been made to revert
a deploy. For "is this even a real problem?" questions, start with `/incident`.

**Authorization: STOP** for every step, even in dev. Propose, wait for approval.

## Steps
1. Triage (15 min budget) — confirm user impact; check if Argo auto-aborted canary
2. Load `.windsurf/skills/rollback/SKILL.md` — execute the 7-step procedure:
   - Confirm incident → identify target revision → abort Argo rollout → undo deploy
   - Revert MLflow model if artifact changed
   - Silence related alerts
   - Verify (error rate, latency, score distribution, `/ready`)
   - Open audit issue tagged `rollback,incident`

## Followups (5 business days)
- [ ] Blameless RCA in `docs/incidents/{date}-{service}.md`
- [ ] Regression test for the ROOT cause
- [ ] Skill update if gap exposed

## Not this
- Not a "just undo" button — requires triage
- Does not replace postmortem — triggers it
- Does not handle data corruption (separate runbook)

**Canonical**: `.windsurf/skills/rollback/SKILL.md` + `.windsurf/workflows/rollback.md`.
