---
description: Incident workflow for leaked secrets — halt pipeline, rotate, audit, post-mortem
allowed-tools:
  - Bash(gcloud:*)
  - Bash(aws:*)
  - Bash(gh:*)
  - Bash(git:*)
  - Read
---

# /secret-breach

STOP-class for EVERY step. Emergency path (vs scheduled rotation runbook).

## 1. HALT pipeline (immediate)
- Pause CI/CD: `gh workflow disable <workflow>`
- Lock main branch (admin)
- Revoke any session tokens tied to the leaked credential
- Do NOT `git push` until contained

## 2. Classify (2 min)
- What leaked? (API key, cloud cred, DB password, signing key)
- Where? (git history, log, PR, chat, screenshot)
- Blast radius: what does this cred authorize?
- When? (timestamp of exposure)

## 3. Revoke + rotate (D-17, D-18)
- Cloud: revoke in console, rotate IRSA trust policy / WI pool
- DB: kill sessions, rotate password
- Signing: rotate Cosign identity; verify previous signatures

## 4. Audit access
- Cloud audit logs for abnormal calls since exposure
- Data exfiltration signals: egress spikes, new IAM roles
- If > 1 hour window: assume compromise, re-rotate dependent secrets

## 5. Clean history
- If in git: `git filter-repo` or BFG to remove from history
- Force-push (coordinate with team)
- Invalidate cached forks

## 6. Notify
- Internal: #security channel + on-call owner
- Customers: only if data exposure is confirmed (legal review)
- Regulators: per jurisdiction (GDPR 72h, SEC material, etc.)

## 7. Post-mortem (5 business days)
- `docs/incidents/{date}-secret-breach.md`
- Root cause (not "someone made a mistake")
- Corrective: pre-commit gitleaks? Rotate automation? Training?

**Canonical**: `.windsurf/skills/secret-breach-response/SKILL.md` + workflow `.windsurf/workflows/secret-breach.md`.
