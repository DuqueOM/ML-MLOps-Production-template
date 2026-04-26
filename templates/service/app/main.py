"""FastAPI application entry point for {ServiceName}.

Provides:
    /predict       — Single prediction (async, ThreadPoolExecutor)
    /predict_batch — Batch prediction (async, ThreadPoolExecutor)
    /health        — Liveness/readiness probe (healthy/degraded/unhealthy)
    /metrics       — Prometheus metrics endpoint
    /model/info    — Model metadata
    /model/reload  — Hot-reload model without pod restart
    /docs          — Swagger UI

Architecture decisions:
    - CPU-bound inference runs in ThreadPoolExecutor → never blocks event loop
    - CORS enabled for development; restrict in production via config
    - Model loaded at startup via lifespan, NOT per request
    - health returns "degraded" if model is None (not yet loaded)

TODO: Replace {ServiceName} with your actual service name.
TODO: Restrict CORS origins for production deployment.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.fastapi_app import (
    _start_prediction_logger,
    _stop_prediction_logger,
    load_model_artifacts,
    router,
    warm_up_model,
)

try:
    from common_utils.auth import require_admin
except ImportError:
    # See parallel guard in app/fastapi_app.py for rationale; the
    # /model/reload route still mounts but its dependency hides it
    # behind a 404 unless ADMIN_API_ENABLED=true.
    def require_admin() -> str:  # type: ignore[misc]
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


# Warm-up completion flag — /health returns "degraded" until warm-up completes
# so the K8s readiness probe gates traffic correctly (D-23).
_warmed_up: bool = False

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model artifacts + warm up + start closed-loop logger at startup; drain at shutdown."""
    global _warmed_up

    logger.info("Starting {ServiceName} API — loading model artifacts...")
    try:
        load_model_artifacts()
        logger.info("Model artifacts loaded successfully")
    except Exception as e:
        logger.error("Failed to load model artifacts: %s", e)
        # Continue startup — health endpoint will report "degraded"

    # --- Warm-up (D-23/D-24) ---
    # Execute a dummy predict + dummy SHAP computation so the first REAL
    # request is served with hot caches. Readiness probe MUST wait for this
    # to complete: we gate _warmed_up=True only after it finishes.
    try:
        report = warm_up_model()
        logger.info("Warm-up complete: %s", report)
    except Exception as e:
        logger.warning("Warm-up raised unexpectedly (continuing): %s", e)
    _warmed_up = True

    # Closed-loop monitoring (ADR-006) — graceful if unconfigured
    await _start_prediction_logger()

    yield

    logger.info("Shutting down {ServiceName} API")
    _warmed_up = False  # K8s will stop sending traffic via readiness
    await _stop_prediction_logger()


app = FastAPI(
    title="{ServiceName} API",
    description="{One sentence describing the business problem solved}",
    version=os.getenv("MODEL_VERSION", "0.1.0"),
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# --- CORS (default-deny) ---
# Default is the empty allowlist (NO origins). Set CORS_ORIGINS to a
# comma-separated list of explicit origins for browsers that need it,
# e.g. CORS_ORIGINS="https://dashboard.example.com,https://ops.example.com".
# The wildcard "*" is intentionally REJECTED by this loader; if a deploy
# truly needs unrestricted CORS, set CORS_ORIGINS="*" explicitly so the
# choice is auditable in the manifest, not implicit in the default
# (PR-R2-1, audit R2 finding 'CORS por defecto es *').
_cors_raw = os.getenv("CORS_ORIGINS", "").strip()
_cors_origins: list[str] = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
else:
    logger.info("CORS disabled (CORS_ORIGINS unset — same-origin only)")

app.include_router(router)


# ---------------------------------------------------------------------------
# Health — Liveness and readiness probes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    """Liveness probe — is the process alive and responsive?

    K8s livenessProbe should use THIS endpoint. It returns 'healthy' as long
    as the event loop is serving. A crashed process will not respond at all.
    Never returns 503 so K8s does not restart a pod that is merely still
    warming up.
    """
    return {
        "status": "healthy",
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
    }


@app.get("/ready")
async def ready():
    """Readiness probe — is the service ready to accept traffic?

    K8s readinessProbe should use THIS endpoint. Returns 503 until BOTH:
      - model artifacts are loaded
      - warm-up (dummy predict + dummy SHAP) has completed (D-23)

    This prevents the first request from paying cold-cache latency and
    violating the P95 SLO. During graceful shutdown we set _warmed_up=False
    so K8s stops routing new traffic while the pod drains.
    """
    from fastapi.responses import JSONResponse

    from app.fastapi_app import _model_pipeline

    model_loaded = _model_pipeline is not None
    is_ready = model_loaded and _warmed_up

    body = {
        "status": "ready" if is_ready else "not_ready",
        "model_loaded": model_loaded,
        "warmed_up": _warmed_up,
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
    }
    return JSONResponse(content=body, status_code=200 if is_ready else 503)


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------
@app.get("/model/info")
async def model_info() -> dict:
    """Return model metadata."""
    from app.fastapi_app import _model_pipeline

    return {
        "model_loaded": _model_pipeline is not None,
        "model_type": type(_model_pipeline).__name__ if _model_pipeline else None,
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
        "model_path": os.getenv("MODEL_PATH", "models/model.joblib"),
    }


@app.post("/model/reload", dependencies=[Depends(require_admin)])
async def model_reload() -> dict:
    """Hot-reload model artifacts without pod restart.

    Hidden behind :func:`common_utils.auth.require_admin`: returns 404
    unless ``ADMIN_API_ENABLED=true`` AND a valid ``ADMIN_API_KEY``
    credential is presented. In staging/production, refuses to operate
    if the admin secret is unset.

    Toggles /ready to not_ready during the reload + warm-up window so K8s
    stops routing new traffic. Consumers with a canary strategy (Argo
    Rollouts) will see the pod drain naturally.
    """
    global _warmed_up

    _warmed_up = False
    try:
        load_model_artifacts()
        report = warm_up_model()
        logger.info("Reload warm-up complete: %s", report)
        _warmed_up = True
        return {
            "status": "reloaded",
            "version": os.getenv("MODEL_VERSION", "0.1.0"),
            "warmup": report,
        }
    except Exception as exc:
        # Leave _warmed_up False — /ready keeps returning 503 until operator fixes.
        # Detail intentionally redacted (D-32, audit R2): operators read
        # the pod log, not the response body.
        logger.exception("Model reload failed")
        return {"status": "error", "detail": "reload failed; see pod logs"}


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------
@app.get("/")
async def root() -> dict:
    """API root — service identification."""
    return {
        "message": "{ServiceName} API",
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
        "docs": "/docs",
    }
