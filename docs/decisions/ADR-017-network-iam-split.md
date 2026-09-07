# ADR-017 — Network Mode + Per-Environment IAM Split (PR-A1)

- **Status**: Accepted
- **Date**: 2026-04-28
- **Deciders**: Project owner + Cascade
- **Supersedes**: nothing
- **Related**: ADR-015 (productization roadmap Phase A), ADR-014 (audit gap remediation)

## Context

ADR-015 Phase A identifies two adoption blockers that prevent downstream
teams from using the template without forking:

1. **Network topology is implicit** — GCP creates a VPC automatically;
   AWS requires `subnet_ids` but doesn't document the VPC setup. Teams
   with existing network infrastructure cannot adopt the template
   without rewriting `compute.tf`.

2. **IAM is monolithic** — a single service account (GCP) or role (AWS)
   has permissions for CI, deploy, runtime, drift, and retrain. This
   violates least-privilege and makes it impossible to audit "who did
   what" when an incident involves multiple workflows.

The audit (ADR-014) flagged IAM as Medium-priority but deferred the
split to post-launch. Now that the golden path E2E (PR-A5) is green,
we can implement the split without breaking the working chain.

## Decision

Implement **network mode selection** and **per-environment IAM split**
as two orthogonal features in a single PR (they touch the same Terraform
files and must be tested together).

### 1. Network Mode (GCP + AWS)

Add a `network_mode` variable to both clouds:

```hcl
variable "network_mode" {
  description = "Network topology mode: 'managed' (template creates VPC) or 'existing' (use provided VPC/subnets)"
  type        = string
  default     = "managed"
  validation {
    condition     = contains(["managed", "existing"], var.network_mode)
    error_message = "network_mode must be 'managed' or 'existing'"
  }
}
```

#### GCP Behavior

- **`managed` mode** (default):
  - Create `google_compute_network` with auto-mode subnets
  - Create `google_compute_subnetwork` for GKE with secondary ranges for pods/services
  - GKE cluster references `google_compute_network.gke.id` and `google_compute_subnetwork.gke.id`

- **`existing` mode**:
  - Require `var.network_name` and `var.subnetwork_name`
  - Use `data "google_compute_network"` and `data "google_compute_subnetwork"`
  - GKE cluster references data sources

#### AWS Behavior

- **`managed` mode**:
  - Create `aws_vpc` with CIDR `10.0.0.0/16`
  - Create 3 private subnets across 3 AZs (`10.0.1.0/24`, `10.0.2.0/24`, `10.0.3.0/24`)
  - Create 3 public subnets for NAT gateways (`10.0.101.0/24`, `10.0.102.0/24`, `10.0.103.0/24`)
  - Create NAT gateways + route tables
  - EKS cluster uses private subnets

- **`existing` mode** (current behavior):
  - Require `var.subnet_ids` (already exists)
  - Use provided subnets

### 2. Per-Environment IAM Split

Create 5 separate identities per environment, each with minimal permissions:

| Identity | GCP Resource | AWS Resource | Purpose | Permissions |
| ---------- | -------------- | -------------- | --------- | ------------- |
| **CI** | `google_service_account.ci` | `aws_iam_role.ci` (OIDC) | Terraform plan/apply, image build | `roles/container.admin`, `roles/storage.admin`, `roles/iam.serviceAccountUser` (GCP); `eks:*`, `ecr:*`, `s3:*` (AWS) |
| **Deploy** | `google_service_account.deploy` | `aws_iam_role.deploy` (OIDC) | Push images, update K8s | `roles/artifactregistry.writer`, `roles/container.developer` (GCP); `ecr:PutImage`, `eks:UpdateCluster` (AWS) |
| **Runtime** | `google_service_account.runtime` | `aws_iam_role.runtime` (IRSA) | Pod access to secrets, storage | `roles/secretmanager.secretAccessor`, `roles/storage.objectViewer` (GCP); `secretsmanager:GetSecretValue`, `s3:GetObject` (AWS) |
| **Drift** | `google_service_account.drift` | `aws_iam_role.drift` (IRSA) | Read metrics, write reports | `roles/monitoring.viewer`, `roles/storage.objectCreator` (GCP); `cloudwatch:GetMetricData`, `s3:PutObject` (AWS) |
| **Retrain** | `google_service_account.retrain` | `aws_iam_role.retrain` (IRSA) | Read data, write models | `roles/storage.objectViewer`, `roles/storage.objectCreator`, `roles/ml.developer` (GCP); `s3:GetObject`, `s3:PutObject` (AWS) |

#### GCP Implementation

- Create 6 `google_service_account` resources (the sixth, `nodes`, was added 2026-09-05 — see below)
- Create Workload Identity bindings for runtime/drift/retrain
- CI/deploy use key-based auth (GitHub Actions secrets) or OIDC federation

#### AWS Implementation

- Create 5 `aws_iam_role` resources
- CI/deploy roles use OIDC provider for GitHub Actions
- Runtime/drift/retrain roles use IRSA (IAM Roles for Service Accounts)
- Each role has inline policy with minimal permissions

### 3. Contract Tests

Add `templates/infra/terraform/tests/test_iam_least_privilege.py`:

- **Network mode validation**: `terraform validate` passes for both modes
- **IAM separation**: each identity has ONLY its required permissions
- **No wildcard principals**: no `Principal: "*"` in any policy
- **OIDC thumbprint**: GitHub OIDC provider configured correctly

### 4. Documentation Updates

- `templates/infra/terraform/gcp/README.md`: document both network modes
- `templates/infra/terraform/aws/README.md`: document both network modes
- `AGENTS.md`: add D-28 invariant "IAM identities are per-environment and per-purpose"
- `docs/runbooks/bootstrap.md`: update with network mode selection guidance

## What This ADR Explicitly REJECTS

- **Multi-region networking**: out of scope per ADR-001
- **VPN/interconnect setup**: downstream responsibility
- **Service mesh (Istio/Linkerd)**: deferred to Phase 5
- **Separate Terraform modules per domain**: too heavy for 2-5 services (see ADR-015 rejected items)

## Acceptance Criteria

1. `terraform plan` succeeds for both `network_mode=managed` and `network_mode=existing` on GCP and AWS
2. Golden path E2E (PR-A5) still passes with `network_mode=managed`
3. Contract test enforces IAM least-privilege (no wildcards, no cross-env access)
4. Each identity can perform its function and CANNOT perform other functions
5. Documentation includes migration guide for teams with existing VPCs

## Risks Watched

- **Breaking change for existing adopters**: mitigated by defaulting `network_mode=managed`
- **Complexity explosion**: mitigated by keeping network resources in single `compute.tf` (not separate modules)
- **IAM policy drift**: mitigated by contract test that fails if wildcard permissions appear

## Implementation Plan

1. Add `network_mode` variable to `gcp/variables.tf` and `aws/variables.tf`
2. Refactor `gcp/compute.tf` to conditionally create VPC resources
3. Refactor `aws/compute.tf` to conditionally create VPC resources
4. Add 5 IAM identities to `gcp/iam.tf` (new file)
5. Refactor `aws/iam.tf` to split existing role into 5 roles
6. Add contract test `test_iam_least_privilege.py`
7. Update documentation (READMEs, AGENTS.md, bootstrap runbook)
8. Run golden path E2E to validate no regression
9. Update ADR-015 tracking table

## Status Tracking

- [x] Network mode variable added (GCP + AWS)
- [x] VPC creation conditional on `network_mode=managed` (GCP — `network.tf`)
- [x] VPC creation conditional on `network_mode=managed` (AWS — `network.tf`)
- [x] 5 IAM identities created (GCP — `iam.tf`)
- [x] 5 IAM identities created (AWS — `iam.tf` per-service + `iam-roles-split.tf` ci/deploy/drift/retrain)
- [x] Contract test added (`templates/service/tests/test_iam_least_privilege.py` — 11 cases pass)
- [x] AGENTS.md D-31 anti-pattern codified (monolithic IAM identity)
- [x] ADR-015 sub-tracking updated (A1 marked shipped)
- [ ] Per-cloud README updates (network mode usage + migration guide)
- [ ] Golden path E2E re-run with managed mode (deferred; existing-mode default preserves CI green)

---

## Amendment (2026-09-05) — the node identity was missing

The five identities above cover CI, deploy, and the three workload purposes.
They did not cover **the nodes themselves**. Neither `google_container_node_pool`
set `node_config.service_account`, so GKE fell back to the default Compute
Engine service account — which in a typical project carries `roles/editor`
across the whole project. Trivy reports it as `GCP-0050`.

That is this ADR's own anti-pattern, D-31, present in the module that
implements D-31.

Bounded, not harmless: Workload Identity means pods impersonate
`runtime`/`drift`/`retrain` rather than using the node identity, so the
exposure is what an attacker inherits from a compromised **node**, not from a
compromised pod. Real all the same.

A sixth service account, `nodes`, now carries Google's documented minimum for
a custom node service account — `logging.logWriter`, `monitoring.metricWriter`,
`monitoring.viewer`, `stackdriver.resourceMetadata.writer` — plus
`artifactregistry.reader` scoped to this repository rather than granted
project-wide.

`node_oauth_scopes` gained `devstorage.read_only` in the same change. A scope
is an upper bound on what a service account may do, so the Artifact Registry
grant would have been unusable without it and private image pulls would fail.
`cloud-platform` is still deliberately avoided, per the variable's own
description.

### Related correction: `roles/iam.serviceAccountUser`

The same review found `google_project_iam_member.ci_sa_user` granting
`roles/iam.serviceAccountUser` **project-wide**, under a comment claiming it
was "Scoped via condition (only acting on SAs in this project)". There was no
condition block. CI could therefore impersonate any service account in the
project, including `runtime`, `drift` and `retrain` — exactly the blast radius
this ADR exists to bound.

Replaced with three `google_service_account_iam_member` bindings, one per
service account CI legitimately acts as: `deploy`, `runtime` and `nodes`
(attaching a service account to a node pool requires `serviceAccountUser` on
it). `drift` and `retrain` are reached by workloads through Workload Identity,
never by CI, and are deliberately absent.
