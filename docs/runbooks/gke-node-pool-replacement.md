# Runbook — replacing a GKE node pool without downtime

**When you need this**: `terraform plan` shows `google_container_node_pool`
being **replaced** rather than updated.
**Mode**: CONSULT — the naive path reschedules every workload on the pool.
**Related**: ADR-017 §Amendment (the change that made this necessary), D-27
(PodDisruptionBudget), `docs/runbooks/day-2-operations.md`

## Why this exists

Several `node_config` attributes are replace-forcing in the Google provider:
`service_account`, `machine_type`, `disk_size_gb`, `image_type`, `oauth_scopes`.
Change one and Terraform destroys the pool and creates a new one.

The 2026-09-05 identity change (`service_account`, `image_type`) is exactly
that. `MIGRATION.md` warns about it, and a warning is not a procedure — this
is the procedure.

**What `terraform apply` does on its own**: destroys the old pool, then
creates the new one. Every pod on that pool dies at once, and nothing runs
there until the new nodes register and pods reschedule. On a single-pool
cluster that is a full outage; on this template's two-pool layout it is an
outage of whatever the affected pool carried. PodDisruptionBudgets do **not**
protect you here — a pool deletion is not an eviction, and the budget has no
node left to keep the pod on.

## Pre-flight

1. **Confirm you are on the right cluster.**

   ```bash
   kubectl config current-context
   ```

2. **Confirm PodDisruptionBudgets exist** (D-27). They do not prevent the
   outage the naive path causes, but they are what makes the *drain* in step 3
   safe.

   ```bash
   kubectl get pdb -A
   ```

3. **Confirm you have capacity headroom.** The blue/green procedure runs both
   pools at once, so the project needs quota for double the nodes for the
   duration.

   ```bash
   gcloud compute project-info describe --project "$PROJECT_ID" \
     --format="value(quotas.filter(metric:CPUS).limit,quotas.filter(metric:CPUS).usage)"
   ```

4. **Read the plan.** Confirm what is being replaced and why:

   ```bash
   terraform plan -out=tfplan
   terraform show -json tfplan | jq -r '
     .resource_changes[]
     | select(.change.actions | index("delete"))
     | "\(.address): \(.change.actions | join(","))"'
   ```

## Procedure — blue/green

The idea: stand up the new pool, move work onto it, then remove the old one.
Terraform never holds the cluster in a state with no nodes.

### 1. Add the new pool alongside the old

Copy the pool block, give it a new resource name and a new `name`, and apply
the attribute change **only on the copy**:

```hcl
resource "google_container_node_pool" "workload_v2" {
  name = "${var.project_name}-workload-pool-v2"
  # ... identical to `workload`, plus the change you are making
}
```

```bash
terraform apply -target=google_container_node_pool.workload_v2
```

Both pools now exist. Nothing has moved.

### 2. Stop new work landing on the old pool

```bash
OLD_POOL="${PROJECT_NAME}-workload-pool"
kubectl cordon -l cloud.google.com/gke-nodepool="$OLD_POOL"
```

### 3. Drain the old pool, one node at a time

```bash
for node in $(kubectl get nodes -l cloud.google.com/gke-nodepool="$OLD_POOL" \
                -o name); do
  kubectl drain "$node" \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --timeout=300s
done
```

`drain` evicts through the API, so **PodDisruptionBudgets are honoured** —
this is the step they exist for. If a drain stalls, a PDB is doing its job:
find the blocking workload rather than forcing past it.

```bash
kubectl get pdb -A -o json | jq -r '
  .items[] | select(.status.disruptionsAllowed == 0)
  | "\(.metadata.namespace)/\(.metadata.name): 0 disruptions allowed"'
```

### 4. Verify before you delete anything

```bash
kubectl get pods -A -o wide | grep -c "$OLD_POOL"     # expect 0
kubectl get nodes -l cloud.google.com/gke-nodepool="${OLD_POOL}-v2"
make health-check                                      # service-level probe
```

Do not proceed until the workload is healthy **on the new pool**. This is the
last reversible point.

### 5. Remove the old pool

Delete the original resource block, then:

```bash
terraform apply
```

### 6. Rename back (optional, and itself a replacement)

If you want the original name back, that is another replacement and another
run of this runbook. Usually not worth it — prefer leaving the `-v2` suffix
and dropping it at the next genuine pool change.

## Rollback

Before step 5, rollback is `kubectl uncordon` on the old pool and deleting the
new pool block. Work returns to the original nodes.

After step 5 the old pool is gone; recovery is this same procedure in
reverse, from the previous Terraform revision.

## Why the module does not use `create_before_destroy`

Terraform's `create_before_destroy` would automate this — but only with
`name_prefix` instead of `name`, because two pools cannot share a name. That
trade is not obviously worth it:

- pool names become non-deterministic (prefix plus a generated suffix), so
  anything selecting nodes by exact pool name — dashboards, `nodeSelector`,
  cost queries — has to move to labels;
- adopting it is *itself* a replacing change, so it does not help with the
  migration you are reading this for;
- `name_prefix` is capped at 31 characters in google provider v8 (raised from
  14), and `${var.project_name}-workload-pool` exceeds that for many project
  names, which fails at plan time in a way that reads as a length bug rather
  than a design decision.

The explicit procedure above costs one manual run per replacing change and
keeps names, selectors and cost attribution stable. If your cluster changes
node configuration often enough that this is a burden, the calculus flips —
that is the trigger to revisit.

## What has not been verified

**This procedure has not been executed against a live GKE cluster.** The
template does not deploy to a real cloud by design, so the commands are
derived from the provider's replace semantics and standard GKE practice, not
from a recorded run. Treat the first execution as a rehearsal: do it in dev,
time it, and record what actually happened alongside the other drills — the
template ships them at `templates/service/docs/runbooks/drills/`, which in
your scaffolded service is the drills directory under `docs/runbooks/`.

A runbook that has never been run is a hypothesis in the shape of a
procedure.
