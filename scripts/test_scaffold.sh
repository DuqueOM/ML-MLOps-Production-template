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
  "eda/eda_pipeline.py"
  "eda/requirements.txt"
  "eda/reports"
  "eda/artifacts"
  "eda/notebooks"
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
OVERLAYS=(gcp-dev gcp-staging gcp-prod aws-dev aws-staging aws-prod)
if command -v kustomize >/dev/null 2>&1; then
  for overlay in "${OVERLAYS[@]}"; do
    overlay_dir="$SERVICE_DIR/k8s/overlays/$overlay"
    if [[ -d "$overlay_dir" ]]; then
      if kustomize build "$overlay_dir" > /dev/null 2>&1; then
        pass "Overlay renders: $overlay"
      else
        fail "Overlay fails to render: $overlay"
      fi
    else
      fail "Overlay missing after scaffold: $overlay"
    fi
  done
elif command -v kubectl >/dev/null 2>&1; then
  for overlay in "${OVERLAYS[@]}"; do
    overlay_dir="$SERVICE_DIR/k8s/overlays/$overlay"
    if [[ -d "$overlay_dir" ]]; then
      if kubectl kustomize "$overlay_dir" > /dev/null 2>&1; then
        pass "Overlay renders: $overlay (via kubectl)"
      else
        fail "Overlay fails to render: $overlay"
      fi
    else
      fail "Overlay missing after scaffold: $overlay"
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
# Validation 8 — Smoke: install deps + snapshot + pytest (optional)
# ════════════════════════════════════════════════
# These validations exercise what a freshly-scaffolded service can DO,
# not just what files it has. They are guarded by SCAFFOLD_SMOKE=1 so
# the lightweight structural checks above stay fast for local runs.
# CI (validate-templates.yml) sets the flag to enable the full chain.
if [[ "${SCAFFOLD_SMOKE:-0}" == "1" ]]; then
  info "Running smoke chain (install + snapshot + pytest)..."

  # Use a venv to avoid PEP-668 friction on Ubuntu 22.04+ runners.
  if python3 -m venv "$TEMP_ROOT/venv" 2>/dev/null; then
    # shellcheck disable=SC1091
    source "$TEMP_ROOT/venv/bin/activate"
    pass "Created venv: $TEMP_ROOT/venv"
  else
    echo -e "${YELLOW}⚠${NC} venv unavailable — skipping smoke chain"
    SCAFFOLD_SMOKE=0
  fi
fi

if [[ "${SCAFFOLD_SMOKE:-0}" == "1" ]]; then
  # 8a. Install scaffolded service deps. Bound by 5 min to fail fast on
  # network outages. Warning-only: dep resolution failure is not a
  # scaffolder bug per se.
  info "Installing scaffolded service dependencies (timeout 300s)..."
  if (cd "$SERVICE_DIR" && timeout 300 pip install --quiet --upgrade pip \
        && timeout 300 pip install --quiet -r requirements.txt) 2>"$TEMP_ROOT/pip.log"; then
    pass "Dependencies installed"
  else
    echo -e "${YELLOW}⚠${NC} pip install failed — skipping rest of smoke chain"
    echo "    log tail:"
    tail -5 "$TEMP_ROOT/pip.log" >&2 || true
    SCAFFOLD_SMOKE=0
  fi
fi

if [[ "${SCAFFOLD_SMOKE:-0}" == "1" ]]; then
  # 8b. Bootstrap the OpenAPI contract snapshot (D-28). Required by
  # tests/contract/test_openapi_snapshot.py::test_snapshot_file_exists.
  info "Generating openapi.snapshot.json via refresh_contract.py..."
  if (cd "$SERVICE_DIR" && PYTHONPATH=. python scripts/refresh_contract.py) \
        > "$TEMP_ROOT/refresh.log" 2>&1; then
    if [[ -f "$SERVICE_DIR/tests/contract/openapi.snapshot.json" ]]; then
      pass "OpenAPI snapshot bootstrapped"
    else
      fail "refresh_contract.py exited 0 but snapshot file is missing"
    fi
  else
    fail "refresh_contract.py failed:"
    tail -10 "$TEMP_ROOT/refresh.log" >&2
  fi
fi

if [[ "${SCAFFOLD_SMOKE:-0}" == "1" ]]; then
  # 8c. Run the real test suite. Validates that the scaffolded service
  # is testable AND its tests pass against a freshly-generated snapshot.
  # `test_quality_gates_config.py` was added by PR-R2-7 (audit R2 §4.2)
  # to gate every change to configs/quality_gates.yaml — it runs in
  # milliseconds (no sklearn imports) so it's cheap to include here.
  info "Running pytest (test_api.py + test_training.py + test_quality_gates_config.py + contract/)..."
  # `test_prediction_logger_lifecycle.py` (Phase 1.1) gates the env-aware
  # fail-fast contract for closed-loop monitoring. It runs in milliseconds
  # because each test only exercises `_start_prediction_logger` directly,
  # never the full FastAPI lifespan.
  # `test_error_envelope.py` (Phase 1.2) gates the canonical error
  # contract; it runs against the real router so a regression on
  # `install_error_envelope` is caught here.
  # `test_metrics_contract.py` (Phase 1.3) gates the alignment between
  # Counter/Gauge/Histogram declarations in app/fastapi_app.py and
  # src/<svc>/monitoring/* AND the metrics referenced in alert exprs
  # in k8s/base/slo-prometheusrule.yaml + monitoring/alertmanager-rules.yaml.
  # Catches the silent-failure case where a metric is renamed in code
  # but the alert still references the old name and never fires.
  # `test_quality_gates_schema_sync.py` (Phase 2 / PR-B1) gates the
  # behavioural equivalence between the Pydantic QualityGatesConfig
  # model and the committed JSON Schema file used by
  # `scripts/validate_quality_gates.py` and editor tooling. Drift
  # there means a config that passed CI Pydantic validation could
  # still fail JSON-Schema validation in a downstream tool — the
  # exact silent-divergence ADR-015 PR-B1 closes.
  # `test_eda_gate.py` + `test_drift_eda_baseline.py` (PR-B2 stage 2)
  # gate the canonical EDA-artifact contract end-to-end:
  #   - training refuses to start when leakage_report.json is BLOCKED;
  #   - drift CronJob can compute PSI against the parquet baseline;
  #   - both modes (legacy CSV reference / new EDA baseline) agree
  #     within tolerance on no-drift data.
  # Without these, a service could ship the canonical artifacts but
  # silently fall back to legacy CSV mode in production — exactly the
  # silent-divergence ADR-015 PR-B2 closes.
  # `test_split_strategies.py` + `test_training_manifest.py` (PR-B3)
  # gate the leakage-hardening + reproducibility-evidence contract:
  #   - Trainer._split_data dispatches on quality_gates.split.strategy;
  #     temporal split forbids future-leak; grouped split keeps entities
  #     disjoint; random refuses without explicit acknowledge_iid.
  #   - Every Trainer.run() writes a versioned training_manifest.json
  #     with content hashes, dependency versions, EDA cross-reference,
  #     and quality-gate verdict — even on rejected runs.
  if (cd "$SERVICE_DIR" && PYTHONPATH=. timeout 180 pytest \
        tests/test_api.py tests/test_training.py \
        tests/test_quality_gates_config.py \
        tests/test_quality_gates_schema_sync.py \
        tests/test_eda_gate.py \
        tests/test_drift_eda_baseline.py \
        tests/test_split_strategies.py \
        tests/test_training_manifest.py \
        tests/test_evidence_bundle.py \
        tests/test_promote_evidence_gate.py \
        tests/test_prediction_logger_lifecycle.py \
        tests/test_error_envelope.py \
        tests/test_input_validation.py \
        tests/test_metrics_contract.py \
        tests/test_alert_routing_contract.py \
        tests/test_data_paths.py \
        tests/contract/ \
        -q --tb=short --no-cov) > "$TEMP_ROOT/pytest.log" 2>&1; then
    pass "pytest passed on freshly-scaffolded service"
  else
    fail "pytest failed:"
    tail -20 "$TEMP_ROOT/pytest.log" >&2
  fi
fi

# ════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════
echo ""
if [[ "$FAILURES" -eq 0 ]]; then
  echo -e "${GREEN}━━━ SCAFFOLD TEST PASSED ━━━${NC}"
  echo "  new-service.sh produces a valid service structure."
  [[ "${SCAFFOLD_SMOKE:-0}" == "1" ]] && echo "  Smoke chain: install + snapshot + pytest all green."
  exit 0
else
  echo -e "${RED}━━━ SCAFFOLD TEST FAILED ━━━${NC}"
  echo "  $FAILURES validation(s) failed."
  [[ "$KEEP_TEMP" == "false" ]] && echo "  Re-run with --keep to inspect the failing scaffold."
  exit 1
fi
