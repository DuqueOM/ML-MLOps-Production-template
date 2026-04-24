---
paths:
  - ".github/workflows/*.yml"
  - ".github/workflows/*.yaml"
  - "**/cicd/*.yml"
---

# GitHub Actions Rules

## Environment promotion (D-26, ADR-011)
- Deploys chain `dev → staging → prod` in a SINGLE workflow
- Uses reusable `deploy-common.yml` — single source of truth for
  build/apply/smoke-test (no duplication across GCP/AWS)
- Prod job gated by `environment: production`:
  * `required_reviewers: 2`
  * `wait_timer: 15` (minutes soak after staging success)
  * `deployment_branch_policy: protected_tags` — only tag-based deploys
- Staging: `required_reviewers: 1`, no tag restriction

## Secrets + permissions
- `permissions: id-token: write` for Cosign keyless signing (OIDC)
- NO static cloud credentials in env vars — IRSA/WI only (D-18)
- `GITHUB_TOKEN` least-privilege (`contents: read` by default)
- Secrets via `secrets.<NAME>` — never literals; never echo

## SBOM + signing (D-19, D-30)
- Every prod deploy workflow:
  1. Build image + tag with git sha
  2. `syft` CycloneDX SBOM
  3. `cosign sign` keyless
  4. `cosign attest --type cyclonedx` SBOM
  5. `kubectl apply` (via deploy-common.yml)
  6. Smoke test `/ready` before marking success

## Forbidden
- `deploy-prod.yml` as a standalone workflow (D-26)
- `kubectl apply` without going through `deploy-common.yml`
- `uses: org/action@v1` — always pin to sha (supply-chain)
- `run: eval $SECRET` — no dynamic secret interpolation

## Audit
- Every workflow run appends to `ops/audit.jsonl` via `record_operation()`
- CONSULT/STOP modes also open a GitHub issue tagged `audit`

See `.windsurf/rules/05-github-actions.md`, AGENTS.md §Audit Trail Protocol,
ADR-011.
