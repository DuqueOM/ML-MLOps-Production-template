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
for script in deploy.sh promote_model.sh health_check.sh; do
    if [[ -f "$TEMPLATE_ROOT/scripts/$script" ]]; then
        cp "$TEMPLATE_ROOT/scripts/$script" "$TARGET_DIR/scripts/"
    fi
done

# --- Copy DVC templates ---
if [[ -f "$TARGET_DIR/dvc.yaml" ]]; then
    info "DVC pipeline template already present"
else
    info "DVC templates included (dvc.yaml + .dvc/config)"
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
mkdir -p "$TARGET_DIR/data/raw"
mkdir -p "$TARGET_DIR/data/reference"
mkdir -p "$TARGET_DIR/data/validated"
mkdir -p "$TARGET_DIR/data/processed"
mkdir -p "$TARGET_DIR/models"
mkdir -p "$TARGET_DIR/reports"

# --- Create .gitkeep files for empty directories ---
touch "$TARGET_DIR/data/raw/.gitkeep"
touch "$TARGET_DIR/data/reference/.gitkeep"
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
echo "    2. Edit src/$SERVICE_SLUG/schemas.py with your features"
echo "    3. Edit src/$SERVICE_SLUG/training/features.py"
echo "    4. Edit src/$SERVICE_SLUG/training/model.py"
echo "    5. Edit app/schemas.py with your API request/response"
echo "    6. pip install -r requirements.txt"
echo "    7. make train DATA=data/raw/your-dataset.csv"
echo "    8. make serve"
echo ""
info "Done."
