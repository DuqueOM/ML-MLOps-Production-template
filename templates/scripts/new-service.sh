#!/usr/bin/env bash
# =============================================================================
# new-service.sh — Scaffold a new ML service from templates
# =============================================================================
# Usage:
#   ./templates/scripts/new-service.sh FraudDetector fraud_detector
#   ./templates/scripts/new-service.sh ChurnPredictor churn_predictor
#
# Creates a new directory with all template files, placeholders replaced:
#   {ServiceName}  → FraudDetector
#   {service}      → fraud_detector
#   {SERVICE}      → FRAUD_DETECTOR
#
# After scaffolding:
#   1. cd into the new directory
#   2. Edit src/{slug}/schemas.py with your actual features
#   3. Edit src/{slug}/training/features.py with your feature engineering
#   4. Run: make install && make train
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# --- Argument validation ---
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <ServiceName> <service_slug>"
    echo ""
    echo "  ServiceName  — PascalCase name (e.g., FraudDetector)"
    echo "  service_slug — snake_case slug  (e.g., fraud_detector)"
    echo ""
    echo "Example:"
    echo "  $0 FraudDetector fraud_detector"
    exit 1
fi

SERVICE_NAME="$1"
SERVICE_SLUG="$2"
SERVICE_UPPER=$(echo "$SERVICE_SLUG" | tr '[:lower:]' '[:upper:]')

# Locate the templates directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$TEMPLATE_ROOT/.." && pwd)"
TARGET_DIR="$PROJECT_ROOT/$SERVICE_NAME"

if [[ -d "$TARGET_DIR" ]]; then
    error "Directory $TARGET_DIR already exists. Remove it first or choose a different name."
fi

info "Scaffolding $SERVICE_NAME ($SERVICE_SLUG) from templates..."
info "Target: $TARGET_DIR"

# --- Copy service template ---
info "Copying service template..."
cp -r "$TEMPLATE_ROOT/service" "$TARGET_DIR"

# --- Copy K8s base and overlays ---
info "Copying K8s manifests..."
mkdir -p "$TARGET_DIR/k8s"
cp -r "$TEMPLATE_ROOT/k8s/base" "$TARGET_DIR/k8s/base"
cp -r "$TEMPLATE_ROOT/k8s/overlays" "$TARGET_DIR/k8s/overlays"

# --- Copy infrastructure templates ---
info "Copying Terraform templates..."
cp -r "$TEMPLATE_ROOT/infra" "$TARGET_DIR/infra"

# --- Copy CI/CD templates ---
info "Copying CI/CD workflows..."
mkdir -p "$TARGET_DIR/.github/workflows"
cp "$TEMPLATE_ROOT/cicd/"*.yml "$TARGET_DIR/.github/workflows/"

# --- Copy monitoring templates ---
info "Copying monitoring templates..."
cp -r "$TEMPLATE_ROOT/monitoring" "$TARGET_DIR/monitoring"

# --- Copy documentation templates ---
info "Copying documentation templates..."
cp -r "$TEMPLATE_ROOT/docs" "$TARGET_DIR/docs"

# --- Copy operational scripts ---
info "Copying scripts..."
mkdir -p "$TARGET_DIR/scripts"
# Service-level helpers (deploy.sh, promote_model.sh, health_check.sh)
# live under templates/scripts/. The audit_record.py CLI lives at the
# repo root scripts/ (it's a project-wide tool, not a template
# placeholder) and is REQUIRED at runtime: deploy-common.yml invokes
# it on every deploy (success AND failure) to append to ops/audit.jsonl.
# Without it the scaffolded repo's deploy fails at the audit-trail step
# (ADR-014 §3.5; the golden-path workflow validates this end-to-end).
for script in deploy.sh promote_model.sh health_check.sh; do
    if [[ -f "$TEMPLATE_ROOT/scripts/$script" ]]; then
        cp "$TEMPLATE_ROOT/scripts/$script" "$TARGET_DIR/scripts/"
    fi
done
if [[ -f "$PROJECT_ROOT/scripts/audit_record.py" ]]; then
    cp "$PROJECT_ROOT/scripts/audit_record.py" "$TARGET_DIR/scripts/"
else
    warn "scripts/audit_record.py missing in template repo — scaffolded deploys will fail at the audit-trail step"
fi

# PR-B1 (ADR-015) — quality_gates.yaml validator. Required at runtime
# by the scaffolded `.github/workflows/ci.yml` lint job
# (`python scripts/validate_quality_gates.py --require-at-least-one`).
# Without it CI fails on the very first push with a confusing
# `python: can't open file scripts/validate_quality_gates.py` error.
if [[ -f "$PROJECT_ROOT/scripts/validate_quality_gates.py" ]]; then
    cp "$PROJECT_ROOT/scripts/validate_quality_gates.py" "$TARGET_DIR/scripts/"
else
    warn "scripts/validate_quality_gates.py missing — scaffolded CI will fail at the quality-gate validation step (PR-B1)"
fi

# audit_record.py imports from common_utils/agent_context.py (already
# copied below). _lib/ holds shared helpers; ship them too.
if [[ -d "$PROJECT_ROOT/scripts/_lib" ]]; then
    mkdir -p "$TARGET_DIR/scripts/_lib"
    cp -r "$PROJECT_ROOT/scripts/_lib/." "$TARGET_DIR/scripts/_lib/"
fi

# --- Copy DVC templates ---
if [[ -f "$TARGET_DIR/dvc.yaml" ]]; then
    info "DVC pipeline template already present"
else
    info "DVC templates included (dvc.yaml + .dvc/config)"
fi

# --- Copy EDA module ---
if [[ -d "$TEMPLATE_ROOT/eda" ]]; then
    info "Copying EDA module (6-phase exploratory analysis pipeline)..."
    cp -r "$TEMPLATE_ROOT/eda" "$TARGET_DIR/eda"
    mkdir -p "$TARGET_DIR/eda/reports" "$TARGET_DIR/eda/artifacts" "$TARGET_DIR/eda/notebooks"
fi

# --- Copy integration test templates ---
info "Copying integration test templates..."
mkdir -p "$TARGET_DIR/tests/integration"
for f in conftest.py test_service_integration.py; do
    if [[ -f "$TEMPLATE_ROOT/tests/integration/$f" ]]; then
        cp "$TEMPLATE_ROOT/tests/integration/$f" "$TARGET_DIR/tests/integration/"
    fi
done

# --- Copy DX files ---
for f in Makefile .pre-commit-config.yaml .gitleaks.toml .env.example docker-compose.demo.yml; do
    if [[ -f "$TEMPLATE_ROOT/$f" ]]; then
        cp "$TEMPLATE_ROOT/$f" "$TARGET_DIR/"
    fi
done

# --- Copy common_utils ---
info "Copying common_utils..."
cp -r "$TEMPLATE_ROOT/common_utils" "$TARGET_DIR/common_utils"

# --- Rename {service} directory ---
if [[ -d "$TARGET_DIR/src/{service}" ]]; then
    mv "$TARGET_DIR/src/{service}" "$TARGET_DIR/src/$SERVICE_SLUG"
    info "Renamed src/{service} → src/$SERVICE_SLUG"
fi

# --- Replace placeholders in all files ---
info "Replacing placeholders..."
find "$TARGET_DIR" -type f \( -name "*.py" -o -name "*.yaml" -o -name "*.yml" \
    -o -name "*.tf" -o -name "*.md" -o -name "*.toml" -o -name "*.sh" \
    -o -name "Dockerfile" -o -name ".dockerignore" -o -name "Makefile" \
    -o -name "*.json" -o -name "*.txt" -o -name "*.env*" \) | while read -r file; do
    # Replace in order: specific first, general last
    sed -i "s/{ServiceName}/$SERVICE_NAME/g" "$file"
    sed -i "s/{service}/$SERVICE_SLUG/g" "$file"
    sed -i "s/{SERVICE}/$SERVICE_UPPER/g" "$file"
done

# --- Create standard directories ---
# Phase 1.4: data path convention is `raw → processed → reference` for
# training (consumed by `train.py` + `dvc.yaml`) and `production/` for
# drift inputs (consumed by the drift CronJob — `cronjob-drift.yaml`
# mounts `data/production/latest.csv` as the `--current` argument).
# Without `data/production/` the first drift run fails with FileNotFound.
# See `docs/data-paths.md` for the full contract.
mkdir -p "$TARGET_DIR/data/raw"
mkdir -p "$TARGET_DIR/data/processed"
mkdir -p "$TARGET_DIR/data/reference"
mkdir -p "$TARGET_DIR/data/production"
mkdir -p "$TARGET_DIR/data/validated"
mkdir -p "$TARGET_DIR/models"
mkdir -p "$TARGET_DIR/reports"

# --- Create .gitkeep files for empty directories ---
touch "$TARGET_DIR/data/raw/.gitkeep"
touch "$TARGET_DIR/data/processed/.gitkeep"
touch "$TARGET_DIR/data/reference/.gitkeep"
touch "$TARGET_DIR/data/production/.gitkeep"
touch "$TARGET_DIR/models/.gitkeep"

# --- Summary ---
echo ""
info "=== Scaffolding complete ==="
echo ""
echo "  Service:   $SERVICE_NAME"
echo "  Slug:      $SERVICE_SLUG"
echo "  Directory: $TARGET_DIR"
echo ""
echo "  Next steps:"
echo "    1. cd $TARGET_DIR"
echo "    2. Place your dataset: cp <your-data>.csv data/raw/"
echo "    3. Run EDA (produces baseline distributions + schema proposal):"
echo "         pip install -r eda/requirements.txt"
echo "         python -m eda.eda_pipeline --input data/raw/<file>.csv --target <col> --service-slug $SERVICE_SLUG"
echo "    4. Review eda/reports/04_leakage_audit.md (must show BLOCKED_FEATURES: [])"
echo "    5. Copy src/$SERVICE_SLUG/schema_proposal.py → schemas.py (review first)"
echo "    6. Edit src/$SERVICE_SLUG/training/features.py (consume 05_feature_proposals.yaml)"
echo "    7. Edit src/$SERVICE_SLUG/training/model.py"
echo "    8. Edit app/schemas.py with your API request/response"
echo "    9. pip install -r requirements.txt"
echo "   10. make train DATA=data/raw/<file>.csv"
echo "   11. make serve"
echo ""
info "Done."
