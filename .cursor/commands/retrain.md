---
description: Model retraining workflow — triggered by drift alert or manual request
allowed-tools:
  - Bash(python:*)
  - Bash(mlflow:*)
  - Bash(dvc:*)
  - Read
  - Edit
---

# /retrain

Execute retraining with quality gates + safe promotion. CONSULT-class
(or STOP if triggered by incident_active / drift_severe).

## Triggers
- PSI drift alert (ADR-006)
- Scheduled periodic retrain (monthly/quarterly)
- Concept drift detected (`/performance-review` → sliced AUC drop)
- Manual request with documented rationale

## Steps (invoke skill `model-retrain`)
1. Snapshot current baseline (metrics, PSI, slices)
2. Retrain on updated data window (with Pandera validation)
3. Run ALL quality gates (D-12):
   - Primary metric ≥ threshold, no regression > 5%
   - Fairness: DIR ≥ 0.80 per attribute + intersectional (C6)
   - Leakage: metric < 0.99 (D-06 escalation)
   - Latency: p95 ≤ 1.2× current prod
4. Register in MLflow as `Staging` (CONSULT — Tech Lead)
5. Run Champion/Challenger gate (McNemar + bootstrap ΔAUC, ADR-008)
6. If PROMOTE → transition to `Production` (STOP — Platform Engineer via PR)
7. If KEEP/BLOCK → open issue; fall back to champion

## Escalation to STOP
- Marginal fairness (DIR ∈ [0.80, 0.85])
- Suspicious metric > 0.99 (D-06)
- Regression > 5% on any slice

**Canonical**: `.windsurf/skills/model-retrain/SKILL.md` + `.windsurf/workflows/retrain.md`.
