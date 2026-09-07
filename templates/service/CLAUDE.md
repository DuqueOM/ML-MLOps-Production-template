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

Everything below runs from this service's root. `make help` lists the full
set; these are the ones you reach for daily.

```bash
# Train, serve, exercise
make train                 # training pipeline -> artifacts/ + MLflow run
make serve                 # uvicorn, single worker (never --workers N in K8s)
make test                  # pytest with coverage gates
make local-loop            # train -> serve -> smoke, no cloud required

# Quality gates before you push
make lint typecheck        # ruff + mypy
make security-scan         # gitleaks + bandit + trivy fs
make doc-coherence         # rule 16 / ADR-031
make audit-rules           # scan this service against D-01..D-38

# Operate
make drift-check           # PSI data drift + sliced performance
make retrain               # retrain behind the quality gates
make release-checklist     # pre-promotion sweep
make rollback              # emergency rollback (STOP-class)

# Keep up with the upstream template
make scaffold-update       # copier update, pinned
```

## File Structure

This is **your service**, rendered from the ML-MLOps template. The layout
follows CCDS (ADR-034).

```text
AGENTS.md              → Full architecture, invariants D-01..D-38 (canonical source)
CLAUDE.md              → This file (Claude Code context, condensed)
AGENT_CONTEXT.md       → Runtime context contract for agents
Makefile               → Every command above; `make help` is the index
src/<service_slug>/    → Your package: features, training, inference, monitoring
app/                   → FastAPI surface (main.py, schemas.py, fastapi_app.py)
common_utils/          → seed, logging, model_persistence, agent_context, risk_context
eda/                   → EDA pipeline + artifact contract
configs/               → config.yaml, quality_gates, champion/challenger, profiles/
config/                → context files + schemas (company, project, adopter, service spec)
k8s/
├── base/              → Deployment, HPA, Service, SLO PrometheusRule, Kustomize
└── overlays/          → 6 env×cloud overlays (gcp/aws × dev/staging/prod), each
                          with namespace.yaml carrying PSS labels (D-29)
infra/terraform/       → GCP + AWS + Cloudflare root modules; partial backend config
                          + backend-configs/{dev,staging,prod}.hcl (D-10)
monitoring/            → AlertManager rules, Grafana dashboards, Prometheus
.github/workflows/     → CI + deploy chain (digest pin → Cosign sign+attest → Kyverno verify)
scripts/               → deploy.sh, promote_model.sh, health_check.sh, drills/, audit_record.py
tests/                 → unit, contract, integration, policy
ops/                   → audit.jsonl, reports
docs/
├── decisions/         → your ADRs (+ README.md explaining the template's own ADR refs)
└── runbooks/          → day-2-operations, drift-detection, model-retrain, drills/
agentic/               → 19 rules + 27 skills + 20 workflows (canonical agent surface)
.claude_context.md     → per-adapter context pointers (also .codex/.cursor/.devin)
```

## Upstream template

This service was rendered from the ML-MLOps Production Template with
Copier. The answers live in the `.copier-answers` file at the service root
— never edit it by hand.

- `make scaffold-update TEMPLATE_REF=<tag>` pulls upstream template changes
  into this service. The ref is required: unpinned, Copier resolves to the
  highest-sorting tag and the service jumps to a release nobody chose.
- The invariants above (`D-01`..`D-38`) and the `agentic/` surface come
  from upstream. Local overrides belong in your own ADRs under
  `docs/decisions/`, not in edits to the vendored files — those are
  reconciled on the next update and your edits would be lost.
- `docs/decisions/README.md` explains which `ADR-NNN` references in
  template-provided files are the *template's* ADRs rather than yours.

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
- Coverage: >= 90% lines, >= 80% branches
- ADR for every non-trivial decision in `docs/decisions/`
