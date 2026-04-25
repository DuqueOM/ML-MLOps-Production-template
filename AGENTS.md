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
  ├── Agent-EDAProfiler       Dataset exploration, baseline distributions, leakage pre-audit
  ├── Agent-DataValidator     Pandera schemas, DVC versioning, leakage checks
  ├── Agent-MLTrainer         Training pipeline, model selection, Optuna tuning
  ├── Agent-APIBuilder        FastAPI app, async inference, SHAP integration
  ├── Agent-DockerBuilder     Optimized Dockerfile, init container pattern
  ├── Agent-K8sBuilder        K8s manifests, HPA, Kustomize overlays
  ├── Agent-TerraformBuilder  IaC for GCP + AWS resources
  ├── Agent-CICDBuilder       GitHub Actions workflows
  ├── Agent-SecurityAuditor   Secret scans, IAM least-privilege, image signing, SBOM
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

## Agent Behavior Protocol

Agents operate in one of **three modes** depending on the operation's risk and reversibility.
This protocol is NOT optional — every skill and workflow must map its operations to a mode.

### The three modes

| Mode | Meaning | Example |
|------|---------|---------|
| **AUTO** | Execute without asking. Reversible or low-risk. | Scaffolding a new service, running tests, generating reports |
| **CONSULT** | Propose the plan + rationale, wait for human approval before executing. | Promoting a model to production, applying Terraform in staging |
| **STOP** | Do nothing. Block the pipeline. Require explicit human instruction to proceed. | `terraform apply` in prod, rotating a secret, overriding a quality gate failure |

### Operation → Mode mapping (canonical)

| Operation | Mode | Notes |
|-----------|------|-------|
| Scaffold new service (`new-service.sh`) | AUTO | Reversible via `rm -rf` |
| Run EDA pipeline on `data/raw/` | AUTO | No side effects outside `eda/` |
| Generate ADR, README, runbook | AUTO | Documents are reviewable in PRs |
| Run tests, lint, validators | AUTO | Read-only or sandboxed |
| `dvc add` new data artifact | AUTO | Reversible before push |
| Train model locally + save to MLflow | AUTO | Experiment tracking is append-only |
| Transition MLflow model to `Staging` | **CONSULT** | Affects staging deploys |
| Promote model to `Production` | **STOP** | Requires governance approval (see ADR-002) |
| `terraform plan` any environment | AUTO | Read-only |
| `terraform apply` dev | AUTO | Reversible, dev is sandbox |
| `terraform apply` staging | **CONSULT** | Propose diff, wait for approval |
| `terraform apply` prod | **STOP** | Requires PR + Platform Engineer approval |
| `kubectl apply` dev cluster | AUTO | — |
| `kubectl apply` staging cluster | **CONSULT** | Show diff, wait |
| `kubectl apply` prod cluster | **STOP** | Via GitHub Actions only, with approval |
| Build + push Docker image | AUTO | Images are content-addressable |
| Sign image (Cosign) | AUTO | Additive |
| Rotate a leaked secret | **STOP** | Execute `/secret-breach` workflow; never silent rotation |
| Delete any cloud resource | **STOP** | Always |
| Override a failing quality gate | **STOP** | Requires ADR documenting why |

### Escalation triggers (automatic STOP)

The agent **must** escalate to STOP mode even from AUTO/CONSULT when any of:
- Metric suspiciously high (D-06): primary metric > 0.99 without explanation
- Fairness DIR in `[0.80, 0.85]` — within margin, human judgment required
- Drift PSI > 2× the configured threshold (not just > threshold)
- Cost estimate > 1.2× monthly budget for that environment
- Any detection of a credential pattern in a commit, log, or artifact
- A test that previously passed now fails without a code change explanation

### How agents signal mode transitions

When an agent decides to change mode, it must output a structured signal:
```
[AGENT MODE: CONSULT]
Operation: Transition fraud_detector v42 to MLflow Staging
Rationale: CI passed, tests green, metrics within gates
Waiting for: Tech Lead approval via PR review
```

This makes handoffs auditable and reproducible.

## Agent Handoff Schema

When one specialist agent produces an artifact consumed by another, the handoff
MUST use a typed dataclass from `templates/common_utils/agent_context.py`. This
replaces ad-hoc dict passing with validated contracts that fail fast.

Canonical handoff chain:

```
Agent-EDAProfiler     ──[EDAHandoff]──►     Agent-MLTrainer
Agent-MLTrainer       ──[TrainingArtifact]──► Agent-DockerBuilder
Agent-DockerBuilder   ──[BuildArtifact]──► Agent-SecurityAuditor
Agent-SecurityAuditor ──[SecurityAuditResult]──► Agent-K8sBuilder
Agent-K8sBuilder      ──[DeploymentRequest]──► cluster (via GitHub Actions)
```

Each dataclass is `frozen=True` (immutable) and validates invariants at construction.
Example: `DeploymentRequest` refuses to construct if `environment == PRODUCTION` and
`security_audit.passed == False` — a gate that cannot be bypassed by omission.

## Audit Trail Protocol

Every agentic operation MUST produce an `AuditEntry` (defined in
`common_utils/agent_context.py`). Entries are append-only JSONL in
`ops/audit.jsonl` and mirrored to the GitHub Actions step summary in CI.

Minimum fields:
- `agent`, `operation`, `environment`, `mode`
- `inputs` (what was requested)
- `outputs` (what was produced — sha256, image refs, PR URLs)
- `approver` (populated when mode is CONSULT or STOP)
- `result` (`success` | `failure` | `halted`)
- `timestamp` (UTC ISO8601)

Agents MUST NOT open a GitHub issue for every operation (noise). Instead:
- Routine operations → `ops/audit.jsonl` + GHA step summary
- Operations that required CONSULT/STOP → additionally open a GitHub issue tagged
  `audit` with the entry pre-filled
- Failures → open an issue tagged `audit` + `incident`

## Agent Permissions Matrix

Some operations are intrinsically not permitted for certain agents regardless of
environment. This matrix codifies capability boundaries.

| Agent | dev | staging | production |
|-------|-----|---------|------------|
| Agent-EDAProfiler | read data, write `eda/**` | read data | **blocked** |
| Agent-MLTrainer | train, log MLflow, transition None→Staging | transition Staging→None | transition to Production **blocked** (via PR only) |
| Agent-DockerBuilder | build, push to registry | build, push, sign | build, push, sign |
| Agent-K8sBuilder | `kubectl apply` | `kubectl apply` (CONSULT) | **blocked** (GitHub Actions only) |
| Agent-TerraformBuilder | `plan`, `apply` | `plan`, `apply` (CONSULT) | `plan` only; `apply` **blocked** |
| Agent-SecurityAuditor | scan, report | scan, report, block pipeline | scan, report, block pipeline |
| Agent-DriftMonitor | read metrics | read metrics | read metrics |
| Agent-RetrainingAgent | trigger retrain | trigger retrain (CONSULT) | trigger retrain **blocked**; propose via PR |
| Agent-CostAuditor | read billing | read billing | read billing |
| Agent-DocumentationAI | write `docs/**` | — | — |

"Blocked" means the agent must emit `[AGENT MODE: STOP]` and refuse the operation,
even if the human insists in conversation. The only path through is the governed
GitHub Actions flow with required_reviewers.

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
| D-13 | EDA performed directly on production data without sandbox | Move to isolated `data/raw/` copy; EDA never writes to prod paths |
| D-14 | Pandera schema without observed ranges from EDA | Add `Check.in_range(min, max)` derived from EDA distribution analysis |
| D-15 | Baseline distributions not persisted for drift detection | Save `baseline_distributions.pkl` during EDA; consume in drift CronJob |
| D-16 | Feature engineering without documented rationale | Add `feature_proposals.yaml` with justification tied to EDA evidence |
| D-17 | Hardcoded credentials in code, configs, or `os.environ[...]` for secrets | Use `common_utils/secrets.py` — delegates to AWS Secrets Manager / GCP Secret Manager |
| D-18 | Static AWS access keys or GCP JSON service-account keys in production | Migrate to IRSA (AWS) or Workload Identity (GCP) — remove all static creds |
| D-19 | Unsigned images reaching production or missing SBOM | Sign with Cosign, generate SBOM with Syft, enforce via Kyverno admission controller |
| D-20 | Prediction log events missing `prediction_id` or `entity_id` | Both are required at construction of `PredictionEvent`; `entity_id` is the JOIN key with ground truth |
| D-21 | Prediction logging blocking the async inference event loop | `log_prediction()` MUST buffer + flush in background task via `run_in_executor(None, ...)` |
| D-22 | Logging backend failure propagating to the HTTP response | `log_prediction()` MUST swallow exceptions and increment `prediction_log_errors_total` — observability failures NEVER break serving |
| D-23 | Liveness and readiness probes share a path | Split: `/health` (liveness, always 200 while process alive) and `/ready` (readiness, 503 until warm-up done). Add `startupProbe` on `/health` with `failureThreshold: 24` |
| D-24 | SHAP explainer rebuilt per request | Build `KernelExplainer` once in warm-up (`fastapi_app.py::warm_up_model`), cache on app state, reuse for every `/explain` call |
| D-25 | Pod killed mid-request on deploy / scale-down | Set `terminationGracePeriodSeconds` (default 30s) STRICTLY GREATER than uvicorn's `--timeout-graceful-shutdown` (default 20s) |
| D-26 | Deploys go directly to prod without staging validation | Four-job chain (build → dev → staging → prod) with GitHub Environment Protection: 1 reviewer at staging, 2 reviewers + wait_timer + tag-only at prod (ADR-011) |
| D-27 | Deployment without PodDisruptionBudget | Every Deployment ships with `PodDisruptionBudget` (`minAvailable: 1`). HPA `minReplicas >= 2`. `minAvailable: 0` requires `mlops.template/pdb-zero-acknowledged` annotation referencing an ADR |
| D-28 | Breaking API change without version bump + snapshot update | Update `tests/contract/openapi.snapshot.json` via `scripts/refresh_contract.py`, bump `app.version` in `main.py` (semver: additive=minor, renames/narrows=major), announce in `CHANGELOG.md ### API Contract`. CI rejects snapshot changes without matching version bump |
| D-29 | Namespace without Pod Security Standards labels | Label prod namespaces `pod-security.kubernetes.io/enforce: restricted`; dev/staging `enforce: baseline` + `warn/audit: restricted`. See `templates/k8s/policies/pod-security-standards.yaml`. Container `securityContext` drops ALL capabilities, `allowPrivilegeEscalation: false`, `runAsNonRoot: true` |
| D-30 | Production image without SBOM attestation | Deploy workflow MUST generate an SBOM (Syft / CycloneDX) and attach it as a Cosign attestation (`cosign attest --type cyclonedx`). Full SLSA L3 provenance is documented as roadmap in `deploy-gcp.yml` §1b |

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
- `eda-analysis` — 6-phase exploratory analysis with leakage gate + baseline distributions
- `security-audit` — pre-build/pre-deploy scans: gitleaks, trivy, cosign verify, IAM review
- `secret-breach-response` — incident playbook when a secret is leaked (detect → rotate → audit → postmortem)
- `debug-ml-inference` — diagnose serving issues (starts with D-01→D-27 checklist)
- `drift-detection` — analyze PSI drift + concept drift (sliced performance)
- `concept-drift-analysis` — root-cause sliced performance regressions with ground truth
- `model-retrain` — execute retraining with quality gates + Champion/Challenger
- `deploy-gke` / `deploy-aws` — deploy to GKE or EKS with Kustomize overlays
- `release-checklist` — full multi-cloud release process
- `rollback` — STOP-class emergency revert (Argo Rollouts abort + undo, MLflow revert, alert silencing)
- `cost-audit` — monthly cloud cost review
- `batch-inference` — scaffold + run batch scoring jobs (CronJob + Parquet output) reusing the service's model and feature-engineering code
- `performance-degradation-rca` — end-to-end RCA for a performance-degradation incident: correlates sliced metrics, drift, deploy history, upstream data changes, and prediction logs into one evidence-backed root cause
- `rule-audit` — automated scan of a service/repo for compliance with AGENTS.md invariants D-01 through D-30; produces a PASS/FAIL report with file:line evidence

**Workflows** (user-triggered via slash commands):
- `/new-service` — end-to-end service creation
- `/retrain` — model retraining with quality gates
- `/incident` — classify severity (P1-P4) → execute runbook
- `/drift-check` — run PSI analysis for one or all services
- `/release` — multi-cloud deploy with rollback plan
- `/cost-review` — monthly FinOps analysis
- `/load-test` — Locust load tests against ML services
- `/new-adr` — create Architecture Decision Record
- `/eda` — run 6-phase exploratory data analysis on a new dataset
- `/secret-breach` — incident workflow for leaked secrets (STOP pipeline, rotate, audit)
- `/performance-review` — monthly sliced-performance review using ground-truth metrics (detect silent concept drift, document findings)
- `/rollback` — emergency rollback of a production ML service — pairs with the `rollback` skill (STOP-class operation)

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
│   ├── 10-examples.md                 # glob: examples/**/*
│   ├── 11-data-eda.md                 # glob: **/eda/**, **/notebooks/**/*.ipynb
│   ├── 12-security-secrets.md         # always_on — D-17/D-18/D-19
│   └── 13-closed-loop-monitoring.md   # glob: prediction_logger/ground_truth/performance_monitor — D-20/D-21/D-22
├── skills/                             # Multi-step operational procedures
│   ├── debug-ml-inference/SKILL.md
│   ├── deploy-gke/SKILL.md
│   ├── deploy-aws/SKILL.md
│   ├── drift-detection/SKILL.md
│   ├── eda-analysis/SKILL.md
│   ├── security-audit/SKILL.md
│   ├── secret-breach-response/SKILL.md
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
    ├── eda.md                          # /eda
    ├── secret-breach.md                # /secret-breach
    ├── new-service.md                  # /new-service
    └── cost-review.md                  # /cost-review
```

### Skills → Workflow Cross-References

| Trigger | Skill Invoked | Workflow Chained |
|---------|--------------|-----------------|
| New dataset to explore | `eda-analysis` | `/eda` → `/new-service` (if leakage-free) |
| Pre-build / pre-deploy | `security-audit` | auto-chain before DockerBuilder/K8sBuilder |
| Secret leak detected | `secret-breach-response` | `/secret-breach` (STOP pipeline, rotate) |
| Inference bug | `debug-ml-inference` | `/incident` |
| Drift alert (PSI ≥ threshold) | `drift-detection` | `/retrain` |
| Version release | `release-checklist` | `/release` |
| Tag push (GKE) | `deploy-gke` | — |
| Tag push (EKS) | `deploy-aws` | — |
| Scheduled retrain | `model-retrain` | `/drift-check` post-deploy |
| New ML service request | `new-service` | `/new-service` |
| Monthly cost review | `cost-audit` | `/cost-review` |

## Multi-IDE Support

The template supports **3 IDEs** with equivalent invariant coverage. Windsurf is
the canonical source (full rules + skills + workflows); Cursor and Claude Code
receive the rules condensed for their native formats (they don't natively support
skills/workflows — those are invoked via conversation in any IDE).

```
.claude/rules/          # Claude Code — paths: frontmatter
├── 01-serving.md       # paths: **/app/*.py, **/api/*.py
├── 02-training.md      # paths: **/training/*.py, **/models/*.py
├── 03-kubernetes.md    # paths: k8s/**/*.yaml
├── 04-terraform.md     # paths: **/*.tf
├── 05-examples.md      # paths: examples/**/*
├── 06-data-eda.md      # paths: eda/**/*, **/notebooks/**/*.ipynb, **/eda_*.py
└── 07-security-secrets.md  # paths: **/* (always-applicable)

.cursor/rules/          # Cursor IDE — globs: frontmatter
├── 01-mlops-conventions.mdc  # globs: **/* — session protocol, D-01→D-27, Behavior Protocol
├── 02-kubernetes.mdc         # globs: k8s/**/*.yaml — HPA, init container
├── 03-python-serving.mdc     # globs: **/app/*.py — async, SHAP
├── 04-python-training.mdc    # globs: **/training/*.py — pipeline, gates
├── 05-docker.mdc             # globs: **/Dockerfile* — multi-stage, no model
├── 06-data-eda.mdc           # globs: eda/**/*, **/notebooks/**/*.ipynb
└── 07-security-secrets.mdc   # globs: **/* — D-17/D-18/D-19
```

### IDE Parity Matrix (invariant coverage)

| Invariant group | Windsurf | Cursor | Claude |
|-----------------|----------|--------|--------|
| Core + D-01→D-12 | `01-mlops-conventions.md` (always_on) | `01-mlops-conventions.mdc` | `01-serving.md` + `02-training.md` |
| Closed-loop (D-20→D-22) | `13-closed-loop-monitoring.md` | `08-closed-loop.mdc` | `08-closed-loop.md` |
| Kubernetes (D-02) | `02-kubernetes.md` | `02-kubernetes.mdc` | `03-kubernetes.md` |
| Terraform | `03-terraform.md` | — (covered in 01) | `04-terraform.md` |
| Serving (D-01/03/04) | `04a-python-serving.md` | `03-python-serving.mdc` | `01-serving.md` |
| Training (D-05/06/12) | `04b-python-training.md` | `04-python-training.mdc` | `02-training.md` |
| Docker (D-11) | `07-docker.md` | `05-docker.mdc` | (in training/serving) |
| Data validation (D-14) | `08-data-validation.md` | — | — |
| EDA (D-13→D-16) | `11-data-eda.md` | `06-data-eda.mdc` | `06-data-eda.md` |
| Security (D-17→D-19) | `12-security-secrets.md` (always_on) | `07-security-secrets.mdc` (always) | `07-security-secrets.md` (always) |
| Skills (procedures) | `skills/**/SKILL.md` (12 skills) | *(invoked in conversation)* | *(invoked in conversation)* |
| Workflows (slash cmds) | `workflows/*.md` (11 workflows) | *(invoked in conversation)* | *(invoked in conversation)* |

All three IDEs enforce the same **Agent Behavior Protocol** (AUTO/CONSULT/STOP) —
it is referenced from `AGENTS.md` which all IDEs read first per the session protocol.

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

| MCP | Package / Server | What the agent gains |
|-----|-----------------|----------------------|
| **`github`** | Streamable HTTP — `api.githubcopilot.com/mcp/` + PAT | Read CI logs, PR status, issues — no copy-paste into chat |
| **`kubectl-mcp-server`** | `npx kubectl-mcp-server@latest` | Run `kubectl apply/get/logs/describe` directly — skills execute instead of instruct |
| **`terraform-mcp-server`** | `docker run hashicorp/terraform-mcp-server` | Registry lookup, `plan/validate` — workflow `/release` with real infra state |
| **`mcp-prometheus`** | varies by deployment | Query live metrics — `drift-detection` and `/incident` with real data |

### Setup (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "github": {
      "serverUrl": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_GITHUB_PAT"
      }
    },
    "kubectl-mcp-server": {
      "command": "/path/to/envs/ml/bin/kubectl-mcp-serve",
      "args": ["serve", "--transport", "stdio", "--read-only"],
      "env": {}
    },
    "terraform-mcp-server": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "hashicorp/terraform-mcp-server:latest"],
      "env": {}
    },
    "mcp-prometheus": {
      "command": "uvx",
      "args": ["mcp-prometheus"],
      "env": {
        "PROMETHEUS_URL": "http://prometheus.monitoring:9090"
      }
    }
  }
}
```

**GitHub PAT scopes needed**: `repo`, `actions` (CI logs), `pull_requests`.
Create at: https://github.com/settings/personal-access-tokens/new

**Note**: `kubectl-mcp-server` uses your current `kubectl` context.
**Always run** `kubectl config current-context` before any cluster operation.

**`mcp-prometheus` is required for the Dynamic Behavior Protocol (ADR-010).**
Without it, the agent falls back to the static AGENTS.md mapping — which is
safe but less precise. The template's `common_utils/risk_context.py` helper
reads this server when available and transparently degrades to local-file
signals otherwise.

### Agent behavior with MCPs installed

When `mcp-github` is active: agents read CI failures directly — no need to paste logs into chat.
When `mcp-kubernetes` is active: skills `deploy-gke`/`deploy-aws` verify pod status after apply.
When `mcp-terraform` is active: skill `release-checklist` validates infra before deploying.
When `mcp-prometheus` is active: the Dynamic Behavior Protocol escalates
AUTO → CONSULT or CONSULT → STOP based on live risk signals (incident,
drift, off-hours, error budget) — see `common_utils/risk_context.py`.

Without MCPs: agents generate correct commands and instruct the human to run them (current behavior).
With MCPs: agents execute those commands directly and verify the results. Same invariants apply.

## AI Transparency

This template uses AI-assisted coding agents for code generation and boilerplate. All architectural decisions, system design, trade-off analysis, and ADR documentation require human engineering judgment. AI tools accelerate throughput — they don't replace the engineer's responsibility to calibrate solutions to the right scale.
