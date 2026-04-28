# Makefile — ML Service Template
# Standard developer entry point for all operations.
#
# Usage:
#   make help          # Show all available targets
#   make install       # Install dependencies
#   make train         # Run training pipeline
#   make serve         # Start local dev server
#   make test          # Run all tests
#   make build         # Build Docker image
#   make deploy        # Deploy to K8s (requires configured kubectl)
#
# TODO: Replace {service} and {SERVICE_SLUG} with your actual service names.

.PHONY: help install train serve test lint format build deploy health-check clean \
        new-service eda drift-check retrain release-checklist rollback \
        incident-runbook performance-review cost-review new-adr \
        secret-breach-check security-audit audit-rules batch-inference

# Colors
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
BLUE   := \033[0;34m
NC     := \033[0m

# Configuration — customize per service
SERVICE_SLUG ?= {service}
MODEL_PATH   ?= models/model.joblib
DATA_PATH    ?= data/raw/dataset.csv
IMAGE_TAG    ?= $(SERVICE_SLUG):latest
PORT         ?= 8000

help: ## Show this help message
	@echo "$(GREEN)ML Service — Available Commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# ═══════════════════════════════════════════════
# Development
# ═══════════════════════════════════════════════

install: ## Install dependencies
	@echo "$(GREEN)Installing dependencies...$(NC)"
	pip install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: ## Install dev dependencies + pre-commit hooks
	@echo "$(GREEN)Installing dev dependencies...$(NC)"
	pip install -r requirements.txt
	pip install pre-commit pytest-cov locust
	pre-commit install
	@echo "$(GREEN)✓ Dev environment ready$(NC)"

# ═══════════════════════════════════════════════
# ML Pipeline
# ═══════════════════════════════════════════════

train: ## Run training pipeline
	@echo "$(GREEN)Running training pipeline...$(NC)"
	python src/$(SERVICE_SLUG)/training/train.py --data $(DATA_PATH)
	@echo "$(GREEN)✓ Training complete$(NC)"

serve: ## Start local dev server (uvicorn)
	@echo "$(GREEN)Starting dev server on port $(PORT)...$(NC)"
	MODEL_PATH=$(MODEL_PATH) uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

# ═══════════════════════════════════════════════
# Quality & Testing
# ═══════════════════════════════════════════════

test: ## Run all tests
	@echo "$(GREEN)Running tests...$(NC)"
	pytest tests/ -v --tb=short

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	pytest tests/ --cov=src --cov=app --cov-report=term-missing --cov-fail-under=90

lint: ## Run linting (pre-commit hooks)
	@echo "$(GREEN)Running linters...$(NC)"
	pre-commit run --all-files

format: ## Auto-format code (black + isort)
	@echo "$(GREEN)Formatting code...$(NC)"
	black . --exclude '/(\.git|\.venv|data|models|mlruns)/'
	isort . --skip-gitignore
	@echo "$(GREEN)✓ Code formatted$(NC)"

typecheck: ## Run mypy type checking
	@echo "$(GREEN)Running type checks...$(NC)"
	mypy src/ app/ --ignore-missing-imports

security-scan: ## Run bandit security scan
	@echo "$(GREEN)Running security scan...$(NC)"
	bandit -r src/ app/ -ll -i

# ═══════════════════════════════════════════════
# Docker
# ═══════════════════════════════════════════════

build: ## Build Docker image
	@echo "$(GREEN)Building Docker image $(IMAGE_TAG)...$(NC)"
	docker build -t $(IMAGE_TAG) .
	@echo "$(GREEN)✓ Image built: $(IMAGE_TAG)$(NC)"

run: ## Run Docker container locally
	@echo "$(GREEN)Running container on port $(PORT)...$(NC)"
	docker run -p $(PORT):8000 \
		-v $(PWD)/models:/app/models:ro \
		-e LOG_FORMAT=json \
		$(IMAGE_TAG)

scan: ## Run Trivy security scan on Docker image
	@echo "$(GREEN)Scanning image $(IMAGE_TAG)...$(NC)"
	trivy image --severity HIGH,CRITICAL $(IMAGE_TAG)

# ═══════════════════════════════════════════════
# Deploy
# ═══════════════════════════════════════════════

deploy: ## Deploy to K8s (requires kubectl context)
	@echo "$(GREEN)Deploying to Kubernetes...$(NC)"
	bash scripts/deploy.sh $(SERVICE_SLUG) $(IMAGE_TAG)

health-check: ## Check health of deployed service
	@echo "$(GREEN)Checking service health...$(NC)"
	@curl -sf http://localhost:$(PORT)/health | python -m json.tool && \
		echo "$(GREEN)✓ Service healthy$(NC)" || \
		echo "$(RED)✗ Service unhealthy$(NC)"

load-test: ## Run Locust load test (headless, 60s)
	@echo "$(GREEN)Running load test...$(NC)"
	locust -f tests/load_test.py --host=http://localhost:$(PORT) \
		--headless -u 100 -r 10 --run-time 60s \
		--csv=reports/load_test

# ═══════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════

demo-up: ## Start demo stack (service + MLflow + Pushgateway)
	@echo "$(GREEN)Starting demo stack...$(NC)"
	docker compose -f docker-compose.demo.yml up -d --build
	@echo "$(GREEN)✓ Demo started$(NC)"
	@echo "$(YELLOW)Service:$(NC)     http://localhost:8000/health"
	@echo "$(YELLOW)MLflow:$(NC)      http://localhost:5000"
	@echo "$(YELLOW)Pushgateway:$(NC) http://localhost:9091"

demo-down: ## Stop demo stack
	@echo "$(YELLOW)Stopping demo stack...$(NC)"
	docker compose -f docker-compose.demo.yml down
	@echo "$(GREEN)✓ Demo stopped$(NC)"

# ═══════════════════════════════════════════════
# Non-agentic on-ramp (PR-R2-12)
#
# Every /slash workflow has a `make` equivalent below. Teams that don't
# operate with AI assistants can adopt the template without inheriting
# the agentic surface. See docs/ADOPTION.md for the full mapping table
# and the maturity matrix per cloud × environment.
#
# Each target either:
#   (a) invokes a real script (drift drills, retrain, security scan), or
#   (b) prints the canonical runbook path for procedures that are
#       inherently human-judgment (cost review, incident response).
# ═══════════════════════════════════════════════

new-service: ## Scaffold a new ML service (NAME=PascalCase SLUG=snake_case)
	@if [ -z "$(NAME)" ] || [ -z "$(SLUG)" ]; then \
		echo "$(RED)Usage:$(NC) make new-service NAME=FraudDetector SLUG=fraud_detector"; \
		exit 1; \
	fi
	bash templates/scripts/new-service.sh $(NAME) $(SLUG)

eda: ## Run 6-phase EDA pipeline on data/raw/
	@echo "$(GREEN)Running EDA pipeline...$(NC)"
	@if [ -f eda/run_eda.py ]; then \
		python eda/run_eda.py; \
	else \
		echo "$(YELLOW)See eda/README.md for the 6-phase pipeline.$(NC)"; \
	fi

drift-check: ## Run reproducible drift drill against data/production/
	@echo "$(GREEN)Running drift drill...$(NC)"
	python scripts/drills/run_drift_drill.py

retrain: ## Run training pipeline + quality gates (non-agentic equivalent of /retrain)
	@echo "$(GREEN)Retraining $(SERVICE_SLUG)...$(NC)"
	python src/$(SERVICE_SLUG)/training/train.py --data $(DATA_PATH)
	@echo "$(GREEN)Validating quality gates...$(NC)"
	python scripts/validate_quality_gates.py --require-at-least-one
	@echo "$(GREEN)✓ Retraining + gate validation complete$(NC)"
	@echo "$(YELLOW)Promotion is a CONSULT-class operation \u2014 see docs/runbooks/model-retrain.md$(NC)"

release-checklist: ## Print the canonical release checklist
	@echo "$(GREEN)Release checklist:$(NC)"
	@if [ -f docs/runbooks/release-checklist.md ]; then \
		cat docs/runbooks/release-checklist.md; \
	else \
		echo "$(YELLOW)See .windsurf/skills/release-checklist/SKILL.md$(NC)"; \
	fi

rollback: ## Roll back the last deploy (REV=<revision> optional)
	@echo "$(RED)EMERGENCY ROLLBACK \u2014 STOP-class operation$(NC)"
	@echo "$(YELLOW)See docs/runbooks/rollback.md before proceeding.$(NC)"
	@if [ -n "$(REV)" ]; then \
		kubectl rollout undo deployment/$(SERVICE_SLUG)-predictor --to-revision=$(REV); \
	else \
		kubectl rollout undo deployment/$(SERVICE_SLUG)-predictor; \
	fi
	kubectl rollout status deployment/$(SERVICE_SLUG)-predictor --timeout=5m

incident-runbook: ## Print the incident-response runbook
	@echo "$(GREEN)Incident response runbook:$(NC)"
	@if [ -f docs/runbooks/incident-response.md ]; then \
		cat docs/runbooks/incident-response.md; \
	else \
		echo "$(YELLOW)See .windsurf/workflows/incident.md$(NC)"; \
	fi

performance-review: ## Sliced performance review (concept drift detection)
	@echo "$(GREEN)Running performance review...$(NC)"
	@if [ -f scripts/run_performance_review.py ]; then \
		python scripts/run_performance_review.py; \
	else \
		echo "$(YELLOW)See docs/runbooks/performance-review.md$(NC)"; \
	fi

cost-review: ## Print the cost-review runbook
	@echo "$(GREEN)Monthly cost review procedure:$(NC)"
	@if [ -f docs/runbooks/cost-review.md ]; then \
		cat docs/runbooks/cost-review.md; \
	else \
		echo "$(YELLOW)See .windsurf/skills/cost-audit/SKILL.md$(NC)"; \
	fi

new-adr: ## Create a new ADR (TITLE='<title>')
	@if [ -z "$(TITLE)" ]; then \
		echo "$(RED)Usage:$(NC) make new-adr TITLE='Introduce feature flags'"; \
		exit 1; \
	fi
	@bash -c 'set -e; \
		num=$$(ls docs/decisions/ADR-*.md 2>/dev/null | sed -E "s/.*ADR-([0-9]+).*/\1/" | sort -n | tail -1); \
		num=$${num:-000}; \
		next=$$(printf "%03d" $$((10#$$num + 1))); \
		slug=$$(echo "$(TITLE)" | tr "[:upper:] " "[:lower:]-" | tr -cd "a-z0-9-"); \
		path="docs/decisions/ADR-$$next-$$slug.md"; \
		if [ -f docs/decisions/template.md ]; then \
			cp docs/decisions/template.md "$$path"; \
		else \
			printf "# ADR-%s: %s\n\n## Status\n\nProposed\n\n## Context\n\n## Decision\n\n## Consequences\n" "$$next" "$(TITLE)" > "$$path"; \
		fi; \
		echo "$(GREEN)Created$(NC) $$path"'

secret-breach-check: ## Scan for leaked secrets (gitleaks)
	@echo "$(GREEN)Scanning for leaked secrets...$(NC)"
	gitleaks detect --no-git --source=. --redact

security-audit: ## Run combined security audit (gitleaks + bandit + trivy)
	@echo "$(GREEN)Running security audit...$(NC)"
	@$(MAKE) secret-breach-check
	@$(MAKE) security-scan
	@if [ -f $(IMAGE_TAG) ] || docker image inspect $(IMAGE_TAG) >/dev/null 2>&1; then \
		$(MAKE) scan; \
	else \
		echo "$(YELLOW)Image $(IMAGE_TAG) not built locally \u2014 skipping trivy.$(NC)"; \
	fi

audit-rules: ## Validate AGENTS.md D-XX invariants are documented + tested
	@echo "$(GREEN)Validating AGENTS.md invariants...$(NC)"
	@if [ -f scripts/validate_agentic.py ]; then \
		python scripts/validate_agentic.py; \
	fi
	@echo "$(GREEN)Running policy suite over scaffolded output...$(NC)"
	pytest templates/service/tests/policy/ -v --no-cov --tb=short || true

batch-inference: ## Run batch scoring job (DATA=path/to/input.parquet)
	@if [ -z "$(DATA)" ]; then \
		echo "$(RED)Usage:$(NC) make batch-inference DATA=data/batch/input.parquet"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running batch inference on $(DATA)...$(NC)"
	@if [ -f scripts/batch_inference.py ]; then \
		python scripts/batch_inference.py --input $(DATA); \
	else \
		echo "$(YELLOW)See .windsurf/skills/batch-inference/SKILL.md for the K8s CronJob pattern$(NC)"; \
	fi

# ═══════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════

clean: ## Clean temporary files
	@echo "$(YELLOW)Cleaning...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage reports/
	@echo "$(GREEN)✓ Clean$(NC)"

.DEFAULT_GOAL := help
