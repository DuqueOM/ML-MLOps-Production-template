# Release Checklist — {ServiceName}

Use this checklist before every production release. Copy to an issue or PR description.

---

## Pre-Release

- [ ] All quality gates pass (primary metric, secondary metric, fairness DIR >= 0.80)
- [ ] No data leakage detected (suspiciously high metrics investigated)
- [ ] SHAP values computed in original feature space
- [ ] Coverage >= 90% lines, >= 80% branches
- [ ] All anti-patterns checked (D-01 through D-12)
- [ ] ADR created for any non-trivial decisions
- [ ] CHANGELOG.md updated with release notes
- [ ] Version bumped in pyproject.toml / requirements.txt

## Model Artifacts

- [ ] Model trained on latest validated dataset
- [ ] Model artifact uploaded to GCS/S3 (not baked into Docker image)
- [ ] Model metadata (metrics, hash, training date) recorded in MLflow
- [ ] SHA256 integrity hash matches between training and serving
- [ ] `promote_model.sh` quality gates passed

## Docker

- [ ] Multi-stage build, non-root USER
- [ ] HEALTHCHECK instruction present
- [ ] No model artifacts in image (init container pattern)
- [ ] `uvicorn --workers 1` (single worker, HPA handles scale)
- [ ] Image tagged with immutable version (never overwrite)
- [ ] Trivy/Snyk scan passes (no critical/high CVEs)

## Kubernetes

- [ ] `kubectl config current-context` verified (correct cluster)
- [ ] HPA uses CPU-only metric (never memory)
- [ ] Init container downloads correct model version
- [ ] NetworkPolicy applied
- [ ] RBAC (Role + RoleBinding) applied
- [ ] ServiceAccount with Workload Identity / IRSA configured
- [ ] Resource requests/limits set appropriately

## Infrastructure

- [ ] Terraform state is remote (GCS for GCP, S3+DynamoDB for AWS)
- [ ] No secrets in tfvars or repository
- [ ] `terraform plan` shows expected changes only
- [ ] tfsec + Checkov pass

## CI/CD

- [ ] CI pipeline green (lint + test + build + scan)
- [ ] Deploy workflow targets correct environment
- [ ] Smoke test passes after deployment
- [ ] Rollback plan documented

## Monitoring

- [ ] Prometheus alerts configured (P1-P4)
- [ ] Drift detection CronJob running
- [ ] Drift heartbeat alert active (fires if CronJob missing > 48h)
- [ ] Grafana dashboard deployed
- [ ] `/health` and `/metrics` endpoints responding

## Post-Release

- [ ] Smoke test in production environment
- [ ] Drift detection baseline updated if data distribution changed
- [ ] GitHub Release published with notes from CHANGELOG
- [ ] Team notified of release

---

## Multi-Cloud Verification

### GCP (GKE)

- [ ] Artifact Registry image pushed
- [ ] Workload Identity binding verified
- [ ] GCS model bucket accessible from pod
- [ ] `kubectl apply -k k8s/overlays/gcp-production/`

### AWS (EKS)

- [ ] ECR image pushed
- [ ] IRSA role binding verified
- [ ] S3 model bucket accessible from pod
- [ ] `kubectl apply -k k8s/overlays/aws-production/`
