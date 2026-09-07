---
description: Full multi-cloud release process — build, deploy GCP + AWS, verify, rollback if needed
---

# /release Workflow

## 1. Pre-Release Checks (D-36, ADR-039)

Invoke `/ci-green` (or `agentic/skills/ci-green-verify/SKILL.md` directly)
against the commit being released — check EVERY workflow, not just
`ci.yml`:

```bash
gh run list --branch main --limit 20 \
  --json name,status,conclusion,headSha,workflowName
```

This is a **hard precondition**, not an informational listing: if any
workflow is RED or MISSING for the target commit, STOP here. Do not
continue to step 2 without an explicit human override AND a
`scripts/audit_record.py` entry documenting why (D-36 — same rule whether
the release "feels safe" or not; there is no urgency exception).
// turbo

## 2. Run Full Test Suite

```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=90
```

## 3. Tag the Release

```bash
# Confirm releases/v{VERSION}.md exists first — check_doc_coherence.py C6
python3 scripts/check_doc_coherence.py

git tag -a v{VERSION} -m "Release v{VERSION}: {summary}"
git push origin v{VERSION}
```

Pushing the tag triggers `.github/workflows/release-on-tag.yml`, which
publishes the GitHub Release automatically (title + body from
`releases/v{VERSION}.md`). Do not follow up with a manual
`gh release create`/`edit` — verify instead:

```bash
gh release view v{VERSION}
```

## 4. Build and Push Docker Images (GCP)

For each service in the project:

```bash
docker build -t ${GCP_REGISTRY}/${SERVICE}:v{VERSION} ${SERVICE}/
docker push ${GCP_REGISTRY}/${SERVICE}:v{VERSION}
```

## 5. Build and Push Docker Images (AWS)

```bash
aws ecr get-login-password | docker login --username AWS --password-stdin ${AWS_REGISTRY}
docker build -t ${AWS_REGISTRY}/${SERVICE}:v{VERSION} ${SERVICE}/
docker push ${AWS_REGISTRY}/${SERVICE}:v{VERSION}
```

## 6. Deploy to GKE

```bash
kubectl config use-context ${GKE_CONTEXT}
kubectl apply -k k8s/overlays/gcp-prod/
kubectl rollout status deployment --all -n ${NAMESPACE} --timeout=300s
```

## 7. Smoke Test GCP

```bash
curl -f http://${GCP_ENDPOINT}/health
curl -X POST http://${GCP_ENDPOINT}/predict -H "Content-Type: application/json" -d '${TEST_PAYLOAD}'
```

## 8. Deploy to EKS

```bash
kubectl config use-context ${EKS_CONTEXT}
kubectl apply -k k8s/overlays/aws-prod/
kubectl rollout status deployment --all -n ${NAMESPACE} --timeout=300s
```

## 9. Smoke Test AWS

```bash
curl -f http://${AWS_ENDPOINT}/health
curl -X POST http://${AWS_ENDPOINT}/predict -H "Content-Type: application/json" -d '${TEST_PAYLOAD}'
```

## 10. Post-Deploy Verification

- Check Grafana dashboards show new version
- Check Prometheus scraping all services
- Check AlertManager has no active P1/P2 alerts
- Verify HPA is functioning correctly

## 11. Rollback (if needed)

```bash
# GKE
kubectl config use-context ${GKE_CONTEXT}
kubectl rollout undo deployment --all -n ${NAMESPACE}

# EKS
kubectl config use-context ${EKS_CONTEXT}
kubectl rollout undo deployment --all -n ${NAMESPACE}
```

## 12. Update Documentation

- Update CHANGELOG.md
- Close related GitHub Issues
- Update cost projections if resources changed
