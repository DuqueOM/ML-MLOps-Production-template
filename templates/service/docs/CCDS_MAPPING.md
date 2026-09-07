# CCDS Layout Mapping

> This document maps the production directory layout to the
> [Cookiecutter Data Science](https://drivendata.github.io/cookiecutter-data-science/)
> vocabulary, so practitioners from a CCDS background can orient
> quickly. See ADR-034 for the rationale.

## Mapping

| CCDS directory | This service | What lives here |
| ---------------- | ------------- | ----------------- |
| `data/raw/` | `data/raw/` | Untouched inputs (DVC-versioned) |
| `data/interim/` | `data/validated/` | Pandera-validated frames (training cache) |
| `data/processed/` | `data/processed/` | Cleaned + featurised data |
| `data/external/` | `data/reference/` | Frozen distributions, SHAP background, holdout labels |
| `notebooks/` | `eda/notebooks/` | Structured EDA companion notebooks |
| `models/` | `models/` | Trained artifacts (DVC-tracked, `model.joblib` + `metadata.json`) |
| `references/` | `docs/` + `eda/artifacts/` | Data dictionaries, schemas, EDA summaries, runbooks |
| `src/` | `src/{@ service_slug @}/` | Service source code (training, serving, monitoring) |

## Directories with no CCDS equivalent

These directories are production-specific and have no CCDS counterpart:

| Directory | Purpose |
| ----------- | --------- |
| `app/` | FastAPI application (API schemas, main entry point) |
| `k8s/` | Kubernetes manifests (base + overlays) |
| `infra/` | Terraform infrastructure-as-code |
| `monitoring/` | Prometheus rules, Grafana dashboards, alerts |
| `reports/` | JSON/HTML metrics (champion-challenger, drift, performance) |
| `eda/reports/` | Human-readable EDA outputs (regenerable) |
| `eda/artifacts/` | Machine-readable EDA outputs (DVC-tracked) |
| `configs/` | Service configuration (profiles, feature flags) |
| `ops/` | Audit trail, runbook outputs |
| `scripts/` | CI/CD and operational scripts |
| `tests/` | Unit, integration, contract, policy, regression tests |

## Quick orientation

If you are looking for:

- **Your dataset** → `data/raw/`
- **Your notebook** → `eda/notebooks/`
- **Your trained model** → `models/model.joblib`
- **Your feature engineering code** → `src/{@ service_slug @}/training/features.py`
- **Your API code** → `app/main.py`
- **Your EDA report** → `eda/reports/`
- **Your drift baseline** → `eda/artifacts/baseline_distributions.parquet`
- **Your data schema** → `src/{@ service_slug @}/schemas.py`
- **Your K8s manifests** → `k8s/`
- **Your Terraform** → `infra/`
