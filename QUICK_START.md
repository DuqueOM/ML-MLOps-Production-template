# Quick Start — ML-MLOps Production Template

**From clone to first model served in 10 minutes.**

---

## Prerequisites

| Component | Version | Check |
|-----------|---------|-------|
| **Python** | 3.11+ | `python --version` |
| **Docker** | 20.10+ | `docker --version` |
| **Make** | Any | `make --version` |

---

## Option A: Try the Working Example (5 min)

Run the fraud detection demo — no setup required beyond Python.

```bash
git clone https://github.com/DuqueOM/ML-MLOps-Production-Template.git
cd ML-MLOps-Production-Template

# Install and run end-to-end
make demo-minimal
```

Or step by step:

```bash
cd examples/minimal
pip install -r requirements.txt

# Train (synthetic data + Pandera validation + quality gates)
python train.py

# Serve (async inference + SHAP + Prometheus metrics)
uvicorn serve:app --host 0.0.0.0 --port 8000

# Predict (in another terminal)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"amount": 150.0, "hour": 2, "is_foreign": true, "merchant_risk": 0.8, "distance_from_home": 45.0}'

# With SHAP explanation
curl "http://localhost:8000/predict?explain=true" \
  -X POST -H "Content-Type: application/json" \
  -d '{"amount": 9500.0, "hour": 3, "is_foreign": true, "merchant_risk": 0.9, "distance_from_home": 200.0}'

# Regression tests (leakage, SHAP consistency, latency, fairness)
pytest test_service.py -v

# Drift detection
python drift_check.py
```

---

## Option B: Scaffold Your Own Service (10 min)

```bash
git clone https://github.com/DuqueOM/ML-MLOps-Production-Template.git
cd ML-MLOps-Production-Template

# Scaffold a new service (copies all templates, replaces placeholders)
./templates/scripts/new-service.sh ChurnPredictor churn_predictor

# Or via Make
make new-service NAME=ChurnPredictor SLUG=churn_predictor
```

This creates a complete service directory:

```
ChurnPredictor/
├── app/                    # FastAPI serving layer
├── src/churn_predictor/    # Training, features, monitoring
├── tests/                  # Unit, integration, explainer, load
├── k8s/                    # Kubernetes manifests (base + overlays)
├── infra/                  # Terraform GCP + AWS
├── monitoring/             # Grafana + Prometheus
├── .github/workflows/      # CI/CD pipelines
├── Dockerfile              # Multi-stage, non-root
├── Makefile                # train, test, serve, build, deploy
└── docker-compose.demo.yml # Local demo stack
```

**Next steps after scaffolding:**

```bash
cd ChurnPredictor

# 1. Define your data schema
#    Edit src/churn_predictor/schemas.py

# 2. Define your features
#    Edit src/churn_predictor/training/features.py

# 3. Define your model pipeline
#    Edit src/churn_predictor/training/model.py

# 4. Define your API schema
#    Edit app/schemas.py

# 5. Install, train, serve
pip install -r requirements.txt
make train DATA=data/raw/your-dataset.csv
make serve
```

---

## Option C: Full Stack with MLflow (15 min)

Requires Docker.

```bash
cd ML-MLOps-Production-Template

# Start MLflow + Pushgateway
docker compose -f templates/infra/docker-compose.mlflow.yml up -d

# Scaffold and run your service
./templates/scripts/new-service.sh MyService my_service
cd MyService
export MLFLOW_TRACKING_URI=http://localhost:5000
pip install -r requirements.txt
make train
make serve
```

**Access points:**

| Service | URL |
|---------|-----|
| Your API | http://localhost:8000/docs |
| MLflow UI | http://localhost:5000 |

---

## Agentic Workflows

If using Windsurf Cascade, Claude Code, or Cursor, the template includes pre-configured rules, skills, and workflows:

```
# In your AI assistant:
/new-service       # Scaffold a new ML service
/retrain           # Retrain with quality gates
/drift-check       # Run PSI drift analysis
/release           # Full multi-cloud release
/incident          # Incident response
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| Port 8000 in use | `lsof -i :8000` then `kill -9 <PID>` |
| Model not found | Run `make train` first |
| Docker OOM | Increase Docker memory to 8GB+ |

---

## Next Steps

- **[README.md](README.md)** — Full documentation, architecture, invariants
- **[RUNBOOK.md](RUNBOOK.md)** — Template operations reference
- **[CHANGELOG.md](CHANGELOG.md)** — Release history
- **[examples/minimal/](examples/minimal/)** — Working fraud detection demo
