# Runbook — Edge Protection Setup (Cloud Armor / AWS WAF+Shield / Cloudflare optional)

One-time (per overlay) setup wiring a WAF + rate-limiting + DDoS
mitigation layer in front of a service's Ingress. Native-cloud is the
default; Cloudflare is optional for genuinely concurrent multi-cloud
deployments or a zero-cloud-account learning path.

Authority: D-38, `docs/decisions/ADR-042-native-cloud-edge-protection.md`.

## Prerequisites

- The service is already scaffolded and has a working overlay under
  `k8s/overlays/<overlay>/` (this runbook does not cover initial
  service setup — see `QUICK_START.md`).
- **AWS only**: `aws-load-balancer-controller` is already installed on
  the EKS cluster. This is a cluster-level, install-once component —
  not part of this template's per-service scaffolding. See the
  [AWS Load Balancer Controller docs](https://kubernetes-sigs.github.io/aws-load-balancer-controller/).
- Terraform >= 1.7, applied against the SAME backend the rest of
  `infra/terraform/<cloud>/` uses for this environment.
- **Cloudflare only**: a zone already exists for the domain, and an API
  token scoped to `Zone:Edit` + `DNS:Edit` for that zone specifically
  (never the account-wide Global API Key).

## 1 — terraform apply (CONSULT, every environment)

This is a **hard CONSULT in every environment, including dev** — never
run this as part of a routine, unattended `terraform apply` (rule
`17-edge-protection.md`, ADR-042 §2.2). Public exposure and cost do not
shrink because the environment label says "dev."

### GCP

```bash
cd infra/terraform/gcp
terraform plan \
  -var="enable_edge_protection=true" \
  -var-file=environments/<env>.tfvars
# Review the plan. Then, after approval:
terraform apply \
  -var="enable_edge_protection=true" \
  -var-file=environments/<env>.tfvars

terraform output edge_security_policy_names
terraform output edge_ssl_policy_names
```

### AWS

```bash
cd infra/terraform/aws
terraform plan \
  -var="enable_edge_protection=true" \
  -var-file=environments/<env>.tfvars
# Review the plan. Then, after approval:
terraform apply \
  -var="enable_edge_protection=true" \
  -var-file=environments/<env>.tfvars

terraform output edge_wafv2_web_acl_arns
```

### Cloudflare (optional)

```bash
cd infra/terraform/cloudflare
terraform apply \
  -var="cloudflare_zone_id=<zone-id>" \
  -var='origin_by_service={"<service>"={type="A",hostname="<gcp-lb-ip-or-aws-alb-hostname>"}}'
```

## 2 — Wire the Kustomize Component into the overlay

Edit `k8s/overlays/<overlay>/kustomization.yaml`:

```yaml
components:
  - ../../components/edge-gcp   # or edge-aws
```

Then fill the component's own placeholders with the Terraform outputs
from step 1:

- `k8s/components/edge-gcp/managedcertificate.yaml` — `{DOMAIN}`
- `k8s/components/edge-aws/ingress.yaml` — `{ACM_CERT_ARN}`, `{WAFV2_ACL_ARN}`
  (the ARN from `terraform output edge_wafv2_web_acl_arns`)

The security-policy name (`{@ service_kebab @}-edge-policy`) and SSL-policy
name (`{@ service_kebab @}-ssl-policy`) in the GCP component already match
what Terraform creates by construction (both derive from the same
service name) — no manual copy needed there.

## 3 — Verify

```bash
make edge-setup OVERLAY=<overlay>
```

Or invoke the `edge-audit` skill directly. Confirm:

- `edge_protection.mlops-template.io/implementation` annotation present
  on the rendered Ingress, matching the cloud you configured.
- The Terraform resource (Cloud Armor policy / WAFv2 ACL) resolves —
  Step 4 of `edge-audit` confirms this if cloud credentials are
  available in the current context.
- `curl -I https://<domain>/health` succeeds through the new Ingress.

## Coverage Missing

Runbook for `{@ service_slug @}EdgeProtectionMissing` firing.

This means the last `edge-audit` run found a `*-prod` overlay with no
edge-protection component wired in, or wired in incorrectly (D-38
violation). This is a real gap, not a false positive by default — treat
it as P2 (ticket, not page; a missing WAF is a risk, not an active
incident, unless combined with other signals).

1. Run `make edge-setup OVERLAY=<overlay>` to see the current state.
2. If step 2 above (component wiring) was never done: do it now,
   following steps 1-3 of this runbook.
3. If the component IS wired in but the audit still fails: check the
   annotation's cloud matches the overlay's cloud (copy-paste drift
   from wiring the wrong component — e.g. `edge-aws` into a `gcp-prod`
   overlay).
4. If both look correct: check whether the underlying Terraform
   resource was ever actually applied (`edge-audit` Step 4) — a common
   failure mode is wiring the K8s side without ever running step 1 of
   this runbook.

## Audit Heartbeat

Runbook for `{@ service_slug @}EdgeAuditHeartbeatMissing` firing.

No `edge-audit` run has pushed a coverage metric in 14 days. This means
the coverage panel on `dashboard-edge.json` is showing a STALE verdict,
not necessarily a wrong one — treat as P3/info (notify, not page).

1. Run `edge-audit` (or `make edge-setup OVERLAY=<overlay>`) for every
   overlay that should be audited regularly.
2. If this is a recurring gap, consider wiring a scheduled CI job that
   invokes the skill weekly — no reference job ships with the template
   (every adopter's CI scheduling conventions differ), so this is a
   documented pattern, not a shipped cron.

## Cloud equivalence matrix

The three implementations are NOT drop-in equivalents — the underlying
mechanisms differ enough that a single shared configuration value would
misrepresent at least one cloud. Key differences an adopter must
account for when tuning `waf_mode` / rate limits per cloud:

| Dimension | Cloud Armor (GCP) | AWS WAFv2 | Cloudflare (optional) |
| --- | --- | --- | --- |
| WAF rule source | Google preconfigured rules (`sqli-v33-stable`, `xss-v33-stable`, `lfi-v33-stable`) | AWS Managed Rules (`AWSManagedRulesCommonRuleSet`, `AWSManagedRulesSQLiRuleSet`) | Cloudflare Managed Ruleset (single bundle, OWASP + CVE coverage) |
| Observe-before-block mode | `waf_mode = "count"` (per-rule action) | `waf_mode = "count"` (`override_action { count {} }`) | `waf_mode = "log"` (ruleset-level override) |
| Block mode | `waf_mode = "deny(403)"` | `waf_mode = "block"` | `waf_mode = "block"` |
| Rate-limit window | Configurable `interval_sec` (default 60s, `rate_limit_requests_per_minute`) | Fixed 5-minute rolling window (AWS API constraint, `rate_limit_requests_per_5min`, minimum 100) | Fixed 10-second window (`rate_limit_requests_per_10s`) |
| Rate-limit action | `throttle` → HTTP 429 (conform/exceed split) | `block` (no native throttle — AWS WAFv2 rate rules only block) | `block` → HTTP 429 (custom response configured) |
| DDoS mitigation | Adaptive Protection (`adaptive_protection_config`), layer 7 | Shield Standard (automatic, free, always-on for ALB) | Always-on at the edge (part of every plan); "I'm Under Attack" mode is an explicit, disruptive opt-in (`under_attack_mode`) |
| Paid DDoS tier | Cloud Armor Managed Protection Plus (not covered by this template) | Shield **Advanced** (~$3k/mo) — explicitly out of scope (ADR-042 §4) | Cloudflare Enterprise-tier DDoS SLA (not covered by this template) |
| TLS policy | `google_compute_ssl_policy`, `MODERN` profile, TLS 1.2 floor | ALB `ssl-policy` annotation, `ELBSecurityPolicy-TLS13-1-2-2021-06` | Managed at the zone level (Cloudflare dashboard, not this Terraform module) |
| Terraform → K8s wiring | `BackendConfig` CRD references the policy by name | ALB annotation references the ACL ARN directly | N/A — Cloudflare sits in front of DNS, not wired into K8s at all |

**Practical implication**: do not copy a rate-limit number from one
cloud's tfvars into another's expecting the same real-world behavior.
"600 requests per minute" (GCP) and "3000 requests per 5 minutes" (AWS)
are the same AVERAGE rate but very different burst tolerances, because
the windows differ. Tune each cloud's threshold against that cloud's
own observed traffic, not by converting a number from the other cloud's
config.

## Disabling or loosening a rule

**STOP-class, every environment, no exceptions** (ADR-042 §2.2). This
is not a step in this runbook to execute unattended — propose nothing,
change nothing, until a human explicitly instructs it, and record the
decision via `scripts/audit_record.py` before making the change. Same
precedent as `/rollback` and the D-36 CI-override gate: removing a
safety control is always a human decision.

## Related

- `docs/decisions/ADR-042-native-cloud-edge-protection.md`
- `agentic/rules/17-edge-protection.md`
- `agentic/skills/edge-audit/SKILL.md`
- `agentic/workflows/edge-setup.md`
- `templates/service/infra/terraform/{gcp,aws,cloudflare}/security.tf`
- `templates/service/k8s/components/edge-{gcp,aws}/`
- `templates/service/monitoring/grafana/dashboard-edge.json`
- `docs/runbooks/gcp-wif-setup.md`, `docs/runbooks/aws-irsa-setup.md` —
  the IAM prerequisites this runbook's Terraform steps build on
