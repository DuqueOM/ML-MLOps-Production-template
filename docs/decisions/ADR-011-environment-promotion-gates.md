# ADR-011: Environment Promotion Gates (dev → staging → prod)

## Status

Accepted

## Date

2026-04-24

## Context

Until v1.7.0, the template's deploy workflows (`deploy-gcp.yml`,
`deploy-aws.yml`) were tag-triggered and targeted a single flat
environment (`production-gcp` / `production-aws`). There was no formal
dev → staging → prod chain enforced by CI, and no required-reviewer
gates between environments.

In practice this produced:

- Version tags going **directly** to prod with no staging validation
- No kill-switch between "CI passed" and "customers see it"
- AGENTS.md's AUTO/CONSULT/STOP protocol existed at the **agent layer**
  but had no corresponding enforcement at the **GitHub API layer**

This is **D-26** — "No environment promotion gates → changes go directly
to prod without staging validation".

## Decision

Implement a four-job promotion chain enforced by **GitHub Environment
Protection Rules** as the primary gate, with workflow `if:` conditions
as defense in depth.

### Structure

```text
  [build]                   one-time image build + push + cosign sign
      │
  [deploy-dev]              Environment: {cloud}-dev        AUTO
      │
  [deploy-staging]          Environment: {cloud}-staging    CONSULT (1 rev)
      │
  [deploy-prod]             Environment: {cloud}-production STOP (2 rev + wait)
```

### Gate settings

| Env | Reviewers | Wait timer | Branches |
| --- | --- | --- | --- |
| `{cloud}-dev` | 0 | 0 | all |
| `{cloud}-staging` | 1 | 0 | main + tags |
| `{cloud}-production` | 2 | 5 min | version tags ONLY |

### Reusable workflow

`deploy-common.yml` (`on: workflow_call`) centralizes build/apply/smoke-
test logic so a fix to any one (e.g., hardening the smoke test) applies
automatically to both clouds and all three environments.

## Rationale

**Why GitHub Environment Protection instead of a custom approval bot?**  
Built-in. Integrates with OIDC, audit log, `gh` CLI, and the
Environment-scoped secrets model (D-18). Zero new dependencies.

**Why a `wait_timer` on prod?**  
Deliberate friction. 5 minutes is enough time to catch "oh wait, I
didn't mean to click approve" without being operationally painful. The
timer also provides a chance for newly-fired alerts to surface before
the deploy proceeds.

**Why tag-only for prod?**  
Content-addressability. A tag cannot be "moved" silently (tag races
exist, but GitHub's `deployment_branches` regex catches them). This
aligns with D-19 (image signing) — the same artifact approved in
staging MUST be the one deploying to prod.

**Why build ONCE and reuse the image across envs?**  
Otherwise we deploy a DIFFERENT binary to prod than the one validated
in staging. The whole point of promotion is to test the EXACT artifact
that will reach customers.

## Consequences

### Positive

- Prod deploys always have two signatures (2 reviewers) recorded by
  GitHub Deployments API — audit-ready.
- The Agent Behavior Protocol's STOP class becomes enforceable by CI,
  not just an agent convention.
- Staging becomes an actual validation layer (currently prod was the
  first place traffic hit the new image).
- Environment-scoped secrets eliminate the "prod creds readable by dev
  job" misconfiguration.

### Negative

- Operators must configure 6 environments per repo (gcp/aws × dev/staging/prod).
  Manual one-time cost.
- Overlay layout grows from `gcp-prod` / `aws-prod` to six overlays.
- Feature branches stop at dev; PR reviewers must remember to tag for
  staging validation (mitigated by "main → staging" auto-promotion).

### Mitigations

- Setup guide: `docs/environment-promotion.md` with copy-pastable
  environment configs.
- Migration section documents the zero-data-loss path from flat to
  chained.
- CI comment on the PR template reminds reviewers of the chain.

## Revisit When

- The number of environments exceeds 3 (e.g., `pre-staging`, `canary`,
  `hotfix`) → consider a GitOps tool (ADR-013)
- Multiple teams begin using the same environments with different
  reviewer requirements → consider Environment-scoped teams
- Cross-cloud promotion ordering matters (e.g., deploy GCP prod THEN
  AWS prod with a wait between) → consider a meta-orchestrator

## Related

- ADR-005 — Agent Behavior Protocol (the enforcement this ADR realizes)
- ADR-013 (future) — CD Strategy (GitOps revisit trigger)
- `docs/environment-promotion.md` — operator setup guide
- `.windsurf/rules/05-github-actions.md` §Environment Promotion Gates (D-26)
- `.windsurf/skills/rollback/SKILL.md` — emergency path out of production
