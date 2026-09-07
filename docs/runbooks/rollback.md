# Rollback Runbook (P1 — STOP-class operation)

> **Authorization mode**: STOP. Rollback is a STOP-class operation per
> AGENTS.md (production state mutation). Execute only with explicit human
> authorization (PagerDuty primary on-call OR tech lead OR security
> on-call for compliance-related rollbacks).

## When to use this runbook

Trigger rollback when ANY of these fire:

- `*ServiceDown` or `*HighErrorRate` Alertmanager alert (P1).
- SLO burn-rate `*_SLO_AvailabilityBurnRateCritical` fires (P1) AND a deploy
  occurred in the last 30 minutes.
- Champion/Challenger online analysis (Argo Rollouts AnalysisRun) fails on
  any of the 4 proxy metrics during canary.
- Manual operator review during release (`/release` workflow §"Smoke check").
- Tech lead override after a deploy that breached an unstated invariant
  (e.g., regulatory data leakage, unexpected PII surface).

## Pre-flight (≤ 60 s — do NOT skip)

```bash
# 1. Identify last healthy deployment id and the previous image digest.
#    The audit log is the source of truth (NOT MLflow, NOT GitHub Releases).
jq -r 'select(.operation | startswith("deploy") and .result == "success")
       | "\(.timestamp)  \(.environment)  \(.outputs.image_digest)  \(.outputs.deployment_id)"' \
   ops/audit.jsonl | tail -10

# 2. Confirm there is no active canary still progressing.
kubectl -n "<service>-prod" get rollouts.argoproj.io <service>-predictor -o jsonpath='{.status.phase}{"\n"}'
# Expected before rollback: "Paused" (canary stalled) or "Healthy" (steady-state)

# 3. Capture the current state for the post-mortem BEFORE you mutate anything.
kubectl -n "<service>-prod" get deploy/<service>-predictor -o yaml > /tmp/pre-rollback-deploy.yaml
kubectl -n "<service>-prod" describe rollout.argoproj.io <service>-predictor > /tmp/pre-rollback-rollout.txt
```

## Procedure

### Path A — Argo Rollouts canary in progress (preferred)

```bash
# 1. Abort the in-flight rollout — Argo restores the stable replica set.
kubectl -n "<service>-prod" argo rollouts abort <service>-predictor
kubectl -n "<service>-prod" argo rollouts status <service>-predictor --watch
#    Wait for `Phase: Healthy, Status: ✓ Healthy`. ETA: 1-3 min.

# 2. Verify traffic flipped back to the stable revision.
curl -sf https://<service>.<env>.example.com/ready | jq .
#    Expect HTTP 200 + body {"status":"ready","model_loaded":true,"warmed_up":true}

# 3. Smoke /predict against a known-good payload.
curl -sf -X POST https://<service>.<env>.example.com/predict \
  -H 'Content-Type: application/json' \
  -d @docs/runbooks/fixtures/known-good-payload.json | jq .
#    Expect HTTP 200 + prediction_score in [0,1].
```

### Path B — Plain Deployment rollback (no Argo Rollouts)

```bash
# 1. List recent revisions (most recent first).
kubectl -n "<service>-prod" rollout history deployment/<service>-predictor

# 2. Roll back to the previous revision (or a specific REV from history).
kubectl -n "<service>-prod" rollout undo deployment/<service>-predictor
#    Or, to a specific revision:
#    make rollback REV=<N>

# 3. Wait for the rollout to finish.
kubectl -n "<service>-prod" rollout status deployment/<service>-predictor --timeout=5m

# 4. Smoke /ready + /predict (same as Path A step 2/3).
```

### Path C — Argo Rollouts already aborted but pod stuck

```bash
# Force-delete the stuck pod; the stable RS will recreate.
kubectl -n "<service>-prod" delete pod -l app=<service>,rollouts-pod-template-hash=<canary-hash>
```

## Verification (≤ 5 min — must all pass before declaring rollback complete)

| Check | Command | Expected |
| ------- | --------- | ---------- |
| Pods Ready | `kubectl -n "<service>-prod" get pods -l app=<service>` | All `1/1 Running`, AGE ≥ 2 min |
| `/ready` returns 200 | `curl -sf https://<service>.<env>.example.com/ready -o /dev/null -w '%{http_code}'` | `200` |
| `/predict` returns 200 | (see Path A step 3) | HTTP 200 + valid `prediction_score` |
| Error rate < 1 % | Grafana `<service>` dashboard, panel "5xx rate" | flat near zero |
| P95 latency < SLO | Grafana, panel "p95 latency /predict" | < 500 ms (or service-specific SLO) |
| Audit entry written | `tail -1 ops/audit.jsonl` | `{"agent":"Agent-K8sBuilder","operation":"<env>-rollback","result":"success",...}` |

## Audit + comms (do NOT skip — STOP-class operation)

```bash
# 1. Append rollback entry to the audit log.
python scripts/audit_record.py \
  --agent "Agent-K8sBuilder" \
  --operation "rollback-<env>" \
  --environment "production" \
  --base-mode "STOP" --final-mode "STOP" \
  --result "success" \
  --inputs  "$(jq -nc --arg svc <service> --arg trigger '<alert-name|operator>' '{service:$svc, trigger:$trigger}')" \
  --outputs "$(jq -nc --arg from_digest <bad-digest> --arg to_digest <restored-digest> --arg revision <N> '{from_digest:$from_digest, to_digest:$to_digest, revision:$revision}')" \
  --approver "<github-handle-of-on-call>"

# 2. Open a P1 incident issue (mandatory for prod rollbacks).
gh issue create --label incident,P1,rollback \
  --title "Rollback: <service> <env> @ $(date -u +%FT%TZ)" \
  --body "$(cat <<EOF
**Trigger**: <alert-name | operator-initiated>
**Bad image digest**: \`<digest>\`
**Restored image digest**: \`<digest>\`
**Pre-rollback evidence**: \`/tmp/pre-rollback-deploy.yaml\`, \`/tmp/pre-rollback-rollout.txt\`
**Verification**: see runbook table above; all 6 checks green at $(date -u +%FT%TZ).
**Next steps**: post-mortem within 48 h (use \`docs/incidents/EXAMPLE.md\` as scaffold).
EOF
)"

# 3. Notify #ml-incidents (Slack, PagerDuty) with link to the issue.
```

## Exit criteria

Rollback is COMPLETE when:

1. All 6 verification checks above are GREEN for ≥ 10 minutes.
2. Audit entry is in `ops/audit.jsonl` AND visible in the GitHub Actions run summary.
3. P1 issue is opened AND tagged `rollback`.
4. The PR / tag that introduced the bad release is reverted OR has a
   linked issue blocking re-promotion until root cause is fixed.

## Post-rollback obligations (within 48 h)

- Incident post-mortem in `docs/incidents/<YYYY-MM-DD>-<service>-rollback.md`
  (template: `docs/incidents/EXAMPLE.md`).
- If the bad release introduced a model regression: open a retrain issue
  blocked by the post-mortem.
- If the bad release introduced a security regression: chain to
  `/secret-breach` workflow even if no secret was leaked, so the
  audit-trail invariant fires.

## Anti-patterns (DO NOT)

- ❌ Don't `kubectl delete deployment` — that drops the audit trail.
- ❌ Don't roll back by editing the image tag in the manifest manually
  (digest pinning is the contract; manual edits bypass Kyverno
  verification).
- ❌ Don't skip the audit step "because it was urgent" — that's exactly
  when it matters most.
- ❌ Don't close the P1 issue until the post-mortem is published.
