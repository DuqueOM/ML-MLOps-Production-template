# Makefile — ML-MLOps Production Template (root)
# For contributors working on the template itself.
# For the per-service Makefile (train, serve, build, deploy), see templates/Makefile.
#
# Usage:
#   make help              # Show all targets
#   make install-dev       # Set up contributor environment
#   make lint-all          # Lint all Python in templates/ and examples/
#   make format-all        # Auto-format all Python
#   make validate-templates# Validate K8s + Terraform + Python templates
#   make demo-minimal      # Run the fraud detection example end-to-end
#   make test-examples     # Run example regression tests

.PHONY: help install-dev lint-all format-all validate-templates \
        validate-agentic bootstrap \
        demo-minimal test-examples clean

# Colors
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
BLUE   := \033[0;34m
NC     := \033[0m

help: ## Show this help message
	@echo "$(GREEN)ML-MLOps Template — Contributor Commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-22s$(NC) %s\n", $$1, $$2}'

# ═══════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════

install-dev: ## Install contributor tools + pre-commit hooks
	@echo "$(GREEN)Installing contributor tools...$(NC)"
	pip install black isort flake8 mypy pre-commit
	pip install -r examples/minimal/requirements.txt
	pre-commit install
	@echo "$(GREEN)✓ Contributor environment ready$(NC)"

bootstrap: ## One-command setup: detect OS, install deps, configure MCPs, run example
	@bash scripts/bootstrap.sh

bootstrap-check: ## Verify required tooling is installed (no install, no changes)
	@bash scripts/bootstrap.sh --check-only

# ═══════════════════════════════════════════════
# Quality
# ═══════════════════════════════════════════════

lint-all: ## Lint all Python (templates/ + examples/)
	@echo "$(GREEN)Running flake8...$(NC)"
	flake8 --max-line-length=120 --extend-ignore=E203,W503 \
		templates/service/ templates/common_utils/ examples/minimal/
	@echo "$(GREEN)Running black check...$(NC)"
	black --check --line-length=120 \
		templates/service/ templates/common_utils/ examples/minimal/
	@echo "$(GREEN)✓ Lint passed$(NC)"

format-all: ## Auto-format all Python (templates/ + examples/)
	@echo "$(GREEN)Formatting...$(NC)"
	black --line-length=120 templates/service/ templates/common_utils/ examples/minimal/
	isort --profile=black --line-length=120 \
		templates/service/ templates/common_utils/ examples/minimal/
	@echo "$(GREEN)✓ Format done$(NC)"

# ═══════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════

validate-k8s: ## Validate K8s manifests with kustomize
	@echo "$(GREEN)Validating K8s manifests...$(NC)"
	kustomize build templates/k8s/base/ > /dev/null
	@echo "$(GREEN)✓ K8s valid$(NC)"

validate-tf: ## Validate Terraform syntax
	@echo "$(GREEN)Validating Terraform (GCP)...$(NC)"
	@if command -v terraform >/dev/null 2>&1; then \
		terraform -chdir=templates/infra/gcp validate; \
		terraform -chdir=templates/infra/aws validate; \
		echo "$(GREEN)✓ Terraform valid$(NC)"; \
	else \
		echo "$(YELLOW)⚠ terraform not installed, skipping$(NC)"; \
	fi

validate-agentic: ## Validate agentic system (rules, skills, workflows, AGENTS.md refs)
	@echo "$(GREEN)Validating agentic system...$(NC)"
	python3 scripts/validate_agentic.py

test-scaffold: ## End-to-end test: runs new-service.sh in a tmp dir and validates output
	@echo "$(GREEN)Testing scaffolder end-to-end...$(NC)"
	@bash scripts/test_scaffold.sh

validate-templates: lint-all validate-k8s validate-agentic test-scaffold ## Validate all templates (lint + K8s + agentic + scaffold e2e)
	@echo "$(GREEN)✓ All templates validated$(NC)"

# ═══════════════════════════════════════════════
# Example (Fraud Detection)
# ═══════════════════════════════════════════════

demo-install: ## Install example dependencies
	pip install -r examples/minimal/requirements.txt

demo-train: ## Train the fraud detection example model
	@echo "$(GREEN)Training fraud detection model...$(NC)"
	python examples/minimal/train.py
	@echo "$(GREEN)✓ Model trained$(NC)"

demo-serve: ## Serve the fraud detection example API
	@echo "$(GREEN)Starting example API on :8000...$(NC)"
	@echo "$(YELLOW)Test with: curl -X POST http://localhost:8000/predict -H 'Content-Type: application/json' -d '{\"amount\": 150.0, \"hour\": 2, \"is_foreign\": true, \"merchant_risk\": 0.8, \"distance_from_home\": 45.0}'$(NC)"
	cd examples/minimal && uvicorn serve:app --host 0.0.0.0 --port 8000

demo-minimal: demo-install demo-train ## Run minimal example end-to-end (train + test + drift)
	@echo "$(GREEN)Running full example pipeline...$(NC)"
	cd examples/minimal && pytest test_service.py -v --tb=short
	cd examples/minimal && python drift_check.py
	@echo "$(GREEN)✓ Example pipeline complete$(NC)"

test-examples: demo-install ## Run all example regression tests
	@echo "$(GREEN)Running example tests...$(NC)"
	cd examples/minimal && python train.py
	cd examples/minimal && pytest test_service.py -v --tb=short
	@echo "$(GREEN)✓ Example tests passed$(NC)"

# ═══════════════════════════════════════════════
# Scaffolding
# ═══════════════════════════════════════════════

new-service: ## Scaffold a new service: make new-service NAME=FraudDetection SLUG=fraud_detection
	@if [ -z "$(NAME)" ] || [ -z "$(SLUG)" ]; then \
		echo "$(RED)Usage: make new-service NAME=FraudDetection SLUG=fraud_detection$(NC)"; \
		exit 1; \
	fi
	bash templates/scripts/new-service.sh $(NAME) $(SLUG)

# ═══════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════

clean: ## Clean Python cache files
	@echo "$(YELLOW)Cleaning...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Clean$(NC)"

.DEFAULT_GOAL := help
