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
  local repo_root="$1"

  # Core contributor deps
  echo "Installing contributor Python tools..."
  pip install -q black isort flake8 mypy pre-commit || {
    echo "Failed to install contributor tools" >&2
    return 1
  }
  echo "  ✓ black, isort, flake8, mypy, pre-commit"

  # Example dependencies (proves the template works)
  if [[ -f "$repo_root/examples/minimal/requirements.txt" ]]; then
    pip install -q -r "$repo_root/examples/minimal/requirements.txt" || {
      echo "Failed to install example dependencies" >&2
      return 1
    }
    echo "  ✓ example dependencies (numpy, pandas, scikit-learn, fastapi, etc.)"
  fi
}
