# ADR-015 — Productization Roadmap (post-audit)

- **Status**: Accepted
- **Date**: 2026-04-26
- **Deciders**: Project owner + Cascade (this session)
- **Supersedes**: nothing — extends ADR-014 §B (post-launch hardening)
- **Related**: ADR-001 (template scope boundaries), ADR-010 (dynamic
  behavior protocol), ADR-011 (environment promotion), ADR-014 (gap
  remediation plan)

## Context

After the v1.10.0 audit closed 15 Critical/High/Medium findings
(commits `9d8894e..adf4eb6`), the template's invariants are
**aligned with the catalog and operational** for the first time.
But "aligned" is not the same as "ready to adopt". Adoption blockers
that did not appear in the audit:

- Network setup forces a fork to invent its own VPC topology
- IAM roles per env exist conceptually (per the runbooks) but the
  Terraform doesn't ship the split
- No single test proves that the entire chain (scaffold → build →
  digest → sign → attest → admit → namespace → smoke) works
  end-to-end. CI checks each link in isolation.
- Quality gates are inline in `train.py` rather than a versionable
  contract file
- EDA outputs are consumed by humans, not by drift/retrain workflows
- Alerts route by severity but don't carry a `runbook_url` field
- No drills exist to validate the response loops the runbooks describe

This ADR records the plan to close those gaps without scope-creeping
the template into a multi-team enterprise platform.

## Decision

Implement productization in **3 phases × 12 PRs**, sequenced by what
unblocks adoption first. Phases run sequentially; PRs within a phase
can be parallel only when explicitly noted.

### Phase A — Operable product (5 PRs)

What a new adopter needs to deploy a real service without forking
the template.

| PR | Scope | Critical-path |
|----|-------|---------------|
| **A5** | Golden path E2E in CI: scaffold → build → kind+local-registry → cosign sign by digest → Kyverno admit → smoke | YES — proves all prior audit work converges |
| **A1** | Network mode `managed \| existing` + per-env IAM split (CI / deploy / runtime / drift / retrain) | NO — depends on A5 to validate |
| **A2** | Bootstrap/live Terraform split (state + KMS + AR/ECR + CI identities only in bootstrap) | NO — depends on A1 |
| **A3** | Cluster defaults: private endpoint opt-in, system/workload node pools, NetworkPolicy deny-default | NO — depends on A2 |
| **A4** | Day-2 ops runbook (single file, both clouds) + nightly `terraform plan` workflow | NO — independent, can run last (✅ shipped — see sub-table) |

**A5 first** because it is the only single test that cumulatively
validates everything the v1.10.0 audit fixed. If A5 passes, A1–A4
add operational quality. If A5 fails on day one, A1–A4 are premature.

### Phase B — ML quality as executable contract (4 PRs)

| PR | Scope |
|----|-------|
| **B1** | `quality_gates.yaml` per service + Pandera-equivalent JSON schema + CI validation step (✅ shipped — `templates/service/configs/quality_gates.schema.json` + `scripts/validate_quality_gates.py` + drift-gate `test_quality_gates_schema_sync.py` + CI lint step) |
| **B2** | EDA produces 5 versioned artifacts (`eda_summary.json`, `schema_ranges.json`, `baseline_distributions.parquet`, `feature_catalog.yaml`, `leakage_report.json`); training/drift/retrain consume them by reference (✅ shipped — `templates/common_utils/eda_artifacts.py` contract + loaders; `eda_pipeline.py` emits all 5; `drift_detection.py --eda-baseline` consumer; `train.py` `_enforce_eda_gate` consumer; full test coverage) |
| **B3** | Leakage hardening (temporal split when timestamp present; grouped split when entity_id present; random split requires explicit config) + reproducibility manifest per run (✅ shipped — `SplitConfig` Pydantic model in `{service}.config` + JSON Schema; `Trainer._split_data` dispatch with future-leak / group-disjoint invariants; `common_utils.training_manifest` versioned manifest with SHAs, deps, EDA cross-ref; full test coverage incl. determinism check) |
| **B4** | Promotion gate enforcement — verify `promote_to_mlflow` blocks without an evidence bundle from B2/B3 (✅ shipped — `templates/common_utils/evidence_bundle.py` pure-stdlib gate verdict; `promote_to_mlflow.py` runs the gate BEFORE MLflow connection (exit 4 on refuse); `--skip-evidence-gate` requires a non-empty `--skip-reason` recorded as an MLflow tag; gate verdict + warnings persisted as run tags for audit; full test coverage of every failure mode + the skip-with-reason escape hatch) |

### Phase C — Operational observability (3 PRs)

| PR | Scope |
|----|-------|
| **C1** | Correlation IDs standard (`request_id`, `prediction_id`, `model_version`, `deployment_id`, `audit_id`, `drift_run_id`, `retrain_run_id`) carried through serving logs, events, audit (✅ shipped — `audit_id` in `agent_context` + `audit_record.py`; `deployment_id` via Downward API + `deploy-common.yml` patch; `drift_run_id` in report/Pushgateway/issue; contract codified in `templates/service/docs/correlation-ids.md`) |
| **C2** | Alert routing: `runbook_url` field MANDATORY on every PrometheusRule; multi-window burn-rate SLO alerts with action mapping (✅ shipped — `templates/service/tests/test_alert_routing_contract.py` auto-discovers every PrometheusRule + bare alert-groups doc and asserts: every alert has a non-empty `runbook_url` annotation, every alert has an `action` label in `{page, ticket, notify}`, the SLO file contains at least one multi-window/multi-burn-rate alert (long+short joined by `and`), and severity↔action pairs are not nonsense; `slo-prometheusrule.yaml` rewritten to the canonical 4-level SRE Workbook ladder (P1 14.4x/1h+5m page, P2 6x/6h+30m page, P3 3x/1d+2h ticket, P4 1x/3d+6h notify); `performance-prometheusrule.yaml`, `alertmanager-rules.yaml`, and `alerts-template.yaml` audited and patched for both invariants; `alerts-template.yaml` placeholders quoted to make the file valid YAML pre-render) |
| **C3** | 2 reproducible drills: drift simulated + deploy degraded; per-drill evidence in `docs/runbooks/drills/` (✅ shipped — `templates/scripts/drills/run_drift_drill.py` exercises the production `detect_drift(--eda-baseline ...)` path against a synthetic +3σ shift on `feature_a`; `run_deploy_degraded_drill.py` exercises `champion_challenger.compare_models` with a champion vs a challenger trained on shuffled labels and asserts the gate returns `block`; both write `evidence.md` + `evidence.json` + a per-drill artifacts dir under `docs/runbooks/drills/<drill>/<run_id>/`; `_drill_common.py` defines the shared `DrillEvidence` frozen dataclass; `templates/service/tests/test_drills_reproducible.py` runs both end-to-end + reproducibility checks (same seeds → byte-identical PSI / ΔAUC) + a catalogue sentinel; wired into `scripts/test_scaffold.sh` smoke chain and into `new-service.sh` so every scaffolded service ships drills; `templates/docs/runbooks/drills/README.md` documents cadence (per PR + per release + quarterly) and the contract for adding new drills) |

## What this ADR explicitly REJECTS

These items appeared in the source plan but violate ADR-001's
calibration for 2-5 service single-team templates:

| Rejected item | Why |
|---------------|-----|
| 6-module Terraform split (network/cluster/iam/registry/state/observability) | Module-per-domain is right at 10+ services, wrong at 2-5. Phase A keeps Terraform as **one cluster module per cloud** with focused sub-blocks. The audit's PR-03 expectation is a future ADR if/when the trigger fires. |
| Two separate Day-2 checklists (`CHECKLIST_DAY2_GCP.md` + `CHECKLIST_DAY2_AWS.md`) | Single `docs/runbooks/day-2-operations.md` with cloud-tagged tables is more maintainable. |
| `dashboards/QUESTIONS.md` as a PR of its own | Editorial commit inside Phase C2. Not a PR. |
| Module-style `iam_identity` separation in Terraform | Too much for 2-5 services. Phase A1 ships split identities as **resources within the existing modules**, not new modules. |
| Multi-region failover, blue/green, canary | ADR-001 explicitly excludes; left for downstream Argo Rollouts adoption. |

## Sequencing rule

**Within Phase A**, A5 lands first; A1–A4 may parallelize after A5
green. **Phase B starts only after Phase A is green** because
quality contracts that aren't deploy-tested are speculation.
**Phase C requires both A and B** because correlation IDs need
real services and runbook URLs need real alerts firing.

## Acceptance criteria (global)

The template is "productized" when ALL of:

1. `new-service.sh` produces a service with overlays for dev/staging/prod
   (✅ achieved v1.10.0)
2. A workflow E2E deploys by signed digest and is admitted by Kyverno (PR-A5)
3. `audit_record.py` works on a minimal CI runner (✅ achieved v1.10.0)
4. `terraform plan` per env with real remote backend works (✅ achieved v1.10.0;
   Phase A2 will tighten the bootstrap/live split)
5. Each scaffolded service ships `quality_gates.yaml` validated by CI (✅ achieved — PR-B1)
6. EDA emits 5 artifacts consumed by schema/drift/retrain (✅ achieved — PR-B2)
7. Retrain produces `promotion_packet.json` with statistical evidence
   (✅ achieved — adapter `b8708b6` produces evidence; PR-B3 manifest carries it; PR-B4 `evidence_bundle.evaluate_evidence` enforces it as a hard gate in `promote_to_mlflow.py`)
8. Every alert has a `runbook_url` (✅ achieved — PR-C2 contract test enforces it across all auto-discovered PrometheusRule manifests)
9. Logs/events correlate by standard IDs (✅ achieved — PR-C1)
10. ≥1 drift drill + ≥1 deploy-degraded drill repeat cleanly (✅ achieved — PR-C3 ships both, with reproducibility asserted by the contract test: same seeds produce byte-identical PSI on the drift drill and byte-identical ΔAUC CI lower bound on the deploy-degraded drill)

## Risks watched

- **Scope creep into a multi-team platform**: every PR in this ADR
  has an explicit "and this is NOT what we're doing" footnote. The
  rejected-items table is the canonical list.
- **Documentation drift**: Phase 5 §5.1 of ADR-014 (doc generators)
  remains pending. Until then, AGENTS.md / README / CLAUDE remain
  manually edited; PR descriptions of B/C phases must include the
  doc updates needed.
- **CI runtime**: PR-A5 is slow (kind + Kyverno + sign + admit).
  Mitigation: opt-in via `workflow_dispatch` + scheduled weekly run;
  per-PR validation stays on the existing `validate-templates.yml`
  scaffold-e2e gate.

## Tracking

| Phase | Status | Commits |
|-------|--------|---------|
| A — Operable product | **In progress** | see sub-table below |
| B — ML quality contract | ✅ **COMPLETE** | B1 PR-B1; B2 PR-B2; B3 PR-B3; B4 `6978272` |
| C — Observational loops | ✅ **COMPLETE** | C1 (audit_id/deployment_id/drift_run_id chain shipped pre-PR-C2); C2 `3298134`; C3 this commit |

### Phase A sub-tracking

| PR | Status | Commits / notes |
|----|--------|------------------|
| A5 | **In progress** — landed; golden-path workflow brought up; surfaced PR-A5b | `78accae` (initial), `e28151c` (path), `20142f6` (k8s tooling actions), `cc621e2` (kyverno chart ver), `3f3a867` (inline policy), this commit |
| A5b | ✅ **shipped** — placeholder vocabulary split | `{service-name}` (kebab, RFC 1123) for K8s names + image refs + IRSA/WI annotations + URL paths; `{service}` (snake) reserved for Python identifiers + Prometheus metric names + `SERVICE_METRIC_PREFIX` env var. `templates/scripts/new-service.sh` derives `SERVICE_KEBAB` from `SERVICE_SLUG` via `tr '_' '-'` and substitutes `{service-name}` BEFORE `{service}`. 39 K8s manifests + 2 monitoring rules patched mechanically (6-pattern sed: `{service}-`, `app: "{service}"`, `service: "{service}"`, `/{service}/`, `job="{service}"`, `service="{service}"`). Contract test `templates/service/tests/test_k8s_name_vocabulary.py` enforces both layers: static (no `{service}` in kebab-required positions) AND rendered (substitute snake-heavy `golden_path` slug → every `metadata.name`/`metadata.namespace`/`labels.{app,service}`/`serviceAccountName`/`containers[*].name`/`subjects[*].name`/`roleRef.name` validates against RFC 1123 regex `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`). 85 test cases pass; smoke-tested end-to-end with `bash new-service.sh GoldenPath golden_path` confirming `golden-path-predictor` (kebab) + `golden_path_performance_metric` (snake) coexist correctly. Wired into `scripts/test_scaffold.sh`. |
| A1 | ✅ **shipped** — network mode + per-env IAM split | ADR-017 documents the design. GCP (`templates/infra/terraform/gcp/`): `network.tf` adds custom-mode VPC + secondary ranges for pods/services with VPC Flow Logs (sample 0.5); `iam.tf` adds 5 service accounts (ci/deploy/runtime/drift/retrain) with Workload Identity bindings on the runtime/drift/retrain trio. AWS (`templates/infra/terraform/aws/`): `network.tf` adds VPC + 3 private + 3 public subnets across 3 AZs + NAT gateways tagged for AWS LB controller auto-discovery; `iam-roles-split.tf` adds GitHub OIDC provider (gated on `var.github_repo`), CI role (TF state R/W + ECR push, no IAM mutation), Deploy role (ECR push + EKS describe), per-service drift IRSA (CloudWatch read + scoped S3 reports), per-service retrain IRSA (data read + models write). Both clouds expose `network_mode = "managed" \| "existing"` with backwards-compat default ('managed' on GCP, 'existing' on AWS to preserve `var.subnet_ids` callers). Contract test `templates/service/tests/test_iam_least_privilege.py` (11 cases) enforces no wildcard principals, no `Action: "*"` on custom policies, GitHub OIDC sub-claim repo binding, 5 GCP SAs exist, separate AWS drift+retrain IRSA, network_mode validation block on both clouds, CI role lacks IAM mutation, runtime/drift/retrain WI bindings present. Anti-pattern codified as **D-31** in `AGENTS.md`. `terraform validate` passes on both clouds. |
| A2 | Pending | After A1 |
| A3 | Pending | After A2 |
| A4 | ✅ **shipped** — Day-2 runbook + nightly TF plan | `templates/docs/runbooks/day-2-operations.md` (single multi-cloud, GCP+AWS tagged tables; required sections enforced by contract test: preflight, scale, drain, cert/secret rotation, cost spike, terraform drift, backup, model rollback). `templates/cicd/terraform-plan-nightly.yml` (auto-shipped via `cp cicd/*.yml`; cron `0 4 * * *`; per-cloud jobs `plan-gcp` + `plan-aws` with `-detailed-exitcode` to distinguish drift from tooling failure; `terraform apply` deliberately absent — contract test enforces); WIF (GCP) + OIDC role-assume (AWS), no static credentials per D-18; opens deduplicated `infra-drift` GitHub Issue with truncated plan when state has drifted; `audit_record.py` invocation per ADR-014 §3.5. `templates/service/tests/test_day2_artifacts_contract.py` (10 cases) enforces both the runbook section list AND the workflow shape (schedule, plan-not-apply, both clouds, OIDC, issue-on-drift, audit). Also fixed `runbook-template.md` A5b kebab leftovers. Wired into `scripts/test_scaffold.sh`. |

The sub-table is the canonical Phase A status. The 5-commit
sequence on A5 reflects the run-by-run debugging the workflow
itself produced — each fix narrows the failure surface by one
step further into the chain. This is the intended operating
shape of an E2E bring-up: each green step proves a contract.

Updates to this table land alongside each PR commit so the ADR
reflects reality, not intent.
