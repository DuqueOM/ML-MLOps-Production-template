---
description: Monthly sliced-performance review using ground-truth metrics — detect silent concept drift, document findings
allowed-tools:
  - Bash(python:*)
  - Read
---

# /performance-review

Monthly review of closed-loop monitoring output. Detects concept drift
even when PSI is flat (ADR-007).

## 1. Load 30-day window
```bash
python -m {service}.monitoring.performance_monitor --window 30d --slices configs/slices.yaml
```

## 2. Global metrics
Compare to baseline (last retrain):
- AUC drop > 0.02 → investigate
- F1 drop > 0.05 → investigate
- Brier increase > 0.01 → calibration issue

## 3. Sliced metrics
For each `slice_name` in `configs/slices.yaml`:
- Identify top-5 worst slices by AUC drop
- Flag slices with < 30 samples (unreliable)
- Highlight NEW slices (entered the system this month)

## 4. Degrading cohorts
- Country/channel regressions → feature drift
- Score-bucket miscalibration → threshold recalibration candidate
- Per-model_version gaps → canary didn't generalize

## 5. Actions
| Finding | Action |
|---|---|
| Global AUC drop > 0.02 | `/retrain` (CONSULT) |
| One slice degraded | Feature audit + targeted retrain |
| Calibration drift | Threshold review, not retrain |
| Data quality | `/drift-check` + upstream escalation |

## 6. Document
- `docs/reviews/performance-YYYY-MM.md`
- Include slice heatmap from Grafana `dashboard-closed-loop.json`
- Append audit entry

**Canonical**: `.windsurf/workflows/performance-review.md` + skill `performance-degradation-rca`.
