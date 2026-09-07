# Environment Promotion (dev → staging → prod)

**Status**: implemented in `deploy-gcp.yml`, `deploy-aws.yml`, and the
reusable `deploy-common.yml` (v1.7.1). Anti-pattern **D-26** codifies the
gap: changes reaching production without passing through staging
validation.

This document explains how to configure the GitHub Environment Protection
Rules so the Agent Behavior Protocol's **AUTO/CONSULT/STOP** modes are
enforced at the GitHub level, not just at the agent layer.

## Promotion chain

```text
  push / tag
       │
   [build]          ← produces signed images once
       │
   [deploy-dev]     ← AUTO     — every push to main runs this
       │
   [deploy-staging] ← CONSULT  — requires 1 reviewer (tech lead)
       │
   [deploy-prod]    ← STOP     — requires 2 reviewers + wait_timer
                                 + version-tag branch rule
```

## GitHub Environment Protection Rules to configure

The YAML only DECLARES which environment each job targets. The PROTECTION
lives in `Settings → Environments` of the repository. Configure these
environments manually once per repo (or via `gh api`).

### gcp-dev / aws-dev

| Setting | Value |
| --- | --- |
| Required reviewers | none |
| Wait timer | 0 |
| Deployment branches | All branches |

### gcp-staging / aws-staging

| Setting | Value |
| --- | --- |
| Required reviewers | 1 (a team member with `@MLTechLeads` or equivalent) |
| Wait timer | 0 |
| Deployment branches | `main` + version tags |

### gcp-production / aws-production

| Setting | Value |
| --- | --- |
| Required reviewers | 2 (must include `@PlatformEngineer` or equivalent) |
| Wait timer | 5 minutes |
| Deployment branches | Version tags ONLY: `v*` |

## Secrets/vars layout

Per ADR-014 §3.1 and invariant D-18, **no static cloud credentials**
live in this repo or in GitHub Secrets. Both clouds federate identity
from GitHub OIDC tokens at workflow runtime.

### GCP — Workload Identity Federation (NO static service account keys)

- Setup: `docs/runbooks/gcp-wif-setup.md`
- The deploy chain authenticates via `google-github-actions/auth@v2`
  exchanging the GitHub OIDC token for a federated SA. NO `GCP_SA_KEY`
  secret is used or required.
- If you find `GCP_SA_KEY` referenced anywhere in this repo, it is a
  bug — open an issue. The previous template iteration leaked this
  pattern; it has been removed.

### AWS — IAM Identity Provider + IRSA (per-env federated role)

- Setup: `docs/runbooks/aws-irsa-setup.md`
- One IAM role per env (`github-actions-ci-deployer-{dev,staging,prod}`)
  trusts the GitHub OIDC provider with a `sub:` condition restricting
  to this repo and (for prod) only main + version tags.
- The role ARN IS sensitive (it controls deploy access to that env)
  and lives in **Environment Secrets**:
  `Settings → Environments → {aws-dev,aws-staging,aws-production}` →
  add secret `AWS_ROLE_ARN`. Each env's role has the smallest IAM
  policy needed for its scope.

### Environment vars (per env, in `Settings → Environments → <env>`)

- `GCP_PROJECT_ID` — the cloud project ID for this env (GCP only)
- `GKE_DEV_CLUSTER` / `GKE_STAGING_CLUSTER` / `GKE_PROD_CLUSTER`
- `EKS_DEV_CLUSTER` / `EKS_STAGING_CLUSTER` / `EKS_PROD_CLUSTER`

### Repository-level vars (shared, in `Settings → Variables`)

- `GCP_REGION`, `AWS_REGION`, `AWS_ACCOUNT_ID`
- `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT` (federation targets)
- `AWS_REGISTRY_ID` (ECR account ID)
- `PROMETHEUS_URL` (used by the Dynamic Behavior Protocol pre-deploy
  check — see ADR-010, ADR-014 §4.2)

## Branch-based guards (defense in depth)

Even with Environment Protection Rules, the workflow files add a second
guard via `if:` conditions:

- Feature branches → only `deploy-dev` runs
- `main` branch → dev + staging run; prod is gated (`if: startsWith(github.ref, 'refs/tags/v')` is false)
- Version tag `v1.2.3` → dev + staging + prod all run (but prod still needs reviewer approval)

This prevents a misconfigured environment (e.g., someone removed the
`deployment_branches` rule) from letting a feature branch reach prod.

## Overlay-per-environment layout

Each environment has its own Kustomize overlay so resource sizing and
namespaces differ:

```text
k8s/
├── base/                    # Deployment, Service, HPA, PDB, etc.
└── overlays/
    ├── gcp-dev/             # small replicas, dev namespace
    ├── gcp-staging/
    ├── gcp-prod/            # prod sizing, Kyverno policies, etc.
    ├── aws-dev/
    ├── aws-staging/
    └── aws-prod/
```

## How this maps to the Agent Behavior Protocol

The workflow's structure enforces AGENTS.md invariants at CI time:

| Env | GitHub Protection | Agent mode | Why |
| --- | --- | --- | --- |
| dev | none | AUTO | Low blast radius; reversible |
| staging | 1 reviewer | CONSULT | Validates pre-prod; single sign-off sufficient |
| prod | 2 reviewers + wait_timer | STOP | Customer-facing; requires deliberation + branch gate |

Agents proposing a deploy via `/release` or `deploy-gke` skill do NOT
bypass these gates — the gate lives at the GitHub API level, not at the
agent layer.

## Migration from pre-v1.7.1 setup

Services created with v1.7.0 or earlier have flat `production-gcp` /
`production-aws` environments and tag-triggered deploys. Migration:

1. Create the 6 new environments in repo Settings (dev/staging/prod × gcp/aws)
2. Move secrets from repo-level to environment-scoped
3. Adopt the new `deploy-*.yml` (diffable — minimal user edits)
4. Add `k8s/overlays/*-dev` and `*-staging` overlays
5. Delete the old flat environments AFTER the first successful pipeline

No data or runtime migration required — images continue to build and
deploy; only the promotion chain changes.

## See also

- ADR-011 — Environment Promotion Gates (authorship & trade-offs)
- `agentic/rules/05-github-actions.md` — D-26 enforcement
- `agentic/skills/rollback/SKILL.md` — emergency path out of production
