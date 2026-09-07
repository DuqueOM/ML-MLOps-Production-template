# ADR-001: Template Scope Boundaries

## Status

Accepted

## Date

2026-04-16

## Context

External reviewers have identified several capabilities that "enterprise-grade" systems typically include but this
template does not:

1. **LLM/GenAI serving** — streaming responses, prompt versioning, guardrails, token observability
2. **Multi-tenancy** — namespace-per-team isolation, team-scoped RBAC, model access policies
3. **HashiCorp Vault** — centralized secret management beyond IRSA/Workload Identity
4. **Feature store** — shared feature repository across multiple models (Feast, Tecton)
5. **Data contracts** — formal schema agreements between producer/consumer teams
6. **Compliance frameworks** — SOC2, GDPR, HIPAA audit-ready templates
7. **Audit logs** — immutable trail of model access, predictions, and data lineage

Each of these is a legitimate enterprise need. The question is whether they belong in **this** template.

## Decision

**Defer all seven items.** This template targets **single-team, 1–5 model deployments of classical ML** (scikit-learn,
XGBoost, LightGBM). Each deferred item is documented with a concrete revisit trigger.

## Rationale

Per the **Engineering Calibration Principle** (AGENTS.md): *"The solution must match the scale of the problem."*

| Capability | Why Deferred | What We Have Instead |
| --- | --- | --- |
| **LLM/GenAI** | Fundamentally different serving pattern (streaming, token budgets, prompt chains). Mixing classical ML and LLM patterns in one template creates confusion, not value. | Template is clearly scoped to classical ML. A separate `LLM-MLOps-Template` is the correct approach. |
| **Multi-tenancy** | Requires org-level decisions (shared cluster vs dedicated, tenant isolation model). A template can't make these decisions. | Per-service RBAC (`rbac.yaml`), NetworkPolicy, ServiceAccount with least-privilege. Each scaffolded service gets its own namespace. |
| **HashiCorp Vault** | Adds operational complexity (Vault cluster, unsealing, policies). K8s-native alternatives (IRSA, Workload Identity) cover 90% of use cases without extra infrastructure. | IRSA (AWS) + Workload Identity (GCP) + `.gitleaks.toml` pre-commit + RUNBOOK guidance for Secrets Manager. |
| **Feature store** | Single-team templates don't need cross-team feature sharing. Feast/Tecton add significant operational burden. | Pandera schemas at 3 validation points + DVC for data versioning. |
| **Data contracts** | Formal contracts (protobuf, Avro) require multi-team governance. Pandera covers single-team validation. | Pandera `DataFrameModel` with type constraints, ranges, coercion. Pydantic for API contracts. |
| **SOC2/GDPR/HIPAA** | Compliance requires legal review, organizational policies, and audit infrastructure. Code templates can't substitute for compliance programs. | Security best practices: non-root containers, RBAC, NetworkPolicy, OPA policies, gitleaks, no secrets in code. |
| **Audit logs** | Requires centralized log infrastructure (SIEM). MLflow experiment tracking provides model lineage. | MLflow logs params, metrics, artifacts, git_commit, environment. JSON structured logging compatible with log aggregation. |

## Consequences

### Positive

- Template stays focused and learnable (< 1 hour to understand)
- No dead code or unused infrastructure templates
- Clear scope attracts the right users (ML engineers shipping classical models)
- Each component is battle-tested, not placeholder

### Negative

- Enterprise teams with multi-tenancy needs must extend the template
- LLM teams need a different starting point
- Some reviewers may perceive gaps vs "enterprise" expectations

### Mitigations

- This ADR documents the rationale transparently
- `AGENTS.md` references Engineering Calibration for agents to explain scope
- `CONTRIBUTING.md` welcomes extensions as community contributions

## Revisit When

- **LLM**: When >50% of new ML projects in the target audience involve LLM components
- **Multi-tenancy**: When a user contributes a tested multi-tenant overlay pattern
- **Vault**: When IRSA/Workload Identity prove insufficient for a documented use case
- **Feature store**: When the template supports >5 models sharing features
- **Compliance**: When a legal-reviewed compliance module is contributed
- **Audit logs**: When MLflow tracking proves insufficient for audit requirements
