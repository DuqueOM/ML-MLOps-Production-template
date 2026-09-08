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
2. **CONFIRM** scaffold is complete:

   ```bash
   grep -r "{% raw %}{@ service_name @}{% endraw %}\|{% raw %}{@ service_slug @}{% endraw %}" . --include="*.py" --include="*.yaml"
   ```

3. **CHECK** invariants:

   ```bash
   grep -r "TODO\|{% raw %}{@ service_name @}{% endraw %}\|{% raw %}{@ service_slug @}{% endraw %}" . --include="*.py" --include="*.yaml"
   ```

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

## Anti-Patterns (D-01 to D-38)

Compact summary; full table with corrective actions in `AGENTS.md`.

| Range | Domain |
| ------- | -------- |
| D-01..D-08 | Serving + ML quality (workers, HPA, async, SHAP, drift, leakage) |
| D-09..D-12 | Operations (heartbeat, tfstate, model-in-image, quality gates) |
| D-13..D-16 | EDA + data validation (sandbox, Pandera, baseline, schema-evolution) |
| D-17..D-19 | Supply chain (no static creds, IRSA/WI, signed+SBOM-attested images) |
| D-20..D-22 | Closed-loop monitoring (prediction logger, ground truth, sliced perf) |
| D-23..D-25 | Probes + warmup + graceful shutdown |
| D-26..D-27 | Promotion gates + PodDisruptionBudget |
| D-28..D-30 | API contract semver + Pod Security Standards + SBOM attestation |
| D-31..D-32 | Per-purpose IAM identities (ADR-017) + snake_case Python package paths in K8s manifests |
| D-33..D-34 | Copier scaffolding (scaffolder delegates to `copier copy`; quote Jinja tokens in YAML list items) |
| D-35 | `local` stack profile must not accept cloud credentials or target a cluster (ADR-033) |
| D-36 | Promoting/deploying without verified-green CI, or overriding red without STOP-class approval (ADR-039) |
| D-37 | Non-English documentation or a private/personal repo reference committed to this public repo (ADR-040) |
| D-38 | Public inference Ingress without an edge-protection component (Cloud Armor/AWS WAF), or disabling/loosening an existing WAF/rate-limit rule (ADR-042) |

The full anti-pattern table with corrective actions and file references
lives in `AGENTS.md`. The `rule-audit` skill scans a service against
all 38 invariants and reports file:line evidence for any failure.

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
ruff check templates/service/ templates/service/common_utils/
kustomize build templates/k8s/base/ > /dev/null
```

## File Structure

```text
AGENTS.md              → Full architecture, invariants D-01..D-38, anti-patterns (canonical source)
CLAUDE.md              → This file (Claude Code context, condensed)
QUICK_START.md         → 10-minute setup guide (standalone)
RUNBOOK.md             → Template operations reference
CHANGELOG.md           → Release notes, version-by-version
docs/runbooks/         → Operational runbooks:
  ├─ gcp-wif-setup.md            — GCP Workload Identity Federation
  ├─ aws-irsa-setup.md           — AWS IAM Identity Provider + IRSA
  ├─ terraform-state-bootstrap.md — per-env state buckets/tables
  ├─ mcp-config-hygiene.md       — MCP secret loading
  ├─ secret-rotation.md          — quarterly rotation
  └─ edge-protection-setup.md    — Cloud Armor/WAFv2/Cloudflare setup + equivalence matrix (D-38)
templates/
├── service/           → the scaffolder payload: everything Copier renders into
│   │                     a generated service (ADR-030 moved these here; the
│   │                     old top-level templates/{cicd,k8s,monitoring,docs,
│   │                     common_utils,infra,eda} paths no longer exist)
│   ├── .github/workflows/ → GitHub Actions (deploy chain pins images by
│   │                     digest → Cosign sign+attest → Kyverno verify)
│   ├── k8s/base/      → Deployment, HPA, Service, SLO PrometheusRule, Kustomize
│   ├── k8s/overlays/  → 6 env×cloud overlays (gcp/aws × dev/staging/prod)
│   │                     each with namespace.yaml carrying PSS labels (D-29)
│   ├── infra/terraform/ → GCP + AWS + Cloudflare root modules; partial backend
│   │                     config + backend-configs/{dev,staging,prod}.hcl
│   ├── monitoring/    → AlertManager rules, Grafana dashboards, Prometheus
│   ├── common_utils/  → seed, logging, model_persistence, agent_context, risk_context
│   ├── docs/          → ADR, runbook, model card, CHECKLIST_RELEASE.md
│   ├── eda/           → EDA pipeline + artifact contract
│   └── agentic/       → byte-identical mirror of the repo-root agentic/ surface
├── config/            → agentic manifest, context schemas, MCP registry
├── governance/        → promotion workflow + roles (copied into the adopter repo)
├── k8s/policies/      → Kyverno ClusterPolicies (image digest + signature)
├── scripts/           → new-service.sh, dora_metrics.py
└── tests/             → template-repo tests (infra + unit)
examples/minimal/      → Working fraud detection demo (5 min)
scripts/audit_record.py → CLI for ops/audit.jsonl entries (CI + local skills)
scripts/validate_agentic.py → Strict-mode validator (rules + skills + workflows + AGENTS.md refs)
releases/              → Release notes: active v0.x line + legacy v1.x audit snapshots (see releases/README.md)
.claude/rules/         → 19 path-scoped rule pointers (this IDE)
.claude/skills/        → 27 skills as <id>/SKILL.md pointers (Claude Code discoverable layout)
agentic/             → Canonical: 19 rules + 27 skills + 20 workflows
.cursor/rules/         → 19 glob-scoped .mdc rule pointers
```

## Recent template audit (closed)

The template went through a 15-finding audit covering CI/CD, supply chain,
testing, security, and infra hygiene. All Critical + High + Medium gaps
were closed in commits `9d8894e` through `b8708b6`:

- Per-environment overlays + PSS namespaces (was 2 misnamed overlays);
  `batch-only` was added later, and CI discovers the set rather than counting it
- Image digest pinning end-to-end (push → sign → attest → verify by digest)
- Cosign installer in deploy workflows (was missing)
- AWS_ROLE_ARN declared in workflow_call.secrets contract (was lying)
- Smoke test FQDN + correct namespace (was hitting `default`)
- Prometheus metric prefix env-resolved (root pytest no longer crashes)
- common_utils.**init**.py lazy imports (audit_record runs without joblib)
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

- ruff (lint + format, line-length=120) — replaces black/isort/flake8 (ADR-044) — plus mypy
- Google-style docstrings, type hints on all public functions
- `~=` for ML package pinning (never `==` or bare `>=`)
- Coverage: **enforced floor 40%** (`fail_under` in `pyproject.toml`), target 90% lines / 80% branches.
  The floor is a ratchet at the measured value, not the target — see the note in
  `pyproject.toml`. Branch coverage is not yet enabled, and the measured scope is
  three paths, so `scripts/` is unmeasured.
- ADR for every non-trivial decision in `docs/decisions/`
