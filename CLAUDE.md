# CLAUDE.md — ML-MLOps Production Template

This file provides context for Claude Code when working in this repository.

## Project Identity

**ML-MLOps Production Template**: Agent-driven framework for building production-grade ML
systems with multi-cloud deployment (GKE + EKS), observability, and enterprise CI/CD.
Every architectural decision is documented in ADRs with measured trade-offs.

## Stack (non-negotiable)

- **Language**: Python 3.11+ with type hints on all public functions
- **ML**: scikit-learn, XGBoost, LightGBM, Optuna, Pandera, SHAP (KernelExplainer)
- **Serving**: FastAPI + uvicorn (single worker in K8s) + ThreadPoolExecutor
- **Clouds**: GCP (primary) + AWS (secondary parity)
- **Infra**: Kubernetes (GKE + EKS), Terraform >= 1.7, Kustomize overlays
- **CI/CD**: GitHub Actions
- **Tracking**: MLflow | **Monitoring**: Prometheus + Grafana + AlertManager + Evidently
- **Data**: DVC (GCS + S3 remotes), Pandera DataFrameModel validation

## Session Initialization Protocol

When starting a new session:

1. **READ** `AGENTS.md` fully before writing any code
2. **CONFIRM** scaffold is complete: `grep -r "{ServiceName}\|{service}" . --include="*.py" --include="*.yaml"`
3. **CHECK** invariants: `grep -r "TODO\|{ServiceName}\|{service}" . --include="*.py" --include="*.yaml"`
4. **IDENTIFY** phase: **Build** (new service) vs **Operate** (existing service)
5. **SELECT** the appropriate approach based on the task

## Critical Invariants — NEVER VIOLATE

### ML Serving
- **NEVER** `uvicorn --workers N` in K8s — 1 worker, HPA handles horizontal scale
- **NEVER** memory HPA for ML pods — CPU only (fixed RAM prevents scale-down)
- **ALWAYS** `asyncio.run_in_executor()` + `ThreadPoolExecutor` for inference
- **ALWAYS** `KernelExplainer` for SHAP with ensemble/pipeline models
- **NEVER** bake models into Docker — use Init Container + emptyDir
- **NEVER** `model.predict()` directly in async endpoint — blocks event loop

### Infrastructure
- **ALWAYS** IRSA (AWS) / Workload Identity (GCP) — no hardcoded credentials
- **ALWAYS** remote Terraform state (GCS for GCP, S3+DynamoDB for AWS)
- **NEVER** commit secrets to tfvars or repository
- **NEVER** overwrite existing container image tags — tags are immutable
- **ALWAYS** verify `kubectl config current-context` before applying manifests

### Model Quality
- **ALWAYS** quality gates before promotion (metric, fairness DIR >= 0.80, leakage check)
- **ALWAYS** compute SHAP in ORIGINAL feature space, never transformed
- **ALWAYS** compatible release pinning (`~=`) — `numpy 2.x` corrupts joblib models
- **ALWAYS** ADR for non-trivial decisions

## Anti-Patterns (D-01 to D-12)

| ID | Anti-Pattern | Fix |
|----|-------------|-----|
| D-01 | `uvicorn --workers N` | Single worker + ThreadPoolExecutor |
| D-02 | Memory HPA | CPU-only HPA |
| D-03 | `model.predict()` in async | `run_in_executor` |
| D-04 | TreeExplainer on ensemble | KernelExplainer + predict_proba_wrapper |
| D-05 | `==` pinning for ML packages | `~=` compatible release |
| D-06 | Unrealistically high metric | Investigate data leakage |
| D-07 | SHAP background with one class | Replace with representative sample |
| D-08 | PSI with uniform bins | Quantile-based bins |
| D-09 | No heartbeat alert | Add AlertManager rule for CronJob |
| D-10 | tfstate in git | Remote state + rotate secrets |
| D-11 | Model in Docker image | Init Container pattern |
| D-12 | No quality gates | Add all gates before deploy |

## Key Commands

```bash
# Scaffold a new ML service
bash templates/scripts/new-service.sh ServiceName service_slug

# Run the working example (fraud detection)
cd examples/minimal && pip install -r requirements.txt
python train.py && uvicorn serve:app --port 8000
pytest test_service.py -v
python drift_check.py

# Validate templates (CI)
flake8 --max-line-length=120 templates/service/ templates/common_utils/
kustomize build templates/k8s/base/ > /dev/null
```

## File Structure

```
AGENTS.md              → Full architecture, invariants, anti-patterns (canonical source)
CLAUDE.md              → This file (Claude Code context)
QUICK_START.md         → 10-minute setup guide (standalone)
RUNBOOK.md             → Template operations reference
LICENSE                → MIT License
docker-compose.yml     → Local dev: example API + MLflow
templates/
├── service/           → FastAPI + training + tests + Dockerfile + DVC pipeline
├── tests/integration/ → Integration test templates (health, predict, latency SLA)
├── k8s/base/          → Deployment, HPA, Service, SLO PrometheusRule, Kustomize
├── infra/             → Terraform GCP + AWS, docker-compose.mlflow.yml
├── cicd/              → GitHub Actions workflows
├── scripts/           → new-service.sh, deploy.sh, promote_model.sh
├── docs/              → ADR, runbook, model card, mkdocs.yml, CHECKLIST_RELEASE.md
├── monitoring/        → AlertManager rules, Grafana dashboards, Prometheus
└── common_utils/      → seed, logging, model_persistence, telemetry
examples/minimal/      → Working fraud detection demo (5 min)
releases/              → GitHub Release notes (v1.0.0, v1.1.0, v1.2.0)
.claude/rules/         → Context-aware rules (this IDE, paths: globs)
.windsurf/             → Rules, skills, workflows (Windsurf Cascade)
.cursor/rules/         → Cursor IDE rules
```

## Engineering Calibration

Match solution complexity to problem scale:
- 2-3 models → CronJob + GitHub Actions (not Airflow)
- In-memory DataFrames → Pandera (not Great Expectations)
- Simple drift → PSI with quantile bins (not feature store)
- Small team → README + ADRs (not Confluence + Backstage)

## Coding Conventions

- black (line-length=120), isort (profile=black), flake8, mypy
- Google-style docstrings, type hints on all public functions
- `~=` for ML package pinning (never `==` or bare `>=`)
- Coverage: >= 90% lines, >= 80% branches
- ADR for every non-trivial decision in `docs/decisions/`
