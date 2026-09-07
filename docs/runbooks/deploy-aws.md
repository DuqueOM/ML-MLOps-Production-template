# Deploy to AWS (EKS) Runbook

> **Authorization mode**: AUTO (dev) → CONSULT (staging) → STOP (prod).
> Mirror of `deploy-gke.md` for the AWS path. The contract is identical;
> only the cloud-specific commands differ. Read `deploy-gke.md` for the
> rationale and verification matrix; this file lists ONLY the EKS deltas.

## Pre-flight (EKS-specific)

```bash
# 1. Identify the image digest (ECR).
gh run view <run_id_of_build> --log | grep "image_digests=" | tail -1

# 2. Verify cosign signature against the deploy-aws.yml workflow identity.
cosign verify \
  --certificate-identity-regexp "https://github.com/<ORG>/<REPO>/.github/workflows/(ci|deploy-aws)\\.yml@.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  <account>.dkr.ecr.<region>.amazonaws.com/<service-name>-predictor@sha256:<digest>

cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp "https://github.com/<ORG>/<REPO>/.github/workflows/(ci|deploy-aws)\\.yml@.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  <account>.dkr.ecr.<region>.amazonaws.com/<service-name>-predictor@sha256:<digest>

# 3. Confirm the kubectl context is the intended EKS cluster.
aws eks update-kubeconfig --name <cluster-name> --region <region> --alias <env>-eks
kubectl config current-context     # should be <env>-eks
```

## Procedure

The trigger and chain mirror GKE: push to `main` → dev (AUTO), staging (CONSULT, 1 reviewer), `v*` tag → prod (STOP, 2
reviewers + 5 min wait). The IAM identity for each environment is IRSA-federated; no static AWS keys (D-18).

```bash
# Manual trigger:
gh workflow run deploy-aws.yml --ref main

# Tag-driven prod promotion:
git tag -a v0.16.0 -m "Release v0.16.0"
git push origin v0.16.0
gh run watch
```

## Verification (EKS-specific deltas vs deploy-gke.md)

In addition to the 8 checks in `deploy-gke.md`:

| Check | Command | Expected |
| ------- | --------- | ---------- |
| IRSA bound | `kubectl --context <prod> -n "<service-name>-prod" get sa <service-name>-sa -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'` | matches `aws_iam_role.service[<service>].arn` from Terraform |
| ECR pull succeeded | `kubectl --context <prod> -n "<service-name>-prod" describe pod -l app=<service-name>` | no `ImagePullBackOff`, no `ErrImagePull` |
| ALB / NLB targets healthy | `aws elbv2 describe-target-health --target-group-arn <tg-arn>` | all targets `healthy` |

## Exit Criteria

Same as `deploy-gke.md` §"Exit criteria". AWS deploy is COMPLETE when all 8 base checks + the 3 EKS-specific deltas
above are GREEN for ≥ 10 min, the audit entry is in `ops/audit.jsonl`, and the digest-pinned image matches the
`cosign verify` output.

## Failure paths

- **`AccessDenied` on ECR pull**: IRSA role missing `ecr:GetAuthorizationToken` or the OIDC trust policy `sub` doesn't
  match the SA. See `docs/runbooks/aws-irsa-setup.md`.
- **All other failure paths**: identical to `deploy-gke.md`.

## Anti-patterns

Same as `deploy-gke.md`. Plus:

- ❌ Do NOT use long-lived `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — D-18 forbids; use IRSA only.
- ❌ Do NOT mutate the IAM role attached to a running ServiceAccount without rolling restart — pods cache the
  assumed-role token until expiry.
