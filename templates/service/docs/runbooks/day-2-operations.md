# Day-2 operations — {@ service_name @}

> Routine, NON-incident operational procedures. For severity-driven
> incident response see `runbook-template.md` (P1–P4 incident playbook).
> For drills see `drills/README.md`.

This runbook is **single-source for both clouds**. Per-cloud commands
are tagged with **GCP** / **AWS** badges in the same table; ADR-015 PR-A4
deliberately rejected the two-runbook split (`CHECKLIST_DAY2_GCP.md`

+ `CHECKLIST_DAY2_AWS.md`) as harder to maintain.

## Audience and cadence

| Procedure | Cadence | Owner |
| ----------- | --------- | ------- |
| Scale up/down | On demand | Service owner |
| Drain a node | Maintenance window | Platform |
| Rotate certificate | Quarterly (cert-manager auto) | Platform |
| Rotate secrets | Quarterly + on-leak | Service owner via `/secret-breach` |
| Drift drill | Quarterly + post-deploy | Service owner |
| Cost spike triage | On alert | Service owner |
| Terraform drift check | Nightly (automated) | Platform |
| Backup verification | Monthly | Platform |
| Model rollback | On `decision=block` from C/C gate | Service owner via `/rollback` |

## Universal preflight

```bash
# Run BEFORE any cluster-touching procedure.
kubectl config current-context           # confirm intended cluster
kubectl get nodes                        # cluster reachable + healthy
kubectl get pods -n {@ service_kebab @}-prod  # service pods running
kubectl version --short                  # client/server version skew
```

If `kubectl config current-context` shows the wrong cluster, **STOP**
and `kubectl config use-context <correct>`. Mis-context is the most
common cause of accidental cross-environment changes.

## Procedure: scale a deployment

```bash
# 1. Inspect current state
kubectl get hpa {@ service_kebab @}-hpa -n {@ service_kebab @}-prod

# 2a. Adjust HPA bounds (preferred — scaling stays autonomic)
kubectl patch hpa {@ service_kebab @}-hpa -n {@ service_kebab @}-prod \
  --type=merge -p '{"spec":{"minReplicas":3,"maxReplicas":15}}'

# 2b. Force a fixed replica count (escape hatch — disables autoscaling temporarily)
kubectl scale deployment/{@ service_kebab @}-predictor -n {@ service_kebab @}-prod --replicas=10

# 3. Verify
kubectl get pods -l app={@ service_kebab @} -n {@ service_kebab @}-prod -w
```

**Invariant**: `replicas >= 2` in prod (PDB enforces). If you need
`replicas=1` for a maintenance window, also patch the PDB —
otherwise drain blocks indefinitely.

## Procedure: drain a node

| Cloud | Node label discovery |
| ------- | ---------------------- |
| **GCP** | `kubectl get nodes -L cloud.google.com/gke-nodepool` |
| **AWS** | `kubectl get nodes -L eks.amazonaws.com/nodegroup` |

```bash
# 1. Cordon (no new pods will land)
kubectl cordon <node-name>

# 2. Drain (existing pods evicted respecting PDB)
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=120 \
  --timeout=10m

# 3. Confirm pods rescheduled
kubectl get pods -l app={@ service_kebab @} -n {@ service_kebab @}-prod -o wide

# 4. After maintenance, uncordon
kubectl uncordon <node-name>
```

**Common failure**: drain hangs because PDB `minAvailable=1` and only
2 replicas are running on this node. Fix by scaling up first
(`kubectl scale ... --replicas=4`), then drain.

## Procedure: certificate rotation

cert-manager auto-rotates 30 days before expiry. Manual force-rotation:

```bash
# Verify cert-manager is healthy first
kubectl get pods -n cert-manager

# Inspect the certificate
kubectl get certificate -n {@ service_kebab @}-prod
kubectl describe certificate {@ service_kebab @}-tls -n {@ service_kebab @}-prod

# Force renewal
kubectl annotate certificate {@ service_kebab @}-tls \
  cert-manager.io/issue-temporary-certificate=true \
  -n {@ service_kebab @}-prod --overwrite

# Watch the new cert get issued (within ~60s)
kubectl get certificate {@ service_kebab @}-tls -n {@ service_kebab @}-prod -w
```

If renewal stalls, see ACME challenge debugging:

```bash
kubectl get challenges --all-namespaces
kubectl describe challenge <name> -n {@ service_kebab @}-prod
```

## Procedure: secret rotation (planned)

> **Unplanned** secret rotation = leak. Use the `/secret-breach`
> workflow instead — it is a STOP-class operation that requires
> human authorization.

| Cloud | Where the secret lives |
| ------- | ------------------------ |
| **GCP** | Secret Manager — `gcloud secrets versions add ...` |
| **AWS** | AWS Secrets Manager — `aws secretsmanager update-secret ...` |

```bash
# 1. Add new version to the secret store (cloud command above)

# 2. Force pod restart so the External Secrets / CSI driver reloads
kubectl rollout restart deployment/{@ service_kebab @}-predictor -n {@ service_kebab @}-prod
kubectl rollout status deployment/{@ service_kebab @}-predictor -n {@ service_kebab @}-prod

# 3. Verify the new version is in use (this assumes you log a hash, not the value)
kubectl logs -l app={@ service_kebab @} -n {@ service_kebab @}-prod --tail=20 | grep secret_version
```

**Invariant** (D-17, D-18): credentials are NEVER in code, NEVER in
env-from-literal, ALWAYS via IRSA (AWS) / Workload Identity (GCP) +
the cloud secret store.

## Procedure: cost spike triage

Triggered by AlertManager `{@ service_kebab @}MonthlyCostBudgetExceeded`
or by manual review.

```bash
# 1. Snapshot current resource consumption
kubectl top pod -l app={@ service_kebab @} -n {@ service_kebab @}-prod
kubectl top node

# 2. Inspect HPA history — has it been pegged at maxReplicas?
kubectl describe hpa {@ service_kebab @}-hpa -n {@ service_kebab @}-prod | tail -20

# 3. Cross-check Prometheus for traffic spike
# Open Grafana → {@ service_name @} dashboard → "Requests/sec" panel
```

| Cloud | Cost API |
| ------- | ---------- |
| **GCP** | `gcloud billing accounts list` + Cost Explorer console |
| **AWS** | `aws ce get-cost-and-usage --time-period Start=...,End=...` |

**Common causes**:

+ HPA pegged at `maxReplicas` due to traffic spike → raise bound or
  investigate if traffic is malicious.
+ Prediction-log backend writing to GCS/S3 with `Standard` storage
  class instead of `Nearline`/`Standard-IA` → see ADR-016 §3.2.
+ Forgotten dev cluster → `terraform destroy` per env after work.

For deeper analysis run the `/cost-review` workflow (monthly cadence).

## Procedure: terraform drift check

Automated nightly via `.github/workflows/terraform-plan-nightly.yml`.
The workflow runs `terraform plan` against `infra/terraform/<cloud>/`,
posts a summary to GitHub Actions, and FAILS if the plan is non-empty
(state has drifted from declared config).

Manual run:

| Cloud | Command |
| ------- | --------- |
| **GCP** | `(cd infra/terraform/gcp && terraform init && terraform plan -no-color)` |
| **AWS** | `(cd infra/terraform/aws && terraform init && terraform plan -no-color)` |

**On non-empty plan**:

1. Inspect the plan output. Distinguish:
   + **Authored drift** (someone changed config but didn't run apply)
     → run `terraform apply` per the change-management process.
   + **Unauthored drift** (state shows resources someone hand-edited
     in the cloud console) → reconcile by either reverting the
     console change OR updating the TF code to match.
2. `terraform apply` is **CONSULT** in staging and **STOP** in prod
   per ADR-015 §"Operation → Mode mapping".

## Procedure: backup verification

Velero (if installed) snapshots PVs nightly. Verify monthly:

```bash
velero backup get
velero backup describe <latest>
velero restore create --from-backup <latest> --restore-volumes=false --dry-run
```

If Velero is not installed, document where the team's backup
mechanism lives (e.g. external CSI snapshots, application-level
state export).

## Procedure: model rollback (operational, not incident)

**Incident** rollback = `/rollback` workflow (STOP-class). This
section is for the rare case where C/C gate said `block` but the
rollback didn't auto-complete (e.g. Argo Rollouts had its own bug).

```bash
# 1. Find the last good revision
kubectl rollout history deployment/{@ service_kebab @}-predictor -n {@ service_kebab @}-prod

# 2. Roll back
kubectl rollout undo deployment/{@ service_kebab @}-predictor -n {@ service_kebab @}-prod \
  --to-revision=<N>
kubectl rollout status deployment/{@ service_kebab @}-predictor -n {@ service_kebab @}-prod

# 3. MLflow side: re-promote the previous model version
python scripts/promote_to_mlflow.py --version <prev_version> --skip-evidence-gate \
  --skip-reason "ROLLBACK: previous model promoted after C/C block on v<N>"
```

The `--skip-evidence-gate` is required because the previous model's
evidence bundle has already been consumed by its original promotion;
re-promotion is metadata-only. The `--skip-reason` is mandatory and
becomes an MLflow tag (PR-B4 contract).

## Cross-references

+ **Incident response** (P1–P4): `runbook-template.md`
+ **Drills** (drift, deploy-degraded): `drills/README.md`
+ **Secret breach** workflow: `/secret-breach`
+ **Rollback** workflow: `/rollback`
+ **Cost review** workflow: `/cost-review`
+ **Architecture decisions**: `docs/decisions/`
+ **AGENTS.md** invariants: D-01 to D-29

## What this runbook does NOT cover

+ **Disaster recovery** (multi-region failover): out of scope per
  ADR-001 calibration for 2-5 service single-team templates.
+ **Multi-cluster federation**: not in template; see Cluster API
  if/when needed.
+ **Compliance evidence collection** (SOC2, HIPAA): organizational,
  not template.
+ **Performance tuning beyond HPA bounds**: see `/load-test`
  workflow for capacity tests.
