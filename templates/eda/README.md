# EDA Module

Structured, agentic Exploratory Data Analysis for ML services.

This module implements the 6-phase pipeline described in
`.windsurf/skills/eda-analysis/SKILL.md` and enforced by
`.windsurf/rules/11-data-eda.md`.

## Why a structured EDA module

Without structure, EDA tends to:
- Leak production features into training (D-13)
- Produce Pandera schemas disconnected from observed distributions (D-14)
- Forget to persist baseline distributions, silently breaking drift detection (D-15)
- Propose features without documented rationale (D-16)

This module makes all four anti-patterns impossible by design.

## Directory layout (enforced)

```
eda/
├── reports/                            # Human-readable outputs (gitignored — regenerable)
│   ├── 00_ingest_report.md
│   ├── 01_profile.html
│   ├── 02_univariate.html
│   ├── 03_correlations.html
│   ├── 04_leakage_audit.md            # Contains BLOCKED_FEATURES list
│   └── eda_summary.md
├── artifacts/                          # Machine-readable outputs (committed or DVC-tracked)
│   ├── 01_dtypes_map.json
│   ├── 02_baseline_distributions.pkl   # DVC-tracked — drift detection input
│   ├── 03_feature_ranking_initial.csv
│   └── 05_feature_proposals.yaml       # Consumed by features.py
└── notebooks/
    └── eda_<dataset>.ipynb             # Interactive exploration companion
```

## Files in this module

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `eda_pipeline.py` | Scriptable 6-phase implementation |
| `notebook_template.ipynb` | Structured Jupyter notebook companion |
| `requirements.txt` | Python dependencies (heavy + lightweight modes) |
| `.gitignore` | Excludes HTML reports and large artifacts from git |

## Quick start

```bash
# 1. Install deps (lightweight by default)
pip install -r templates/eda/requirements.txt

# 2. Run the 6-phase pipeline
python -m eda.eda_pipeline \
  --input data/raw/dataset.csv \
  --target target_column \
  --output-dir eda/

# 3. Review the leakage gate (phase 4)
cat eda/reports/04_leakage_audit.md
# Must show: BLOCKED_FEATURES: []

# 4. Inspect proposals and schema
less eda/artifacts/05_feature_proposals.yaml
less src/<service>/schema_proposal.py

# 5. Commit via DVC
dvc add data/raw/dataset.csv
dvc add eda/artifacts/02_baseline_distributions.pkl
git add eda/ .dvc/
git commit -m "feat(eda): complete EDA for <dataset>"
```

Or in agentic mode:
```
/eda data/raw/dataset.csv fraud_detector
```

## Two modes: lightweight vs heavy

### Lightweight (default)
- `pandas`, `scipy`, `scikit-learn`, `matplotlib`, `pandera`
- ~50MB total
- Phase 1 produces a Markdown profile, not ydata-profiling HTML
- **Recommended for CI and small-to-medium datasets (< 1M rows)**

### Heavy (opt-in)
```bash
pip install -r templates/eda/requirements-heavy.txt
python -m eda.eda_pipeline --heavy ...
```
- Adds `ydata-profiling` (~500MB) for rich HTML profiling
- `plotly` for interactive plots
- `great_tables` for publication-quality tables
- Recommended for initial exploration on large datasets or when stakeholders review reports

## Phase artifacts reference

| Phase | Output (report) | Output (artifact) | Consumer |
|-------|----------------|-------------------|----------|
| 0 | `00_ingest_report.md` | `data/processed/dataset_clean.parquet` | All downstream |
| 1 | `01_profile.html` | `01_dtypes_map.json` | Phase 6 schema proposal |
| 2 | `02_univariate.html` | **`02_baseline_distributions.pkl`** | **Drift CronJob (prod)** |
| 3 | `03_correlations.html` | `03_feature_ranking_initial.csv` | Phase 5 proposals |
| 4 | `04_leakage_audit.md` | — (GATE, not an artifact) | Pipeline control flow |
| 5 | — | `05_feature_proposals.yaml` | `features.py` |
| 6 | `eda_summary.md` | `schema_proposal.py` | `schemas.py` (review) |

## The drift detection loop

```
      EDA phase 2
           │
           ▼
02_baseline_distributions.pkl  ←─────── DVC tracked
           │
           ▼
   Drift CronJob (prod)
           │
           ▼
   PSI score per feature
           │
           ▼
   Alert if PSI > threshold
           │
           ▼
   /drift-check → /retrain
```

This loop is **broken by default** in most ML templates because the baseline is either
missing or uses raw `min/max` instead of quantile bins. EDA phase 2 fixes this
explicitly.

## Contract with `features.py`

```python
# In src/<service>/training/features.py
import yaml

with open("eda/artifacts/05_feature_proposals.yaml") as f:
    proposals = yaml.safe_load(f)

class FeatureEngineer:
    def transform(self, df):
        # Each proposal below must cite its rationale field (invariant D-16)
        for prop in proposals["transforms"]:
            assert "rationale" in prop, f"D-16 violation: {prop['name']} lacks rationale"
            # Apply the transform...
```

## References

- Rule: `.windsurf/rules/11-data-eda.md`
- Skill: `.windsurf/skills/eda-analysis/SKILL.md`
- Workflow: `.windsurf/workflows/eda.md` (`/eda`)
- ADR: `docs/decisions/ADR-004-eda-phase-integration.md`
- Invariants: D-13, D-14, D-15, D-16 (see AGENTS.md)
