# Runbook — Terraform State Bootstrap

One-time setup of Terraform remote state per environment, per cloud.
Closes audit High-6 (state collisions between dev/staging/prod).

Authority: ADR-011 (environment promotion gates), invariants D-10
(remote state) and D-17 (no hardcoded credentials).

## Two bootstrap paths (ADR-015 PR-A2)

There are now **two equivalent ways** to provision the state backend:

| Path | When to use | How |
| ------ | ------------- | ----- |
| **Terraform bootstrap** (recommended) | New projects, reproducibility matters | `cd templates/service/infra/terraform/{gcp,aws}/bootstrap && terraform apply` per env |
| **CLI bootstrap** (legacy, below) | Existing deployments, manual control | `gcloud` / `aws` commands in §GCP / §AWS sections |

The Terraform bootstrap creates state bucket + KMS key + container
registry + (AWS) DynamoDB lock table, all version-controlled. See
`templates/service/infra/terraform/README.md` for the full workflow including
output capture and migration from CLI-bootstrapped buckets.

The CLI sections below remain authoritative for adopters who prefer to
keep state-bucket creation outside of Terraform's lifecycle.

---

## Why per-env state

A single `terraform.tfstate` shared across dev/staging/prod is two
unrelated bugs away from a production incident:

- A `terraform apply -auto-approve` in dev that picks up the wrong
  workspace can drift prod resources.
- A locked state file from a stuck CI run blocks ALL environments.
- Audit trails cannot tell which env's apply produced which diff.

The template's backends are now PARTIAL config — the actual bucket,
prefix, and key MUST come from `backend-configs/<env>.hcl` files.
This runbook bootstraps the buckets/tables those files reference.

## GCP — bootstrap GCS state buckets

Run ONCE per environment per project. Substitute `{project}`,
`{region}`, and pick names that match `backend-configs/<env>.hcl`.

```bash
PROJECT=your-gcp-project
REGION=us-central1

for ENV in dev staging prod; do
  BUCKET="${PROJECT}-tfstate-${ENV}"

  gcloud storage buckets create "gs://${BUCKET}" \
    --project="$PROJECT" \
    --location="$REGION" \
    --uniform-bucket-level-access

  # Versioning catches accidental rollback of state
  gcloud storage buckets update "gs://${BUCKET}" --versioning

  # 7-day soft delete (recovery window) + 90-day total retention
  gcloud storage buckets update "gs://${BUCKET}" \
    --soft-delete-duration=7d
done
```

Then update `templates/service/infra/terraform/gcp/backend-configs/<env>.hcl`
to match the bucket names you chose.

Initialize:

```bash
cd templates/service/infra/terraform/gcp
terraform init -backend-config=backend-configs/dev.hcl
# To switch envs in the same checkout:
terraform init -backend-config=backend-configs/staging.hcl -reconfigure
```

## AWS — bootstrap S3 + DynamoDB lock tables

```bash
PROJECT=your-aws-project
REGION=us-east-1

for ENV in dev staging prod; do
  BUCKET="${PROJECT}-tfstate-${ENV}"
  TABLE="${PROJECT}-tfstate-lock-${ENV}"

  # S3 bucket with versioning + SSE-S3
  aws s3api create-bucket \
    --bucket "$BUCKET" \
    --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION"
  aws s3api put-bucket-versioning \
    --bucket "$BUCKET" --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption \
    --bucket "$BUCKET" \
    --server-side-encryption-configuration '{
      "Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]
    }'

  # DynamoDB table for state locking
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION"
done
```

Initialize:

```bash
cd templates/service/infra/terraform/aws
terraform init -backend-config=backend-configs/dev.hcl
terraform init -backend-config=backend-configs/staging.hcl -reconfigure
```

## CI integration

`templates/service/.github/workflows/deploy-{gcp,aws}.yml` (or a dedicated `infra-apply.yml`
in your scaffold) MUST pass the env-specific backend config:

```yaml
- name: Init terraform (per env)
  working-directory: templates/service/infra/terraform/${{ matrix.cloud }}
  run: |
    terraform init -backend-config=backend-configs/${{ matrix.env }}.hcl

- name: Plan
  run: terraform -chdir=templates/service/infra/terraform/${{ matrix.cloud }} plan
```

Without `-backend-config` Terraform errors out at init (the partial
config requires it). This is the security gate: a copy-paste workflow
that forgets the flag fails immediately rather than silently writing
to whatever default state existed before.

## Verification

```bash
# Each env's state is in its own bucket/key
for ENV in dev staging prod; do
  cd templates/service/infra/terraform/gcp
  terraform init -backend-config=backend-configs/${ENV}.hcl -reconfigure
  terraform state list | head -3
done
```

If two envs ever return the same state list, the backend configs are
pointing at the same bucket — fix immediately.

## Related

- ADR-011 — environment promotion gates
- D-10 invariant — remote state, no local tfstate
- `templates/service/infra/terraform/{gcp,aws}/main.tf` — partial backend declarations
- `templates/service/infra/terraform/{gcp,aws}/backend-configs/` — env-pinned configs
- `docs/runbooks/gcp-wif-setup.md`, `docs/runbooks/aws-irsa-setup.md`
  — paired identity setup
