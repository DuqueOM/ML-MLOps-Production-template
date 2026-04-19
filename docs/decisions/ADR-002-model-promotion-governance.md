# ADR-002: Model Promotion Governance as Opt-in Module

## Status

Accepted

## Date

2026-04-19

## Context

ADR-001 deferred "multi-tenancy", "SOC2/GDPR compliance", and "audit logs" as
out of scope. However, a narrower need remained: teams with more than one
engineer shipping models need **approval gates between environments** and a
**minimal audit trail** of who promoted what, when, and why.

The questions were:
1. Is promotion governance the same thing as compliance/multi-tenancy?
2. Should it be baked into the template, or kept as an opt-in module?
3. What's the minimum viable implementation that doesn't violate ADR-001?

## Decision

**Add governance as an opt-in module** (`templates/governance/`) that:
- Uses **GitHub Environments** for approval gates (no new infrastructure)
- Uses **MLflow Model Registry stages** for state transitions (already in stack)
- Provides a **roles document** (`ROLES.md`) instead of code-enforced RBAC
- Is **fully removable** — deleting the directory breaks nothing

The module is **not activated by default**. The `new-service.sh` scaffolder
does not copy it. Users opt in explicitly per `templates/governance/README.md`.

## Rationale

### Governance ≠ compliance

| Compliance (ADR-001 defers) | Governance (this ADR adds) |
|---|---|
| SOC2/GDPR/HIPAA audit programs | Approval gate between staging and production |
| Legal review requirements | Who can promote a model to prod |
| Immutable audit log infrastructure | Model version metadata (who, when, why) |
| Organization-wide policies | Team-level workflow |

Compliance is an organizational program that code can't substitute. Governance
is a **workflow contract** between team members — code absolutely can (and
should) encode it.

### Why this respects ADR-001

| ADR-001 concern | How this module preserves it |
|---|---|
| No new infrastructure | Uses GitHub Environments + MLflow (already required) |
| Template stays learnable | Module is optional, clearly marked opt-in |
| No dead code | Users who don't enable it see only a directory in `templates/` |
| Engineering Calibration | Adds ~5 files, solves a real single-team problem |

### Why GitHub Environments over custom UI

- Native to the target audience (teams already using GitHub Actions)
- `required_reviewers` is enforced by GitHub, not by our code (security-by-construction)
- Deployment history tab provides audit UI for free
- Zero additional services to host or secure

### Why MLflow stages instead of a custom state machine

- Already the source of truth for model artifacts
- Native `transition_model_version_stage` API with `archive_existing_versions`
- Tags provide free metadata for audit (`promoted_by`, `reason`, `timestamp`)
- Promotion is atomic (single API call)

## Consequences

### Positive

- Teams that need approval gates get them without re-architecting
- Solo projects can ignore the module entirely
- The audit trail (who/when/why) lives in MLflow tags + GitHub deployment logs
- Nothing in the module requires new services, secrets, or infrastructure

### Negative

- GitHub Environments are a GitHub-specific feature (not portable to GitLab/BitBucket)
- The wait_timer mechanism is GitHub-native; porting requires custom scheduling
- `ROLES.md` is a documentation contract, not code-enforced. A malicious actor
  with production credentials can bypass it. This is **acceptable** for the
  single-team scope — code-enforced RBAC is a different problem (see ADR-001
  on multi-tenancy).

### Mitigations

- `templates/governance/README.md` documents the GitHub-specific assumption
- For teams on other Git hosts: the `promote_to_stage.sh` script works standalone;
  only the `required_reviewers` part needs a platform equivalent
- ROLES.md is paired with GitHub Environment `required_reviewers` config, which
  IS code-enforced at the platform level

## Alternatives Considered

### Alternative 1: Bake governance into the default template

**Rejected.** ADR-001 explicitly targets 1–5 model, single-team use. Forcing
approval gates on solo projects violates the Engineering Calibration Principle.

### Alternative 2: Custom approval service

**Rejected.** Would require a new service (auth, storage, UI), violating "no
new infrastructure" constraint from ADR-001.

### Alternative 3: OPA policies for promotion

**Rejected.** OPA is used for K8s admission (already present). Extending it for
model promotion would require a custom admission controller and webhooks.
GitHub Environments cover 95% of the use case with 1% of the complexity.

## Revisit When

- **Code-enforced RBAC is needed** (multi-team org) → promote to ADR-003 on multi-tenancy
- **Non-GitHub Git hosting becomes the norm** → add GitLab/BitBucket equivalents
- **Audit requirements exceed MLflow tags** (immutable store required) → integrate
  with enterprise SIEM; this would graduate from opt-in module to infrastructure ADR

## References

- ADR-001: Template Scope Boundaries (`ADR-001-template-scope-boundaries.md`)
- `templates/governance/README.md`: How to enable this module
- `templates/governance/ROLES.md`: Role definitions
