#!/usr/bin/env bash
# Installs system dependencies based on OS.
# Never installs without prompting. Never forces sudo.

install_system_deps() {
  local os="$1"
  shift
  local tools=("$@")

  case "$os" in
    linux|wsl)
      echo "Use your package manager to install: ${tools[*]}"
      echo "Examples:"
      echo "  Debian/Ubuntu:  sudo apt-get install python3.11 python3-pip docker.io git make"
      echo "  kubectl:        https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/"
      echo "  terraform:      https://developer.hashicorp.com/terraform/install"
      ;;
    macos)
      if ! command -v brew >/dev/null 2>&1; then
        echo "Homebrew not found. Install from https://brew.sh first."
        return 1
      fi
      echo "Run: brew install ${tools[*]}"
      ;;
  esac

  echo ""
  echo "After installing, re-run: ./scripts/bootstrap.sh"
}

install_python_deps() {
  # PEP-668 safe installer (ADR-014 §5.3). Three strategies, in order:
  #   1. `uv` is on PATH       → use `uv pip install` (10-100× faster, PEP-668 native)
  #   2. VIRTUAL_ENV is set    → use the active venv's pip
  #   3. neither of the above  → create $repo_root/.venv and use its pip
  #
  # Refuses to call a bare `pip` against the system interpreter on
  # PEP-668 systems — that path fails with "externally-managed-environment"
  # on Ubuntu 22.04+, Debian 12+, modern Fedora, and Homebrew Python.
  local repo_root="$1"
  local pip_cmd
  local venv_msg=""

  if command -v uv >/dev/null 2>&1; then
    # uv resolves a project-local environment automatically.
    pip_cmd="uv pip install"
    venv_msg="(via uv → $repo_root/.venv)"
    # uv pip install requires a target environment; create one if missing.
    if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ ! -d "$repo_root/.venv" ]]; then
      uv venv "$repo_root/.venv" >/dev/null 2>&1 || {
        echo "Failed to create venv via uv" >&2
        return 1
      }
    fi
    # Activate the local .venv so subsequent uv pip install lands there.
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
      # shellcheck disable=SC1091
      source "$repo_root/.venv/bin/activate"
    fi
  elif [[ -n "${VIRTUAL_ENV:-}" ]]; then
    pip_cmd="pip install"
    venv_msg="(active venv: $VIRTUAL_ENV)"
  else
    # Last resort: stdlib venv + project-local .venv/.
    if [[ ! -d "$repo_root/.venv" ]]; then
      echo "Creating project-local .venv at $repo_root/.venv (PEP-668 safe fallback)..."
      python3 -m venv "$repo_root/.venv" || {
        echo "python3 -m venv failed. Install python3-venv or run with uv." >&2
        echo "  Debian/Ubuntu: sudo apt install python3-venv" >&2
        echo "  uv:            curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
        return 1
      }
    fi
    # shellcheck disable=SC1091
    source "$repo_root/.venv/bin/activate"
    pip_cmd="pip install"
    venv_msg="(via stdlib venv → $repo_root/.venv)"
  fi

  echo "Installing contributor Python tools $venv_msg..."
  # shellcheck disable=SC2086 — pip_cmd may be 'uv pip install' (multi-word)
  $pip_cmd -q black isort flake8 mypy pre-commit || {
    echo "Failed to install contributor tools" >&2
    return 1
  }
  echo "  ✓ black, isort, flake8, mypy, pre-commit"

  if [[ -f "$repo_root/examples/minimal/requirements.txt" ]]; then
    # shellcheck disable=SC2086
    $pip_cmd -q -r "$repo_root/examples/minimal/requirements.txt" || {
      echo "Failed to install example dependencies" >&2
      return 1
    }
    echo "  ✓ example dependencies (numpy, pandas, scikit-learn, fastapi, etc.)"
  fi

  # Footer reminder so the user knows where deps actually went.
  if [[ -d "$repo_root/.venv" ]] && [[ "$VIRTUAL_ENV" = "$repo_root/.venv" ]]; then
    echo ""
    echo "  Note: deps installed in $repo_root/.venv. Activate before running:"
    echo "    source $repo_root/.venv/bin/activate"
  fi
}
