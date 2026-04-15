# {ServiceName}

> {One sentence describing the business problem solved by this service}

[![CI](https://github.com/{org}/{repo}/actions/workflows/ci.yml/badge.svg)](https://github.com/{org}/{repo}/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/{org}/{repo}/branch/main/graph/badge.svg)](https://codecov.io/gh/{org}/{repo})
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Train model
python src/{service}/training/train.py --data data/raw/dataset.csv

# Run API locally
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Test prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"feature_a": 42.0, "feature_b": 50000.0, "feature_c": "category_A"}'
```

## Model

| Property | Value |
|----------|-------|
| Architecture | {Model type — e.g., GBM pipeline with ColumnTransformer} |
| Primary Metric | {metric_name} = {measured_value} |
| Secondary Metric | {metric_name} = {measured_value} |
| Fairness (DIR) | {value} per {protected_attributes} |
| Training Date | {YYYY-MM-DD} |
| Training Samples | {N} |
| Features | {N} features ({N} numeric, {N} categorical) |
| ADR | ADR-{NNN}: {Model Selection Rationale} |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/predict` | Main prediction (probability + risk level) |
| POST | `/predict?explain=true` | + SHAP feature contributions |
| GET | `/health` | Liveness/readiness probe |
| GET | `/metrics` | Prometheus metrics |

## Serving Latency (Measured {YYYY-MM-DD})

| Cloud | Instance | Replicas | P50 (idle) | P95 (idle) | P50 (100u) | P95 (100u) | Error % |
|-------|----------|----------|-----------|-----------|-----------|-----------|---------|
| GCP | {type} | {N} | {X}ms | {Y}ms | {X}ms | {Y}ms | {Z}% |
| AWS | {type} | {N} | {X}ms | {Y}ms | {X}ms | {Y}ms | {Z}% |

## Drift Detection

- **Method**: PSI with quantile-based bins
- **Schedule**: Daily at 02:00 UTC (K8s CronJob)
- **Heartbeat Alert**: Fires if no drift check in 48h
- **Key Thresholds**:

| Feature | Warning | Alert | Reason |
|---------|---------|-------|--------|
| {feature_a} | 0.10 | 0.20 | Historically stable |
| {feature_b} | 0.15 | 0.30 | High natural variance |

## Deploy

```bash
# GCP GKE
kubectl apply -k k8s/overlays/gcp/

# AWS EKS
kubectl apply -k k8s/overlays/aws/
```

## Resource Profile

```
Model + deps in memory: ~{N}Mi
Pod request: cpu={X}, memory={Y}Mi
Pod limit: cpu={X}, memory={Y}Mi
HPA: {min}-{max} replicas, CPU target {N}%
```

## Total Cost of Ownership (Measured {YYYY-MM-DD})

```
Serving (2 clouds, {N} replicas): ${X}/mo
Training (spot, monthly): ${X}/mo
Storage (GCS + S3): ${X}/mo
Monitoring: ${X}/mo
TOTAL: ${X}/mo
```

## Architecture Decisions

- **ADR-{NNN}**: {Model selection and rationale}
- **ADR-{NNN}**: {Any service-specific decisions}

## Monitoring

- **Grafana Dashboard**: {URL}
- **AlertManager**: P1-P4 alerts configured
- **Metrics**: `{service}_predictions_total`, `{service}_prediction_latency_seconds`, `{service}_psi_score`
