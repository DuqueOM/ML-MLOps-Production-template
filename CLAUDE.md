# CLAUDE.md — ML-MLOps Production Template

This file provides context for Claude Code when working in this repository.

## Project Identity

**ML-MLOps Production Template**: Agent-driven framework for building production-grade ML
systems with multi-cloud deployment (GKE + EKS), observability, and enterprise CI/CD.
Every architectural decision is documented in ADRs with measured trade-offs.

## Stack (non-negotiable)

- **Language**: Python 3.11+ with type hints on all public functions
- **ML**: scikit-learn, XGBoost, LightGBM, Optuna, Pandera, SHAP (KernelExplainer)
- **Serving**: FastAPI + uvicorn (single worker in K8s) + ThreadPoolExecutor
- **Clouds**: GCP (primary) + AWS (secondary parity)
- **Infra**: Kubernetes (GKE + EKS), Terraform >= 1.7, Kustomize overlays
- **CI/CD**: GitHub Actions
- **Tracking**: MLflow | **Monitoring**: Prometheus + Grafana + AlertManager + Evidently
- **Data**: DVC (GCS + S3 remotes), Pandera DataFrameModel validation

## Session Initialization Protocol

When starting a new session:

1. **READ** `AGENTS.md` fully before writing any code
2. **CONFIRM** scaffold is complete: `grep -r "{ServiceName}\|{service}" . --include="*.py" --include="*.yaml"`
3. **CHECK** invariants: `grep -r "TODO\|{ServiceName}\|{service}" . --include="*.py" --include="*.yaml"`
4. **IDENTIFY** phase: **Build** (new service) vs **Operate** (existing service)
5. **SELECT** the appropriate approach based on the task

## Critical Invariants — NEVER VIOLATE

### ML Serving
- **NEVER** `uvicorn --workers N` in K8s — 1 worker, HPA handles horizontal scale
- **NEVER** memory HPA for ML pods — CPU only (fixed RAM prevents scale-down)
- **ALWAYS** `asyncio.run_in_executor()` + `ThreadPoolExecutor` for inference
- **ALWAYS** `KernelExplainer` for SHAP with ensemble/pipeline models
- **NEVER** bake models into Docker — use Init Container + emptyDir
- **NEVER** `model.predict()` directly in async endpoint — blocks event loop

### Infrastructure
- **ALWAYS** IRSA (AWS) / Workload Identity (GCP) — no hardcoded credentials
- **ALWAYS** remote Terraform state (GCS for GCP, S3+DynamoDB for AWS)
- **NEVER** commit secrets to tfvars or repository
- **NEVER** overwrite existing container image tags — tags are immutable
- **ALWAYS** verify `kubectl config current-context` before applying manifests

### Model Quality
- **ALWAYS** quality gates before promotion (metric, fairness DIR >= 0.80, leakage check)
- **ALWAYS** compute SHAP in ORIGINAL feature space, never transformed
- **ALWAYS** compatible release pinning (`~=`) — `numpy 2.x` corrupts joblib models
- **ALWAYS** ADR for non-trivial decisions

## Anti-Patterns (D-01 to D-30)

Compact summary; full table with corrective actions in `AGENTS.md`.

| Range | Domain |
|-------|--------|
| D-01..D-08 | Serving + ML quality (workers, HPA, async, SHAP, drift, leakage) |
| D-09..D-12 | Operations (heartbeat, tfstate, model-in-image, quality gates) |
| D-13..D-16 | EDA + data validation (sandbox, Pandera, baseline, schema-evolution) |
| D-17..D-19 | Supply chain (no static creds, IRSA/WI, signed+SBOM-attested images) |
| D-20..D-22 | Closed-loop monitoring (prediction logger, ground truth, sliced perf) |
| D-23..D-25 | Probes + warmup + graceful shutdown |
| D-26..D-27 | Promotion gates + PodDisruptionBudget |
| D-28..D-30 | API contract semver + Pod Security Standards + SBOM attestation |

The full anti-pattern table with corrective actions and file references
lives in `AGENTS.md`. The `rule-audit` skill scans a service against
all 30 invariants and reports file:line evidence for any failure.

## Key Commands

```bash
# Scaffold a new ML service
bash templates/scripts/new-service.sh ServiceName service_slug

# Run the working example (fraud detection)
cd examples/minimal && pip install -r requirements.txt
python train.py && uvicorn serve:app --port 8000
pytest test_service.py -v
python drift_check.py

# Validate templates (CI)
flake8 --max-line-length=120 templates/service/ templates/common_utils/
kustomize build templates/k8s/base/ > /dev/null
```

## File Structure

```
AGENTS.md              → Full architecture, invariants D-01..D-30, anti-patterns (canonical source)
CLAUDE.md              → This file (Claude Code context, condensed)
QUICK_START.md         → 10-minute setup guide (standalone)
RUNBOOK.md             → Template operations reference
CHANGELOG.md           → Release notes, version-by-version
docs/runbooks/         → Operational runbooks:
  ├─ gcp-wif-setup.md            — GCP Workload Identity Federation
  ├─ aws-irsa-setup.md           — AWS IAM Identity Provider + IRSA
  ├─ terraform-state-bootstrap.md — per-env state buckets/tables
  ├─ mcp-config-hygiene.md       — MCP secret loading
  └─ secret-rotation.md          — quarterly rotation
templates/
├── service/           → FastAPI + training + tests + Dockerfile + DVC pipeline
├── tests/integration/ → Integration tests (health, predict, latency SLA)
├── k8s/
│   ├── base/          → Deployment, HPA, Service, SLO PrometheusRule, Kustomize
│   └── overlays/      → 6 env×cloud overlays (gcp/aws × dev/staging/prod)
│                          each with namespace.yaml carrying PSS labels (D-29)
├── infra/terraform/   → GCP + AWS modules; partial backend config + per-env
│                          backend-configs/{dev,staging,prod}.hcl (D-10, audit High-6)
├── cicd/              → GitHub Actions workflows (deploy chain pins images by
│                          digest → Cosign sign+attest → Kyverno verify)
├── scripts/           → new-service.sh, deploy.sh, promote_model.sh
├── docs/              → ADR, runbook, model card, CHECKLIST_RELEASE.md
├── monitoring/        → AlertManager rules, Grafana dashboards, Prometheus
└── common_utils/      → seed, logging, model_persistence, agent_context, risk_context
examples/minimal/      → Working fraud detection demo (5 min)
scripts/audit_record.py → CLI for ops/audit.jsonl entries (CI + local skills)
scripts/validate_agentic.py → Strict-mode validator (rules + skills + workflows + AGENTS.md refs)
releases/              → GitHub Release notes (v1.0.0..v1.9.0)
.claude/rules/         → 14 path-scoped rules (this IDE)
.windsurf/             → Canonical: 15 rules + 16 skills + 12 workflows
.cursor/rules/         → 12 glob-scoped .mdc rules
```

## Recent template audit (closed)

The template went through a 15-finding audit covering CI/CD, supply chain,
testing, security, and infra hygiene. All Critical + High + Medium gaps
were closed in commits `9d8894e` through `b8708b6`:

- 6 environment overlays + PSS namespaces (was 2 misnamed overlays)
- Image digest pinning end-to-end (push → sign → attest → verify by digest)
- Cosign installer in deploy workflows (was missing)
- AWS_ROLE_ARN declared in workflow_call.secrets contract (was lying)
- Smoke test FQDN + correct namespace (was hitting `default`)
- Prometheus metric prefix env-resolved (root pytest no longer crashes)
- common_utils.__init__.py lazy imports (audit_record runs without joblib)
- SecurityAuditResult HIGH gate (was passing HIGH findings silently)
- Per-env Terraform state segregation
- Drift + retrain workflows operationalized with cloud-aware adapters

See `CHANGELOG.md` for the full list with verification commands.

## Engineering Calibration

Match solution complexity to problem scale:
- 2-3 models → CronJob + GitHub Actions (not Airflow)
- In-memory DataFrames → Pandera (not Great Expectations)
- Simple drift → PSI with quantile bins (not feature store)
- Small team → README + ADRs (not Confluence + Backstage)

## Coding Conventions

- black (line-length=120), isort (profile=black), flake8, mypy
- Google-style docstrings, type hints on all public functions
- `~=` for ML package pinning (never `==` or bare `>=`)
- Coverage: >= 90% lines, >= 80% branches
- ADR for every non-trivial decision in `docs/decisions/`
