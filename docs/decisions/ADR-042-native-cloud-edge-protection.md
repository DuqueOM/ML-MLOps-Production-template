# ADR-042 — Native-Cloud-First Edge Protection (Cloud Armor / AWS WAF+Shield), Cloudflare Optional

- **Status**: Accepted
- **Date**: 2026-07-06
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none
- **Superseded by**: none
- **Related artifacts**:
  - `templates/service/k8s/components/edge-gcp/`, `templates/service/k8s/components/edge-aws/` —
    the opt-in Kustomize Components this ADR governs (delivered ahead of
    this ADR; the components exist, this ADR fixes their design intent
    in writing).
  - `agentic/rules/17-edge-protection.md`
  - `agentic/skills/edge-audit/SKILL.md`
  - `agentic/workflows/edge-setup.md`
  - `AGENTS.md` — anti-pattern D-38.
  - `docs/observability/monitoring-stations.md` — the audit that found
    this gap.

## 1. Context

A monitoring-coverage audit against six operational stations (Edge,
Infrastructure, Inference, Models, Logs & Traces, Business KPIs) found
Edge to be the one real gap: this template's Kubernetes Ingress
resources ship with no edge-layer protection by default — no WAF, no
DDoS mitigation, no bot management, no rate limiting in front of the
load balancer.

The obvious next question was whether to introduce Cloudflare as the
template's edge-protection layer. Cloudflare is a strong choice on its
own merits: it works identically regardless of which cloud a service
runs on, and its WAF/rate-limiting/bot-scoring surface is a good
vehicle for learning the underlying concepts hands-on.

But this template's own identity (`CLAUDE.md` "Project Identity") is
"multi-cloud deployment (GKE + EKS)" in the sense of **cloud parity** —
an adopter picks GCP or AWS per deployment and gets an equivalent
experience on either — not that a single deployment spans both clouds
simultaneously. For that common case, making Cloudflare the default or
reference edge implementation would hand the adopter a third-party
account, a DNS delegation, and a second control plane they did not ask
for, layered on top of the cloud they already chose — a cloud that
already ships a native, equivalent capability (Cloud Armor / AWS WAF +
Shield Standard) which:

- requires no new vendor account or DNS delegation,
- integrates with the same IAM / Workload-Identity model the rest of
  the template already standardizes on (D-17/D-18, ADR-017),
- bills through the same cloud invoice the adopter already reconciles
  (feeding the same `cost-audit` skill and Business KPIs dashboard),
- is the tool a platform or security engineer reviewing GCP/AWS
  infrastructure would expect to see used by default.

Cloudflare's real advantage — cloud-agnosticism — only pays off for an
adopter who is genuinely running both GKE and EKS concurrently, or who
wants a zero-cloud-account path to learn WAF concepts before touching
Terraform. Both are legitimate scenarios this template should support —
just not as the default for the common single-cloud-per-deployment
case.

## 2. Decision

**Native-cloud-first, Cloudflare-optional.**

| Deployment shape | Default edge protection | Cloudflare |
| --- | --- | --- |
| GCP only (GKE) | Cloud Armor, via `BackendConfig` CRD + a `google_compute_security_policy` | optional, off by default |
| AWS only (EKS) | AWS WAFv2 + Shield Standard (automatic/free for ALB), via ALB annotations + an `aws_wafv2_web_acl` | optional, off by default |
| Genuine concurrent multi-cloud (GKE + EKS both serving production traffic), or a zero-cloud-account local/demo path | Either native option per-cluster, or Cloudflare as one control plane spanning both | adopter's explicit choice, documented in the equivalence matrix (Wave B4) |

### 2.1 New surfaces

1. **K8s Kustomize Components** `k8s/components/edge-gcp/` and
   `k8s/components/edge-aws/` — opt-in (not referenced by any overlay's
   `kustomization.yaml` by default, matching the local-first / D-35
   opt-in philosophy). Each Ingress carries a custom
   `edge-protection.mlops-template.io/implementation` annotation
   (`cloud-armor` / `aws-waf`, and later `cloudflare`) that downstream
   tooling — the `edge-audit` skill, the D-38 policy test — reads to
   confirm coverage without having to parse cloud-specific Terraform.
2. **Terraform**: `google_compute_security_policy` (GCP) and
   `aws_wafv2_web_acl` (AWS) modules, plus an optional Cloudflare
   module — tracked as their own wave of work, not duplicated here.
3. **Rule `17-edge-protection`** (glob-scoped) — behavioral constraints
   for anyone editing Ingress/WAF-adjacent Kubernetes or Terraform.
4. **Skill `edge-audit`** (AUTO, read-only) — scans a service for
   edge-protection coverage, mirroring `rule-audit`'s shape for this one
   new invariant domain rather than growing `rule-audit` itself past its
   current per-domain catalogue structure.
5. **Workflow `/edge-setup`** (CONSULT) — the human-invokable entry
   point to wire an edge component into an overlay and apply the
   matching Terraform.
6. **Anti-pattern D-38**: a public inference endpoint (a production
   overlay's Ingress) shipped without an edge-protection component
   wired in, or an existing WAF/rate-limit rule disabled/loosened
   without STOP-class approval.

### 2.2 Mode assignment (verb-separated — ADR-039 precedent)

The same verb-separation ADR-039 introduced for CI-green verification
(AUTO-verify / CONSULT-act / STOP-override) applies here, because the
same shape of problem recurs: reading state is safe, changing state has
real effects, and *removing* a safety control is categorically
different from either.

| Verb | Mode | Rationale |
| --- | --- | --- |
| Read/audit current edge-protection coverage (`edge-audit`) | **AUTO** | Read-only; an agent must always be able to check |
| `terraform apply` of Cloud Armor / WAFv2 / Cloudflare resources, **in any environment including dev** | **CONSULT** | Creates a publicly-reachable resource plus real cost. Unlike the rest of the Operation → Mode table, this does not downgrade to AUTO in dev — the blast radius (public exposure) does not shrink because an environment label says "dev" |
| Disabling, removing, or loosening an existing WAF/rate-limit rule, **in any environment** | **STOP**, unconditionally | Mirrors D-36 / `rollback`'s environment-independent STOP: removing a safety control is always a human decision, never a convenience, regardless of urgency or environment |

## 3. Invariants (contract-enforced)

- **I-042-1** — any Ingress produced by `k8s/components/edge-{gcp,aws}/`
  MUST carry a non-empty
  `edge-protection.mlops-template.io/implementation` annotation with a
  value in `{cloud-armor, aws-waf, cloudflare}`. Enforced by
  `templates/service/tests/policy/test_anti_patterns.py::test_d38_edge_component_carries_implementation_annotation`.
- **I-042-2** — `terraform apply` of edge-protection resources MUST be
  CONSULT in every environment (no environment-based downgrade to
  AUTO) — enforced the same way as D-36, via
  `validate_agentic_manifest.py --strict`'s blanket rule that no
  `escalation_override` may de-escalate a mode.
- **I-042-3** — disabling an existing WAF/rate-limit rule MUST be STOP
  in every environment, same mechanism.

## 4. Scope

**In scope**: the two K8s components (already delivered), this
governance surface (rule/skill/workflow/anti-pattern), the native
Terraform modules and optional Cloudflare module, edge-specific
monitoring, and the setup runbook + cloud-equivalence matrix — tracked
across several waves of the same initiative, not separate ADRs.

**Out of scope**:

- Cloudflare Workers/Pages — an application-hosting product, unrelated
  to edge *protection*.
- AWS Shield **Advanced** (~$3k/mo) — not justified at this template's
  target scale (Engineering Calibration Principle, `CLAUDE.md`); Shield
  **Standard** (automatic, free for ALB-fronted resources) is in scope.
- A generic multi-WAF abstraction layer hiding all three providers
  behind one interface — this would hide exactly the provider-specific
  configuration a platform engineer needs to see and audit, and
  contradicts this template's existing preference for explicit,
  provider-specific Terraform over abstraction layers (the GCP/AWS
  module split is deliberate elsewhere in `infra/terraform/` for the
  same reason).

## 5. Consequences

### Positive

- Closes the one real gap the six-station monitoring audit found.
- Matches the tool a reviewing platform or security engineer would
  actually expect on native GCP/AWS infrastructure — the same reasoning
  that already drives this template's IRSA/Workload-Identity-only
  stance (D-17/D-18).
- Cloudflare remains available for the two scenarios where it is
  genuinely the better tool, without being forced onto the common case.

### Negative

- Three edge-protection code paths to maintain and keep at parity
  (Cloud Armor, AWS WAFv2, Cloudflare) instead of one.
- An adopter must still run `/edge-setup` (CONSULT) explicitly — by
  design (see D-35 / local-first philosophy): this template does not
  silently wire public-facing security infrastructure into a scaffolded
  service without an explicit human decision.

### Neutral

- Surface counts move: rules 17→18, skills 25→26, workflows 17→18,
  anti-patterns D-01..D-37→D-01..D-38. Cascaded through `AGENTS.md`,
  `CLAUDE.md` (×2), `README.md`, `llms.txt`, and
  `templates/config/agentic_manifest.yaml` in the same change (rule 16
  / ADR-031 discipline).

## 6. Revisit triggers

- An adopter reports genuinely concurrent multi-cloud (GKE + EKS both
  serving production traffic for the same logical service) → revisit
  whether Cloudflare should become the *recommended* default for that
  specific topology; this ADR intentionally leaves that door open
  rather than closing it.
- AWS Shield Advanced becomes justified (an adopter reports a real
  volumetric attack against a small-scale deployment) → revisit the
  §4 out-of-scope call.
- Cloud Armor or AWS WAFv2 pricing/feature parity diverges enough that
  "native-first" stops being the objectively better default for the
  common case.

## 7. Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Cloudflare as the default/reference implementation, native tools shown as a comparison table | Adds a third-party account + DNS delegation for the common single-cloud case, when the cloud already chosen ships an equivalent native tool integrated with the same IAM model the rest of the template uses |
| Native tools only, no Cloudflare option | Discards real value for genuinely multi-cloud adopters and for a zero-cloud-account learning/demo path |
| A common abstraction layer hiding all three providers behind one Terraform module | Hides exactly the provider-specific configuration a platform engineer needs to see and audit; contradicts this template's existing explicit-over-abstracted Terraform convention |

## 8. Related

- `docs/decisions/ADR-011-environment-promotion-gates.md` — the
  environment-based AUTO/CONSULT/STOP baseline this ADR deviates from
  for `terraform apply` (never AUTO, even in dev).
- `docs/decisions/ADR-039-ci-green-verification-gate.md` — the
  verb-separation pattern (AUTO-verify / CONSULT-act / STOP-override)
  this ADR reuses.
- `agentic/skills/rollback/SKILL.md` — the STOP-regardless-of-environment
  precedent for disabling a safety control.
- `docs/observability/monitoring-stations.md` — the audit that
  identified this gap.
