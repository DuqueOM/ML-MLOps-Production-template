# Terraform Layout — Bootstrap + Live (ADR-015 PR-A2)

Two layers per cloud, applied in order:

```text
infra/terraform/
├── gcp/
│   ├── bootstrap/    ← run ONCE per (project, env)
│   ├── *.tf          ← live layer; run on every infra change
│   └── backend-configs/<env>.hcl
└── aws/
    ├── bootstrap/    ← run ONCE per (account, env)
    ├── *.tf          ← live layer
    └── backend-configs/<env>.hcl
```

## Why two layers

| Concern | Bootstrap | Live |
| --------- | ----------- | ------ |
| Cadence | Once per env (yearly) | Every PR |
| State | LOCAL (chicken-and-egg) | Remote (created by bootstrap) |
| Privilege | `roles/owner` / AdministratorAccess | Least-privilege CI identity |
| Resources | State bucket, KMS, registry, future CI WIF | Workloads (GKE/EKS, IAM, networking) |
| Blast radius | Foundation — destroying breaks everything | Workload — re-runnable |

Mixing them in one plan would require every CI run to authenticate with
foundation-level privilege. The split lets the live layer run with minimal
permissions delegated to it by the bootstrap.

## Bootstrap workflow

### GCP

```bash
cd infra/terraform/gcp/bootstrap

# 1. Authenticate as a project owner (one-time, manual).
gcloud auth application-default login

# 2. Apply per environment.
for ENV in dev staging prod; do
  terraform init -reconfigure
  terraform apply \
    -var="project_id=$YOUR_PROJECT" \
    -var="project_name=$YOUR_NAME" \
    -var="environment=$ENV" \
    -state="terraform.tfstate.$ENV"
done

# 3. Capture outputs into backend-configs/<env>.hcl
terraform output -state="terraform.tfstate.dev" tfstate_bucket
# Paste into ../backend-configs/dev.hcl as `bucket = "..."`

# 4. (Optional) Back up local state to a private bucket.
gsutil cp terraform.tfstate.* gs://your-private-tf-bootstrap-backups/
```

### AWS

```bash
cd infra/terraform/aws/bootstrap

# 1. Authenticate as account admin (one-time, manual).
aws configure  # or `aws sso login`

# 2. Apply per environment.
for ENV in dev staging prod; do
  terraform init -reconfigure
  terraform apply \
    -var="project_name=$YOUR_NAME" \
    -var="environment=$ENV" \
    -state="terraform.tfstate.$ENV"
done

# 3. Capture outputs into backend-configs/<env>.hcl
terraform output -state="terraform.tfstate.dev" tfstate_bucket
terraform output -state="terraform.tfstate.dev" tfstate_lock_table
# Paste into ../backend-configs/dev.hcl as `bucket = "..."` and
# `dynamodb_table = "..."`.
```

## Live workflow

After bootstrap, the live layer runs normally:

```bash
cd infra/terraform/gcp   # or aws

terraform init -backend-config=backend-configs/dev.hcl
terraform plan
terraform apply
```

The live layer reads bootstrap-created resources via data sources where
needed (the registry URL, KMS key IDs). Most live resources are
self-contained and don't reference bootstrap.

## What's intentionally NOT in bootstrap

- **Network** (VPC, subnets): in live layer because operators may want
  managed-mode VPC swapped for existing-mode without re-running bootstrap.
- **GKE/EKS cluster**: in live layer because cluster lifecycle is faster
  than foundation lifecycle.
- **GitHub OIDC provider**: currently in live layer (PR-A1). Migrating to
  bootstrap is a follow-up — moving requires a `terraform state mv` ritual
  documented in the upgrade runbook.

## Migration from flat layout

Existing adopters who provisioned state buckets manually via the runbook
(`docs/runbooks/terraform-state-bootstrap.md`) can either:

1. **Keep going as-is** — bootstrap is OPT-IN. Manually-created buckets
   still work with the live-layer `backend "s3"` / `backend "gcs"`.
2. **Migrate to bootstrap** — `terraform import` the existing state
   bucket into the bootstrap state, then run `terraform plan` to confirm
   no diff. Procedure in `docs/runbooks/terraform-state-bootstrap.md`.
