---
description: ML service incident response — diagnose, mitigate, resolve, document
allowed-tools:
  - Bash(kubectl:*)
  - Bash(curl:*)
  - Read
  - Grep
---

# /incident

Triage before action. Most "incidents" are dashboard blips or upstream issues.

## 1. Classify severity (5 min)
- P1: user-facing 5xx > 1% OR complete outage
- P2: SLO burn > 2x budget, automated canary aborted
- P3: degraded performance (latency, sliced AUC drop)
- Dashboard blip: <1% errors, resolves in 2 min → no incident

## 2. Collect evidence pack
- `kubectl get pods,events -n <service-ns> --sort-by=.lastTimestamp`
- `kubectl logs -l app=<service> --tail=100 --previous`
- Prometheus: request rate, error rate, p95 latency, score distribution
- Argo Rollouts status; recent deploys (`ops/audit.jsonl`)

## 3. Hypothesis → action mapping
| Hypothesis | Action |
|---|---|
| Bad deploy | `/rollback` |
| Data drift | `/drift-check` → `/retrain` if confirmed |
| Upstream outage | Silence alerts, escalate upstream |
| Infra capacity | Scale HPA ceiling temporarily |
| Concept drift | `/performance-review` → retrain |

## 4. Document
- Every incident → `docs/incidents/{date}-{service}.md` (blameless RCA)
- Append audit entry

**Canonical**: `.windsurf/workflows/incident.md`.
