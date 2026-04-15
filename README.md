# ML-MLOps Production Template

> Agent-driven framework for building and maintaining production-grade ML systems with multi-cloud deployment, comprehensive observability, and enterprise CI/CD.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Terraform >= 1.7](https://img.shields.io/badge/terraform-%3E%3D1.7-blueviolet.svg)](https://www.terraform.io/)
[![Kubernetes](https://img.shields.io/badge/k8s-GKE%20%2B%20EKS-326CE5.svg)](https://kubernetes.io/)

---

## What This Is

A **complete, opinionated template** for shipping ML models to production — not a toy notebook, not a mega-framework. It includes:

- **An agentic system** (rules, skills, workflows) that guides AI coding assistants to build and maintain MLOps projects following enterprise patterns
- **Production-ready templates** for every layer of the stack: serving, training, infrastructure, CI/CD, monitoring, and documentation
- **Encoded invariants** that prevent the 12 most common ML production failures (event loop blocking, memory HPA, model baked in images, etc.)
- **Engineering calibration** — every component is sized to actual requirements, avoiding both under-engineering and over-engineering

## Who It's For

- ML engineers shipping models to production for the first time
- Teams standardizing their MLOps across multiple services
- Engineers using AI coding assistants (Windsurf Cascade, Claude Code, Cursor) who want those tools to follow best practices automatically

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                     AGENTIC SYSTEM                                 │
│                                                                    │
│  AGENTS.md          → Root-level invariants + anti-pattern rules   │
│  .windsurf/rules/   → 9 context-aware behavioral constraints      │
│  .windsurf/skills/  → 8 multi-step operational procedures          │
│  .windsurf/workflows/→ 8 prompt-triggered structured workflows     │
│                                                                    │
├──────────────────────────────────────────────────────────────────────┤
│                     TEMPLATE SYSTEM                                │
│                                                                    │
│  templates/service/     → FastAPI + training + monitoring          │
│  templates/k8s/         → Deployment, HPA, CronJob, ServiceAccount │
│  templates/infra/       → Terraform GCP + AWS                      │
│  templates/cicd/        → GitHub Actions (CI, deploy, drift, retrain)│
│  templates/docs/        → ADR, runbook, service README             │
│  templates/monitoring/  → Grafana dashboard + Prometheus alerts     │
│                                                                    │
├──────────────────────────────────────────────────────────────────────┤
│                     TARGET PROJECT                                 │
│                                                                    │
│  {ServiceName}/                                                    │
│  ├── app/           → FastAPI (1 worker, ThreadPoolExecutor)       │
│  ├── src/{service}/                                                │
│  │   ├── training/  → train.py, features.py, model.py             │
│  │   ├── monitoring/→ drift_detection.py, business_kpis.py         │
│  │   └── schemas.py → Pandera DataFrameModel                      │
│  ├── tests/         → unit, integration, explainer, load           │
│  ├── k8s/           → base/ + overlays/gcp/ + overlays/aws/       │
│  ├── infra/         → terraform/gcp/ + terraform/aws/              │
│  ├── docs/decisions/→ ADRs with measured trade-offs                │
│  └── monitoring/    → Grafana + Prometheus per service             │
└────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **ML Core** | scikit-learn, XGBoost, LightGBM, Optuna | Compatible release pinning (`~=`) |
| **Serving** | FastAPI + uvicorn (1 worker) | `asyncio.run_in_executor()` for inference |
| **Explainability** | SHAP KernelExplainer | Always in original feature space |
| **Data Validation** | Pandera DataFrameModel | Training, API, and drift checkpoints |
| **Drift Detection** | PSI (quantile-based bins) | CronJob + Pushgateway + heartbeat alert |
| **Experiment Tracking** | MLflow | Self-hosted on K8s |
| **Containers** | Docker (multi-stage, non-root) | Model via Init Container, never baked in |
| **Orchestration** | Kubernetes (GKE + EKS) | CPU-only HPA, Kustomize overlays |
| **Infrastructure** | Terraform >= 1.7 | Remote state, tfsec + Checkov scanning |
| **CI/CD** | GitHub Actions | Lint → Test → Build → Deploy → Drift → Retrain |
| **Monitoring** | Prometheus + Grafana + AlertManager | P1–P4 severity levels per service |
| **Data Versioning** | DVC (GCS + S3 remotes) | Tracked in git, stored in cloud |
| **Clouds** | GCP (primary) + AWS (parity) | Workload Identity / IRSA — no hardcoded creds |

---

## Quick Start

### 1. Clone the template

```bash
git clone https://github.com/DuqueOM/ML-MLOps-Production-template.git
cd ML-MLOps-Production-template
```

### 2. Create a new ML service

Use the `/new-service` workflow (in Windsurf Cascade) or manually scaffold:

```bash
SERVICE_NAME="ChurnPredictor"
SERVICE_SLUG="churn_predictor"

# Copy service template
cp -r templates/service/ ${SERVICE_NAME}/

# Replace placeholders
find ${SERVICE_NAME}/ -type f -exec sed -i "s/{ServiceName}/${SERVICE_NAME}/g" {} +
find ${SERVICE_NAME}/ -type f -exec sed -i "s/{service}/${SERVICE_SLUG}/g" {} +

# Rename directories
mv ${SERVICE_NAME}/src/\{service\} ${SERVICE_NAME}/src/${SERVICE_SLUG}
```

### 3. Configure your features

Edit the following files with your actual features:

- `{ServiceName}/src/{service}/schemas.py` — Pandera schema
- `{ServiceName}/src/{service}/training/features.py` — Feature engineering
- `{ServiceName}/src/{service}/training/model.py` — Model pipeline
- `{ServiceName}/app/schemas.py` — Pydantic request/response

### 4. Train and serve

```bash
cd ${SERVICE_NAME}
pip install -r requirements.txt

# Train
python src/${SERVICE_SLUG}/training/train.py --data data/raw/dataset.csv

# Serve locally
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Test prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"feature_a": 42.0, "feature_b": 50000.0, "feature_c": "category_A"}'
```

### 5. Deploy to production

```bash
# Build and push Docker image
docker build -t ${SERVICE_SLUG}-predictor:v1.0.0 .

# Deploy to GKE
kubectl apply -k k8s/overlays/gcp/

# Deploy to EKS
kubectl apply -k k8s/overlays/aws/
```

---

## Repository Structure

```
ML-MLOps-Production-template/
│
├── AGENTS.md                              # Agent architecture, invariants, anti-patterns
├── README.md                              # This file
├── description_project.md                 # Detailed project specification
│
├── .windsurf/                             # Agentic system configuration
│   ├── rules/                             # 9 behavioral constraint files
│   │   ├── 01-mlops-conventions.md        #   always_on — core stack + ADR patterns
│   │   ├── 02-kubernetes.md               #   glob: k8s/**/*.yaml
│   │   ├── 03-terraform.md                #   glob: **/*.tf
│   │   ├── 04-python-ml.md                #   glob: **/*.py
│   │   ├── 05-github-actions.md           #   glob: .github/workflows/*.yml
│   │   ├── 06-documentation.md            #   glob: docs/**/*.md
│   │   ├── 07-docker.md                   #   glob: **/Dockerfile*
│   │   ├── 08-data-validation.md          #   glob: **/schemas.py
│   │   └── 09-monitoring.md               #   glob: monitoring/**/*
│   │
│   ├── skills/                            # 8 multi-step operational procedures
│   │   ├── debug-ml-inference/SKILL.md    #   Diagnose inference issues
│   │   ├── deploy-gke/SKILL.md            #   Deploy to GCP GKE
│   │   ├── deploy-aws/SKILL.md            #   Deploy to AWS EKS
│   │   ├── drift-detection/SKILL.md       #   Run PSI drift analysis
│   │   ├── model-retrain/SKILL.md         #   Retrain with quality gates
│   │   ├── release-checklist/SKILL.md     #   Multi-cloud release
│   │   ├── new-service/SKILL.md           #   Scaffold a new ML service
│   │   └── cost-audit/SKILL.md            #   Cloud cost review
│   │
│   └── workflows/                         # 8 prompt-triggered workflows
│       ├── release.md                     #   /release
│       ├── retrain.md                     #   /retrain
│       ├── load-test.md                   #   /load-test
│       ├── new-adr.md                     #   /new-adr
│       ├── incident.md                    #   /incident
│       ├── drift-check.md                 #   /drift-check
│       ├── new-service.md                 #   /new-service
│       └── cost-review.md                 #   /cost-review
│
└── templates/                             # Production scaffolding templates
    ├── service/                           # Complete ML service boilerplate
    │   ├── app/                           #   FastAPI serving layer
    │   │   ├── main.py                    #     Application entrypoint
    │   │   ├── fastapi_app.py             #     Async inference + SHAP + metrics
    │   │   └── schemas.py                 #     Pydantic request/response models
    │   ├── src/{service}/                 #   Core ML logic
    │   │   ├── training/                  #     train.py, features.py, model.py
    │   │   ├── monitoring/                #     drift_detection.py, business_kpis.py
    │   │   └── schemas.py                 #     Pandera DataFrameModel
    │   ├── tests/                         #   test_training.py, test_api.py, test_explainer.py
    │   ├── Dockerfile                     #   Multi-stage, non-root, HEALTHCHECK
    │   ├── .dockerignore                  #   Excludes models, data, tests
    │   ├── requirements.txt               #   Pinned with ~= (compatible release)
    │   └── README.md                      #   Service-specific documentation
    │
    ├── k8s/                               # Kubernetes manifest templates
    │   ├── deployment.yaml                #   1-worker pod + init container for model
    │   ├── hpa.yaml                       #   CPU-only autoscaling (never memory)
    │   ├── service.yaml                   #   ClusterIP service
    │   ├── cronjob-drift.yaml             #   Daily drift detection CronJob
    │   └── serviceaccount.yaml            #   Workload Identity / IRSA annotations
    │
    ├── infra/terraform/                   # Multi-cloud infrastructure
    │   ├── gcp/                           #   GKE cluster, GCS buckets, Artifact Registry
    │   │   ├── main.tf
    │   │   ├── compute.tf
    │   │   ├── storage.tf
    │   │   └── variables.tf
    │   └── aws/                           #   EKS cluster, OIDC, IAM roles
    │       ├── main.tf
    │       ├── compute.tf
    │       └── variables.tf
    │
    ├── cicd/                              # GitHub Actions workflow templates
    │   ├── ci.yml                         #   Lint + Test + Build + Scan
    │   ├── ci-infra.yml                   #   Terraform validate + tfsec + K8s validate
    │   ├── deploy-gcp.yml                 #   Deploy to GKE on tag push
    │   ├── deploy-aws.yml                 #   Deploy to EKS on tag push
    │   ├── drift-detection.yml            #   Daily drift check + alert creation
    │   └── retrain-service.yml            #   Manual/triggered retraining pipeline
    │
    ├── docs/                              # Documentation templates
    │   ├── decisions/adr-template.md      #   ADR with Options, Rationale, Revisit When
    │   ├── runbooks/runbook-template.md   #   P1–P4 incident response procedures
    │   └── service-readme-template.md     #   Service README with measured data slots
    │
    └── monitoring/                        # Observability templates
        ├── prometheus/alerts-template.yaml #   P1–P4 alerts, drift heartbeat, resource alerts
        └── grafana/dashboard-template.json #   Request rate, latency, PSI, HPA, resources
```

---

## Agentic System

The `.windsurf/` directory configures AI coding assistants to follow production best practices automatically.

### Rules (Behavioral Constraints)

Rules activate based on file context. When you edit a Kubernetes YAML, `02-kubernetes.md` activates and enforces single-worker pods, CPU-only HPA, init containers, etc. When you edit Python, `04-python-ml.md` activates and enforces async inference, KernelExplainer, quality gates, etc.

| Rule | Trigger | Enforces |
|------|---------|----------|
| `01-mlops-conventions` | Always on | Stack, pinning, ADRs, file org |
| `02-kubernetes` | `k8s/**/*.yaml` | 1 worker, CPU HPA, init containers |
| `03-terraform` | `**/*.tf` | Remote state, no secrets, lifecycle rules |
| `04-python-ml` | `**/*.py` | Async inference, SHAP, quality gates |
| `05-github-actions` | `.github/workflows/*.yml` | Workflow org, required secrets |
| `06-documentation` | `docs/**/*.md` | ADR structure, measured data |
| `07-docker` | `**/Dockerfile*` | Multi-stage, non-root, no model |
| `08-data-validation` | `**/schemas.py` | Pandera at 3 validation points |
| `09-monitoring` | `monitoring/**/*` | Mandatory metrics, PSI, heartbeat |

### Skills (Operational Procedures)

Skills are step-by-step guides the agent follows when performing complex operations:

| Skill | Purpose |
|-------|---------|
| `debug-ml-inference` | Diagnose latency, blocking, SHAP, and resource issues |
| `deploy-gke` | Pre-flight → build → push → apply → smoke test → verify |
| `deploy-aws` | Same as GKE but with ECR + IRSA verification |
| `drift-detection` | Run PSI analysis, push metrics, trigger retraining |
| `model-retrain` | Validate data → train → quality gates → promote/reject |
| `release-checklist` | Multi-cloud release with rollback plan |
| `new-service` | End-to-end scaffolding of a new ML service |
| `cost-audit` | Collect GCP/AWS costs, check FinOps rules |

### Workflows (Slash Commands)

Workflows are triggered by typing a slash command in the AI assistant:

| Command | Description |
|---------|-------------|
| `/release` | Full multi-cloud release process |
| `/retrain` | Model retraining with quality gates |
| `/load-test` | Locust load tests against ML services |
| `/new-adr` | Create a new Architecture Decision Record |
| `/incident` | ML service incident response |
| `/drift-check` | Run PSI drift analysis |
| `/new-service` | Create a complete new ML service from template |
| `/cost-review` | Monthly cloud cost review |

---

## Critical Patterns (Invariants)

These are **non-negotiable rules** encoded in `AGENTS.md` and enforced across all templates:

### ML Serving

- **1 uvicorn worker per pod** — K8s HPA manages horizontal scaling. Multiple workers cause CPU thrashing under pod limits.
- **`asyncio.run_in_executor()`** for all CPU-bound inference — never call `model.predict()` directly in an async endpoint.
- **SHAP KernelExplainer** for ensemble/pipeline models — TreeExplainer produces wrong feature names with ColumnTransformer.
- **Model via Init Container** (`emptyDir` volume) — never bake models into Docker images.

### Infrastructure

- **Workload Identity (GCP) / IRSA (AWS)** — no hardcoded credentials.
- **Remote Terraform state** — GCS for GCP, S3 + DynamoDB for AWS.
- **Immutable image tags** — never overwrite an existing tag.

### Model Quality

- **Quality gates before every promotion** — primary metric, secondary metric, fairness (DIR >= 0.80).
- **Data leakage detection** — suspiciously high metrics trigger investigation.
- **SHAP in original feature space** — never in the post-ColumnTransformer space.

### Monitoring

- **CPU-only HPA** — memory is constant for ML models (loaded model = fixed RAM).
- **PSI with quantile-based bins** — uniform bins produce unreliable drift scores.
- **Drift heartbeat alert** — fires if CronJob hasn't run in 48h.

---

## Anti-Pattern Detection

The agentic system automatically detects and corrects 12 known production failure modes:

| ID | Anti-Pattern | Corrective Action |
|----|-------------|-------------------|
| D-01 | `uvicorn --workers N` in K8s | Change to 1 worker + ThreadPoolExecutor |
| D-02 | Memory metric in HPA | Remove, keep CPU only |
| D-03 | `model.predict()` in async endpoint | Wrap in `run_in_executor` |
| D-04 | `shap.TreeExplainer` with pipeline | Change to KernelExplainer |
| D-05 | `==` pinning for ML packages | Change to `~=` (compatible release) |
| D-06 | Unrealistically high metric | Investigate data leakage |
| D-07 | Single-class SHAP background | Replace with representative sample |
| D-08 | PSI with uniform bins | Refactor to quantile bins |
| D-09 | No drift heartbeat alert | Add AlertManager alert |
| D-10 | `terraform.tfstate` in git | Move to remote state |
| D-11 | Model baked in Docker image | Implement init container pattern |
| D-12 | No quality gates | Add all gates before deploy |

---

## Engineering Calibration

Every component is **sized to match the actual scale of the problem**:

| Scale | Correct Tool | Over-Engineered Alternative |
|-------|-------------|---------------------------|
| 2–3 models | CronJob + GitHub Actions | Airflow / Prefect |
| In-memory DataFrames | Pandera | Great Expectations |
| Simple drift monitoring | PSI with quantile bins | Full feature store |
| Small team docs | README + ADRs | Confluence + Notion + Backstage |

This principle is documented in the **Engineering Calibration Principle** section of `AGENTS.md` and is evaluated for every new component.

---

## Templates Detail

### Service Template (`templates/service/`)

A complete, production-ready ML service with:

- **FastAPI app** with async inference via ThreadPoolExecutor
- **SHAP KernelExplainer** with consistency check (base_value + SHAP ≈ prediction)
- **Prometheus metrics** (predictions counter, latency histogram, score distribution)
- **Pandera validation** at training, API, and drift detection
- **Optuna hyperparameter tuning** with configurable number of trials
- **Quality gates** (primary metric, secondary metric, fairness DIR)
- **MLflow integration** for experiment tracking and model registry
- **Tests** for data leakage, quality gates, API endpoints, SHAP consistency

### K8s Templates (`templates/k8s/`)

- **Deployment** with init container model download, health probes, rolling update (zero downtime)
- **HPA** with CPU-only autoscaling, asymmetric scale-up/down behavior
- **CronJob** for daily drift detection with Pushgateway integration
- **ServiceAccount** with Workload Identity / IRSA annotation placeholders

### Terraform Templates (`templates/infra/`)

- **GCP**: GKE cluster with Workload Identity, node pool autoscaling, GCS buckets (models, data, MLflow, logs), Artifact Registry
- **AWS**: EKS cluster with OIDC for IRSA, managed node group, IAM roles and policies

### CI/CD Templates (`templates/cicd/`)

- **CI**: flake8 + black + isort + mypy → pytest (90% coverage) → Docker build + Trivy scan
- **Infrastructure CI**: terraform fmt/init/validate + tfsec + Checkov + kubeval
- **Deploy GCP/AWS**: Tag-triggered deploy with cluster verification and smoke tests
- **Drift Detection**: Daily scheduled + manual trigger, auto-creates GitHub issue on alert
- **Retraining**: Manual trigger with data validation, training, quality gates, and artifact upload

### Documentation Templates (`templates/docs/`)

- **ADR template**: Context, Options, Decision, Rationale, Consequences, Revisit When
- **Runbook template**: P1–P4 severity procedures with `kubectl` commands
- **Service README**: Measured latency tables, drift thresholds, cost breakdown, resource profile

### Monitoring Templates (`templates/monitoring/`)

- **Prometheus alerts**: Error rate, service down, drift heartbeat, latency, resource usage, pod restarts
- **Grafana dashboard**: Request rate, error rate, latency percentiles, PSI scores, prediction distribution, HPA replicas, CPU/memory usage

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

When adding new templates or rules, ensure they follow the **Engineering Calibration Principle** — sized to the actual problem, not the theoretical maximum.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## AI Transparency

This template uses AI-assisted coding agents for code generation and boilerplate. All architectural decisions, system design, trade-off analysis, and ADR documentation require human engineering judgment. AI tools accelerate throughput — they don't replace the engineer's responsibility to calibrate solutions to the right scale.
