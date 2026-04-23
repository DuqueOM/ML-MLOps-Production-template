# ADR-009: Retraining Orchestration — When (and When Not) to Migrate Beyond GitHub Actions

## Status

Accepted

## Date

2026-04-23

## Context

A recurring external suggestion is to migrate the retraining pipeline from
GitHub Actions to an in-cluster DAG orchestrator (Argo Workflows, Kubeflow
Pipelines, Prefect). This ADR documents why the current setup is correct
for the template's target scope AND the exact conditions that would
trigger a migration.

The current pipeline:

1. GitHub Actions `retrain-service.yml` is triggered (manual or drift-alert)
2. Downloads fresh data
3. Runs Pandera validation
4. Executes training (Optuna + cross-validation + MLflow logging)
5. Evaluates on holdout, checks quality gates
6. (New, ADR-008) Runs Champion/Challenger statistical gate
7. Promotes model to object store + MLflow registry on success
8. Opens GitHub issue on failure / block

This is a single-stage-per-job DAG inside GitHub Actions. For 1–5 models
with no complex retraining logic (no backfills, no hyperparameter sweeps
at scale, no distributed training), this is exactly right.

## Decision

**Keep GitHub Actions as the retraining orchestrator for the template's
target scope (1–5 classical ML models, single team).** Document the exact
set of conditions that would justify migration to Argo Workflows, and
provide migration guidance without implementing it premature-optimally.

### Migration triggers (ANY ONE is sufficient)

| Trigger | Example | Why GHA is insufficient |
|---------|---------|------------------------|
| **Backfill requirement** | Retrain monthly model for last 18 months in one run | GHA has 6h job limit; backfills need checkpointing |
| **>10 parallel model variants** | Sweep 12 algorithms × 50 Optuna trials each | GHA concurrent jobs capped; no cluster-local cache |
| **Distributed training** | Multi-node XGBoost / Dask / Ray training | GHA runners are single-node |
| **Stateful DAG dependencies** | Step B consumes step A's artifact from a large object store with provenance tracking | GHA artifacts are limited to 10GB / 90d |
| **Retry with exponential backoff and partial replay** | Transient GCP/AWS API errors that should re-run ONLY the failed step | GHA retries whole jobs; no step-level replay |
| **>5 production models** | Orchestrator becomes the easier place to share training code | Scaling GHA workflows becomes copy-paste |

### What stays in GitHub Actions even after migration

Even when Argo Workflows takes over the training DAG itself, GitHub
Actions continues to own:

- CI (lint, unit tests, Docker build, SBOM, Cosign signing)
- Code-review workflow (PR checks)
- Triggering Argo Workflows via `argo submit` — GHA remains the entry
  point for ADR-003 approval/governance consistency

This hybrid pattern is documented in the migration guide section below.

### Migration guide (if a trigger fires)

1. Install Argo Workflows in the cluster via Helm
   (`kustomize build k8s/addons/argo-workflows/` — to be added when
   the trigger fires)
2. Translate `retrain-service.yml` job steps to
   `WorkflowTemplate` YAML with equivalent tasks
3. Replace the CI `Execute training` step with
   `argo submit --name retrain-{service} --parameter data-version=...`
4. Keep the C/C gate (ADR-008) in the workflow so the same tri-state
   decision drives promotion
5. Port the GitHub Issue creation step to an Argo Workflows exit handler
6. Update the `model-retrain` skill to reference the new entry point

## Rationale

**Why not pre-empt?** Shipping Argo Workflows as the default would:

- Force every template consumer to install a CRD-heavy operator (Argo
  Workflows + Argo Events + Argo Rollouts) even if they have 1 model
- Add significant operational surface (RBAC, executor sidecars,
  artifact repository) that contradicts the Engineering Calibration
  Principle ("match complexity to scale")
- Duplicate capabilities that already exist in GitHub Actions for the
  majority of target users (small MLOps teams shipping 2–3 models)

**Why document the trigger so precisely?** Ambiguity leads to premature
migration. Explicit measurable conditions ("10 parallel variants", ">5
production models") mean the decision is evidence-driven, not fashion-driven.

**Why keep GHA as the CI / entry-point even post-migration?** Consistency
with ADR-002 (model promotion governance requires human approval via PR).
PR-based governance is what GitHub Actions excels at, and that does not
change when the training DAG itself moves to Argo.

## Consequences

### Positive

- Template stays easy to adopt — no extra cluster operator required
- Documented migration path means the decision is reversible and
  transparent
- Triggers are measurable — engineers can point to a specific condition
  rather than argue about taste

### Negative

- Teams whose scale justifies Argo Workflows must implement the
  migration themselves (the template does not ship the addon YAMLs)
- Some reviewers may perceive absence of Argo Workflows as a gap — this
  ADR addresses that perception explicitly

### Mitigations

- `templates/k8s/addons/` structure left as a known extension point for a
  future contribution of the Argo Workflows addon
- `AGENTS.md` references this ADR when an agent is asked to "add Argo
  Workflows", reducing accidental premature adoption

## Revisit When

- A contributor submits a tested `k8s/addons/argo-workflows/` overlay and
  a migration recipe for `retrain-service.yml`
- The template scope grows beyond 1–5 models (trigger coincides with
  ADR-001 revisit)
- New evidence of GHA limits blocking real users (job timeout hits on
  retraining) is documented

## Related

- ADR-001 — Template scope boundaries (this ADR is a concrete application)
- ADR-002 — Model promotion governance
- ADR-008 — Champion/Challenger gate (integrates regardless of orchestrator)
- Skill `model-retrain`
- Workflow `/retrain`
