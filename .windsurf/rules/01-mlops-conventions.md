---
trigger: always_on
description: Core MLOps conventions — concise reference, full detail in AGENTS.md
---

# MLOps Production Template — Core Rules

## Stack (non-negotiable)
- Python 3.11+, scikit-learn/XGBoost/LightGBM, FastAPI, Kubernetes, Terraform
- Clouds: GCP (primary) + AWS (secondary)
- Tracking: MLflow | Monitoring: Prometheus + Grafana | Validation: Pandera

## 5 Invariants (NEVER violate)
1. `uvicorn --workers 1` only — HPA provides horizontal scale
2. HPA uses CPU only — never memory for ML pods
3. CPU-bound inference always via `run_in_executor(ThreadPoolExecutor)`
4. SHAP always in original feature space via predict_proba_wrapper
5. No model artifacts in Docker images — init container pattern only

## Dependency Pinning
Always `~=` for ML packages. Never `==` (conflicts) or bare `>=` (breaks).

## Quality Standards
- Coverage >= 90% lines, >= 80% branches
- Type hints on all public functions, Google-style docstrings
- black (120), isort (black profile), flake8, mypy
- ADR for every non-trivial decision in `docs/decisions/`

## Engineering Calibration
Match complexity to scale: CronJob not Airflow, Pandera not GE, PSI not feature store.

## When to Load Skills
- Creating a new service? → `new-service` (uses `templates/scripts/new-service.sh`)
- Debugging inference? → `debug-ml-inference`
- Drift alert fired? → `drift-detection` → `model-retrain`
- Deploying? → `deploy-gke` or `deploy-aws`
- Monthly cost review? → `cost-audit`

## Full Details
- Anti-pattern table D-01 to D-12: see `AGENTS.md`
- All invariants with reasoning: see `AGENTS.md`
- Session initialization protocol: see `AGENTS.md`
