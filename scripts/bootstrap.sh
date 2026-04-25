#!/usr/bin/env bash
# bootstrap.sh — One-command setup for ML-MLOps Production Template
#
# Detects OS, installs required tooling, configures MCPs (optional),
# runs the minimal example to validate, and prints next steps.
#
# Usage:
#   ./scripts/bootstrap.sh                 # Full setup
#   ./scripts/bootstrap.sh --skip-mcp      # Skip MCP configuration
#   ./scripts/bootstrap.sh --skip-demo     # Skip running the example
#   ./scripts/bootstrap.sh --check-only    # Only verify, don't install
#
# Idempotent: safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=_lib/detect_os.sh
source "$SCRIPT_DIR/_lib/detect_os.sh"
# shellcheck source=_lib/install_deps.sh
source "$SCRIPT_DIR/_lib/install_deps.sh"
# shellcheck source=_lib/configure_mcp.sh
source "$SCRIPT_DIR/_lib/configure_mcp.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKIP_MCP=false
SKIP_DEMO=false
CHECK_ONLY=false

for arg in "$@"; do
  case $arg in
    --skip-mcp)    SKIP_MCP=true ;;
    --skip-demo)   SKIP_DEMO=true ;;
    --check-only)  CHECK_ONLY=true ;;
    -h|--help)
      grep '^#' "$0" | head -20
      exit 0
      ;;
  esac
done

header() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1" >&2; }

# ═══════════════════════════════════════════════════════════
# 1. System detection
# ═══════════════════════════════════════════════════════════
header "System Detection"
OS="$(detect_os)"
success "OS detected: $OS"

if [[ "$OS" == "unsupported" ]]; then
  error "Unsupported OS. This script supports Linux, macOS, WSL."
  exit 1
fi

# ═══════════════════════════════════════════════════════════
# 2. Required tooling check
# ═══════════════════════════════════════════════════════════
header "Required Tools"

MISSING=()
check_tool() {
  local tool="$1"
  local min_version="${2:-}"
  if command -v "$tool" >/dev/null 2>&1; then
    local version
    version=$("$tool" --version 2>&1 | head -1 || echo "unknown")
    success "$tool: $version"
  else
    warn "$tool: not installed"
    MISSING+=("$tool")
  fi
}

check_tool python3
check_tool docker
check_tool kubectl
check_tool terraform
check_tool git
check_tool make

if [[ ${#MISSING[@]} -gt 0 ]]; then
  if [[ "$CHECK_ONLY" == "true" ]]; then
    error "Missing tools: ${MISSING[*]}"
    exit 1
  fi
  warn "Missing tools: ${MISSING[*]}"
  echo ""
  read -rp "Install missing tools? [y/N] " reply
  if [[ "$reply" =~ ^[Yy]$ ]]; then
    install_system_deps "$OS" "${MISSING[@]}"
  else
    warn "Skipping system deps install. Some steps may fail."
  fi
fi

# Python version check (3.11+)
if command -v python3 >/dev/null 2>&1; then
  py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  py_major=$(echo "$py_version" | cut -d. -f1)
  py_minor=$(echo "$py_version" | cut -d. -f2)
  if [[ "$py_major" -eq 3 ]] && [[ "$py_minor" -ge 11 ]]; then
    success "Python $py_version meets requirement (>=3.11)"
  else
    error "Python 3.11+ required, found $py_version"
    exit 1
  fi
fi

# ═══════════════════════════════════════════════════════════
# 3. Python dependencies
# ═══════════════════════════════════════════════════════════
if [[ "$CHECK_ONLY" == "false" ]]; then
  header "Python Dependencies"
  install_python_deps "$REPO_ROOT"
fi

# ═══════════════════════════════════════════════════════════
# 4. Pre-commit hooks
# ═══════════════════════════════════════════════════════════
if [[ "$CHECK_ONLY" == "false" ]]; then
  header "Pre-commit Hooks"
  if command -v pre-commit >/dev/null 2>&1; then
    (cd "$REPO_ROOT" && pre-commit install >/dev/null 2>&1)
    success "pre-commit hooks installed"
  else
    warn "pre-commit not available (install with: uv pip install pre-commit, or pip install pre-commit inside a venv)"
  fi
fi

# ═══════════════════════════════════════════════════════════
# 5. MCP configuration
# ═══════════════════════════════════════════════════════════
if [[ "$SKIP_MCP" == "false" ]] && [[ "$CHECK_ONLY" == "false" ]]; then
  header "MCP Configuration"
  configure_mcps "$REPO_ROOT"
fi

# ═══════════════════════════════════════════════════════════
# 6. Validation — run the minimal example
# ═══════════════════════════════════════════════════════════
if [[ "$SKIP_DEMO" == "false" ]] && [[ "$CHECK_ONLY" == "false" ]]; then
  header "Validating Example (fraud detection)"
  cd "$REPO_ROOT/examples/minimal"
  # PEP-668 safe install (ADR-014 §5.3): install_python_deps above already
  # set up a venv. Use whichever pip is on PATH after activation.
  PIP_BIN="pip"
  if command -v uv >/dev/null 2>&1; then
    PIP_BIN="uv pip"
  fi
  if $PIP_BIN install -q -r requirements.txt; then
    success "Example dependencies installed"
  else
    error "Failed to install example dependencies"
    exit 1
  fi

  if python train.py >/dev/null 2>&1; then
    success "train.py completed — quality gates passed"
  else
    error "train.py failed. Run manually: cd examples/minimal && python train.py"
    exit 1
  fi

  if [[ -f artifacts/model.joblib ]] && [[ -f artifacts/metrics.json ]]; then
    success "Artifacts created: model.joblib, metrics.json"
  fi
  cd "$REPO_ROOT"
fi

# ═══════════════════════════════════════════════════════════
# 7. Summary
# ═══════════════════════════════════════════════════════════
if [[ "$CHECK_ONLY" == "true" ]]; then
  header "Check complete"
  echo -e "${GREEN}All required tooling is present.${NC}"
  echo ""
  echo "To finish setup, run: make bootstrap"
  exit 0
fi

header "Ready!"
echo ""
echo -e "${GREEN}Your ML-MLOps template is ready to use.${NC}"
echo ""
echo "Next steps:"
echo "  1. Create a new service:"
echo -e "     ${YELLOW}make new-service NAME=MyService SLUG=my_service${NC}"
echo ""
echo "  2. Run the example end-to-end:"
echo -e "     ${YELLOW}make demo-minimal${NC}"
echo ""
echo "  3. Validate the agentic system:"
echo -e "     ${YELLOW}make validate-agentic${NC}"
echo ""
echo "  4. Read the docs:"
echo -e "     - Quick start:    ${BLUE}QUICK_START.md${NC}"
echo -e "     - Agentic system: ${BLUE}AGENTS.md${NC}"
echo -e "     - Scope:          ${BLUE}docs/decisions/ADR-001-template-scope-boundaries.md${NC}"
echo -e "     - Governance:     ${BLUE}docs/decisions/ADR-002-model-promotion-governance.md${NC}"
echo ""
