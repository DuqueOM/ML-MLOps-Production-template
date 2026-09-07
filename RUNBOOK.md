# Operations Runbook — ML-MLOps Production Template

Quick reference for working with the template: scaffolding services, running examples, validating templates, and releasing.

## Quick Reference

| Operation | Command |
| ----------- | --------- |
| Scaffold new service | `./templates/scripts/new-service.sh ServiceName service_slug` |
| Run example (end-to-end) | `make demo-minimal` |
| Validate all templates | `make validate-templates` |
| Lint all Python | `make lint-all` |
| Format all Python | `make format-all` |
| Run example tests | `make test-examples` |
| Start MLflow stack | `docker compose -f templates/service/infra/docker-compose.mlflow.yml up -d` |
| Clean cache files | `make clean` |

## Prerequisites

- Python 3.11+, Docker 20.10+, Make, Git
- Optional: kustomize, terraform, kubectl (for validation targets)

```bash
git clone https://github.com/DuqueOM/ml-service-template.git
cd ml-service-template
make install-dev    # Install contributor tools + pre-commit hooks
```

## Scaffold a New Service

```bash
# Automated (recommended)
./templates/scripts/new-service.sh FraudDetector fraud_detector

# Via Make
make new-service NAME=FraudDetector SLUG=fraud_detector
```

**What it does:**

1. Copies `templates/service/` → `FraudDetector/`
2. Copies K8s, infra, CI/CD, monitoring, docs, scripts, common_utils
3. Replaces `{ServiceName}` → `FraudDetector`, `{service}` → `fraud_detector`, `{SERVICE}` → `FRAUD_DETECTOR`
4. Creates `data/`, `models/` directories with `.gitkeep`

**After scaffolding:**

```bash
cd FraudDetector
# Edit schemas, features, model, API schema (see QUICK_START.md)
pip install -r requirements.txt
make train DATA=data/raw/your-dataset.csv
make serve
```

## Validate Templates

```bash
# All validations (lint + K8s)
make validate-templates

# Individual
make lint-all         # flake8 + black check
make validate-k8s     # kustomize build
make validate-tf      # terraform validate (if installed)
```

## Run the Working Example

```bash
# Full pipeline: install → train → test → drift
make demo-minimal

# Or step by step
make demo-install     # Install dependencies
make demo-train       # Train fraud detection model
make demo-serve       # Start API on :8000

# Test
cd examples/minimal
pytest test_service.py -v
python drift_check.py
```

## MLflow (Local Development)

```bash
# Start MLflow + PostgreSQL + MinIO
docker compose -f templates/service/infra/docker-compose.mlflow.yml up -d

# Access
# MLflow UI: http://localhost:5000
# MinIO Console: http://localhost:9001

# Stop
docker compose -f templates/service/infra/docker-compose.mlflow.yml down
# Full cleanup (remove volumes)
docker compose -f templates/service/infra/docker-compose.mlflow.yml down -v
```

## Secret Management

The template enforces **no secrets in code** at multiple levels:

| Layer | Mechanism |
| ------- | ----------- |
| **Pre-commit** | `.gitleaks.toml` scans for API keys, tokens, passwords on every commit |
| **K8s** | Workload Identity (GCP) / IRSA (AWS) — pods get cloud IAM roles, no static credentials |
| **CI/CD** | GitHub Actions secrets (`${{ secrets.* }}`) — never stored in repo |
| **Local dev** | `.env` (gitignored) from `.env.example` — placeholder values only |

**For production secrets (DB passwords, API keys):**

```bash
# GCP Secret Manager
gcloud secrets create mlflow-db-password --data-file=-
# Reference in K8s: use ExternalSecrets Operator or Workload Identity + SDK

# AWS Secrets Manager
aws secretsmanager create-secret --name mlflow-db-password --secret-string "..."
# Reference in K8s: use ExternalSecrets Operator or IRSA + SDK
```

**Anti-pattern D-10**: Never commit `terraform.tfstate` or `.tfvars` with real values. Use remote state
(GCS/S3+DynamoDB) configured in `templates/service/infra/terraform/*/main.tf`.

## Contributing to the Template

```bash
make install-dev      # Set up contributor environment
make format-all       # Auto-format before committing
make lint-all         # Verify lint passes
make test-examples    # Verify examples work
make validate-templates  # Full validation
```

Pre-commit hooks run automatically on `git commit`.

## Release Process

See [templates/service/docs/CHECKLIST_RELEASE.md](templates/service/docs/CHECKLIST_RELEASE.md) for the full checklist.

Quick summary:

```bash
# 1. Update CHANGELOG.md
# 2. Tag
git tag -a v1.3.0 -m "Release v1.3.0: description"
git push origin v1.3.0

# 3. Create GitHub Release from tag with notes from CHANGELOG
```

## Local development port allocation

Canonical local port map (R6 audit follow-up). Every tool, doc, and
launch config must agree with this table; in-cluster traffic always
goes through `Service:80` → container `8000` regardless of it.

| Port | Owner | Why this port |
| ------ | ------- | --------------- |
| 8000 | Primary ML service API (example demo or scaffolded service) | FastAPI/uvicorn upstream default; matches Dockerfile `EXPOSE`, probes, and `/metrics` scrape annotations |
| 8001 | Secondary/template API instance (e.g. `templates/service` in modelless dev mode) | One-port-per-service rule — never share 8000 between two local instances |
| 5000 | MLflow tracking server | MLflow upstream default (`docker-compose.mlflow.yml`) |
| 9000 / 9001 | MinIO S3 API / console (MLflow artifact store) | MinIO upstream defaults |
| 9090 | Prometheus | Prometheus upstream default |
| 9091 | Pushgateway (drift CronJob metrics) | Pushgateway upstream default |
| 3000 | Grafana | Grafana upstream default |
| 5432 | Postgres (MLflow backend / ground-truth dev DB) | Postgres upstream default; expose locally only, never in overlays |

Rules: keep upstream defaults (least surprise for any SRE), one port
per service instance, resolve conflicts with `lsof -i :<port>`, and
never encode a local port into a K8s manifest — overlays own cluster
networking.

## Troubleshooting

| Issue | Fix |
| ------- | ----- |
| `kustomize build` fails | Ensure kustomize is installed: `brew install kustomize` |
| `terraform validate` skipped | Install terraform: `brew install terraform` |
| Pre-commit fails on first run | Run `make install-dev` to install hooks |
| Example test fails | Run `make demo-train` first to generate model |
| Docker compose port conflict | Check `lsof -i :5000` or `:8000` |

## Links

- [README.md](README.md) — Full documentation
- [QUICK_START.md](QUICK_START.md) — 10-minute setup guide
- [CHANGELOG.md](CHANGELOG.md) — Release history
- [AGENTS.md](AGENTS.md) — Agent architecture and invariants
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines
