# Changelog

All notable changes to the ML-MLOps Production Template are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

---

## [1.3.0] - 2026-04-16

### Added

#### Standalone Documentation (root)
- **`QUICK_START.md`** — 10-minute setup guide: Option A (example demo), Option B (scaffold service), Option C (full MLflow stack)
- **`RUNBOOK.md`** — Template operations reference: scaffolding, validation, MLflow, contributing, release process
- **`LICENSE`** — MIT License (was referenced in README but file was missing)
- **`docker-compose.yml`** — Local dev stack: example fraud detection API + MLflow (one command: `docker compose up`)
- **`releases/`** — GitHub Release notes directory: `v1.0.0.md`, `v1.1.0.md`, `v1.2.0.md` ready to publish

#### DVC Templates (new)
- **`templates/service/dvc.yaml`** — DVC pipeline with 4 stages: validate → featurize → train → evaluate
- **`templates/service/.dvc/config`** — DVC remote configuration template for GCS/S3 storage

#### Infrastructure (from portfolio)
- **`templates/infra/docker-compose.mlflow.yml`** — Production-like MLflow stack: PostgreSQL + MinIO (S3-compatible) + MLflow server with health checks

#### Documentation Templates (new)
- **`templates/docs/CHECKLIST_RELEASE.md`** — Pre-deployment release checklist: quality gates, Docker, K8s, infra, monitoring, multi-cloud
- **`templates/docs/mkdocs.yml`** — MkDocs Material configuration template with navigation, plugins, theme, and docstring support

#### Integration Test Templates (new)
- **`templates/tests/integration/conftest.py`** — Service health wait fixture, auto-skip if unavailable
- **`templates/tests/integration/test_service_integration.py`** — Full service validation: health, predictions, SHAP, latency SLA, metrics, model info

#### Enterprise K8s & Security (new)
- **`templates/tests/infra/policies/kubernetes.rego`** — OPA/Conftest policies (ported from portfolio): non-root, resource limits, health probes, no :latest, namespace, HPA scaleDown + ML-specific D-01/D-02 enforcement
- **`templates/k8s/base/slo-prometheusrule.yaml`** — SLO/SLA definitions as PrometheusRule:
  - Availability SLI (99.5% non-5xx), Latency SLI (95% < 500ms)
  - Error budget recording rules (30-day window)
  - Multi-window burn rate alerts: P1 (14.4x/1h), P2 (6x/6h), P3 (budget < 25%)

#### Service Template Additions
- **`templates/service/codecov.yml`** — Codecov configuration template with per-service coverage flags

#### Example Improvements
- **`examples/minimal/Dockerfile`** — Docker image for the fraud detection example (used by root docker-compose.yml)

### Changed

#### README — Major Restructure
- **Concise hook at top** — Problem statement + differentiator in 3 lines, replacing verbose intro
- **Quick Navigation** — Replaced bullet list with 3-column table (Getting Started | Architecture | Development)
- **Quick Start** — Removed manual `sed -i` commands, now uses `new-service.sh` exclusively (fixes inconsistency with CHANGELOG v1.1.0)
- **"Try It in 5 Minutes"** — Added `make demo-minimal` one-liner and Docker Compose alternative
- **Repository Structure** — Updated tree with all new files: QUICK_START.md, RUNBOOK.md, LICENSE, docker-compose.yml, releases/, DVC, integration tests, SLO, mkdocs, checklist, MLflow compose
- **Templates Detail** — Added sections for DVC, integration tests, SLO, MLflow, release checklist, MkDocs
- **MkDocs section** — Now references `templates/docs/mkdocs.yml` template instead of just the portfolio
- Added links to QUICK_START.md and RUNBOOK.md at top of README

#### AGENTS.md
- Updated Template System tree with DVC, pyproject.toml, integration tests, SLO, MLflow compose, mkdocs, checklist

#### CLAUDE.md
- Updated File Structure with all new files and directories

#### `new-service.sh`
- Added DVC template copying step
- Added integration test template copying
- Added `data/validated/`, `data/processed/`, `reports/` to standard directories

### Notes

#### Claude-code-main Assessment
- Evaluated `/home/duque_om/projects/Claude-code-main` — TypeScript CLI rebuild of Claude Code, **no reusable content** for this MLOps template

#### Enterprise Gap Assessment
- **Already present**: RBAC (`rbac.yaml`), NetworkPolicy (`networkpolicy.yaml`), Workload Identity / IRSA
- **Added in v1.3.0**: SLO/SLA PrometheusRule
- **Still missing** (tracked for future): External Secrets Operator templates, multi-tenancy considerations. These are deferred per the Engineering Calibration Principle — they add complexity beyond the template's target scale.

---

## [1.2.0] - 2026-04-15

### Added

#### Developer Experience (root DX files)
- **`Makefile`** (root) — Contributor entry point with template-specific targets:
  - `make validate-templates` — lint + K8s validation in one command
  - `make lint-all` / `make format-all` — operate on all Python across `templates/` and `examples/`
  - `make demo-minimal` — run fraud detection example end-to-end (install → train → test → drift)
  - `make test-examples` — regression tests for examples/
  - `make new-service NAME=X SLUG=y` — scaffold wrapper around `new-service.sh`
- **`.pre-commit-config.yaml`** (root) — Contributor hooks: black, isort, flake8, `pre-commit-hooks` (yaml, merge conflicts, large files), gitleaks
- **`.gitleaks.toml`** (root) — Secret detection config shared between root and `templates/`, with allowlists for template placeholder tokens (`{ServiceName}`, `{service}`)

#### Multi-IDE Cursor Parity
- **`.cursor/rules/02-kubernetes.mdc`** — K8s rules: 1 worker, CPU HPA, init container pattern with code example
- **`.cursor/rules/03-python-serving.mdc`** — Serving rules: async inference, SHAP KernelExplainer, Prometheus metrics
- **`.cursor/rules/04-python-training.mdc`** — Training rules: pipeline sequence, quality gate table, required tests
- **`.cursor/rules/05-docker.mdc`** — Docker rules: multi-stage, non-root USER, HEALTHCHECK, no model artifacts

#### GitHub Releases
- **v1.0.0** — tag pushed to remote (was created locally, not published)
- **v1.1.0** — annotated tag created and pushed with full release notes

### Changed

#### CI Template (`templates/cicd/ci.yml`)
- Added **Python 3.12 matrix** — test job now runs `["3.11", "3.12"]` in parallel
- Added **Codecov integration** — uploads `coverage.xml` on `3.11` run via `codecov/codecov-action@v4`
- Coverage report format changed from `term-missing` only → `xml` + `term-missing`

#### README
- Added **Release badge** with dynamic version from GitHub Releases
- Updated **Python badge** to `3.11 | 3.12`
- Added **Codecov badge**
- Updated `.cursor/rules/` entry to reflect 5 MDC rules (was 1)
- Updated repo tree with root DX files (`Makefile`, `.pre-commit-config.yaml`, `.gitleaks.toml`)

#### AGENTS.md / CLAUDE.md / .cursor/rules/
- Updated Multi-IDE Support section in AGENTS.md to show all 5 cursor rules

---

## [1.1.0] - 2026-04-15

### Added

#### Working Example (`examples/minimal/`)
- **Fraud detection service** — fully functional end-to-end demo (train → serve → predict → test → drift)
- `train.py` — synthetic data generation, Pandera validation, sklearn pipeline, quality gates
- `serve.py` — FastAPI with async inference (ThreadPoolExecutor), SHAP KernelExplainer, Prometheus metrics
- `test_service.py` — regression tests: data leakage, SHAP consistency, latency SLA, fairness DIR
- `drift_check.py` — PSI drift detection with quantile bins and exit codes (0/1/2)

#### Scaffolding
- **`new-service.sh`** — automated scaffolding script: copies templates, replaces placeholders ({ServiceName}, {service}, {SERVICE}), creates directory structure

#### Monitoring
- **`alertmanager-rules.yaml`** — production AlertManager rules with P1–P4 severity:
  - Service down + error rate spike (P1)
  - Inference latency degradation (P2)
  - **Drift heartbeat missing** (P2) — fires if CronJob hasn't run in 48h
  - PSI drift alert/warning (P3)
  - CPU approaching limit + pod restarts (P4)

### Changed

#### drift_detection.py — Production CronJob Integration
- Added **exit codes** (0=ok, 1=warning, 2=alert) for K8s CronJob integration
- Added **GitHub Issue creation** on alert-level drift via GitHub API
- Added **reference data update** with timestamped backups
- Added proper `main()` function with `sys.exit()` for clean process control

#### test_explainer.py — Self-Contained SHAP Tests
- Replaced stub tests with **runnable, self-contained regression tests**
- Tests use synthetic data + simple pipeline (no service dependency)
- Covers: all-zero SHAP detection, consistency property, original feature space, background representativeness, latency SLA

#### Kustomize Structure
- Moved manifests to `k8s/base/` (standard Kustomize pattern)
- Fixed `commonLabels` (deprecated) → `labels` with pairs syntax
- Fixed `patchesStrategicMerge` (deprecated) → `patches` in overlays
- Replaced `kubeval` (abandoned) with `kubeconform` in CI

#### README
- Added **"Try It in 5 Minutes"** section with copy-paste commands
- Added **"What's Different From Other Templates"** comparison table
- Updated Quick Start to use `new-service.sh` scaffolding script
- Updated repo structure tree with all new files

#### Agentic System Improvements
- **Split `04-python-ml.md`** into `04a-python-serving.md` (app/) and `04b-python-training.md` (training/) — reduces unnecessary context loading
- **Added `10-examples.md`** — prevents production rules from firing in `examples/` directory
- **Added `.claude/rules/`** — 5 context-aware rules with `paths:` frontmatter for Claude Code IDE
- **AGENTS.md** — added Session Initialization Protocol, How to Invoke Skills, Multi-IDE Support sections
- **01-mlops-conventions.md** — slimmed from 75 to 43 lines, references `AGENTS.md` for detail
- **CLAUDE.md** — comprehensive rewrite: session protocol, full anti-pattern table, key commands
- **`.cursor/rules/`** — enhanced with session protocol, full D-01→D-12 table, key commands
- **Skill `new-service`** — now invokes `new-service.sh`, verifies zero remaining placeholders
- **Skill `debug-ml-inference`** — added D-01→D-12 anti-pattern checklist as Step 1
- **Skill `drift-detection`** — added PSI interpretation table with exit codes, special cases for time series/NLP/categorical
- **Workflow `/new-service`** — uses `new-service.sh` with manual fallback
- **Workflow `/incident`** — added Step 0: severity classification decision tree (P1–P4)
- **Workflow `/retrain`** — added explicit quality gate table with typical thresholds and verification script
- **Workflow `/cost-review`** — added PromQL queries for CPU/memory/throughput/HPA utilization

### Fixed
- black formatting: reformatted `test_explainer.py` and `drift_detection.py`
- flake8 F401: removed unused imports across 7 files
- flake8 E501/F841: fixed long lines and unused variable in cli.py
- Kustomize cycle error: restructured to standard `base/` + `overlays/` layout

---

## [1.0.0] - 2026-04-15

### Added

#### Agentic System
- **AGENTS.md** - Root-level agent architecture with 3-layer design (Orchestrator, 11 Specialist Agents, 4 Maintenance Agents), 12 anti-pattern detectors (D-01 to D-12), and Engineering Calibration Principle
- **10 context-aware rules** (`.windsurf/rules/`) - Behavioral constraints for K8s, Terraform, Python serving/training (split), CI/CD, Docker, docs, data validation, monitoring, examples
- **8 operational skills** (`.windsurf/skills/`) - Structured frontmatter with `allowed-tools`, `when_to_use`, `argument-hint`, per-step `Success criteria`
- **8 slash-command workflows** (`.windsurf/workflows/`) - `/release`, `/retrain`, `/load-test`, `/new-adr`, `/incident`, `/drift-check`, `/new-service`, `/cost-review`

#### Service Template (`templates/service/`)
- FastAPI app with async inference via ThreadPoolExecutor
- SHAP KernelExplainer integration with consistency checks
- Prometheus metrics (counter, histogram, summary)
- Pandera DataFrameModel for training, API, and drift validation
- Optuna hyperparameter tuning with configurable trials
- Quality gates (primary metric, secondary metric, fairness DIR >= 0.80)
- MLflow experiment tracking and model registry integration
- Comprehensive pytest tests (leakage, quality gates, API, SHAP, latency SLA)
- Locust load test template (100 concurrent users, < 1% error rate)
- Multi-stage Dockerfile with non-root USER and HEALTHCHECK

#### Common Utils (`templates/common_utils/`)
- `seed.py` - Reproducibility across Python, NumPy, PyTorch, TensorFlow
- `logging.py` - JSON formatter (production K8s) + colored human-readable (dev)
- `model_persistence.py` - joblib save/load with SHA256 integrity validation
- `telemetry.py` - OpenTelemetry tracing with graceful no-op fallback

#### Kubernetes (`templates/k8s/`)
- Deployment with init container for model download from GCS/S3
- CPU-only HPA (never memory for ML pods)
- Kustomize base + GCP-production and AWS-production overlays
- Argo Rollouts canary deployment with Prometheus-based AnalysisTemplate
- ServiceAccount with Workload Identity (GCP) and IRSA (AWS) annotations

#### Infrastructure (`templates/infra/`)
- Terraform GCP: GKE cluster, Workload Identity, GCS buckets, Artifact Registry
- Terraform AWS: EKS cluster, OIDC for IRSA, managed node group, IAM roles

#### CI/CD (`templates/cicd/`)
- CI: flake8 + black + isort + mypy, pytest (90% coverage), Docker build + Trivy
- Infrastructure CI: terraform validate + tfsec + Checkov + kubeval
- Deploy GCP/AWS: tag-triggered with cluster verification and smoke tests
- Drift Detection: daily scheduled + manual trigger, auto-creates GitHub issue
- Retraining: manual trigger with data validation, quality gates, artifact upload

#### Scripts (`templates/scripts/`)
- `deploy.sh` - Build, push, deploy with kubectl context verification and tag immutability
- `promote_model.sh` - Quality gates (metric, fairness, leakage, integrity) before promotion
- `health_check.sh` - Pod status + /health and /model/info endpoint checks

#### Developer Experience
- `docker-compose.demo.yml` - Demo stack with MLflow + Pushgateway + optional monitoring
- `Makefile` - Standard targets: train, test, serve, build, deploy, health-check, demo
- `.pre-commit-config.yaml` - black, isort, flake8, mypy, bandit, gitleaks
- `.gitleaks.toml` - Secret detection configuration
- `.env.example` - Environment variable documentation

#### Documentation Templates
- ADR template with Context, Options, Decision, Rationale, Consequences, Revisit When
- Runbook template with P1-P4 severity procedures
- Service README template with measured data slots
- Model card template for ML transparency
- Dependency analysis template for conflict documentation

#### Monitoring Templates
- Prometheus alerts: error rate, service down, drift heartbeat, latency, resources
- Grafana dashboard: request rate, latency percentiles, PSI scores, HPA, CPU/memory

#### Open Source Maturity
- `SECURITY.md` - Vulnerability reporting policy and security measures
- `CONTRIBUTING.md` - Contribution guidelines with Engineering Calibration awareness
- `CODE_OF_CONDUCT.md` - Contributor Covenant v2.0
- `.github/ISSUE_TEMPLATE/` - Bug report and feature request templates
- `.github/pull_request_template.md` - PR checklist with anti-pattern verification
- `.github/dependabot.yml` - Automated dependency updates
- `.gitattributes` - Git LFS for model artifacts, line ending normalization
- CI workflow `validate-templates.yml` - Validates K8s, Terraform, and Python templates

---

*This template was extracted from [ML-MLOps-Portfolio](https://github.com/DuqueOM/ML-MLOps-Portfolio), a production portfolio with 3 live ML services.*
