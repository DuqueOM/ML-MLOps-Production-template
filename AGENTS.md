# AGENTS.md — ML-MLOps Production Template

## Project Identity

**ML-MLOps Production Template**: Agent-driven framework for building and maintaining production-grade ML systems with multi-cloud deployment (GKE + EKS), comprehensive observability, and enterprise CI/CD. Every architectural decision documented in ADRs with measured trade-offs.

- **Stack**: Python 3.11+, scikit-learn, XGBoost, LightGBM, FastAPI, Docker, Kubernetes, Terraform, GitHub Actions
- **Clouds**: GCP (primary) + AWS (secondary parity)
- **Tracking**: MLflow (self-hosted on K8s)
- **Monitoring**: Prometheus + Grafana + AlertManager + Evidently
- **Data**: DVC (GCS + S3 remotes), Pandera validation

## Agent Architecture

```
LAYER 1: ORCHESTRATOR
  → Receives high-level requests ("create a new ML service for [domain]")
  → Determines which specialist agents are needed and in what order
  → Manages task dependencies (cannot deploy before training completes)
  → Calibrates engineering level to project scale (no under/over-engineering)

LAYER 2: SPECIALIST AGENTS (build phase)
  ├── Agent-DataValidator     Pandera schemas, DVC versioning, leakage checks
  ├── Agent-MLTrainer         Training pipeline, model selection, Optuna tuning
  ├── Agent-APIBuilder        FastAPI app, async inference, SHAP integration
  ├── Agent-DockerBuilder     Optimized Dockerfile, init container pattern
  ├── Agent-K8sBuilder        K8s manifests, HPA, Kustomize overlays
  ├── Agent-TerraformBuilder  IaC for GCP + AWS resources
  ├── Agent-CICDBuilder       GitHub Actions workflows
  ├── Agent-MonitoringSetup   Prometheus metrics, Grafana dashboards, alerts
  ├── Agent-DriftSetup        PSI thresholds, CronJob, heartbeat alerts
  ├── Agent-DocumentationAI   ADRs, READMEs, runbooks
  └── Agent-TestGenerator     Unit, integration, regression, load tests

LAYER 3: MAINTENANCE AGENTS (operate phase)
  ├── Agent-DriftMonitor      PSI scores → alerts → retraining triggers
  ├── Agent-RetrainingAgent   Executes retraining with quality gates
  ├── Agent-CostAuditor       Reviews costs against budget
  └── Agent-DocUpdater        Keeps documentation in sync with code
```

## Critical Patterns — DO NOT VIOLATE

### ML Serving Invariants

- **NEVER** use `uvicorn --workers N` in Kubernetes — causes CPU thrashing, dilutes HPA signal
- **NEVER** use memory as an HPA metric for ML pods — fixed RAM footprint prevents scale-down
- **ALWAYS** use `asyncio.run_in_executor()` + `ThreadPoolExecutor` for CPU-bound inference
- **ALWAYS** use `KernelExplainer` for SHAP with complex ensemble/pipeline models
- **ALWAYS** use compatible release pinning (`~=`) for ML dependencies — `numpy 2.x` silently corrupts joblib
- **NEVER** bake model artifacts into Docker images — use `emptyDir` + Init Container
- **NEVER** call `model.predict()` directly in an async endpoint — blocks asyncio event loop

### Infrastructure Invariants

- **ALWAYS** use IRSA (AWS) and Workload Identity (GCP) — no hardcoded credentials in pods
- **ALWAYS** use remote Terraform state (GCS for GCP, S3+DynamoDB for AWS)
- **NEVER** commit secrets to tfvars or repository — use Secrets Manager
- **NEVER** overwrite existing container image tags — tags are immutable
- **ALWAYS** verify `kubectl config current-context` before applying K8s manifests

### Model Quality Invariants

- **ALWAYS** define minimum production metric thresholds per service
- **ALWAYS** run fairness checks (Disparate Impact Ratio >= 0.80) before every deploy
- **ALWAYS** compute SHAP values in ORIGINAL feature space, never transformed space
- **ALWAYS** include a data leakage sanity check (suspiciously high metrics = investigate)
- **NEVER** promote a model without passing ALL quality gates

### Documentation Invariants

- **ALWAYS** create an ADR for every non-trivial architectural decision
- **ALWAYS** document costs with real measured numbers, not estimates
- **ALWAYS** document production problems with measured evidence

## Engineering Calibration Principle

```
The solution must match the scale of the problem.

UNDER-ENGINEERING: Missing monitoring, no tests, no drift detection, no ADRs
  → The system will fail silently in production

CORRECT SCALE: Each component sized to the actual requirements
  → CronJob + GitHub Actions for 2-3 models (not Airflow/Prefect)
  → Pandera for in-memory DataFrames (not Great Expectations)
  → PSI with quantile bins for drift (not a full feature store)

OVER-ENGINEERING: Full orchestrator for 2 models, GE for simple DataFrames
  → Complexity without proportional value
```

## Anti-Patterns That Agents Must Detect and Correct

| ID | Anti-Pattern | Corrective Action |
|----|-------------|-------------------|
| D-01 | `uvicorn --workers N` in Dockerfile or deployment | Change to 1 worker, add ThreadPoolExecutor |
| D-02 | Memory HPA in any HorizontalPodAutoscaler | Remove memory metric, keep CPU only |
| D-03 | `model.predict()` directly in async endpoint | Wrap in `run_in_executor` with ThreadPoolExecutor |
| D-04 | `shap.TreeExplainer` with ensemble/pipeline/stacking | Change to KernelExplainer with predict_proba_wrapper |
| D-05 | `==` in requirements.txt for ML packages | Change to `~=` (compatible release) |
| D-06 | Unrealistically high primary metric | Investigate data leakage before promoting |
| D-07 | SHAP background data with only one class | Replace with representative sample |
| D-08 | PSI with uniform bins (not quantile-based) | Refactor to quantile bins from reference |
| D-09 | Drift detection without heartbeat alert | Add AlertManager alert for broken CronJobs |
| D-10 | `terraform.tfstate` in git repository | Move to remote state, rotate exposed secrets |
| D-11 | Models included in Docker image | Remove, implement init container pattern |
| D-12 | No quality gates before model promotion | Add all gates before deploy |

## Session Initialization Protocol

When starting a new session in a project derived from this template:

1. **READ** this AGENTS.md fully before writing any code
2. **CONFIRM** the project has completed scaffold: check that `{ServiceName}` placeholders have been replaced
3. **CHECK** invariants: `grep -r "TODO\|{ServiceName}\|{service}" . --include="*.py" --include="*.yaml"`
4. **IDENTIFY** the current phase: **Build** (new service) vs **Operate** (existing service)
5. **SELECT** the appropriate skill or workflow based on the task

## How to Invoke Skills and Workflows

**Skills** (multi-step procedures — invoked by the agent when task matches):
- `new-service` — scaffold a new ML service using `templates/scripts/new-service.sh`
- `debug-ml-inference` — diagnose serving issues (starts with D-01→D-12 checklist)
- `drift-detection` — analyze PSI drift and trigger retraining
- `model-retrain` — execute retraining with quality gates
- `deploy-gke` / `deploy-aws` — deploy to GKE or EKS with Kustomize overlays
- `release-checklist` — full multi-cloud release process
- `cost-audit` — monthly cloud cost review

**Workflows** (user-triggered via slash commands):
- `/new-service` — end-to-end service creation
- `/retrain` — model retraining with quality gates
- `/incident` — classify severity (P1-P4) → execute runbook
- `/drift-check` — run PSI analysis for one or all services
- `/release` — multi-cloud deploy with rollback plan
- `/cost-review` — monthly FinOps analysis
- `/load-test` — Locust load tests against ML services
- `/new-adr` — create Architecture Decision Record

## Agentic Configuration

```
.windsurf/
├── rules/                              # Behavioral constraints (context-aware)
│   ├── 01-mlops-conventions.md         # always_on — core stack + ADR patterns
│   ├── 02-kubernetes.md                # glob: k8s/**/*.yaml, helm/**/*.yaml
│   ├── 03-terraform.md                 # glob: **/*.tf
│   ├── 04a-python-serving.md           # glob: **/app/*.py, **/api/*.py
│   ├── 04b-python-training.md          # glob: **/training/*.py, **/models/*.py
│   ├── 05-github-actions.md            # glob: .github/workflows/*.yml
│   ├── 06-documentation.md             # glob: docs/**/*.md
│   ├── 07-docker.md                    # glob: **/Dockerfile*, docker-compose*.yml
│   ├── 08-data-validation.md           # glob: **/schemas.py, **/validate*.py
│   ├── 09-monitoring.md               # glob: monitoring/**/*
│   └── 10-examples.md                 # glob: examples/**/*
├── skills/                             # Multi-step operational procedures
│   ├── debug-ml-inference/SKILL.md
│   ├── deploy-gke/SKILL.md
│   ├── deploy-aws/SKILL.md
│   ├── drift-detection/SKILL.md
│   ├── model-retrain/SKILL.md
│   ├── release-checklist/SKILL.md
│   ├── new-service/SKILL.md
│   └── cost-audit/SKILL.md
└── workflows/                          # Prompt-triggered structured workflows
    ├── release.md                      # /release
    ├── retrain.md                      # /retrain
    ├── load-test.md                    # /load-test
    ├── new-adr.md                      # /new-adr
    ├── incident.md                     # /incident
    ├── drift-check.md                  # /drift-check
    ├── new-service.md                  # /new-service
    └── cost-review.md                  # /cost-review
```

### Skills → Workflow Cross-References

| Trigger | Skill Invoked | Workflow Chained |
|---------|--------------|-----------------|
| Inference bug | `debug-ml-inference` | `/incident` |
| Drift alert (PSI ≥ threshold) | `drift-detection` | `/retrain` |
| Version release | `release-checklist` | `/release` |
| Tag push (GKE) | `deploy-gke` | — |
| Tag push (EKS) | `deploy-aws` | — |
| Scheduled retrain | `model-retrain` | `/drift-check` post-deploy |
| New ML service request | `new-service` | `/new-service` |
| Monthly cost review | `cost-audit` | `/cost-review` |

## Multi-IDE Support

```
.claude/rules/          # Claude Code — paths: frontmatter for context-aware rules
├── 01-serving.md       # paths: **/app/*.py, **/api/*.py
├── 02-training.md      # paths: **/training/*.py, **/models/*.py
├── 03-kubernetes.md    # paths: k8s/**/*.yaml
├── 04-terraform.md     # paths: **/*.tf
└── 05-examples.md      # paths: examples/**/*

.cursor/rules/          # Cursor IDE — globs: frontmatter (5 files)
├── 01-mlops-conventions.mdc  # globs: **/* — session protocol, full D-01→D-12
├── 02-kubernetes.mdc         # globs: k8s/**/*.yaml — HPA, init container
├── 03-python-serving.mdc     # globs: **/app/*.py — async, SHAP
├── 04-python-training.mdc    # globs: **/training/*.py — pipeline, gates
└── 05-docker.mdc             # globs: **/Dockerfile* — multi-stage, no model
```

## Template System

```
templates/
├── service/            # Complete ML service boilerplate
│   ├── app/            # FastAPI serving layer
│   ├── src/            # Training, features, monitoring
│   ├── tests/          # Unit, integration, regression
│   ├── dvc.yaml        # DVC pipeline (validate → featurize → train → evaluate)
│   ├── .dvc/config     # DVC remote config (GCS/S3)
│   ├── Dockerfile
│   ├── pyproject.toml  # Modern Python project config
│   ├── requirements.txt
│   └── README.md
├── tests/integration/  # Integration test templates (health, predict, latency SLA)
├── k8s/                # K8s manifests (base/ + overlays/), SLO PrometheusRule
├── infra/              # Terraform IaC (GCP + AWS), docker-compose.mlflow.yml
├── scripts/            # new-service.sh, deploy.sh, promote_model.sh
├── cicd/               # GitHub Actions workflow templates
├── docs/               # ADR, runbook, model card, mkdocs.yml, CHECKLIST_RELEASE.md
├── common_utils/       # Shared utilities (seed, logging, persistence)
└── monitoring/         # Grafana dashboard + Prometheus alert templates
```

```
docs/                   # Template-level architectural decisions
└── decisions/
    └── ADR-001-template-scope-boundaries.md  # Scope: LLM, multi-tenancy, Vault, compliance
```

## MCP Integrations

MCPs (Model Context Protocol servers) extend what agents can **do**, not just what they can read.
Install only MCPs that change agent capabilities for this stack. Skip MCPs for technologies not in this template.

### Recommended MCPs (high ROI for this template)

| MCP | Install | What the agent gains |
|-----|---------|----------------------|
| **`mcp-github`** | `windsurf mcp add github` | Read CI logs, PR status, issues without copy-pasting output into chat. Agents can diagnose CI failures autonomously. |
| **`mcp-kubernetes`** | `windsurf mcp add kubernetes` | Run `kubectl apply/get/logs/describe` directly. Skills `deploy-gke` and `deploy-aws` execute instead of instruct. |
| **`mcp-terraform`** | `windsurf mcp add terraform` | Run `terraform plan/validate/apply` directly. Workflow `/release` can verify infra state in real time. |
| **`mcp-prometheus`** | `windsurf mcp add prometheus` | Query live metrics. Skills `drift-detection` and `/incident` work with real data, not hypothetical. |

### Setup (Windsurf)

```bash
# Add to ~/.codeium/windsurf/mcp_config.json or via Settings → MCP
# GitHub (requires GITHUB_TOKEN env var)
windsurf mcp add github

# Kubernetes (uses current kubectl context — verify before use)
# ALWAYS run: kubectl config current-context before any apply
windsurf mcp add kubernetes

# Terraform (run from infra directory)
windsurf mcp add terraform
```

### Agent behavior with MCPs installed

When `mcp-github` is active: agents read CI failures directly — no need to paste logs into chat.
When `mcp-kubernetes` is active: skills `deploy-gke`/`deploy-aws` verify pod status after apply.
When `mcp-terraform` is active: skill `release-checklist` validates infra before deploying.

Without MCPs: agents generate correct commands and instruct the human to run them (current behavior).
With MCPs: agents execute those commands directly and verify the results. Same invariants apply.

## AI Transparency

This template uses AI-assisted coding agents for code generation and boilerplate. All architectural decisions, system design, trade-off analysis, and ADR documentation require human engineering judgment. AI tools accelerate throughput — they don't replace the engineer's responsibility to calibrate solutions to the right scale.
