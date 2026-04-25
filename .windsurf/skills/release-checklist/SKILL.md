---
name: release-checklist
description: Full release checklist for multi-cloud deployment (GCP + AWS)
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(docker:*)
  - Bash(kubectl:*)
  - Bash(gh:*)
  - Bash(curl:*)
when_to_use: >
  Use when preparing a version release to production across GCP and AWS.
  Examples: 'release v1.2.0', 'prepare production release', 'deploy new version',
  'multi-cloud release'
argument-hint: "<version-tag> [service-name]"
arguments:
  - version-tag
---

# Release Checklist

## Pre-Release Verification

### Code Quality
- [ ] All CI checks passing (lint, test, build)
- [ ] Coverage >= 90% lines, >= 80% branches
- [ ] No TODO/FIXME items in critical paths
- [ ] Type hints on all public functions

### Model Quality
- [ ] Quality gates passing for all services
- [ ] Fairness checks passed (DIR >= 0.80)
- [ ] SHAP consistency verified
- [ ] No data leakage detected

### Infrastructure
- [ ] Terraform plan shows no unexpected changes
- [ ] tfsec/checkov clean (no HIGH/CRITICAL findings)
- [ ] Secrets rotated if approaching expiry

### Documentation
- [ ] ADRs up to date for any new decisions
- [ ] Service READMEs updated with new metrics
- [ ] AGENTS.md updated if new invariants
- [ ] CHANGELOG.md updated

## Version Tagging

```bash
# Update version
export VERSION=v{MAJOR}.{MINOR}.{PATCH}

# Tag and push
git tag -a ${VERSION} -m "Release ${VERSION}: {summary}"
git push origin ${VERSION}
```

## Build and Push Images

```bash
# For each service
for SERVICE in service-a service-b service-c; do
  # GCP Artifact Registry
  docker build -t ${GCP_REGISTRY}/${SERVICE}:${VERSION} ${SERVICE}/
  docker push ${GCP_REGISTRY}/${SERVICE}:${VERSION}

  # AWS ECR
  docker build -t ${AWS_REGISTRY}/${SERVICE}:${VERSION} ${SERVICE}/
  docker push ${AWS_REGISTRY}/${SERVICE}:${VERSION}
done
```

## Deploy to GCP

```bash
# Update overlays
# k8s/overlays/gcp/kustomization.yaml → newTag: ${VERSION}
kubectl apply -k k8s/overlays/gcp/
kubectl rollout status deployment --all -n {namespace} --timeout=300s
```

## Deploy to AWS

```bash
# Update overlays
# k8s/overlays/aws/kustomization.yaml → newTag: ${VERSION}
kubectl apply -k k8s/overlays/aws/
kubectl rollout status deployment --all -n {namespace} --timeout=300s
```

## Post-Deploy Verification

### Both Clouds
- [ ] `/health` returning 200 on all services
- [ ] `/predict` returning valid predictions
- [ ] `/metrics` being scraped by Prometheus
- [ ] Grafana dashboards showing new version
- [ ] No P1/P2 alerts in AlertManager
- [ ] HPA functioning (correct replica counts)

### Smoke Tests

Smoke tests run **inside** the deploy chain via `deploy-common.yml`
(canonical SSOT). Each environment job invokes the smoke test step
against the freshly-deployed pods; failure halts the chain.

```bash
# Manual invocation (one service, one cloud) for debugging:
kubectl --context=$CLUSTER -n $NAMESPACE port-forward svc/$SERVICE 8000:8000 &
curl -fsS http://localhost:8000/health    # liveness
curl -fsS http://localhost:8000/ready     # readiness (gates traffic)
curl -fsS -X POST http://localhost:8000/predict \
     -H 'content-type: application/json' \
     -d "$(cat tests/fixtures/smoke_payload.json)"
kill %1
```

For a multi-service / multi-cloud sweep, drive the loop from a
runbook page or a CI workflow-dispatch — the template does not ship
a `scripts/smoke_test.py` script (would compete with `deploy-common.yml`
as SSOT).

## Rollback Plan

If any issue detected within 30 minutes:
```bash
# Rollback all services
kubectl rollout undo deployment --all -n {namespace}
kubectl rollout status deployment --all -n {namespace}
```

## Post-Release

- [ ] Update CHANGELOG.md with release notes
- [ ] Close related GitHub Issues
- [ ] Update cost projections if resource changes
- [ ] Schedule next drift detection run
