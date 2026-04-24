---
description: Run 6-phase exploratory data analysis on a new dataset — ingest, profile, leakage gate, feature proposals
allowed-tools:
  - Bash(python:*)
  - Read
  - Edit
---

# /eda

Mandatory BEFORE `/new-service`. Produces the artifacts that schemas,
features, and drift detection depend on (D-13..D-16, ADR-004).

## 6 phases (run `templates/eda/eda_pipeline.py`)
0. Ingest + snake_case normalization (sandbox check — D-13)
1. Structural profile → `01_dtypes_map.json`
2. Univariate + `02_baseline_distributions.pkl` (D-15; quantile bins for PSI)
3. Correlations + VIF + feature ranking
4. **Leakage HARD GATE** — exit 1 if `BLOCKED_FEATURES` non-empty
5. Feature proposals with rationale → `05_feature_proposals.yaml` (D-16)
6. Consolidation → `schema_proposal.py` + `eda_summary.md`

## Hard gate on phase 4
If leakage detected:
- Pipeline exits 1 (not 0)
- Emits `[AGENT MODE: STOP]`
- Chains to `/incident` — NOT `/new-service`
- Document root cause before unblocking

## Required outputs
```
eda/
├── reports/     (00-04 + eda_summary.md)
├── artifacts/   (01_dtypes_map, 02_baseline_distributions, 03_ranking, 05_feature_proposals)
└── notebooks/   (eda_<dataset>.ipynb)
```

## Chains to
- `/new-service` on pass
- `/incident` on leakage block

**Canonical**: `.windsurf/skills/eda-analysis/SKILL.md` + `.windsurf/workflows/eda.md`.
