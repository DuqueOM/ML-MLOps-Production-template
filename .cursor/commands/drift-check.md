---
description: Run PSI drift analysis for one or all services
allowed-tools:
  - Bash(python:*)
  - Bash(kubectl:*)
  - Read
---

# /drift-check

Covers BOTH data drift (PSI per feature) AND concept drift (sliced
performance vs baseline).

## Data drift
1. Load `eda/artifacts/02_baseline_distributions.pkl` (D-15)
2. Run `monitoring/drift_cronjob.py` against recent production window
3. PSI per feature using QUANTILE bins (D-08) — never uniform
4. Alert threshold: PSI > 0.2 (moderate), > 0.3 (severe, STOP-class)

## Concept drift (requires ground truth)
1. `monitoring/performance_monitor.py` — JOINs predictions with labels
2. Sliced AUC/F1/Brier per `configs/slices.yaml`
3. Compare to baseline from last retrain
4. Escalate if global AUC drop > 0.02 OR any slice > 0.05

## Outputs
- `reports/drift-{date}.md` with PSI table + degrading slices
- Metrics to Prometheus Pushgateway
- If severe: chain to `/retrain`

**Canonical**: `.windsurf/skills/drift-detection/SKILL.md` + `.windsurf/workflows/drift-check.md`.
