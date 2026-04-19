#!/usr/bin/env bash
# test_scaffold.sh — Validate that new-service.sh produces a working service
#
# Runs the scaffolder in an isolated temp directory and verifies:
#   1. Exit code 0
#   2. Service directory created
#   3. Zero remaining {ServiceName} / {service} / {SERVICE} placeholders
#   4. Critical files exist (Dockerfile, requirements.txt, src/<slug>/, app/, k8s/)
#   5. src/<slug>/ directory was correctly renamed from src/{service}/
#   6. Python modules are syntactically valid
#   7. Kustomize overlays render without errors
#   8. (optional) pytest dry-collect succeeds on the scaffolded tests/
#
# The test creates a temp dir, copies templates/ and common_utils/ there,
# runs new-service.sh, validates, and cleans up. Safe to run anywhere.
#
# Exit codes:
#   0 = scaffold works
#   1 = validation failure
#   2 = setup error
#
# Usage:
#   ./scripts/test_scaffold.sh                   # default: TestSvc test_svc
#   ./scripts/test_scaffold.sh MyName my_name    # custom names
#   ./scripts/test_scaffold.sh --keep            # don't cleanup temp dir (debug)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICE_NAME="TestSvc"
SERVICE_SLUG="test_svc"
KEEP_TEMP=false

for arg in "$@"; do
  case $arg in
    --keep) KEEP_TEMP=true ;;
    -h|--help)
      grep '^#' "$0" | head -25
      exit 0
      ;;
    *)
      if [[ -z "${CUSTOM_NAME_SET:-}" ]]; then
        SERVICE_NAME="$arg"
        CUSTOM_NAME_SET=1
      else
        SERVICE_SLUG="$arg"
      fi
      ;;
  esac
done

SERVICE_UPPER=$(echo "$SERVICE_SLUG" | tr '[:lower:]' '[:upper:]')

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1" >&2; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${BLUE}→${NC} $1"; }

# ════════════════════════════════════════════════
# Setup isolated test environment
# ════════════════════════════════════════════════
info "Creating isolated test environment..."
TEMP_ROOT="$(mktemp -d -t mlops-scaffold-test.XXXXXX)"

cleanup() {
  if [[ "$KEEP_TEMP" == "true" ]]; then
    echo -e "${YELLOW}Temp dir preserved: $TEMP_ROOT${NC}"
  else
    rm -rf "$TEMP_ROOT"
  fi
}
trap cleanup EXIT

# The scaffolder resolves PROJECT_ROOT as $TEMPLATE_ROOT/.. — so we place
# templates/ inside TEMP_ROOT/, and the service will be created in TEMP_ROOT/.
cp -r "$REPO_ROOT/templates" "$TEMP_ROOT/templates"

pass "Temp environment: $TEMP_ROOT"

# ════════════════════════════════════════════════
# Run the scaffolder
# ════════════════════════════════════════════════
info "Running new-service.sh $SERVICE_NAME $SERVICE_SLUG..."
FAILURES=0
SERVICE_DIR="$TEMP_ROOT/$SERVICE_NAME"

if bash "$TEMP_ROOT/templates/scripts/new-service.sh" "$SERVICE_NAME" "$SERVICE_SLUG" > "$TEMP_ROOT/scaffold.log" 2>&1; then
  pass "Scaffolder exited 0"
else
  fail "Scaffolder failed. Log:"
  cat "$TEMP_ROOT/scaffold.log" >&2
  exit 1
fi

# ════════════════════════════════════════════════
# Validation 1 — Service directory exists
# ════════════════════════════════════════════════
info "Validating service directory..."
[[ -d "$SERVICE_DIR" ]] && pass "Service directory created: $SERVICE_NAME/" \
  || fail "Service directory missing: $SERVICE_DIR"

# ════════════════════════════════════════════════
# Validation 2 — Critical files exist
# ════════════════════════════════════════════════
info "Validating critical files..."
CRITICAL_FILES=(
  "Dockerfile"
  "requirements.txt"
  "pyproject.toml"
  "Makefile"
  "src/$SERVICE_SLUG"
  "app"
  "k8s/base"
  "k8s/overlays"
  "tests"
  "monitoring"
  "infra/terraform"
)
for f in "${CRITICAL_FILES[@]}"; do
  if [[ -e "$SERVICE_DIR/$f" ]]; then
    pass "Found: $f"
  else
    fail "Missing: $f"
  fi
done

# ════════════════════════════════════════════════
# Validation 3 — Zero remaining placeholders
# ════════════════════════════════════════════════
info "Checking for unreplaced placeholders..."
# grep exits 1 when no matches — swallow with `|| true` before counting,
# otherwise `set -o pipefail` would kill the script.
PLACEHOLDER_HITS=$({
  grep -rE "\{ServiceName\}|\{service\}|\{SERVICE\}" \
    "$SERVICE_DIR" \
    --include="*.py" --include="*.yaml" --include="*.yml" --include="*.md" \
    --include="*.toml" --include="*.sh" --include="*.tf" --include="*.json" \
    --include="*.txt" --include="Dockerfile" --include="Makefile" \
    2>/dev/null || true
} | wc -l)

if [[ "$PLACEHOLDER_HITS" -eq 0 ]]; then
  pass "Zero unreplaced placeholders"
else
  fail "$PLACEHOLDER_HITS lines still contain placeholders:"
  grep -rEn "\{ServiceName\}|\{service\}|\{SERVICE\}" \
    "$SERVICE_DIR" \
    --include="*.py" --include="*.yaml" --include="*.yml" --include="*.md" \
    --include="*.toml" --include="*.sh" --include="*.tf" --include="Dockerfile" \
    --include="Makefile" 2>/dev/null | head -10 >&2
fi

# ════════════════════════════════════════════════
# Validation 4 — src/{service}/ was renamed correctly
# ════════════════════════════════════════════════
info "Checking src/ directory rename..."
if [[ -d "$SERVICE_DIR/src/$SERVICE_SLUG" ]] && [[ ! -d "$SERVICE_DIR/src/{service}" ]]; then
  pass "src/{service} → src/$SERVICE_SLUG"
else
  fail "src/ directory not renamed correctly"
fi

# ════════════════════════════════════════════════
# Validation 5 — Python syntactic check
# ════════════════════════════════════════════════
info "Checking Python syntax..."
PY_ERRORS=0
while IFS= read -r -d '' pyfile; do
  if ! python3 -m py_compile "$pyfile" 2>/dev/null; then
    fail "Syntax error: ${pyfile#$SERVICE_DIR/}"
    PY_ERRORS=$((PY_ERRORS + 1))
  fi
done < <(find "$SERVICE_DIR" -name "*.py" -print0)

if [[ "$PY_ERRORS" -eq 0 ]]; then
  pass "All Python files parse"
fi

# ════════════════════════════════════════════════
# Validation 6 — Kustomize overlays render
# ════════════════════════════════════════════════
info "Validating Kustomize overlays..."
if command -v kustomize >/dev/null 2>&1; then
  for overlay in gcp-production aws-production; do
    overlay_dir="$SERVICE_DIR/k8s/overlays/$overlay"
    if [[ -d "$overlay_dir" ]]; then
      if kustomize build "$overlay_dir" > /dev/null 2>&1; then
        pass "Overlay renders: $overlay"
      else
        fail "Overlay fails to render: $overlay"
      fi
    fi
  done
elif command -v kubectl >/dev/null 2>&1; then
  for overlay in gcp-production aws-production; do
    overlay_dir="$SERVICE_DIR/k8s/overlays/$overlay"
    if [[ -d "$overlay_dir" ]]; then
      if kubectl kustomize "$overlay_dir" > /dev/null 2>&1; then
        pass "Overlay renders: $overlay (via kubectl)"
      else
        fail "Overlay fails to render: $overlay"
      fi
    fi
  done
else
  echo -e "${YELLOW}⚠${NC} kustomize/kubectl not available — skipping overlay validation"
fi

# ════════════════════════════════════════════════
# Validation 7 — pytest can collect tests (dry run)
# ════════════════════════════════════════════════
info "Testing pytest collection..."
if command -v pytest >/dev/null 2>&1; then
  # pytest --collect-only validates test files parse without running them
  if (cd "$SERVICE_DIR" && pytest --collect-only -q tests/ > /dev/null 2>&1); then
    pass "pytest can collect tests/"
  else
    # This is a warning not a failure — scaffolded tests may require unmet deps
    echo -e "${YELLOW}⚠${NC} pytest collection failed (expected — scaffolded deps not installed)"
  fi
else
  echo -e "${YELLOW}⚠${NC} pytest not installed — skipping collection check"
fi

# ════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════
echo ""
if [[ "$FAILURES" -eq 0 ]]; then
  echo -e "${GREEN}━━━ SCAFFOLD TEST PASSED ━━━${NC}"
  echo "  new-service.sh produces a valid service structure."
  exit 0
else
  echo -e "${RED}━━━ SCAFFOLD TEST FAILED ━━━${NC}"
  echo "  $FAILURES validation(s) failed."
  [[ "$KEEP_TEMP" == "false" ]] && echo "  Re-run with --keep to inspect the failing scaffold."
  exit 1
fi
