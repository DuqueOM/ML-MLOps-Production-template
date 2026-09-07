# Runbook: Scheduled Secret Rotation

**Pairs with**: `agentic/skills/secret-breach-response/SKILL.md` (for
emergency rotation after a leak) and `agentic/workflows/secret-breach.md`.

This runbook covers **scheduled** rotation — the quarterly / biannual
exercise where no leak has occurred but credentials must be rotated to
comply with policy. It is less chaotic than the emergency path but
shares the same invariants.

## Scope

Scheduled rotation applies to:

| Credential | Frequency | Source |
| --- | --- | --- |
| AWS IRSA role trust policy | quarterly | Terraform `aws_iam_role` |
| GCP Workload Identity pool | quarterly | Terraform `google_iam_workload_identity_pool` |
| MLflow Tracking token | quarterly | AWS Secrets Manager / GCP Secret Manager |
| Feature-store read credentials | biannually | Secrets Manager |
| Third-party API keys (payment, email) | monthly if issuer supports, else quarterly | Secrets Manager |
| GitHub `GH_TOKEN` for CI | annually | GitHub Fine-grained PAT |
| Cosign signing identity (OIDC) | N/A — short-lived | GitHub OIDC provider |

Static AWS/GCP **user** credentials are NEVER in scope — D-18 forbids
them. If you find any in scope, escalate to `/secret-breach`.

## Authorization

**STOP** — every rotation requires human approval. Even in dev, the
agent proposes the exact commands and waits for operator confirmation.
Rationale: a botched rotation causes outages equivalent to (or worse
than) a breach.

## Pre-flight checklist

Before starting:

- [ ] Confirm the rotation calendar entry — this is the scheduled run,
      not an ad-hoc request
- [ ] Review `ops/audit.jsonl` for recent `secret_rotation` or
      `rollback` entries — if < 7 days, postpone (stability window)
- [ ] Verify the on-call owner is available for the rotation window
- [ ] Notify the team in the operations channel (not public)

## Procedure (per credential)

### Step 1 — Create the new credential (CONSULT)

Example for MLflow token:

```bash
# Generate new token out-of-band (via MLflow admin UI or IdP)
NEW_TOKEN=$(mlflow-admin token create --service=ml-template --expires=90d)

# Store in secret manager — DO NOT put in env or files
gcloud secrets versions add mlflow-tracking-token \
  --project="${PROJECT}" \
  --data-file=<(echo -n "$NEW_TOKEN")

# or AWS:
aws secretsmanager update-secret \
  --secret-id mlflow-tracking-token \
  --secret-string "$NEW_TOKEN" \
  --region "${AWS_REGION}"
```

New secret version is created; the OLD version stays intact so
rollback is one CLI call away.

### Step 2 — Canary — roll one pod (CONSULT)

Trigger a rolling restart on ONE replica to pick up the new secret
version (CSI driver or env-from-secretRef):

```bash
kubectl rollout restart deployment/{service}-predictor -n dev
kubectl rollout status deployment/{service}-predictor -n dev --timeout=5m
```

Verify:

```bash
# Health probes green
kubectl get pods -l app={service} -n dev
# No credential errors in logs
kubectl logs -l app={service} -n dev --tail=100 | grep -iE "auth|token|unauthorized"
# Test call
curl -sf http://{service}.dev.internal/ready
```

### Step 3 — Propagate to staging, then prod (STOP per env)

Each env is independent — the operator approves staging AFTER dev is
stable for ≥ 15 min; approves prod AFTER staging is stable for ≥ 1 h.

```text
[AGENT MODE: STOP]
Operation: Rotate MLflow token in STAGING
Rationale: Dev validated 27 min ago, no auth errors in logs, health
probes green. Waiting for: {on-call owner} approval.
```

### Step 4 — Retire the old version (CONSULT, after 7-day soak)

Keep the OLD secret version available for 7 days to allow emergency
rollback. After that:

```bash
# GCP — disable, don't delete (history retention)
gcloud secrets versions disable <VERSION> --secret=mlflow-tracking-token

# AWS — version history expires by default after 30 days
```

### Step 5 — Update Terraform state if infra-level creds (STOP)

For IRSA trust-policy or WI pool rotation, the change is in `*.tf`
and MUST go through the GitHub PR + `terraform plan/apply` path:

```bash
# PR workflow only — NO local apply in prod
gh pr create -B main -H rotate/iam-$(date +%Y%m)-$(git rev-parse --short HEAD) \
  -t "rotate: scheduled Q{N} IRSA rotation" \
  -b "Scheduled rotation per runbook. Plan output attached."
```

Environment Protection Rules on `aws-production` gate the apply.

### Step 6 — Audit entry (AUTO)

The rotation skill appends to `ops/audit.jsonl`:

```json
{"agent":"runbook","operation":"secret_rotation","environment":"production","mode":"STOP","result":"success","approver":"<name>","inputs":{"secret":"mlflow-tracking-token","reason":"scheduled Q2"},"outputs":{"new_version":"projects/.../secrets/.../versions/12"},"timestamp":"..."}
```

This feeds the DORA script (`ops/dora/`) — scheduled rotations do NOT
count as failures; they are normal ops.

## Rollback — if Step 2 fails

Immediate, within 5 min:

```bash
# Point the secret reference back to the PREVIOUS version
gcloud secrets versions enable <PREVIOUS>  --secret=mlflow-tracking-token
gcloud secrets versions disable <CURRENT>   --secret=mlflow-tracking-token

# Restart to pick up the reverted secret
kubectl rollout restart deployment/{service}-predictor -n <env>
```

If symptoms persist, invoke `/rollback` skill (the deploy-level one)
— the problem may not be the credential.

## Invariants

- **Never** commit the new secret to git, `.env`, tfvars, or chat.
- **Never** email the new secret, even encrypted.
- **Always** keep the previous version intact for ≥ 7 days.
- **Always** test in dev before staging, staging before prod — no
  skipping envs (same discipline as deploys, ADR-011).
- Rotation requires STOP mode in every env including dev — the blast
  radius is "every pod loses auth simultaneously", not "my laptop".

## Calendar

Template default cadence (override per deployment):

- Q1 (Mar): MLflow token, third-party API keys
- Q2 (Jun): IRSA trust policies, WI pools
- Q3 (Sep): MLflow token, feature-store read credentials
- Q4 (Dec): Third-party API keys, GitHub PATs

## Related

- `agentic/skills/secret-breach-response/SKILL.md` — emergency path
  when a secret is LEAKED (different: blast-radius is bigger, faster)
- `agentic/workflows/secret-breach.md` — /secret-breach slash command
- `agentic/rules/12-security-secrets.md` — D-17/D-18 invariants
- AGENTS.md §Audit Trail Protocol — where rotation entries live
