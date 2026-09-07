# Secret Breach Runbook (P1 — STOP-class operation)

> **Authorization mode**: STOP. Secret rotation is a STOP-class operation
> per AGENTS.md. Execute only with the security on-call paged and the
> incident commander assigned. Do NOT attempt silent rotation; the
> audit trail is what protects the organization in the post-mortem.

## When to use this runbook

Trigger on ANY of:

- `gitleaks-action` fails on a PR or push (CI step `Self-audit`).
- Hardcoded credential pattern hit by the workflow's `grep -E "AKIA…|AIza…|ghp_…"` step.
- Vendor disclosure (GitHub, AWS, GCP, Anthropic, OpenAI) flags a token leak.
- A pod log or audit entry contains an unredacted secret pattern.
- Internal code review surfaces a hardcoded credential in a merged commit.

The runbook covers the 90 % case (cloud-native credentials). Vault rotation
is out of scope per ADR-001.

## Pre-flight (≤ 2 min — page first, then do this)

1. **Page security on-call IMMEDIATELY** (PagerDuty `mlops-security-pri`).
2. **Capture the hit** without redaction in a private channel only:

   ```bash
   # Where was it found?
   gh run view <run_id> --log | grep -A 3 -B 3 'gitleaks\|AKIA\|AIza\|ghp_' > /tmp/breach-evidence.txt
   chmod 600 /tmp/breach-evidence.txt
   # NEVER paste this into a public issue. Attach to the private incident
   # ticket only.
   ```

3. **Halt the affected pipeline** (do not auto-merge or deploy):

   ```bash
   gh workflow disable validate-templates.yml
   gh workflow disable deploy-gcp.yml
   gh workflow disable deploy-aws.yml
   gh workflow disable retrain-service.yml
   ```

## Procedure

### Step 1 — Revoke at the source (≤ 5 min)

Identify the credential type from the leaked prefix and revoke immediately:

| Pattern | Source | Revoke command |
| --------- | -------- | ---------------- |
| `AKIA[0-9A-Z]{16}` + `wJalrXUt…` (40 chars) | AWS access key | `aws iam delete-access-key --user-name <user> --access-key-id <KEY_ID>` |
| `AIza[0-9A-Za-z_-]{35}` | Google API key | GCP Console → APIs & Services → Credentials → Delete |
| `ghp_[A-Za-z0-9]{36}` or `github_pat_…` | GitHub PAT | github.com/settings/tokens → Revoke |
| `xoxb-…` / `xoxp-…` | Slack token | `https://api.slack.com/apps/<app_id>/oauth` → Revoke |
| `sk-…` (OpenAI) / `sk-ant-…` (Anthropic) | LLM provider | Provider dashboard → Revoke |
| Service account JSON | GCP SA key | `gcloud iam service-accounts keys delete <KEY_ID> --iam-account=<sa>@<project>.iam.gserviceaccount.com` |

Verify revocation:

```bash
# AWS — the next call must return AccessDenied / InvalidAccessKeyId.
AWS_ACCESS_KEY_ID=<leaked> AWS_SECRET_ACCESS_KEY=<leaked> aws sts get-caller-identity
# GCP — the next call must return 403 PERMISSION_DENIED.
curl -H "Authorization: Bearer <leaked>" https://www.googleapis.com/oauth2/v3/tokeninfo
# GitHub PAT — must return 401 Bad credentials.
curl -H "Authorization: token <leaked>" https://api.github.com/user
```

### Step 2 — Rotate in the secret manager (≤ 15 min)

```bash
# AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id <name> \
  --secret-string "$(openssl rand -base64 32)"

# GCP Secret Manager — add a new version, then disable the leaked one.
echo -n "$(openssl rand -base64 32)" | \
  gcloud secrets versions add <name> --data-file=- --project=<project>
gcloud secrets versions disable <leaked-version> --secret=<name> --project=<project>
```

For credentials issued by an external vendor (LLM keys, third-party APIs), follow the vendor's rotation flow and store
the new value in the secret manager — never copy-paste into env vars.

### Step 3 — Force re-deploy of consuming services (≤ 30 min)

```bash
# Restart pods so the projected-volume secret is re-mounted.
kubectl -n "<service>-prod" rollout restart deployment/<service>-predictor
kubectl -n "<service>-prod" rollout status  deployment/<service>-predictor --timeout=5m

# Verify readiness with the new secret in place.
curl -sf https://<service>.<env>.example.com/ready
```

### Step 4 — Scope exposure (≤ 60 min)

Determine where else the leaked credential was used. ALL of these:

```bash
# Cloud audit logs — find every API call made with the leaked key.
# AWS:
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=AccessKeyId,AttributeValue=<KEY_ID> \
  --max-results 200 > /tmp/cloudtrail-leaked-key.json

# GCP:
gcloud logging read \
  "protoPayload.authenticationInfo.principalEmail=\"<sa>@<project>.iam.gserviceaccount.com\"" \
  --project=<project> --freshness=14d --limit=500 > /tmp/gcp-audit-leaked.json

# GitHub:
gh api -H "Accept: application/vnd.github+json" \
  /orgs/<org>/audit-log\?phrase=actor:<user>+created:%3E$(date -u -d -14days +%FT%TZ) \
  > /tmp/gh-audit-leaked.json
```

Run `git log --all -p -S '<token-fragment>'` to find every commit that
ever contained the secret. The `secret-history-scan.md` runbook has the
authoritative procedure if it lived in git history.

### Step 5 — Notify (≤ 2 h)

- File the incident issue (PRIVATE repo if available; otherwise GitHub
  Issue with `incident,P1,security` labels and explicit redaction):

  ```bash
  gh issue create --label incident,P1,security \
    --title "Secret breach: <type> @ $(date -u +%FT%TZ)" \
    --body "See \`/tmp/breach-evidence.txt\` (private channel only)."
  ```

- Notify Security on-call, Platform on-call, Compliance (if regulated industry).
- If the leak was public for any duration, prepare a customer disclosure draft
  using the GDPR/SOC2 templates in `docs/ADOPTION.md` §6.

### Step 6 — Verify rotation (≤ 4 h)

```bash
# Pod is using the NEW secret (compare hash, never compare value).
kubectl -n "<service>-prod" exec deploy/<service>-predictor -- \
  python -c 'import os,hashlib; v=os.getenv("API_KEY",""); print(hashlib.sha256(v.encode()).hexdigest()[:12])'
# Compare against the new secret's sha256 prefix in the secret manager.

# A canary call from a known-good client must succeed.
curl -sf -H "X-API-Key: <new-key-from-secret-manager>" \
  https://<service>.<env>.example.com/predict -d @fixtures/known-good.json
```

### Step 7 — Audit + post-mortem (≤ 48 h)

```bash
python scripts/audit_record.py \
  --agent "Agent-SecurityAuditor" \
  --operation "secret-breach-rotation" \
  --environment "production" \
  --base-mode "STOP" --final-mode "STOP" \
  --result "success" \
  --inputs  "$(jq -nc --arg type '<credential-type>' --arg surface '<git|log|vendor>' '{type:$type, surface:$surface}')" \
  --outputs "$(jq -nc --arg revoked_at $(date -u +%FT%TZ) --arg rotated_at $(date -u +%FT%TZ) '{revoked_at:$revoked_at, rotated_at:$rotated_at, exposure_window_minutes:<N>, blast_radius_summary:"see incident issue"}')" \
  --approver "<security-on-call-handle>"
```

Post-mortem template: `docs/incidents/<YYYY-MM-DD>-secret-breach-<type>.md` (use `docs/incidents/EXAMPLE.md` as
scaffold). Mandatory sections:

1. Timeline (UTC).
2. Detection path (gitleaks / vendor / human / log).
3. Exposure window (first commit / log line → revocation).
4. Blast radius (every API call + scoped resources).
5. Root cause (why was it written? why not caught earlier?).
6. Action items (with owners + due dates).

## Exit criteria

Breach response is COMPLETE when ALL:

1. Credential revoked at source — verified by 401/403 from the leaked credential.
2. New credential active in the secret manager AND consumed by every dependent pod.
3. Cloud audit logs reviewed; blast radius documented.
4. Incident issue + audit entry written.
5. Post-mortem published with action items.
6. Pipelines re-enabled (`gh workflow enable …`) only after Security on-call signs off.

## Anti-patterns (DO NOT)

- ❌ Do NOT rotate silently — the audit trail is the protection.
- ❌ Do NOT paste the leaked secret into a public issue / Slack channel.
- ❌ Do NOT close the issue until the post-mortem and action items are merged.
- ❌ Do NOT re-enable disabled workflows before Step 6 verifies a clean state.
