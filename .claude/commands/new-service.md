---
description: Create a complete new ML service from template — end-to-end scaffolding
allowed-tools:
  - Bash(bash:*)
  - Bash(make:*)
  - Bash(python:*)
  - Read
  - Edit
---

# /new-service

Scaffold a complete ML service: training, API, Docker, K8s, CI/CD,
monitoring, drift detection. AUTO (reversible by `rm -rf`).

## Prerequisites
- EDA complete: `eda/artifacts/{01_dtypes_map,02_baseline_distributions,05_feature_proposals}`
- Name decided: ServiceName (PascalCase), service_slug (snake_case)

## Command
```bash
bash templates/scripts/new-service.sh ServiceName service_slug
```

## What it does
1. Copies `templates/service/` → `services/<slug>/` with placeholder substitution
2. Copies `templates/eda/` for data exploration in the new service
3. Initializes DVC tracking for `data/`
4. Creates first MLflow experiment
5. Wires CI/CD (`.github/workflows/{ci,deploy-gcp,deploy-aws}.yml`)
6. Generates Grafana dashboards from templates

## Validation
- `pytest services/<slug>/tests/ --no-cov` should pass
- `kustomize build services/<slug>/k8s/overlays/dev/` should render
- `make validate-templates` from repo root

## Next steps (after scaffold)
1. Review `src/<slug>/schemas.py` — merge `schema_proposal.py` from EDA
2. Edit `src/<slug>/features.py` — implement proposed transforms
3. Edit `src/<slug>/training/train.py` — model choice
4. Run local training + MLflow tracking
5. Open PR

**Canonical**: `.windsurf/skills/new-service/SKILL.md` + `.windsurf/workflows/new-service.md`.
