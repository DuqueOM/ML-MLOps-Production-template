# Agent Context

Read-first entry point for any agent (Devin, Cursor, Claude, Codex, or
any future surface) that has just attached to this repo. Canonical agentic
bodies live in `agentic/` (ADR-027); IDE surfaces are generated from it.
ADR-023 §F3
caps this file at 150 lines and forbids date-led lines or tables with
more than 10 rows — keep it an index, never a diary.

## Purpose

Production-oriented MLOps template for classical ML services on
Kubernetes with GCP + AWS parity, supply-chain controls, CI/CD
promotion, monitoring, drift detection, and agentic governance.

## Read first (universal, 5 files)

- `AGENTS.md` — invariants D-01..D-35, AUTO/CONSULT/STOP protocol,
  permissions matrix, handoff schema. **Authority for all behaviour.**
- `README.md` — user-facing maturity claims; watch the Verification
  Status matrix (L1 / L2 / L3 / L4 layers).
- `docs/decisions/ADR-001-template-scope-boundaries.md` — what the
  template deliberately does NOT do.
- `docs/decisions/ADR-023-agentic-portability-and-context.md` — this
  portability + context layer.
- `templates/config/agentic_manifest.yaml` — machine-readable index
  of every rule, skill, workflow, and surface.

## Then read only what the task touches

### Serving (FastAPI app, inference path)

- `agentic/rules/04a-python-serving.md`
- `templates/service/app/main.py` and `templates/service/app/fastapi_app.py`
- Invariants to watch: D-01, D-03, D-04, D-23, D-24, D-25

### Training (pipelines, MLflow, quality gates)

- `agentic/rules/04b-python-training.md`
- `templates/service/src/{service}/training/` and `templates/config/model_routing_policy.yaml`
- Invariants to watch: D-05, D-06, D-09, D-14

### Kubernetes (manifests, HPA, overlays, NetworkPolicy)

- `agentic/rules/02-kubernetes.md`
- `templates/service/k8s/base/` and `templates/service/k8s/overlays/`
- Invariants to watch: D-02, D-11, D-23, D-25, D-27, D-29, D-30

### Terraform (GCP + AWS infra, bootstrap)

- `agentic/rules/03-terraform.md`
- `templates/service/infra/terraform/{gcp,aws}/`
- Invariants to watch: D-10 (remote state), D-18 (no literal creds)

### Agentic system (rules, skills, workflows, modes)

- `AGENTS.md`
- `templates/config/agentic_manifest.yaml`
- `templates/config/ci_autofix_policy.yaml`
- `templates/service/common_utils/risk_context.py`
- `scripts/validate_agentic_manifest.py`

### Security (secrets, supply chain, admission)

- `agentic/rules/12-security-secrets.md`
- `docs/runbooks/secrets-integration-e2e.md`
- Skill `security-audit` (pre-build / pre-deploy)

### Monitoring + drift (alerts, PSI, closed loop)

- `agentic/rules/09-monitoring.md` and `13-closed-loop-monitoring.md`
- `templates/service/monitoring/alertmanager.yml`
- `docs/runbooks/alertmanager-validation.md`

## How to contextualize (adopter-specific)

The template ships with two context files that specialise behaviour
without forking:

- `templates/config/company_context.example.yaml` — WHO the adopter is
- `templates/config/project_context.example.yaml` — WHAT this service
  does and which KPIs matter

Adopters copy to `*_context.local.yaml` (gitignored), fill placeholders,
then `python3 scripts/validate_agentic_manifest.py --strict`.
Details: `docs/agentic/contextualization.md`.

## Canonical machine-readable contracts

- Agentic manifest: `templates/config/agentic_manifest.yaml`
- CI autofix policy: `templates/config/ci_autofix_policy.yaml`
- Model routing policy: `templates/config/model_routing_policy.yaml`
- Context schema: `templates/config/context.schema.json`

## Where decisions are written

- `docs/decisions/ADR-<NNN>-*.md` — every non-trivial decision.
- `ops/audit.jsonl` — every AUTO / CONSULT / STOP operation.
- `docs/agentic/red-team-log.md` — adversarial findings + mitigations.

## Running the validators

```bash
python3 scripts/validate_agentic.py --strict
python3 scripts/validate_agentic_manifest.py --strict
python -m pytest templates/service/tests/ templates/tests/ templates/service/monitoring/tests/ --no-cov
```

## Anti-index (what this file is NOT)

- Not a changelog — use `CHANGELOG.md` and `releases/v*.md`.
- Not a conversation log — use `ops/audit.jsonl` for operations.
- Not a secrets location — secrets live in Secret Manager per D-18.
- Not a tutorial — user-facing onboarding lives in `README.md`.
