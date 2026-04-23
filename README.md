# ML-MLOps Production Template

**Ship ML models to production without reinventing the infrastructure.** This template encodes 22 production anti-patterns, multi-cloud K8s deployment (GKE + EKS), an agentic behavior protocol (AUTO/CONSULT/STOP), closed-loop monitoring with delayed ground truth + sliced performance + champion/challenger, and supply-chain security (Cosign + SBOM + Kyverno) — so your AI assistant builds it right the first time.

[![Release](https://img.shields.io/github/v/release/DuqueOM/ML-MLOps-Production-Template.svg)](https://github.com/DuqueOM/ML-MLOps-Production-Template/releases)
[![Python 3.11 | 3.12](https://img.shields.io/badge/python-3.11_%7C_3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Terraform >= 1.7](https://img.shields.io/badge/terraform-%3E%3D1.7-blueviolet.svg)](https://www.terraform.io/)
[![Kubernetes](https://img.shields.io/badge/k8s-GKE%20%2B%20EKS-326CE5.svg)](https://kubernetes.io/)

[![Validate Templates](https://github.com/DuqueOM/ML-MLOps-Production-Template/actions/workflows/validate-templates.yml/badge.svg)](https://github.com/DuqueOM/ML-MLOps-Production-Template/actions/workflows/validate-templates.yml)
[![codecov](https://codecov.io/gh/DuqueOM/ML-MLOps-Production-Template/branch/main/graph/badge.svg)](https://codecov.io/gh/DuqueOM/ML-MLOps-Production-Template)

[![Template](https://img.shields.io/badge/use%20as-template-brightgreen.svg)](https://github.com/DuqueOM/ML-MLOps-Production-Template/generate)
[![Anti-Patterns](https://img.shields.io/badge/anti--patterns-22%20encoded-red.svg)](#anti-pattern-detection)
[![Clouds](https://img.shields.io/badge/clouds-GCP%20%2B%20AWS-orange.svg)](#technology-stack)
[![Agentic](https://img.shields.io/badge/agentic-Windsurf_%7C_Claude_Code_%7C_Cursor-blueviolet.svg)](#agentic-system)

```bash
# Clone → scaffold → serve in 3 commands
git clone https://github.com/DuqueOM/ML-MLOps-Production-Template.git
cd ML-MLOps-Production-Template
./templates/scripts/new-service.sh ChurnPredictor churn_predictor
```

**[QUICK_START.md](QUICK_START.md)** — From clone to first model served in 10 minutes
&nbsp;|&nbsp; **[RUNBOOK.md](RUNBOOK.md)** — Template operations reference

---

## Quick Navigation

| Getting Started | Architecture | Development |
|----------------|-------------|-------------|
| [Try It in 5 Minutes](#try-it-in-5-minutes) | [Architecture Overview](#architecture-overview) | [Agentic System](#agentic-system) |
| [Quick Start](#quick-start) | [Technology Stack](#technology-stack) | [Critical Patterns](#critical-patterns-invariants) |
| [QUICK_START.md](QUICK_START.md) | [What's Different](#whats-different-from-other-templates) | [Anti-Pattern Detection](#anti-pattern-detection) |
| [RUNBOOK.md](RUNBOOK.md) | [Templates Detail](#templates-detail) | [Contributing](#contributing) |

## Real-World Example

This template was extracted from **[ML-MLOps-Portfolio](https://github.com/DuqueOM/ML-MLOps-Portfolio)** — a production portfolio with 3 ML services (BankChurn, NLPInsight, ChicagoTaxi), 18 ADRs, 395+ tests, and live deployments on GKE + EKS.

| Resource | Link |
|----------|------|
| **Source repo** | [github.com/DuqueOM/ML-MLOps-Portfolio](https://github.com/DuqueOM/ML-MLOps-Portfolio) |
| **Full documentation (MkDocs)** | [duqueom.github.io/ML-MLOps-Portfolio](https://duqueom.github.io/ML-MLOps-Portfolio/) |
| **Architecture decisions (18 ADRs)** | [portfolio ADR index](https://duqueom.github.io/ML-MLOps-Portfolio/decisions/) |
| **Operational status** | [PORTFOLIO_STATUS.md](https://github.com/DuqueOM/ML-MLOps-Portfolio/blob/main/PORTFOLIO_STATUS.md) |

The portfolio demonstrates the patterns this template encodes — real
incidents diagnosed, real trade-offs documented, real deployments verified.

---

## What This Is

A **complete, opinionated template** for shipping ML models to production — not a toy notebook, not a mega-framework. It includes:

- **An agentic system** (12 rules, 11 skills, 10 workflows) with a formal **AUTO/CONSULT/STOP behavior protocol** that guides AI coding assistants to build, audit, and maintain MLOps projects
- **Production-ready templates** for every layer: EDA → training → serving → infrastructure → CI/CD → monitoring → documentation
- **Encoded invariants** that prevent the 19 most common ML production failures (event loop blocking, memory HPA, model-in-image, data leakage, hardcoded credentials, unsigned images, etc.)
- **Supply-chain security out of the box** — gitleaks, Trivy, Syft SBOM, Cosign keyless signing (OIDC), Kyverno admission verification
- **Engineering calibration** — every component is sized to actual requirements, avoiding both under-engineering and over-engineering

## Who It's For

- ML engineers shipping models to production for the first time
- Teams standardizing their MLOps across multiple services
- Engineers using AI coding assistants (Windsurf Cascade, Claude Code, Cursor) who want those tools to follow best practices automatically

---

## Try It in 5 Minutes

A working fraud detection service that demonstrates the entire pipeline:

```bash
git clone https://github.com/DuqueOM/ML-MLOps-Production-Template.git
cd ML-MLOps-Production-Template

# Zero-to-ready in one command (detects OS, installs deps, configures MCPs, runs example)
make bootstrap

# Or just the demo (install → train → test → drift)
make demo-minimal

# Or with Docker (API + MLflow)
docker compose up --build
# API: http://localhost:8000/docs | MLflow: http://localhost:5000
```

> `make bootstrap` is idempotent and safe to re-run. Flags: `--skip-mcp`, `--skip-demo`, `--check-only`.

Or step by step:

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

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     AGENTIC SYSTEM                                       │
│                                                                          │
│  AGENTS.md          → Root-level invariants + anti-pattern rules         │
│  CLAUDE.md          → Claude Code project context                        │
│  .claude/rules/     → Claude Code context-aware rules (paths: globs)     │
│  .cursor/rules/     → Cursor IDE rules                                   │
│  .windsurf/rules/   → 12 context-aware behavioral constraints            │
│  .windsurf/skills/  → 11 multi-step operational procedures               │
│  .windsurf/workflows/→ 10 prompt-triggered slash commands                │
│  Agent Behavior Protocol → AUTO / CONSULT / STOP modes per operation     │
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

> For a more detailed guide, see **[QUICK_START.md](QUICK_START.md)**.

### 1. Clone and scaffold

```bash
git clone https://github.com/DuqueOM/ML-MLOps-Production-Template.git
cd ML-MLOps-Production-Template

# Scaffold a new service (copies all templates, replaces placeholders)
./templates/scripts/new-service.sh ChurnPredictor churn_predictor

# Or via Make:
make new-service NAME=ChurnPredictor SLUG=churn_predictor
```

This creates `ChurnPredictor/` with the full service structure: FastAPI app, training pipeline, K8s manifests, Terraform, CI/CD, monitoring, tests, DVC pipeline, and documentation templates.

### 2. Configure your features

```bash
cd ChurnPredictor
```

Edit these files with your actual features:

- `src/churn_predictor/schemas.py` — Pandera schema (data validation)
- `src/churn_predictor/training/features.py` — Feature engineering
- `src/churn_predictor/training/model.py` — Model pipeline
- `app/schemas.py` — Pydantic request/response models

### 3. Train and serve

```bash
pip install -r requirements.txt

# Train
make train DATA=data/raw/your-dataset.csv

# Serve locally
make serve

# Test prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"feature_a": 42.0, "feature_b": 50000.0, "feature_c": "category_A"}'
```

### 4. Deploy to production

```bash
# Build and push Docker image
docker build -t churn_predictor:v1.0.0 .

# Deploy to GKE
kubectl apply -k k8s/overlays/gcp-production/

# Deploy to EKS
kubectl apply -k k8s/overlays/aws-production/
```

See the [Release Checklist](templates/docs/CHECKLIST_RELEASE.md) for the full pre-deployment checklist.

---

## Repository Structure

```
ML-MLOps-Production-Template/
│
├── AGENTS.md                              # Agent architecture, invariants, anti-patterns
├── CLAUDE.md                              # Claude Code project context
├── README.md                              # This file
├── QUICK_START.md                         # 10-minute setup guide (standalone)
├── RUNBOOK.md                             # Template operations reference
├── CHANGELOG.md                           # Semantic versioning changelog
├── LICENSE                                # MIT License
├── SECURITY.md                            # Vulnerability reporting policy
├── CONTRIBUTING.md                        # Contribution guidelines
├── CODE_OF_CONDUCT.md                     # Contributor Covenant v2.0
├── Makefile                               # Contributor DX: validate-templates, lint-all, demo-minimal
├── docker-compose.yml                     # Local dev: example API + MLflow (docker compose up)
├── pyproject.toml                         # Root project config (pytest, coverage, black, isort)
├── .pre-commit-config.yaml               # Contributor pre-commit hooks (black, isort, flake8, gitleaks)
├── .gitleaks.toml                         # Secret detection config (shared root + templates/)
├── .gitattributes                         # Git LFS + line ending config
│
├── releases/                              # GitHub Release notes (copy to Releases page)
│   ├── v1.0.0.md
│   ├── v1.1.0.md
│   ├── v1.2.0.md
│   └── v1.3.0.md
│
├── docs/                                  # Template-level decisions
│   └── decisions/
│       └── ADR-001-template-scope-boundaries.md  # Why LLM/multi-tenancy/Vault deferred
│
├── .github/                               # GitHub community health files
│   ├── ISSUE_TEMPLATE/                    #   Bug report + feature request templates
│   ├── pull_request_template.md           #   PR checklist with anti-pattern verification
│   ├── dependabot.yml                     #   Automated dependency updates
│   └── workflows/validate-templates.yml   #   CI: lint, K8s, TF, Dockerfile + e2e example
│
├── .claude/rules/                         # Claude Code context-aware rules (paths: globs)
│   ├── 01-serving.md                      #   paths: **/app/*.py, **/api/*.py
│   ├── 02-training.md                     #   paths: **/training/*.py, **/models/*.py
│   ├── 03-kubernetes.md                   #   paths: k8s/**/*.yaml
│   ├── 04-terraform.md                    #   paths: **/*.tf
│   ├── 05-examples.md                     #   paths: examples/**/*
│   ├── 06-data-eda.md                     #   paths: eda/**/*, **/notebooks/**/*.ipynb
│   ├── 07-security-secrets.md             #   paths: **/* (always-applicable) — D-17/18/19
│   └── 08-closed-loop.md                  #   paths: prediction_logger/ground_truth/performance_monitor — D-20/21/22
│
├── .cursor/rules/                         # Cursor IDE rules (globs: frontmatter)
│   ├── 01-mlops-conventions.mdc           #   Session protocol, D-01→D-22, Behavior Protocol
│   ├── 02-kubernetes.mdc                  #   K8s: 1 worker, CPU HPA, init container
│   ├── 03-python-serving.mdc              #   Async inference, SHAP, Prometheus
│   ├── 04-python-training.mdc             #   Pipeline, quality gates, tests
│   ├── 05-docker.mdc                      #   Multi-stage, non-root, no model
│   ├── 06-data-eda.mdc                    #   globs: eda/**/*, **/notebooks/**/*.ipynb
│   ├── 07-security-secrets.mdc            #   globs: **/* — D-17/D-18/D-19
│   └── 08-closed-loop.mdc                 #   globs: prediction_logger/ground_truth/performance_monitor — D-20/21/22
│
├── .windsurf/                             # Agentic system configuration (Windsurf Cascade)
│   ├── rules/                             # 13 behavioral constraint files
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
│   │   ├── 10-examples.md                 #   glob: examples/**/*
│   │   ├── 11-data-eda.md                 #   glob: eda/**/*, **/notebooks/**/*.ipynb
│   │   ├── 12-security-secrets.md         #   always_on — D-17/D-18/D-19
│   │   └── 13-closed-loop-monitoring.md   #   glob: prediction_logger/ground_truth/performance_monitor — D-20/D-21/D-22
│   │
│   ├── skills/                            # 12 multi-step operational procedures
│   │   ├── debug-ml-inference/SKILL.md    #   Diagnose inference issues
│   │   ├── deploy-gke/SKILL.md            #   Deploy to GCP GKE (dev=AUTO, staging=CONSULT, prod=STOP)
│   │   ├── deploy-aws/SKILL.md            #   Deploy to AWS EKS (same auth modes)
│   │   ├── drift-detection/SKILL.md       #   Run PSI drift analysis
│   │   ├── eda-analysis/SKILL.md          #   6-phase EDA with leakage gate
│   │   ├── security-audit/SKILL.md        #   Pre-build/deploy: gitleaks + Trivy + Cosign
│   │   ├── secret-breach-response/SKILL.md#   Incident response for leaked secrets
│   │   ├── model-retrain/SKILL.md         #   Retrain with quality gates (STOP on Prod) + C/C (ADR-008)
│   │   ├── concept-drift-analysis/SKILL.md#   RCA for sliced performance regressions
│   │   ├── release-checklist/SKILL.md     #   Multi-cloud release
│   │   ├── new-service/SKILL.md           #   Scaffold a new ML service
│   │   └── cost-audit/SKILL.md            #   Cloud cost review
│   │
│   └── workflows/                         # 11 prompt-triggered workflows
│       ├── release.md                     #   /release
│       ├── retrain.md                     #   /retrain
│       ├── load-test.md                   #   /load-test
│       ├── new-adr.md                     #   /new-adr
│       ├── incident.md                    #   /incident
│       ├── drift-check.md                 #   /drift-check
│       ├── eda.md                         #   /eda
│       ├── performance-review.md          #   /performance-review
│       ├── secret-breach.md               #   /secret-breach
│       ├── new-service.md                 #   /new-service
│       └── cost-review.md                 #   /cost-review
│
├── examples/minimal/                      # Working fraud detection demo (5 min)
│   ├── train.py                           #   Synthetic data + train + quality gates
│   ├── serve.py                           #   FastAPI + async inference + SHAP + Prometheus
│   ├── test_service.py                    #   Leakage, SHAP, latency, fairness tests
│   ├── drift_check.py                     #   PSI drift detection demo
│   ├── Dockerfile                         #   For docker-compose.yml demo
│   └── requirements.txt                   #   Minimal dependencies
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
    │   ├── dvc.yaml                       #   DVC pipeline template (validate → featurize → train → evaluate)
    │   ├── .dvc/config                    #   DVC remote config (GCS/S3)
    │   ├── codecov.yml                    #   Codecov config template
    │   ├── Dockerfile                     #   Multi-stage, non-root, HEALTHCHECK
    │   ├── .dockerignore                  #   Excludes models, data, tests
    │   ├── requirements.txt               #   Pinned with ~= (compatible release)
    │   ├── pyproject.toml                 #   Modern Python project config
    │   └── README.md                      #   Service-specific documentation
    │
    ├── common_utils/                      # Shared utility library
    │   ├── __init__.py                    #   Package init with public exports
    │   ├── seed.py                        #   Reproducibility (Python, NumPy, PyTorch, TF)
    │   ├── logging.py                     #   JSON (prod) + human-readable (dev) logging
    │   ├── model_persistence.py           #   joblib save/load with SHA256 integrity
    │   └── telemetry.py                   #   OpenTelemetry tracing (optional)
    │
    ├── tests/                             # Test templates
    │   ├── integration/                   #   Integration tests
    │   │   ├── conftest.py                #     Service health wait + fixtures
    │   │   └── test_service_integration.py #   Health, predict, SHAP, latency SLA
    │   └── infra/policies/                #   OPA/Conftest policies
    │       └── kubernetes.rego            #     Security + ML anti-pattern enforcement
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
    │   │   ├── slo-prometheusrule.yaml    #     SLO/SLA definitions (availability, latency, error budget)
    │   │   └── argo-rollout.yaml          #     Canary deployment + AnalysisTemplate
    │   └── overlays/                      #   Environment-specific patches
    │       ├── gcp-production/            #     GKE: Artifact Registry, Workload Identity
    │       └── aws-production/            #     EKS: ECR, IRSA
    │
    ├── infra/                             # Infrastructure templates
    │   ├── terraform/gcp/                 #   GKE cluster, GCS buckets, Artifact Registry
    │   ├── terraform/aws/                 #   EKS cluster, OIDC, IAM roles
    │   └── docker-compose.mlflow.yml      #   MLflow + PostgreSQL + MinIO (local tracking)
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
    │   ├── CHECKLIST_RELEASE.md           #   Pre-deployment release checklist
    │   ├── mkdocs.yml                     #   MkDocs Material config template
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
```

---

## Agentic System

This template supports **three AI coding assistants** out of the box:

| IDE / Agent | Config Location | Format |
|-------------|----------------|--------|
| **Windsurf Cascade** | `.windsurf/rules/`, `.windsurf/skills/`, `.windsurf/workflows/` | Markdown with glob triggers |
| **Claude Code** | `CLAUDE.md`, `.claude/rules/` | Context-aware rules with `paths:` frontmatter |
| **Cursor** | `.cursor/rules/*.mdc` | 7 MDC rules with frontmatter globs |

All three share the same invariants from `AGENTS.md` (canonical source). The `.windsurf/` directory has the richest configuration (13 rules, 12 skills, 11 workflows). Claude Code and Cursor have full invariant parity (D-01→D-22) but lack skills/workflows — those are invoked via conversation in any IDE.

#### Claude Code (`.claude/rules/`)

7 context-aware rules using `paths:` frontmatter. Claude Code activates rules automatically when you open matching files:

| File | Paths Trigger | Covers |
|------|--------------|--------|
| `01-serving.md` | `**/app/*.py`, `**/api/*.py` | Async inference, SHAP, Prometheus, D-01/D-03/D-04 |
| `02-training.md` | `**/training/*.py`, `**/models/*.py` | Pipeline, quality gates, fairness, D-05/D-06/D-07 |
| `03-kubernetes.md` | `k8s/**/*.yaml` | 1-worker, CPU HPA, init container, D-01/D-02/D-11 |
| `04-terraform.md` | `**/*.tf` | Remote state, no secrets, lifecycle, D-10 |
| `05-examples.md` | `examples/**/*` | Simplified patterns, self-contained demos |
| `06-data-eda.md` | `eda/**/*`, `**/notebooks/**/*.ipynb` | 6-phase EDA, baseline distributions, leakage gate, D-13/D-14/D-15/D-16 |
| `07-security-secrets.md` | `**/*` (always-applicable) | Secrets hygiene, IRSA/WI, supply chain, D-17/D-18/D-19 |
| `08-closed-loop.md` | `**/prediction_logger.py`, `**/ground_truth.py`, `**/performance_monitor.py`, ... | Prediction logging, ground truth, sliced performance, champion/challenger (D-20→D-22) |

Root context: `CLAUDE.md` provides project-wide context (stack, invariants, file structure) loaded at session start.

#### Cursor (`.cursor/rules/`)

7 MDC rules with `globs:` frontmatter. Cursor activates rules based on glob patterns:

| File | Globs Trigger | Covers |
|------|--------------|--------|
| `01-mlops-conventions.mdc` | `**/*` (always on) | Session protocol, D-01→D-22, Agent Behavior Protocol, stack, ADRs |
| `02-kubernetes.mdc` | `k8s/**/*.yaml`, `helm/**/*.yaml` | HPA, init container, probes, RBAC |
| `03-python-serving.mdc` | `**/app/*.py` | Async, ThreadPoolExecutor, SHAP, metrics |
| `04-python-training.mdc` | `**/training/*.py` | Pipeline, gates, fairness, DVC |
| `05-docker.mdc` | `**/Dockerfile*` | Multi-stage, non-root, HEALTHCHECK, no model in image |
| `06-data-eda.mdc` | `eda/**/*`, `**/notebooks/**/*.ipynb` | EDA structure, baseline distributions, leakage gate (D-13→D-16) |
| `07-security-secrets.mdc` | `**/*` (always-applicable) | Secrets, IRSA/WI, Cosign/SBOM, always-applicable (D-17→D-19) |
| `08-closed-loop.mdc` | `**/prediction_logger.py`, `**/ground_truth.py`, `**/performance_monitor.py`, ... | Prediction logging, ground truth, sliced performance, champion/challenger (D-20→D-22) |

#### Windsurf Cascade (`.windsurf/`)

13 context-aware rules + 12 skills + 11 workflows, plus a formal **Agent Behavior Protocol (AUTO / CONSULT / STOP)** and typed inter-agent handoffs. Canonical source for the other IDEs:

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

The agentic system automatically detects and corrects 22 known production failure modes grouped by domain:

- **D-01→D-05**: Runtime & serving (FastAPI async, ThreadPoolExecutor, SHAP, pinning)
- **D-06→D-09**: Training & monitoring (leakage, SHAP bg, PSI bins, heartbeat)
- **D-10→D-12**: Infrastructure & governance (TF state, init container, quality gates)
- **D-13→D-16**: EDA & data (sandbox, observed ranges, baseline, feature rationale)
- **D-17→D-19**: Security & supply chain (secrets, IRSA/WI, signed images + SBOM)
- **D-20→D-22**: Closed-loop monitoring (prediction_id/entity_id, fire-and-forget logging, observability failure isolation)

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
| D-13 | EDA on production data | Sandbox `data/raw/` copy; EDA never writes to prod paths |
| D-14 | Pandera schema without observed ranges | `Check.in_range(min, max)` from EDA phase 1 |
| D-15 | Baseline distributions not persisted | Save `02_baseline_distributions.pkl` (drift CronJob input) |
| D-16 | Feature engineering without rationale | `05_feature_proposals.yaml` with justification |
| D-17 | Hardcoded credentials / `os.environ` for secrets | Use `common_utils.secrets.get_secret` |
| D-18 | Static AWS keys or GCP JSON keys in production | IRSA (AWS) / Workload Identity (GCP) |
| D-19 | Unsigned images or missing SBOM in production | Cosign keyless + Syft SBOM + Kyverno admission |
| D-20 | Prediction log missing `prediction_id` / `entity_id` | `PredictionEvent` frozen dataclass enforces at construction |
| D-21 | Prediction logging blocking the async event loop | Buffered logger + `run_in_executor(None, ...)` background flush |
| D-22 | Observability backend failure reaching HTTP response | Swallow + counter `prediction_log_errors_total`; serving never breaks |

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
- **DVC pipeline** (`dvc.yaml`) with validate → featurize → train → evaluate stages
- **DVC config** (`.dvc/config`) with GCS/S3 remote storage setup

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
- **SLO/SLA PrometheusRule** — availability (99.5%), latency P95, error budget burn rate alerts
- **Argo Rollouts** canary deployment with Prometheus-based analysis (error rate, P95 latency)

### Scripts (`templates/scripts/`)

- **`deploy.sh`** — Build, push, deploy with kubectl context verification and image tag immutability check
- **`promote_model.sh`** — Run quality gates (metric threshold, fairness, leakage, integrity) before promotion
- **`health_check.sh`** — Quick pod status and /health + /model/info endpoint check

### Integration Tests (`templates/tests/integration/`)

- **`conftest.py`** — Service health wait fixture, auto-skip if service unavailable
- **`test_service_integration.py`** — Full service validation: health, predictions, SHAP, latency SLA, metrics

### OPA/Conftest Policies (`templates/tests/infra/policies/`)

- **`kubernetes.rego`** — 12 policy rules: non-root, resource limits/requests, health probes, no `:latest`, namespace, app label, HPA scaleDown + ML-specific D-01 (no multi-worker) and D-02 (no memory HPA) enforcement

### Terraform & Infrastructure (`templates/infra/`)

- **GCP**: GKE cluster with Workload Identity, node pool autoscaling, GCS buckets (models, data, MLflow, logs), Artifact Registry
- **AWS**: EKS cluster with OIDC for IRSA, managed node group, IAM roles and policies
- **`docker-compose.mlflow.yml`** — Production-like MLflow with PostgreSQL + MinIO (S3-compatible) for local development

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
- **Release checklist**: Pre-deployment verification (quality gates, Docker, K8s, infra, monitoring)
- **MkDocs config**: MkDocs Material template with navigation, plugins, and theme ready to use
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
| **Encoded anti-patterns** (22 detectors) | Yes | No | No | No |
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

For larger teams, move long-form documentation into a versioned docs site:

- **Template**: [`templates/docs/mkdocs.yml`](templates/docs/mkdocs.yml) — MkDocs Material config ready to use
- **Setup**: `pip install mkdocs-material mkdocstrings[python] mkdocs-mermaid2-plugin`
- **Reference**: see `mkdocs.yml` in the [portfolio repo](https://github.com/DuqueOM/ML-MLOps-Portfolio) for a working example with 17 ADRs

---

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting guidelines, supported versions, and response timelines.

---

## MCP Integrations

MCPs extend what agents can **do** (execute commands, read live data) vs. just generate text.

| MCP | Skill/Workflow enhanced | Agent capability unlocked |
|-----|------------------------|--------------------------|
| **`mcp-github`** | All CI workflows | Reads CI logs and PR status directly — no copy-paste into chat |
| **`mcp-kubernetes`** | `deploy-gke`, `deploy-aws`, `/release` | Executes `kubectl apply/get/logs` and verifies pod status |
| **`mcp-terraform`** | `/release`, `release-checklist` | Runs `terraform plan/validate` and reads infra state |
| **`mcp-prometheus`** | `drift-detection`, `/incident` | Queries live metrics instead of hypothetical examples |

MCPs installed = agents **execute**. MCPs absent = agents **instruct**. Same invariants apply either way.

> Full setup instructions and rationale: [`AGENTS.md § MCP Integrations`](AGENTS.md#mcp-integrations)

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

---

<p align="center">
  <b>If this template saved you time, please give it a ⭐</b>
</p>
