# ML-MLOps Production Template

> Agent-driven framework for building and maintaining production-grade ML systems with multi-cloud deployment, comprehensive observability, and enterprise CI/CD.

[![Release](https://img.shields.io/github/v/release/DuqueOM/ML-MLOps-Production-Template.svg)](https://github.com/DuqueOM/ML-MLOps-Production-Template/releases)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11_%7C_3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Terraform >= 1.7](https://img.shields.io/badge/terraform-%3E%3D1.7-blueviolet.svg)](https://www.terraform.io/)
[![Kubernetes](https://img.shields.io/badge/k8s-GKE%20%2B%20EKS-326CE5.svg)](https://kubernetes.io/)

[![Validate Templates](https://github.com/DuqueOM/ML-MLOps-Production-Template/actions/workflows/validate-templates.yml/badge.svg)](https://github.com/DuqueOM/ML-MLOps-Production-Template/actions/workflows/validate-templates.yml)
[![codecov](https://codecov.io/gh/DuqueOM/ML-MLOps-Production-Template/branch/main/graph/badge.svg)](https://codecov.io/gh/DuqueOM/ML-MLOps-Production-Template)

[![Template](https://img.shields.io/badge/use%20as-template-brightgreen.svg)](https://github.com/DuqueOM/ML-MLOps-Production-Template/generate)
[![Anti-Patterns](https://img.shields.io/badge/anti--patterns-12%20encoded-red.svg)](#anti-pattern-detection)
[![Clouds](https://img.shields.io/badge/clouds-GCP%20%2B%20AWS-orange.svg)](#technology-stack)
[![Agentic](https://img.shields.io/badge/agentic-Windsurf_%7C_Claude_Code_%7C_Cursor-blueviolet.svg)](#agentic-system)

---

## Quick Navigation

- **[What This Is](#what-this-is)**
- **[Try It in 5 Minutes](#try-it-in-5-minutes)**
- **[Architecture Overview](#architecture-overview)**
- **[Technology Stack](#technology-stack)**
- **[Quick Start](#quick-start)**
- **[What's Different](#whats-different-from-other-templates)**
- **[Agentic System](#agentic-system)**
- **[Critical Patterns (Invariants)](#critical-patterns-invariants)**
- **[Anti-Pattern Detection](#anti-pattern-detection)**
- **[Templates Detail](#templates-detail)**
- **[Contributing](#contributing)**
- **[Security](#security)**

## Real-World Example

This template was extracted from:

- **[ML-MLOps-Portfolio](https://github.com/DuqueOM/ML-MLOps-Portfolio)**

It shows how these patterns look when applied to real production-like ML services.

---

## Try It in 5 Minutes

A working fraud detection service that demonstrates the entire pipeline:

```bash
cd examples/minimal
pip install -r requirements.txt

# Train model (generates synthetic data, validates with Pandera, runs quality gates)
python train.py

# Start the API (async inference + SHAP + Prometheus metrics)
uvicorn serve:app --host 0.0.0.0 --port 8000

# Predict (in another terminal)
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"amount": 150.0, "hour": 2, "is_foreign": true, "merchant_risk": 0.8, "distance_from_home": 45.0}'

# With SHAP explanation
curl "http://localhost:8000/predict?explain=true" \
  -X POST -H "Content-Type: application/json" \
  -d '{"amount": 9500.0, "hour": 3, "is_foreign": true, "merchant_risk": 0.9, "distance_from_home": 200.0}'

# Run regression tests (leakage, SHAP consistency, latency, fairness)
pytest test_service.py -v

# Run drift detection (simulates production drift)
python drift_check.py
```

See [`examples/minimal/`](examples/minimal/) for the full working example.

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
┌──────────────────────────────────────────────────────────────────────────┐
│                     AGENTIC SYSTEM                                       │
│                                                                          │
│  AGENTS.md          → Root-level invariants + anti-pattern rules         │
│  CLAUDE.md          → Claude Code project context                        │
│  .claude/rules/     → Claude Code context-aware rules (paths: globs)     │
│  .cursor/rules/     → Cursor IDE rules                                   │
│  .windsurf/rules/   → 10 context-aware behavioral constraints            │
│  .windsurf/skills/  → 8 multi-step operational procedures                │
│  .windsurf/workflows/→ 8 prompt-triggered structured workflows           │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                     TEMPLATE SYSTEM                                      │
│                                                                          │
│  templates/service/     → FastAPI + training + monitoring                │
│  templates/common_utils/→ Shared library (seed, logging, persistence)    │
│  templates/k8s/base/    → Deployment, HPA, Kustomize base, Argo Rollouts │
│  templates/infra/       → Terraform GCP + AWS                            │
│  templates/cicd/        → GitHub Actions (CI, deploy, drift, retrain)    │
│  templates/scripts/     → deploy.sh, promote_model.sh, health_check      │
│  templates/docs/        → ADR, runbook, service README                   │
│  templates/monitoring/  → Grafana dashboard + Prometheus alerts          │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│                     TARGET PROJECT                                       │
│                                                                          │
│  {ServiceName}/                                                          │
│  ├── app/           → FastAPI (1 worker, ThreadPoolExecutor)             │
│  ├── src/{service}/                                                      │
│  │   ├── training/  → train.py, features.py, model.py                    │
│  │   ├── monitoring/→ drift_detection.py, business_kpis.py               │
│  │   └── schemas.py → Pandera DataFrameModel                             │
│  ├── tests/         → unit, integration, explainer, load                 │
│  ├── k8s/base/      → manifests + kustomize base                         │
│  ├── k8s/overlays/  → gcp-production/ + aws-production/                  │
│  ├── infra/         → terraform/gcp/ + terraform/aws/                    │
│  ├── docs/decisions/→ ADRs with measured trade-offs                      │
│  └── monitoring/    → Grafana + Prometheus per service                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

> **Note (`common_utils`)**: `templates/common_utils/` in this repository is the **canonical source**.
> If you maintain a copy in another repo (e.g., the portfolio), reconcile differences before production use.

| Layer | Technology | Notes |
|-------|-----------|-------|
| **ML Core** | scikit-learn, XGBoost, LightGBM, Optuna | Compatible release pinning (`~=`) |
| **Serving** | FastAPI + uvicorn (1 worker) | `asyncio.run_in_executor()` for inference |
| **Explainability** | SHAP KernelExplainer | Always in original feature space |
| **Data Validation** | Pandera DataFrameModel | Training, API, and drift checkpoints |
| **Drift Detection** | PSI (quantile bins) + Evidently | CronJob + Pushgateway + heartbeat alert |
| **Experiment Tracking** | MLflow | Self-hosted on K8s |
| **Containers** | Docker (multi-stage, non-root) | Model via Init Container, never baked in |
| **Orchestration** | Kubernetes (GKE + EKS) | CPU-only HPA, Kustomize overlays |
| **Infrastructure** | Terraform >= 1.7 | Remote state, tfsec + Checkov scanning |
| **CI/CD** | GitHub Actions | Lint → Test → Build → Deploy → Drift → Retrain |
| **Monitoring** | Prometheus + Grafana + AlertManager + Evidently | P1–P4 severity levels per service |
| **Data Versioning** | DVC (GCS + S3 remotes) | Tracked in git, stored in cloud |
| **Clouds** | GCP (primary) + AWS (parity) | Workload Identity / IRSA — no hardcoded creds |

---

## Quick Start

### 1. Clone the template

```bash
git clone https://github.com/DuqueOM/ML-MLOps-Production-Template.git
cd ML-MLOps-Production-Template
```

### 2. Create a new ML service

Use the scaffolding script or the `/new-service` workflow (in Windsurf Cascade):

```bash
# Automated scaffolding (recommended)
./templates/scripts/new-service.sh FraudDetector fraud_detector

# Or manually:
SERVICE_NAME="FraudDetector"
SERVICE_SLUG="fraud_detector"
cp -r templates/service/ ${SERVICE_NAME}/
find ${SERVICE_NAME}/ -type f -exec sed -i "s/{ServiceName}/${SERVICE_NAME}/g" {} +
find ${SERVICE_NAME}/ -type f -exec sed -i "s/{service}/${SERVICE_SLUG}/g" {} +
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
ML-MLOps-Production-Template/
│
├── AGENTS.md                              # Agent architecture, invariants, anti-patterns
├── CLAUDE.md                              # Claude Code project context
├── README.md                              # This file
├── SECURITY.md                            # Vulnerability reporting policy
├── CONTRIBUTING.md                        # Contribution guidelines
├── CODE_OF_CONDUCT.md                     # Contributor Covenant v2.0
├── CHANGELOG.md                           # Semantic versioning changelog
├── Makefile                               # Contributor DX: validate-templates, lint-all, demo-minimal
├── .pre-commit-config.yaml               # Contributor pre-commit hooks (black, isort, flake8, gitleaks)
├── .gitleaks.toml                         # Secret detection config (shared root + templates/)
├── .gitattributes                         # Git LFS + line ending config
│
├── .github/                               # GitHub community health files
│   ├── ISSUE_TEMPLATE/                    #   Bug report + feature request templates
│   ├── pull_request_template.md           #   PR checklist with anti-pattern verification
│   ├── dependabot.yml                     #   Automated dependency updates
│   └── workflows/validate-templates.yml   #   CI: Python lint, K8s validate, TF validate
│
├── .claude/rules/                         # Claude Code context-aware rules (paths: globs)
│   ├── 01-serving.md                      #   paths: **/app/*.py, **/api/*.py
│   ├── 02-training.md                     #   paths: **/training/*.py, **/models/*.py
│   ├── 03-kubernetes.md                   #   paths: k8s/**/*.yaml
│   ├── 04-terraform.md                    #   paths: **/*.tf
│   └── 05-examples.md                     #   paths: examples/**/*
│
├── .windsurf/                             # Agentic system configuration (Windsurf Cascade)
│   ├── rules/                             # 10 behavioral constraint files
│   │   ├── 01-mlops-conventions.md        #   always_on — core stack + skill references
│   │   ├── 02-kubernetes.md               #   glob: k8s/**/*.yaml
│   │   ├── 03-terraform.md                #   glob: **/*.tf
│   │   ├── 04a-python-serving.md          #   glob: **/app/*.py — async, SHAP, metrics
│   │   ├── 04b-python-training.md         #   glob: **/training/*.py — pipeline, gates
│   │   ├── 05-github-actions.md           #   glob: .github/workflows/*.yml
│   │   ├── 06-documentation.md            #   glob: docs/**/*.md
│   │   ├── 07-docker.md                   #   glob: **/Dockerfile*
│   │   ├── 08-data-validation.md          #   glob: **/schemas.py
│   │   ├── 09-monitoring.md               #   glob: monitoring/**/*
│   │   └── 10-examples.md                 #   glob: examples/**/*
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
    │   ├── pyproject.toml                 #   Modern Python project config (alternative)
    │   └── README.md                      #   Service-specific documentation
    │
    ├── common_utils/                      # Shared utility library
    │   ├── __init__.py                    #   Package init with public exports
    │   ├── seed.py                        #   Reproducibility (Python, NumPy, PyTorch, TF)
    │   ├── logging.py                     #   JSON (prod) + human-readable (dev) logging
    │   ├── model_persistence.py           #   joblib save/load with SHA256 integrity
    │   └── telemetry.py                   #   OpenTelemetry tracing (optional)
    │
    ├── k8s/                               # Kubernetes manifest templates
    │   ├── base/                          #   Kustomize base (all manifests here)
    │   │   ├── kustomization.yaml         #     Base Kustomize config
    │   │   ├── deployment.yaml            #     1-worker pod + init container for model
    │   │   ├── hpa.yaml                   #     CPU-only autoscaling (never memory)
    │   │   ├── service.yaml               #     ClusterIP service
    │   │   ├── cronjob-drift.yaml         #     Daily drift detection CronJob
    │   │   ├── serviceaccount.yaml        #     Workload Identity / IRSA annotations
    │   │   ├── networkpolicy.yaml         #     Ingress/egress traffic restrictions
    │   │   ├── rbac.yaml                  #     Role + RoleBinding (least privilege)
    │   │   └── argo-rollout.yaml          #     Canary deployment + AnalysisTemplate
    │   └── overlays/                      #   Environment-specific patches
    │       ├── gcp-production/            #     GKE: Artifact Registry, Workload Identity
    │       └── aws-production/            #     EKS: ECR, IRSA
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
    ├── scripts/                           # Operational scripts
    │   ├── new-service.sh                 #   Scaffold a new ML service from templates
    │   ├── deploy.sh                      #   Build, push, deploy with context verification
    │   ├── promote_model.sh               #   Quality gates → promote or reject
    │   └── health_check.sh                #   Pod status + endpoint health
    │
    ├── docs/                              # Documentation templates
    │   ├── decisions/adr-template.md      #   ADR with Options, Rationale, Revisit When
    │   ├── runbooks/runbook-template.md   #   P1–P4 incident response procedures
    │   ├── service-readme-template.md     #   Service README with measured data slots
    │   ├── model-card-template.md         #   ML transparency model card
    │   └── dependency-analysis-template.md#   Dependency conflict documentation
    │
    ├── monitoring/                        # Observability templates
    │   ├── alertmanager-rules.yaml        #   P1–P4 alerts + drift heartbeat + resources
    │   ├── prometheus/alerts-template.yaml #   P1–P4 alerts, drift heartbeat, resource alerts
    │   ├── prometheus/prometheus-demo.yml  #   Prometheus config for demo stack
    │   └── grafana/dashboard-template.json #   Request rate, latency, PSI, HPA, resources
    │
    ├── docker-compose.demo.yml            # Demo stack: service + MLflow + Pushgateway
    ├── Makefile                           # Standard DX targets: train, test, serve, build
    ├── .pre-commit-config.yaml            # black, isort, flake8, mypy, bandit, gitleaks
    ├── .gitleaks.toml                     # Secret detection config
    └── .env.example                       # Environment variable documentation
│
├── examples/minimal/                      # Working fraud detection demo (5 min)
│   ├── train.py                           #   Synthetic data + train + quality gates
│   ├── serve.py                           #   FastAPI + async inference + SHAP + Prometheus
│   ├── test_service.py                    #   Leakage, SHAP, latency, fairness tests
│   ├── drift_check.py                     #   PSI drift detection demo
│   └── requirements.txt                   #   Minimal dependencies
```

---

## Agentic System

This template supports **three AI coding assistants** out of the box:

| IDE / Agent | Config Location | Format |
|-------------|----------------|--------|
| **Windsurf Cascade** | `.windsurf/rules/`, `.windsurf/skills/`, `.windsurf/workflows/` | Markdown with glob triggers |
| **Claude Code** | `CLAUDE.md`, `.claude/rules/` | Context-aware rules with `paths:` frontmatter |
| **Cursor** | `.cursor/rules/*.mdc` | 5 MDC rules with frontmatter globs |

All three share the same invariants from `AGENTS.md` (canonical source). The `.windsurf/` directory has the richest configuration (10 rules, 8 skills, 8 workflows).

### Rules (Behavioral Constraints)

Rules activate based on file context. When you edit a Kubernetes YAML, `02-kubernetes.md` activates and enforces single-worker pods, CPU-only HPA, init containers, etc. When you edit serving code, `04a-python-serving.md` activates with async inference and SHAP rules. Training code gets `04b-python-training.md` instead — reducing unnecessary context.

| Rule | Trigger | Enforces |
|------|---------|----------|
| `01-mlops-conventions` | Always on | Stack, pinning, ADRs, calibration |
| `02-kubernetes` | `k8s/**/*.yaml` | 1 worker, CPU HPA, init containers |
| `03-terraform` | `**/*.tf` | Remote state, no secrets, lifecycle rules |
| `04a-python-serving` | `**/app/*.py` | Async inference, SHAP, Prometheus |
| `04b-python-training` | `**/training/*.py` | Pipeline structure, quality gates, fairness |
| `05-github-actions` | `.github/workflows/*.yml` | Workflow org, required secrets |
| `06-documentation` | `docs/**/*.md` | ADR structure, measured data |
| `07-docker` | `**/Dockerfile*` | Multi-stage, non-root, no model |
| `08-data-validation` | `**/schemas.py` | Pandera at 3 validation points |
| `09-monitoring` | `monitoring/**/*` | Mandatory metrics, PSI, heartbeat |
| `10-examples` | `examples/**/*` | Simplified, self-contained demos |

### Skills (Operational Procedures)

Skills are step-by-step guides the agent follows when performing complex operations. Each skill uses structured frontmatter (inspired by Claude Code's skill architecture) with:

- **`allowed-tools`** — Restricts which tools the agent can use during the skill
- **`when_to_use`** — Natural language examples that trigger the skill
- **`argument-hint`** — Template showing expected arguments
- **Per-step `Success criteria`** — Measurable conditions for each step

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
- **Tests** for data leakage, quality gates, API endpoints, SHAP consistency, latency SLA
- **Load tests** with Locust (100 concurrent users, < 1% error rate)
- **`pyproject.toml`** for modern Python tooling (alternative to `requirements.txt`)

### Common Utils (`templates/common_utils/`)

Reusable shared library for all ML services:

- **`seed.py`** — Reproducibility across Python, NumPy, PyTorch, TensorFlow with env var override
- **`logging.py`** — JSON formatter for K8s log aggregation (prod), colored output (dev)
- **`model_persistence.py`** — Optimized joblib save/load with SHA256 integrity validation
- **`telemetry.py`** — OpenTelemetry tracing with graceful no-op fallback

### K8s Templates (`templates/k8s/`)

- **Deployment** with init container model download, health probes, rolling update (zero downtime)
- **HPA** with CPU-only autoscaling, asymmetric scale-up/down behavior
- **CronJob** for daily drift detection with Pushgateway integration
- **ServiceAccount** with Workload Identity / IRSA annotation placeholders
- **Kustomize base** with namespace, common labels, and resource list
- **NetworkPolicy** restricting ingress (nginx + Prometheus) and egress (DNS, MLflow, cloud storage)
- **RBAC** Role + RoleBinding with least-privilege access (read ConfigMaps/Secrets only)
- **Kustomize overlays** for GCP (Artifact Registry, Workload Identity) and AWS (ECR, IRSA)
- **Argo Rollouts** canary deployment with Prometheus-based analysis (error rate, P95 latency)

### Scripts (`templates/scripts/`)

- **`deploy.sh`** — Build, push, deploy with kubectl context verification and image tag immutability check
- **`promote_model.sh`** — Run quality gates (metric threshold, fairness, leakage, integrity) before promotion
- **`health_check.sh`** — Quick pod status and /health + /model/info endpoint check

### Terraform Templates (`templates/infra/`)

- **GCP**: GKE cluster with Workload Identity, node pool autoscaling, GCS buckets (models, data, MLflow, logs), Artifact Registry
- **AWS**: EKS cluster with OIDC for IRSA, managed node group, IAM roles and policies

### CI/CD Templates (`templates/cicd/`)

- **CI**: flake8 + black + isort + mypy → pytest (90% coverage) → Docker build + Trivy scan
- **Infrastructure CI**: terraform fmt/init/validate + tfsec + Checkov + kubeconform
- **Deploy GCP/AWS**: Tag-triggered deploy with cluster verification and smoke tests
- **Drift Detection**: Daily scheduled + manual trigger, auto-creates GitHub issue on alert
- **Retraining**: Manual trigger with data validation, training, quality gates, and artifact upload

### Documentation Templates (`templates/docs/`)

- **ADR template**: Context, Options, Decision, Rationale, Consequences, Revisit When
- **Runbook template**: P1–P4 severity procedures with `kubectl` commands
- **Service README**: Measured latency tables, drift thresholds, cost breakdown, resource profile
- **Model card**: ML transparency document (intended use, metrics, fairness, limitations)
- **Dependency analysis**: Known conflicts, resolution strategies, CVE tracking

### Monitoring Templates (`templates/monitoring/`)

- **Prometheus alerts**: Error rate, service down, drift heartbeat, latency, resource usage, pod restarts
- **Grafana dashboard**: Request rate, error rate, latency percentiles, PSI scores, prediction distribution, HPA replicas, CPU/memory usage

### Developer Experience (`templates/`)

- **`Makefile`** — Standard targets: `make train`, `make test`, `make serve`, `make build`, `make demo-up`, `make lint`, `make clean`
- **`docker-compose.demo.yml`** — Local demo stack: ML service + MLflow + Pushgateway + Prometheus + Grafana
- **`.pre-commit-config.yaml`** — Pre-commit hooks: black, isort, flake8, mypy, bandit, gitleaks
- **`.gitleaks.toml`** — Secret detection config with allowlist for common false positives
- **`.env.example`** — Documented environment variables (MLflow, logging, API, DVC)

---

## What's Different From Other Templates

| Feature | This Template | cookiecutter-datascience | MLflow Templates | Kubeflow Pipelines |
|---------|:---:|:---:|:---:|:---:|
| **Async inference** (ThreadPoolExecutor) | Yes | No | No | No |
| **SHAP in original feature space** | Yes | No | No | No |
| **Encoded anti-patterns** (12 detectors) | Yes | No | No | No |
| **AI agent rules** (Windsurf/Claude/Cursor) | Yes | No | No | No |
| **Multi-cloud K8s** (GKE + EKS) | Yes | No | No | GKE only |
| **Init container model loading** | Yes | No | No | Yes |
| **PSI drift detection** (quantile bins) | Yes | No | No | Partial |
| **Quality gates** (metric + fairness + leakage) | Yes | No | No | Partial |
| **Heartbeat alerts** (CronJob health) | Yes | No | No | No |
| **Working example** (5 min demo) | Yes | No | No | No |
| **CPU-only HPA** (with reasoning) | Yes | No | No | No |
| **ADR-driven decisions** | Yes | No | No | No |

**In short**: cookiecutter-datascience stops at project structure. MLflow templates stop at experiment tracking.
Kubeflow focuses on pipeline orchestration. This template covers the **full production lifecycle** from
training through deployment, monitoring, drift detection, and retraining — with encoded invariants that
prevent the most common production failures.

---

## Documentation at Scale (MkDocs)

This README is intentionally comprehensive, but for larger teams you should move long-form
documentation (architecture deep-dives, operations guides, incident runbooks) into a versioned
docs site.

- **Recommended**: MkDocs Material + GitHub Pages
- **Reference**: see `mkdocs.yml` in the portfolio repo for a working example

---

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting guidelines, supported versions, and response timelines.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines. Quick summary:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request using the [PR template](.github/pull_request_template.md)

When adding new templates or rules, ensure they follow the **Engineering Calibration Principle** — sized to the actual problem, not the theoretical maximum.

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## AI Transparency

This template uses AI-assisted coding agents for code generation and boilerplate. All architectural decisions, system design, trade-off analysis, and ADR documentation require human engineering judgment. AI tools accelerate throughput — they don't replace the engineer's responsibility to calibrate solutions to the right scale.
