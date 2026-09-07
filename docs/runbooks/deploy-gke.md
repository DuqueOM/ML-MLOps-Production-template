# Deploy to GKE Runbook

> **Authorization mode**: AUTO (dev) → CONSULT (staging) → STOP (prod).
> Production promotion REQUIRES the audit trail, the signed image digest,
> the SBOM attestation, and Kyverno admission acceptance.

## When to use this runbook

Promoting a `{service}-predictor` image through `gcp-dev → gcp-staging →
gcp-prod` via the `Deploy — GCP` workflow (`.github/workflows/deploy-gcp.yml`).

## Pre-flight (≤ 5 min)

```bash
# 1. Identify the image digest you intend to deploy.
gh run view <run_id_of_build> --log | grep "image_digests=" | tail -1
#    Expect: {"<service-name>":"sha256:abc...123"}

# 2. Verify the signature + SBOM attestation are present in Rekor.
cosign verify \
  --certificate-identity-regexp "https://github.com/<ORG>/<REPO>/.github/workflows/(ci|deploy-gcp)\\.yml@.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  <region>-docker.pkg.dev/<project>/ml-images/<service-name>-predictor@sha256:<digest>

cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp "https://github.com/<ORG>/<REPO>/.github/workflows/(ci|deploy-gcp)\\.yml@.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  <region>-docker.pkg.dev/<project>/ml-images/<service-name>-predictor@sha256:<digest>
#    Both must exit 0; if either fails, STOP and chain to /secret-breach.

# 3. Confirm the kubectl context is the intended cluster — D-31 invariant.
kubectl config current-context
#    For prod, this MUST be the prod cluster (not staging, not dev).
```

## Procedure

### Dev (AUTO — auto-deploys on push to main)

```bash
# Triggered automatically by deploy-gcp.yml on every push to main.
# Manual re-run:
gh workflow run deploy-gcp.yml --ref main
gh run watch
#    Expect job sequence: build → deploy-dev (no reviewers).
```

### Staging (CONSULT — 1 reviewer via GitHub Environment Protection)

```bash
# Same workflow continues automatically after dev. The Environment
# Protection Rule on `gcp-staging` requires 1 reviewer to approve.
gh run view <run_id> --json url --jq .url
#    Open the URL → "Review pending deployments" → Approve gcp-staging.
```

Verification after staging deploy:

```bash
kubectl --context <staging-context> -n "<service-name>-staging" rollout status \
  deployment/<service-name>-predictor --timeout=10m
curl -sf https://<service>.staging.example.com/ready
curl -sf -X POST https://<service>.staging.example.com/predict \
  -H 'Content-Type: application/json' \
  -d @docs/runbooks/fixtures/known-good-payload.json | jq .prediction_score
```

### Production (STOP — 2 reviewers + 5 min wait + tag-only)

Requires a `v*` tag (D-26). Pushes to `main` STOP at staging.

```bash
# Cut the release tag.
git tag -a v0.16.0 -m "Release v0.16.0: <summary>"
git push origin v0.16.0

# Watch the workflow.
gh run watch
#    Sequence: build → deploy-dev → deploy-staging (1 reviewer) →
#              deploy-prod (2 reviewers + 5 min wait timer).
```

Two reviewers are required by the GitHub Environment Protection Rule.
With a single CODEOWNER (see `.github/CODEOWNERS` maintainership note),
the second reviewer must be a peer-team handle outside the template
ownership chain.

### Verification (≤ 10 min after prod deploy)

| Check | Command | Expected |
| ------- | --------- | ---------- |
| Pods Ready | `kubectl --context <prod> -n "<service-name>-prod" get pods -l app=<service-name>` | `1/1 Running` for all replicas |
| Image digest matches | `kubectl --context <prod> -n "<service-name>-prod" get deploy <service-name>-predictor -o jsonpath='{.spec.template.spec.containers[0].image}'` | Ends in `@sha256:<expected-digest>` |
| Kyverno admitted | `kubectl --context <prod> get policyreport -n "<service-name>-prod"` | No `Fail` results for the new pod |
| `/ready` returns 200 | `curl -sf https://<service>.example.com/ready` | `{"status":"ready",...}` |
| `/predict` returns 200 | (see above) | HTTP 200 + valid `prediction_score` |
| Error rate < 1% | Grafana `<service>` dashboard | flat near zero for ≥ 10 min |
| Drift heartbeat alive | `kubectl --context <prod> get cronjob -n "<service-name>-prod" <service-name>-drift-detection` | `LAST SCHEDULE` within last 24 h |
| Audit entry | `tail -1 ops/audit.jsonl` | `"operation":"gcp-production-deploy","result":"success"` |
| Model signature verified | `kubectl --context <prod> -n "<service-name>-prod" logs deploy/<service-name>-predictor -c model-verifier` | `[model-verifier] OK: model signature verified.` |

### Model signature verification (init container)

Production pods run a `model-verifier` init container that calls
`cosign verify-blob` against the model artifact downloaded by
`model-downloader`. The verifier matches the signing identity to:

```text
--certificate-identity-regexp "https://github.com/<ORG>/<REPO>/.github/workflows/retrain-service\.yml@.*"
--certificate-oidc-issuer    "https://token.actions.githubusercontent.com"
```

Modes (`MODEL_SIGNATURE_VERIFY` env var):

- `warn` (base default): missing signature emits a warning and the
  pod still starts. Used in dev / staging unless explicitly raised.
- `true` / `enforce` (gcp-prod overlay default): missing signature
  OR signature mismatch FAILS the init container, the pod stays in
  `Init:Error`, the deploy never serves traffic.

If the verifier fails:

1. Check `kubectl logs <pod> -c model-verifier` for the cosign error.
2. If "no matching signatures": the model in the bucket was not produced
   by this repo's `retrain-service.yml`. Treat as `secret-breach.md`
   trigger — run that runbook and rotate any model-bucket credentials.
3. If "signature missing": the `Sign model with cosign` step in the
   retrain workflow failed silently. Re-run retrain with verbose
   logging.

## Exit criteria

Deploy is COMPLETE when:

1. All 8 verification checks above are GREEN for ≥ 10 min.
2. Audit entry is in `ops/audit.jsonl` AND in the workflow's GitHub Actions step summary.
3. Release notes mention the digest, tag, and approver.
4. The `v*` tag annotation matches the deploy actor and timestamp.

## Failure paths

- **Kyverno rejects the pod**: image is unsigned or SBOM missing → STOP, chain to `secret-breach.md` if signing key was
  compromised, otherwise fix the build pipeline.
- **`/ready` stays 503 past 5 min**: warm-up is failing → `kubectl logs` for the SHAP / model-load error; if persistent,
  run `rollback.md`.
- **Smoke `/predict` returns 5xx**: `rollback.md` Path A immediately.
- **2-reviewer requirement cannot be met**: see `.github/CODEOWNERS` maintainer note; do NOT bypass.

## Anti-patterns

- ❌ Do NOT `kubectl set image` manually — bypasses Kyverno digest verification.
- ❌ Do NOT push images to `:latest` — admission policy rejects.
- ❌ Do NOT skip the staging environment for "urgent fixes" — D-26.
- ❌ Do NOT close the deploy issue before the audit entry is written.
