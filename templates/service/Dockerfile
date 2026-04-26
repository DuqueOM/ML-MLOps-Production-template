# =============================================================================
# Multi-stage Dockerfile for {ServiceName}
# =============================================================================
# Target image size: ~600MB (Python 3.11 slim + ML deps)
#
# Stage 1 (builder): Install system build tools + Python packages in a venv
# Stage 2 (runtime): Copy only the venv + app code into a clean slim image
#
# Key decisions (see ADR):
#   - Multi-stage reduces final image ~40% vs single-stage
#   - xgboost/lightgbm installed with --no-deps to avoid nvidia-nccl-cu12 (~290MB)
#   - Non-root USER for K8s Pod Security Standards compliance
#   - HEALTHCHECK for Docker Compose; K8s uses its own probes
#   - Single uvicorn worker — K8s HPA manages horizontal scaling
#     NEVER use --workers N in K8s (causes CPU thrashing, dilutes HPA signal)
#   - Model artifacts are NOT baked in — K8s init container downloads them
#
# TODO: Update LABEL metadata for your service.
# TODO: Adjust requirements file name if you split prod vs dev dependencies.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install dependencies in an isolated venv
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

LABEL maintainer="your-team@example.com" \
      version="1.0.0" \
      description="{ServiceName} — ML prediction API"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System build deps (required for scikit-learn, scipy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements (change to requirements-prod.txt if you have separate files)
COPY requirements.txt ./

# Install into a venv for clean multi-stage copy
# xgboost/lightgbm --no-deps avoids pulling nvidia-nccl-cu12 (~290MB)
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --no-compile -r requirements.txt && \
    # Uncomment if using xgboost/lightgbm:
    # pip install --no-cache-dir --no-deps "xgboost>=1.5.0,<3.0" && \
    # pip install --no-cache-dir --no-deps "lightgbm>=4.0.0,<5.0" && \
    # Clean up to reduce image size
    find /opt/venv -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -type d -name 'tests' -not -path '*/numpy/*' -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -type f -name '*.pyc' -delete 2>/dev/null; \
    rm -rf /opt/venv/lib/python*/site-packages/pip 2>/dev/null; \
    rm -rf /opt/venv/lib/python*/site-packages/setuptools 2>/dev/null; \
    true

# ---------------------------------------------------------------------------
# Stage 2: Runtime — minimal final image
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    MODEL_PATH=models/model.joblib

# Minimal runtime deps (curl for healthcheck, libgomp for lightgbm/xgboost)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Non-root user — required by K8s Pod Security Standards (baseline)
RUN groupadd -r appuser --gid=1000 && \
    useradd -r -g appuser --uid=1000 --home-dir=/app appuser

WORKDIR /app

# Copy venv from builder
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy configs first (changes less frequently → better Docker cache)
COPY --chown=appuser:appuser configs/ ./configs/

# Copy source code (changes more frequently)
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser monitoring/ ./monitoring/

# Closed-loop monitoring helpers (D-21, ADR-006). Without this, the service
# starts but the PredictionLogger silently degrades — production thinks it has
# closed-loop monitoring while no events are written. The lifespan now
# fails fast when PREDICTION_LOG_ENABLED=true AND common_utils is missing.
COPY --chown=appuser:appuser common_utils/ ./common_utils/

# Create runtime directories (models downloaded by K8s init container)
RUN mkdir -p logs data/raw data/processed data/reference models results && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Docker HEALTHCHECK (K8s uses its own liveness/readiness probes)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Single worker — NEVER use --workers N in K8s
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
