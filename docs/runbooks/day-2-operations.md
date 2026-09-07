# Day-2 Operations Runbook

This is the repo-level operational index for adopters and auditors
before a service is scaffolded. The rendered service copy lives at
`templates/service/docs/runbooks/day-2-operations.md` and replaces placeholders
such as `{service-name}` with the concrete service name.

## Required Cadence

| Procedure | Cadence | Owner | Evidence |
| --- | ---: | --- | --- |
| Terraform drift plan | Nightly | Platform | GitHub Actions summary + plan artifact |
| Cluster version check | Weekly | Platform | Issue or audit record |
| Node pool rotation review | Monthly | Platform | Maintenance ticket |
| Secret rotation review | Quarterly + on leak | Service owner | Secret version audit entry |
| Backup/restore verification | Monthly | Platform | Restore drill result |
| Drift drill | Quarterly + after major model change | Service owner | Drill report |
| Cost review | Monthly + on alert | Service owner | Cost report |
| Model rollback drill | Quarterly | Service owner | Rollback report |

## Universal Preflight

Run before any cluster-touching operation:

```bash
kubectl config current-context
kubectl get nodes
kubectl get pods -A | head
kubectl version --short
```

If the context is not the intended environment, **STOP**. Most
production accidents in templates like this come from correct commands
against the wrong cluster.

## Cloud-Specific Entry Points

- Terraform state bootstrap:
  `docs/runbooks/terraform-state-bootstrap.md`
- Secrets integration:
  `docs/runbooks/secrets-integration-e2e.md`
- Alertmanager validation:
  `docs/runbooks/alertmanager-validation.md`
- Ground-truth ingestion SLA:
  `docs/runbooks/ground-truth-ingestion.md`
- Service-rendered Day-2 commands:
  `templates/service/docs/runbooks/day-2-operations.md`

## Definition of Done

A production service is not Day-2 ready until these are true:

- Nightly Terraform plan runs per cloud/environment with remote state.
- Every alert has an owner, severity, runbook URL, and closure criterion.
- Rollback, secret rotation, node drain, and drift drill have been run
  at least once in a non-production environment.
- Budget alerts exist per environment.
- Model artifacts, MLflow artifacts, logs, and state have retention
  policies and restore evidence.
