# Minimal Example — Fraud Detection Service

A **fully working** ML service scaffolded from the template. Uses synthetic data
to demonstrate the entire pipeline: training → serving → prediction → metrics.

## Quick Start (< 5 minutes)

```bash
cd examples/minimal

# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate synthetic data + train model
python train.py

# 3. Start the API
uvicorn serve:app --host 0.0.0.0 --port 8000

# 4. Test prediction (in another terminal)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"amount": 150.0, "hour": 2, "is_foreign": true, "merchant_risk": 0.8, "distance_from_home": 45.0}'

# 5. Check health
curl http://localhost:8000/health

# 6. View metrics
curl http://localhost:8000/metrics
```

## What This Demonstrates

- **Async inference**: `ThreadPoolExecutor` + `run_in_executor` (never blocks event loop)
- **SHAP explanations**: `?explain=true` returns feature contributions
- **Prometheus metrics**: predictions counter, latency histogram, score distribution
- **Health endpoint**: liveness/readiness probe for K8s
- **Pandera validation**: input data validated before training
- **Quality gates**: ROC-AUC threshold, fairness DIR, leakage check
- **PSI drift detection**: quantile-based bins with configurable thresholds

## Files

| File | Purpose |
| ------ | --------- |
| `train.py` | Generate synthetic data + train pipeline + quality gates |
| `serve.py` | FastAPI app with async inference + SHAP + Prometheus |
| `test_service.py` | Regression tests (leakage, SHAP, latency, fairness) |
| `drift_check.py` | PSI drift detection on synthetic drift |
| `requirements.txt` | Minimal dependencies |

## Not Included (Template Provides)

This example focuses on **Python code only**. The full template also provides:

- Dockerfile (multi-stage, non-root)
- K8s manifests (Deployment, HPA, CronJob, NetworkPolicy, RBAC)
- Terraform (GKE + EKS)
- CI/CD workflows (lint, test, build, deploy, drift, retrain)
- Monitoring (Grafana dashboard, AlertManager rules)
- Documentation templates (ADR, runbook, model card)
