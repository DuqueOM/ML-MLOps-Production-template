---
paths:
  - "**/schemas.py"
  - "**/validation*.py"
  - "**/dvc*.yaml"
---

# Data Validation Rules (Pandera + DVC)

## Pandera invariants (D-14)
- Schemas live in `src/{service}/schemas.py` — single source of truth
- `Check.in_range(lo, hi)` MUST use observed ranges from
  `eda/artifacts/01_dtypes_map.json` — never guesses
- `Check.isin(...)` uses the FULL observed category set
- Nullable columns are explicit (`nullable=True`); default is `False`
- Strict mode ON for production inputs: extra columns raise

## DVC conventions
- `data/raw/` — DVC-tracked, gitignored
- `data/processed/` — DVC-tracked, gitignored
- `eda/artifacts/02_baseline_distributions.pkl` — DVC-tracked, used by drift CronJob (D-15)
- Remotes: `gcs://` (primary) + `s3://` (secondary) — both configured

## Schema lifecycle
1. EDA phase 6 produces `schema_proposal.py`
2. Human reviews + merges into `schemas.py` (do NOT auto-overwrite)
3. `test_schema_matches_eda.py` enforces the ranges stay in sync
4. Breaking changes → bump service version + update baselines

## Forbidden
- `Check.in_range(0, 100)` hardcoded — derive from EDA
- Schemas in production never re-fitted from incoming data (cat bag)
- Dropping columns silently — always raise or log

See AGENTS.md D-14, D-15, `.windsurf/rules/08-data-validation.md`,
`.windsurf/rules/11-data-eda.md`, ADR-004.
