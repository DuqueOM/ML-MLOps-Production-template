---
name: edge-audit
description: Scan a service for edge-protection coverage (WAF, DDoS mitigation, rate limiting) against ADR-042/D-38 — produces a PASS/FAIL report with file:line evidence
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(kubectl:*)
  - Bash(gcloud:*)
  - Bash(aws:*)
when_to_use: >
  Invoke before a production deploy, during a security review, after
  scaffolding a new service, or on a schedule (e.g. quarterly) to catch
  drift. Also useful when onboarding a service that was hand-built
  outside the scaffolder. Examples: 'audit edge protection', 'is this
  service WAF-protected', 'check D-38 compliance'.
argument-hint: "[overlay-path] [--cloud gcp|aws|both]"
authorization_mode:
  scan: AUTO
  propose_wiring: CONSULT
  apply_terraform: CONSULT
  disable_or_loosen_rule: STOP
---

# Edge Audit — Coverage scan against ADR-042 / D-38

This skill is READ-ONLY for the scan itself. It never wires a component
into an overlay and never applies Terraform — those are the `/edge-setup`
workflow's job (CONSULT). This skill only answers "is this service
protected, and by what."

## When NOT to use this skill

- **To actually add edge protection** — this skill audits; `/edge-setup`
  (or `agentic/workflows/edge-setup.md` directly) wires the component in
  and applies Terraform. Running this skill produces a finding, not a
  fix.
- **On a `local` stack profile** — the local-first profile (ADR-033,
  D-35) never targets a cluster or accepts cloud credentials; there is
  no public endpoint to protect. Skip.
- **On `batch-only` topology** — a CronJob with no Ingress has no edge
  surface by definition (see `k8s/overlays/batch-only/`); skip with a
  SKIP verdict, not a FAIL.

## Step 1 — Identify the overlay(s) in scope (AUTO, 30s)

```bash
find . -path "*/k8s/overlays/*" -maxdepth 4 -type d -name "kustomization.yaml" -prune
```

If `[overlay-path]` is given, restrict to it. If `--cloud` is given,
restrict to `gcp-*` or `aws-*` overlays only.

## Step 2 — Check whether an edge component is wired in (AUTO, 30s)

```bash
grep -n "components:" -A 5 k8s/overlays/<overlay>/kustomization.yaml
```

- **PASS** if the overlay's `components:` list references
  `../../components/edge-gcp` (for `gcp-*` overlays) or
  `../../components/edge-aws` (for `aws-*` overlays), or an
  adopter-added Cloudflare-equivalent path.
- **FAIL** if a `gcp-prod`/`aws-prod` overlay has no matching component
  reference — this IS a D-38 violation (a production overlay with no
  edge protection wired in).
- **WARN** (not FAIL) for `*-dev`/`*-staging` overlays without one —
  edge protection is mandatory for prod; earlier environments may
  reasonably defer it, but flag it so it doesn't silently stay missing
  by the time prod is cut.

## Step 3 — Render and inspect the Ingress (AUTO, 1 min)

```bash
kubectl kustomize k8s/overlays/<overlay>/ | \
  awk '/^kind: Ingress$/{f=1} f' 
```

Confirm:

- `metadata.annotations["edge-protection.mlops-template.io/implementation"]`
  is present and one of `cloud-armor` / `aws-waf` / `cloudflare`. Missing
  or unrecognized → **FAIL** (rule `17-edge-protection.md`: "the
  annotation is not decorative" — this is the ONLY signal this skill and
  the D-38 policy test trust).
- The annotation's cloud matches the overlay's cloud (a `gcp-*` overlay
  claiming `aws-waf` is a **FAIL** — copy-paste drift from the wrong
  component).
- No `LoadBalancer`-type `Service` or `NodePort` exists for the same
  workload that would let traffic bypass the Ingress entirely (rule
  17's "never bypass the cloud LB" check) — **FAIL** if found, since it
  defeats the WAF regardless of the Ingress's own annotation.

## Step 4 — Confirm the backing Terraform resource actually exists (AUTO, 1 min)

The K8s-side annotation only proves *intent*; confirm the cloud
resource is real, not just referenced:

```bash
# GCP
gcloud compute security-policies describe <policy-name> --format="value(name)"

# AWS
aws wafv2 get-web-acl --name <acl-name> --scope REGIONAL --id <id>
```

- **FAIL** if the K8s side references a policy/ACL name that does not
  resolve in the target cloud project/account — this is the specific
  failure mode of "someone copied the component but never ran
  `/edge-setup`'s Terraform step."
- **SKIP** this step (not FAIL) if no cloud credentials are configured
  in the current context — report it as "not verified, credentials
  unavailable," distinct from a real FAIL.

## Step 4b — Push coverage metrics to Pushgateway (Edge station dashboard)

`dashboard-edge.json`'s "Edge Protection Coverage" panel and the
`{@ service_slug @}EdgeProtectionMissing` / `...HeartbeatMissing` alerts
read these two gauges from Prometheus — this step is what populates them,
mirroring `cost-audit`'s Step 2b Pushgateway pattern. One push per overlay
audited:

```bash
{
  echo "edge_protection_enabled{overlay=\"${OVERLAY}\"} ${ENABLED_0_OR_1}"
  echo "edge_protection_last_audit_timestamp{overlay=\"${OVERLAY}\"} $(date +%s)"
} | curl --data-binary @- \
  "${PUSHGATEWAY_URL:-http://pushgateway:9091}/metrics/job/edge-audit/service/{@ service_slug @}/overlay/${OVERLAY}"
```

`ENABLED_0_OR_1` is `1` only if Step 2 AND Step 3 both PASSed for that
overlay (component wired in AND annotation valid) — Step 4's Terraform
resolution check does not gate this value, since it degrades to SKIP
without cloud credentials and a SKIP must not read as "unprotected."

## Step 5 — Produce summary (AUTO, 30s)

```text
# Edge Audit — {service-name} — {date}

Summary: 2 PASS / 1 FAIL / 1 WARN / 0 SKIPPED

## Failures (require CONSULT via /edge-setup)
- gcp-prod: no `components:` entry for edge-gcp in kustomization.yaml
  Fix: /edge-setup --overlay gcp-prod --cloud gcp

## Warnings
- gcp-staging: no edge component wired (acceptable pre-prod, confirm
  before promoting)

## Passed
- aws-prod: edge-aws wired, annotation=aws-waf, ACL resolves in AWS
```

Append one `AuditEntry` (operation: `edge_audit`) to `ops/audit.jsonl`
via `common_utils.agent_context.AuditLog`, same as `rule-audit`. A run
with any FAIL sets `result: halted`.

## Step 6 — Remediation plan (CONSULT)

For each FAIL, propose the MINIMAL fix (usually: run `/edge-setup` for
that overlay) and wait for operator approval. This skill never invokes
`/edge-setup` itself — audit and remediation are deliberately separate
verbs (ADR-042 §2.2), the same separation `ci-green-verify` draws
between verifying and re-running.

## What this skill is NOT

- **Not a WAF rule-quality reviewer** — it confirms a WAF/rate-limit
  exists and is wired correctly; it does not evaluate whether the
  specific Cloud Armor rules or WAFv2 rule groups chosen are
  well-tuned. That is a security-engineering judgment call, not a
  structural check.
- **Not `security-audit`** — `security-audit`'s scope is broader
  (secrets, image signing, IAM); `edge-audit` is scoped narrowly to
  D-38 the same way `rule-audit`'s `--subset` flags scope to one
  domain at a time.
- **Not a live traffic/WAF-hit analyzer** — reading actual blocked/
  allowed request counts is the edge Grafana dashboard's job (Wave B3
  of ADR-042), not this skill's.

## Invariants

- Audit is READ-ONLY. The agent MUST NOT wire a component or apply
  Terraform while in `scan` mode.
- Every FAIL is evidence-backed (file:line, or a resolved/unresolved
  cloud resource name) — never "might be missing."
- A production overlay (`*-prod`) with no edge component is ALWAYS a
  FAIL, never a WARN — the WARN tier exists only for dev/staging.
- The audit log entry is ALWAYS created, even when every check passes.
- Step 4b's Pushgateway push is ALWAYS attempted for every overlay
  audited, PASS or FAIL — `dashboard-edge.json`'s coverage panel and the
  heartbeat alert both depend on a recent push existing regardless of
  the verdict.

## Related

- `agentic/rules/17-edge-protection.md` — the invariants this skill checks
- `agentic/workflows/edge-setup.md` — the CONSULT-mode remediation workflow
- `docs/decisions/ADR-042-native-cloud-edge-protection.md`
- `agentic/skills/rule-audit/SKILL.md` — the general-invariant precedent
  this skill's structure follows for one specific domain
- `agentic/skills/cost-audit/SKILL.md` — the Pushgateway-push pattern
  Step 4b mirrors
- `templates/service/monitoring/grafana/dashboard-edge.json` — consumes
  the metrics Step 4b pushes
- `common_utils/agent_context.py::AuditLog` — audit trail integration
