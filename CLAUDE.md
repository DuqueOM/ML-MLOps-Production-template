# CLAUDE.md — ML-MLOps Production Template

This file provides context for Claude Code when working in this repository.

## Project Identity

**ML-MLOps Production Template**: Agent-driven framework for building production-grade ML
systems with multi-cloud deployment (GKE + EKS), observability, and enterprise CI/CD.

## Stack

- Python 3.11+, scikit-learn, XGBoost, LightGBM, FastAPI, Docker, Kubernetes, Terraform
- GCP (primary) + AWS (secondary parity)
- MLflow tracking, Prometheus + Grafana + AlertManager + Evidently monitoring
- DVC (GCS + S3 remotes), Pandera data validation

## Critical Rules — DO NOT VIOLATE

- **NEVER** `uvicorn --workers N` in K8s — 1 worker, HPA manages scale
- **NEVER** memory HPA for ML pods — CPU only (fixed RAM prevents scale-down)
- **ALWAYS** `asyncio.run_in_executor()` + `ThreadPoolExecutor` for inference
- **ALWAYS** `KernelExplainer` for SHAP with ensemble/pipeline models
- **ALWAYS** compatible release pinning (`~=`) — numpy 2.x corrupts joblib models
- **NEVER** bake models into Docker — use Init Container + emptyDir
- **NEVER** `model.predict()` directly in async endpoint — blocks event loop
- **ALWAYS** IRSA (AWS) / Workload Identity (GCP) — no hardcoded credentials
- **ALWAYS** quality gates before model promotion (metric, fairness DIR >= 0.80, leakage)
- **ALWAYS** ADR for non-trivial decisions

## Anti-Patterns (D-01 to D-12)

See `AGENTS.md` for the full anti-pattern table. Key ones:
- D-01: Multiple uvicorn workers → single worker + ThreadPoolExecutor
- D-02: Memory HPA → CPU-only HPA
- D-04: TreeExplainer with ensembles → KernelExplainer
- D-05: `==` pinning for ML packages → `~=`
- D-11: Models in Docker image → Init Container pattern

## File Structure

```
.windsurf/          → Windsurf-specific rules, skills, workflows
.cursor/rules/      → Cursor-specific rules
CLAUDE.md           → This file (Claude Code context)
AGENTS.md           → Root-level invariants + anti-pattern table
templates/          → All template code (service, k8s, infra, cicd, docs, monitoring)
```

## Engineering Calibration

Match solution complexity to problem scale:
- 2-3 models → CronJob + GitHub Actions (not Airflow)
- In-memory DataFrames → Pandera (not Great Expectations)
- Simple drift → PSI with quantile bins (not feature store)

## Coding Conventions

- Type hints on all public functions
- Google-style docstrings
- `~=` for ML package pinning (never `==` or bare `>=`)
- 90% line coverage, 80% branch coverage
- black (120 line length), isort (black profile), flake8, mypy
