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

.PHONY: help install train serve test lint format build deploy health-check clean

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
