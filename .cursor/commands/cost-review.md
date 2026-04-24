---
description: Monthly cloud cost review — collect, analyze, optimize, document
allowed-tools:
  - Bash(gcloud:*)
  - Bash(aws:*)
  - Read
---

# /cost-review

Monthly ritual. AUTO to collect + analyze; CONSULT before applying any
cost-cutting change.

## 1. Collect (AUTO)
- GCP: `gcloud billing accounts get-iam-policy` + Cost Export BigQuery
- AWS: `aws ce get-cost-and-usage` (Cost Explorer)
- Kubernetes: `kubectl top pods --all-namespaces` + HPA history

## 2. Analyze
Flag if ANY:
- Monthly spend > 1.2× budget → STOP-class escalation
- HPA rarely scales down (reserved capacity waste)
- Idle MLflow experiments > 30 days
- Oversized requests (`common_utils/agent_context.py` reports underutilization)
- Storage without lifecycle policy

## 3. Optimizations by priority
| Change | Savings | Risk | Mode |
|---|---|---|---|
| Right-size requests | 10-30% | Low (HPA) | AUTO |
| HPA min=1 → min=2 (dev) | Negative | Low | Skip if production |
| Reserved instances for steady workloads | 20-40% | Medium (lock-in) | CONSULT |
| Archive old MLflow runs | 5% | Low | AUTO |
| Region consolidation | Varies | High | STOP |

## 4. Document
- `docs/cost-reviews/YYYY-MM.md`
- Append audit entry
- If action taken → CHANGELOG

**Canonical**: `.windsurf/skills/cost-audit/SKILL.md` + `.windsurf/workflows/cost-review.md`.
