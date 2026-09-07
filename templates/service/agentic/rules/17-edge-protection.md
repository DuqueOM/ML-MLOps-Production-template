---
trigger: glob
globs: ["**/ingress*.yaml", "**/k8s/components/edge-*/**", "**/infra/terraform/**/*waf*.tf", "**/infra/terraform/**/*security_policy*.tf", "**/infra/terraform/**/*cloudflare*.tf", "**/infra/terraform/**/*armor*.tf"]
description: Edge-protection patterns — native-cloud-first WAF/DDoS/rate-limiting, Cloudflare optional (ADR-042, D-38)
---

# Edge Protection Rules

## Native-cloud-first (MANDATORY default)

A production Ingress MUST NOT ship without an edge-protection layer in
front of it. The DEFAULT implementation is the native tool for whichever
cloud the overlay targets — never Cloudflare, never a hand-rolled
alternative, unless the adopter has explicitly chosen the multi-cloud
or zero-cloud-account path (ADR-042 §2):

- GCP overlays (`gcp-*`) → Cloud Armor, via the `edge-gcp` Kustomize
  Component (`BackendConfig` CRD referencing a `google_compute_security_policy`).
- AWS overlays (`aws-*`) → AWS WAFv2 + Shield Standard, via the
  `edge-aws` Kustomize Component (ALB annotations referencing an
  `aws_wafv2_web_acl`).
- Cloudflare is opt-in only, for genuinely concurrent multi-cloud
  deployments or a zero-cloud-account demo path — never the default for
  a single-cloud deployment.

## The implementation annotation is not decorative (D-38)

Every Ingress produced by an edge component MUST carry:

```yaml
metadata:
  annotations:
    edge-protection.mlops-template.io/implementation: cloud-armor  # | aws-waf | cloudflare
```

This annotation is the ONLY thing the `edge-audit` skill and the D-38
policy test read to confirm coverage — they do not parse
cloud-specific Terraform to infer whether a WAF exists. An Ingress with
this annotation missing or set to an unrecognized value is treated as
**unprotected**, even if a WAF happens to exist out-of-band.

## Mode assignment is fixed, not environment-scaled (ADR-042 §2.2)

Unlike most Terraform applies in this template (`03-terraform.md`),
edge-protection resources do NOT get a lighter mode in dev:

| Action | Mode | Never downgrade to |
| --- | --- | --- |
| Read/audit edge-protection coverage | AUTO | — |
| `terraform apply` of Cloud Armor / WAFv2 / Cloudflare resources, ANY environment | CONSULT | AUTO, even in dev — creates public exposure + real cost regardless of environment label |
| Disable, remove, or loosen an existing WAF/rate-limit rule, ANY environment | STOP | CONSULT or AUTO, ever — removing a safety control is always a human decision |

A context file's `escalation_overrides` MUST NOT de-escalate either of
these — `validate_agentic_manifest.py --strict` rejects any override
that weakens a mode repo-wide; this is not a rule specific to edge
protection, just an invariant this rule relies on.

## Never bypass the cloud LB to reach a pod directly

Every edge component's Ingress is the ONLY intended public entry point.
A `LoadBalancer`-type `Service` or a `NodePort` opened for the same
workload defeats the WAF/rate-limiting the Ingress enforces — the
traffic never passes through it. If a `Service` needs external
exposure, it goes through the Ingress, never around it.

## Cloudflare, when chosen, still needs a cloud-native fallback documented

An adopter choosing Cloudflare for the multi-cloud case MUST still
document (per-cluster) what happens if Cloudflare is unreachable or
misconfigured — Cloud Armor / AWS WAF are not automatically still
active once Cloudflare is in front of the LB and the LB's own firewall
rules are loosened to only trust Cloudflare's IP ranges. This is a
design decision to record in an ADR, not a default this template
assumes for you.

## Related

- `docs/decisions/ADR-042-native-cloud-edge-protection.md`
- `agentic/skills/edge-audit/SKILL.md`
- `agentic/workflows/edge-setup.md`
- `agentic/rules/03-terraform.md` — the general Terraform rules this
  one narrows for edge-protection resources specifically
- `agentic/rules/02-kubernetes.md` — general K8s rules; this rule adds
  the edge-specific annotation contract on top
