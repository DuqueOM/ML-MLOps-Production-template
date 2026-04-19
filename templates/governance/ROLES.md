# Roles and Responsibilities

Minimal role model for single-team ML deployments (1–5 models, 1–20 engineers).
Scales down to solo projects (one person plays all roles) without adding friction.

## ML Engineer

**Owns**: model development, training pipelines, quality gates.

**Can do without approval**:
- Create and merge PRs that train a new model version
- Promote a model to `Staging` (CI enforces quality gates automatically)
- Run drift analysis, inspect MLflow runs, review metrics

**Requires approval to**:
- Promote a model to `Production` (needs Tech Lead approval)
- Change quality gate thresholds (needs Tech Lead + ADR)
- Modify production K8s manifests (needs Platform Engineer review)

## Tech Lead

**Owns**: production model decisions, quality gate thresholds, ADRs.

**Approves**:
- `Staging → Production` promotions in GitHub Environments
- Changes to quality gates (DIR threshold, ROC-AUC minimum, leakage threshold)
- New ADRs for non-trivial model decisions

**Monitors**:
- Model performance trends in Grafana
- Fairness metrics per deployment
- Drift alerts and retraining triggers

## Platform Engineer

**Owns**: K8s cluster, Terraform infrastructure, CI/CD pipelines, secrets.

**Approves**:
- Changes to `templates/k8s/` and `templates/infra/`
- New service scaffolds that require infrastructure (new IAM roles, buckets)
- Modifications to GitHub Environments configuration

**Manages**:
- IRSA / Workload Identity bindings
- Secret rotation schedule
- Cluster upgrades and node pool changes
- Cost monitoring (see `cost-audit` skill)

## Solo project note

For solo projects, one engineer plays all roles. The governance module still helps by:
- Forcing a 24h soak in Staging (catches obvious bugs before they hit prod)
- Creating an audit trail in MLflow + GitHub deployment history
- Adding a deliberate pause before production (reduces impulsive deploys)

If even this is too much friction, delete `templates/governance/` and rely only on
the quality gates in `promote_model.sh`.
