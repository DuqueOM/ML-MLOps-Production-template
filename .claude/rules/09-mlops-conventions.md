---
paths:
  - "**/*"
---

# ML-MLOps Core Conventions (always on)

Canonical invariants and Behavior Protocol for Claude Code in this repo.
See `AGENTS.md` for authoritative detail.

## Stack (non-negotiable)
- Python 3.11+, scikit-learn / XGBoost / LightGBM, FastAPI, Kubernetes, Terraform
- GCP (primary) + AWS (secondary) | MLflow | Prometheus + Grafana + Evidently | Pandera

## 6 Critical Invariants
1. `uvicorn --workers 1` only — HPA provides horizontal scale
2. HPA uses CPU only — never memory for ML pods
3. CPU-bound inference always via `run_in_executor(ThreadPoolExecutor)`
4. SHAP always in original feature space via `predict_proba_wrapper`; explainer cached at startup (D-24)
5. No model artifacts in Docker images — init container pattern only
6. Model warm-up runs in `lifespan` BEFORE `_warmed_up=True`; `/ready` gates traffic (D-23)

## Agent Behavior Protocol (AGENTS.md)
- `terraform apply prod`, model → Production, secret rotation → **STOP**
- `kubectl apply staging`, model → Staging → **CONSULT**
- Scaffolding, tests, reports, dev deploys → **AUTO**

## Dynamic Behavior Protocol (ADR-010)
Before AUTO/CONSULT ops, load `common_utils/risk_context.py` and apply:
- `AUTO` + ≥1 signal → **CONSULT**
- `CONSULT` + ≥1 signal → **STOP**
- `STOP` is sticky

Signals: `incident_active`, `drift_severe`, `error_budget_exhausted`,
`off_hours` (weekend / 18–08 UTC), `recent_rollback` (< 6h).

## Anti-patterns D-01..D-30
See `AGENTS.md §Anti-Patterns` — authoritative table.
Also see `.windsurf/rules/01-mlops-conventions.md` for richer narrative.

## Code style
- black (120), isort (black profile), flake8, mypy
- Google-style docstrings, type hints on public functions
- `~=` for ML packages (never `==` or bare `>=`)
- 90% line coverage, 80% branch coverage
- ADR for every non-trivial decision in `docs/decisions/`

## Engineering Calibration
Match complexity to scale: CronJob not Airflow, Pandera not Great Expectations,
PSI not a feature store, `kubectl apply` not ArgoCD until triggers fire (ADR-013).
