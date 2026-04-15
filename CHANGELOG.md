# Changelog

All notable changes to the ML-MLOps Production Template are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

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
