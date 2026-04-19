# Governance Module (opt-in)

**Opt-in module** for teams that need formal approval gates between environments.
This module **does not conflict with ADR-001** — it's optional and adds no new infrastructure.

## When to enable this module

Enable when any of these apply:
- More than 1 person can promote models to production
- Regulatory or internal audit requires sign-off on model changes
- You've had a production incident caused by unreviewed model promotion

**Do NOT enable** for solo projects or prototypes — the approval friction exceeds the benefit.

## What this module provides

1. **3-stage promotion flow**: `dev` → `staging` → `production`
2. **MLflow Model Registry stages** with automated transitions
3. **GitHub Environments** with `required_reviewers` for each stage
4. **Role-based responsibilities** (`ROLES.md`)
5. **Audit trail** via MLflow + GitHub deployment history

## Architecture

```
┌──────────┐    quality     ┌──────────┐   Tech Lead   ┌────────────┐
│  dev     │─── gates ────> │ staging  │── approval ─> │ production │
│          │    (auto)      │          │   (manual)    │            │
└──────────┘                └──────────┘               └────────────┘
     ▲                           ▲                            ▲
     │                           │                            │
MLflow stage:            MLflow stage:                MLflow stage:
  "None"                  "Staging"                  "Production"
```

### Promotion gates

| Stage | Trigger | Gates | Approver |
|-------|---------|-------|----------|
| `None → Staging` | Merge to `main` | All quality gates (`promote_model.sh`) | Automatic (CI) |
| `Staging → Production` | Manual dispatch | Staging soaked ≥24h + approval | Tech Lead |
| `Production → Archived` | New prod deploy | — | Automatic |

## Files in this module

| File | Purpose |
|------|---------|
| `README.md` | This file — overview |
| `ROLES.md` | Who can do what (ML Engineer / Tech Lead / Platform) |
| `github-environments.yml` | GitHub Environments configuration (reference) |
| `promote-with-approval.yml` | GitHub Actions workflow with `required_reviewers` |
| `promote_to_stage.sh` | MLflow stage transition script |

## Installation (3 steps)

### Step 1 — Copy workflow to your service repo

```bash
cp templates/governance/promote-with-approval.yml .github/workflows/
```

### Step 2 — Configure GitHub Environments

In your GitHub repo, go to **Settings → Environments → New environment**.
Create two environments:

**Environment: `staging`**
- Deployment branches: `main` only
- Required reviewers: none (automatic on quality gates)

**Environment: `production`**
- Deployment branches: `main` only
- Required reviewers: 1+ team member (Tech Lead or Platform Engineer)
- Wait timer: 24 hours (optional, enforces staging soak)

See `github-environments.yml` for the complete specification.

### Step 3 — Copy the stage transition script

```bash
cp templates/governance/promote_to_stage.sh scripts/
chmod +x scripts/promote_to_stage.sh
```

## Usage

### Automatic: merge to `main`
CI runs `promote_model.sh` (all quality gates). If gates pass, the model is
transitioned to MLflow stage `Staging` and deployed to the staging K8s namespace.

### Manual: promote to production

```bash
# Option A: via CLI
./scripts/promote_to_stage.sh --model-name fraud_detector --version 42 --stage Production

# Option B: via GitHub Actions
# Actions tab → promote-with-approval.yml → Run workflow
#   model-name: fraud_detector
#   version: 42
```

Either option requires a GitHub Environment approver to click **Approve**.

## What does NOT change

- **Existing quality gates** in `promote_model.sh` remain the first line of defense
- **ADR-001 scope** is preserved — no multi-tenancy, no Vault, no feature store
- **Opt-out path**: delete `templates/governance/` and the workflow file. Nothing breaks.

## References

- ADR-001 (scope boundaries): `docs/decisions/ADR-001-template-scope-boundaries.md`
- ADR-002 (this module's rationale): `docs/decisions/ADR-002-model-promotion-governance.md`
- `RUNBOOK.md` (secret management, deploy commands)
