"""Async inference endpoints with ThreadPoolExecutor and optional SHAP.

CPU-bound model.predict() runs in a thread pool so the asyncio event loop
stays responsive for concurrent requests. SHAP KernelExplainer is used for
complex ensemble/pipeline models (NEVER TreeExplainer with stacking).

Endpoints provided by this router:
    POST /predict        — Single prediction (+ optional SHAP explanation)
    POST /predict_batch  — Batch prediction for multiple inputs
    GET  /metrics        — Prometheus metrics (scraped by prometheus.io/scrape)

Key invariants:
    - model.predict() NEVER called directly in async endpoint → run_in_executor
    - SHAP computed in ORIGINAL feature space via _predict_proba_wrapper
    - Prometheus metrics: request count, latency histogram, score distribution

TODO: Replace {service} in metric names with your actual service name.
TODO: Adjust risk level thresholds (0.7/0.4) for your domain.
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import List, Optional
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

try:
    from common_utils.auth import verify_api_key
except ImportError:
    # common_utils not yet on path during scaffolder unit tests; degrade
    # to a no-op so the router still imports. The Dockerfile and the
    # `Verify common_utils importable` startup check ensure prod always
    # has it (PR-R2-1, ADR-016).
    def verify_api_key() -> str:  # type: ignore[misc]
        return "anonymous"


# Phase 1.2: stable error envelope. ``ServiceError`` is preferred over
# ``HTTPException`` in new code — the global handler converts it to the
# canonical ``{"error": {"code", "message", "request_id", ...}}`` shape.
# We keep an HTTPException fallback in case ``common_utils.errors`` is
# missing (parallel rationale to verify_api_key above).
try:
    from common_utils.errors import ErrorCode, ServiceError
except ImportError:
    ErrorCode = None  # type: ignore[assignment]

    class ServiceError(Exception):  # type: ignore[no-redef]
        """Fallback shim — preserves the call sites' contract.

        When ``common_utils`` is on the runtime path (Dockerfile guarantee),
        the real implementation raises through the envelope handler. When
        it is not, we re-raise as ``HTTPException`` so the response is
        still well-formed JSON.
        """

        def __init__(self, *, code: str, message: str, status_code: int = 500, **_: object) -> None:
            super().__init__(message)
            self.code = code
            self.status_code = status_code
            self.detail = message


from app._pandera_schema import get_pandera_schema
from app.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    PredictionRequest,
    PredictionResponse,
)

try:
    from common_utils.input_validation import (
        validate_predict_batch,
        validate_predict_payload,
    )
except ImportError:
    # Same fallback rationale as for verify_api_key above: keep the
    # router importable in stripped scaffolder smoke tests, where
    # common_utils may not be on sys.path. Production runtime always
    # has common_utils (see Dockerfile) and the validators raise
    # HTTPException(422) on real schema mismatches (PR-R2-4).
    def validate_predict_payload(payload, schema):  # type: ignore[no-redef]
        return None

    def validate_predict_batch(payload, schema):  # type: ignore[no-redef]
        return None


try:
    from common_utils.prediction_logger import (
        PredictionEvent,
        PredictionLogger,
        build_logger,
        utc_now_iso,
    )

    _PREDICTION_LOGGING_AVAILABLE = True
except ImportError:
    # common_utils is optional; closed-loop monitoring is gracefully degraded
    _PREDICTION_LOGGING_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Global state — loaded once at startup via load_model_artifacts()
# ---------------------------------------------------------------------------
_model_pipeline = None
_explainer = None  # shap.KernelExplainer (lazy — only if background data exists)
_feature_names: list[str] = []
_background_data: Optional[np.ndarray] = None

# Closed-loop prediction logger — lifecycle managed by main.lifespan
# (see ADR-006 and .windsurf/rules/13-closed-loop-monitoring.md, D-21)
_prediction_logger: Optional["PredictionLogger"] = None

# ---------------------------------------------------------------------------
# Thread pool for CPU-bound inference — NEVER block the event loop
# max_workers=4 is a safe default for ML inference; K8s HPA handles scale-out
# ---------------------------------------------------------------------------
_inference_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="ml-infer",
)

# ---------------------------------------------------------------------------
# Prometheus metrics — scraped by Prometheus via /metrics endpoint
#
# The metric prefix is resolved at IMPORT time from $SERVICE_METRIC_PREFIX or
# falls back to a literal placeholder "ml_service". This keeps the module
# importable BEFORE the scaffolder substitutes `{service}` (otherwise
# prometheus_client raises ValueError on names containing `{` / `}`).
#
# Production: deployment.yaml sets SERVICE_METRIC_PREFIX=<service>; metrics
# are exposed as `<service>_predictions_total`, etc. Audit Critical-3.
# ---------------------------------------------------------------------------
_METRIC_PREFIX = os.getenv("SERVICE_METRIC_PREFIX", "ml_service").replace("-", "_")

predictions_total = Counter(
    f"{_METRIC_PREFIX}_predictions_total",
    "Total predictions by risk level and model version",
    ["risk_level", "model_version"],
)

request_latency = Histogram(
    f"{_METRIC_PREFIX}_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

prediction_score_distribution = Histogram(
    f"{_METRIC_PREFIX}_prediction_score",
    "Distribution of model output probability scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
)

model_loaded_info = Gauge(
    f"{_METRIC_PREFIX}_model_info",
    "Model metadata (1 = loaded)",
    ["version"],
)

requests_total = Counter(
    f"{_METRIC_PREFIX}_requests_total",
    "Total HTTP requests by status",
    ["status"],
)

# Closed-loop monitoring instrumentation (ADR-006)
prediction_log_total = Counter(
    f"{_METRIC_PREFIX}_prediction_log_total",
    "Prediction events enqueued for closed-loop monitoring",
)
prediction_log_errors_total = Counter(
    f"{_METRIC_PREFIX}_prediction_log_errors_total",
    "Prediction-log errors swallowed by D-22 contract",
)


# ---------------------------------------------------------------------------
# Model loading — called once at startup, can be called again for hot-reload
# ---------------------------------------------------------------------------
def load_model_artifacts() -> None:
    """Load model pipeline and optional SHAP background data.

    Models are downloaded by the K8s init container into /models/ (emptyDir).
    Background data for SHAP should be in data/reference/ (50 representative samples).
    """
    global _model_pipeline, _explainer, _feature_names, _background_data

    model_path = os.getenv("MODEL_PATH", "models/model.joblib")
    _model_pipeline = joblib.load(model_path)

    # Load background data for SHAP KernelExplainer (50 representative samples)
    bg_path = os.getenv("BACKGROUND_DATA_PATH", "data/reference/background.csv")
    if os.path.exists(bg_path):
        try:
            bg_df = pd.read_csv(bg_path)
            _feature_names = list(bg_df.columns)
            _background_data = bg_df.values[:50]

            import shap

            _explainer = shap.KernelExplainer(
                model=_predict_proba_wrapper,
                data=_background_data,
            )
            logger.info("SHAP KernelExplainer initialized with %d samples", len(_background_data))
        except ImportError:
            logger.warning("shap not installed — SHAP explanations disabled")
        except Exception as e:
            logger.warning("Failed to initialize SHAP: %s", e)
    else:
        logger.info("No background data at %s — SHAP explanations disabled", bg_path)

    version = os.getenv("MODEL_VERSION", "0.1.0")
    model_loaded_info.labels(version=version).set(1)
    logger.info("Model loaded from %s (version=%s)", model_path, version)


def warm_up_model() -> dict:
    """Execute a dummy prediction + SHAP computation to absorb first-request latency.

    The first call to ``model.predict`` and ``explainer.shap_values`` incurs
    JIT, branch-prediction, and cache-warming costs that can easily push the
    first real request past the P95 SLO (D-23). By running a throwaway
    inference during startup, the event loop serves its first client request
    with all caches hot.

    Returns a small report so the lifespan can log measured times.
    Safe to call multiple times; safe to call before or after SHAP is ready.
    """
    if _model_pipeline is None or _background_data is None:
        return {"status": "skipped", "reason": "model or background data missing"}

    report: dict = {"status": "ok"}

    # Dummy predict — one sample from background data (same shape as prod input)
    start = time.perf_counter()
    sample_df = pd.DataFrame(_background_data[:1], columns=_feature_names)
    try:
        _ = _model_pipeline.predict_proba(sample_df)[:, 1]
        report["predict_warmup_ms"] = round((time.perf_counter() - start) * 1000, 2)
    except Exception as e:
        logger.warning("Warm-up predict failed: %s", e)
        report["predict_warmup_error"] = str(e)

    # Dummy SHAP — only if explainer is ready (D-24: cached, reused per request)
    if _explainer is not None:
        start = time.perf_counter()
        try:
            _ = _explainer.shap_values(sample_df.values, nsamples=50, silent=True)
            report["shap_warmup_ms"] = round((time.perf_counter() - start) * 1000, 2)
        except Exception as e:
            logger.warning("Warm-up SHAP failed: %s", e)
            report["shap_warmup_error"] = str(e)

    return report


def _predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """SHAP wrapper: numpy → DataFrame (with column names) → predict_proba.

    KernelExplainer passes raw numpy arrays. Without this wrapper, SHAP would
    compute in the post-ColumnTransformer space → feature names like 'x0_France'
    instead of 'Geography'. This ensures SHAP runs in ORIGINAL feature space.
    """
    X_df = pd.DataFrame(X_array, columns=_feature_names)
    return _model_pipeline.predict_proba(X_df)[:, 1]


# ---------------------------------------------------------------------------
# Synchronous prediction — runs in thread pool via run_in_executor
# ---------------------------------------------------------------------------
async def _start_prediction_logger() -> None:
    """Initialize and start the prediction logger. Called from main.lifespan.

    Fail-fast contract (D-21, ADR-006, Phase 1.1):
        * ``PREDICTION_LOG_ENABLED=false`` (explicit opt-out) → degrade silently;
          the operator has acknowledged that closed-loop monitoring is off.
        * ``PREDICTION_LOG_ENABLED=true`` (default) AND import failed:
            - ``ENVIRONMENT in {"dev","local"}`` → log warning, continue.
              Local dev should not be blocked by an editable install missing
              common_utils.
            - any other environment (default ``prod``) → RuntimeError.
              Production-class environments treat closed-loop monitoring as
              non-negotiable; without it, drift detection has no
              ground-truth feed and SLOs become unverifiable.
          Previously this degraded silently in *all* environments, so prod
          could believe it had closed-loop monitoring while no events were
          ever written. The Dockerfile now COPYs ``common_utils/`` into the
          runtime image so this branch only fires on misconfiguration.
        * Backend startup failure with logging enabled → RuntimeError too;
          a logger that can't connect to its backend is not a logger.
    """
    global _prediction_logger
    enabled = os.getenv("PREDICTION_LOG_ENABLED", "true").lower() != "false"
    if not enabled:
        logger.info("PREDICTION_LOG_ENABLED=false — closed-loop monitoring disabled")
        return
    if not _PREDICTION_LOGGING_AVAILABLE:
        env = os.getenv("ENVIRONMENT", "prod").lower()
        msg = (
            "PREDICTION_LOG_ENABLED=true but common_utils.prediction_logger is "
            "not importable. The runtime image is missing common_utils/. "
            "Either add it to the Dockerfile (see templates/service/Dockerfile) "
            "or set PREDICTION_LOG_ENABLED=false to acknowledge closed-loop "
            "monitoring is intentionally off (D-21, ADR-006)."
        )
        if env in {"dev", "local"}:
            # Dev workflow tolerance: a local editable install without
            # common_utils on PYTHONPATH should not block the developer.
            # The Dockerfile import smoke + this fail-fast keep prod safe.
            logger.warning("[%s] %s — degrading silently in dev only.", env, msg)
            return
        raise RuntimeError(msg)
    try:
        _prediction_logger = build_logger()
        await _prediction_logger.start()
        logger.info(
            "PredictionLogger started (backend=%s)",
            type(_prediction_logger.backend).__name__,
        )
    except Exception as exc:
        raise RuntimeError(
            "PredictionLogger failed to start with PREDICTION_LOG_ENABLED=true. "
            "Either fix the configured backend (PREDICTION_LOG_BACKEND env) or "
            "explicitly set PREDICTION_LOG_ENABLED=false to disable it."
        ) from exc


async def _stop_prediction_logger() -> None:
    """Drain buffer and shut down. Called from main.lifespan on shutdown."""
    if _prediction_logger is not None:
        try:
            await _prediction_logger.close()
            logger.info(
                "PredictionLogger stopped (logged=%d, dropped=%d, errors=%d)",
                _prediction_logger.logged_count,
                _prediction_logger.dropped_count,
                _prediction_logger.error_count,
            )
        except Exception as e:
            logger.warning("PredictionLogger shutdown error: %s", e)


async def _fire_and_forget_log(
    prediction_id: str,
    entity_id: str,
    features: dict,
    slices: dict,
    score: float,
    prediction_class: str,
    model_version: str,
    latency_ms: float,
) -> None:
    """Enqueue a PredictionEvent. NEVER blocks the handler (D-21, D-22)."""
    if _prediction_logger is None or not _PREDICTION_LOGGING_AVAILABLE:
        return
    try:
        event = PredictionEvent(
            prediction_id=prediction_id,
            entity_id=entity_id,
            timestamp=utc_now_iso(),
            model_version=model_version,
            features=features,
            score=float(score),
            prediction_class=prediction_class,
            slices=slices or {},
            latency_ms=latency_ms,
            # PR-C1 (ADR-015): correlation key linking the prediction
            # to the deploy that produced this pod. Sourced from the
            # K8s Downward API at pod start (see deployment.yaml). The
            # ``"local"`` fallback keeps host-mode tests honest — the
            # value queried in BigQuery still distinguishes "this row
            # came from a CI pod" from "this row came from prod".
            deployment_id=os.getenv("DEPLOYMENT_ID", "local"),
        )
        await _prediction_logger.log_prediction(event)
        prediction_log_total.inc()
    except Exception as e:
        prediction_log_errors_total.inc()
        logger.debug("prediction_log enqueue swallowed (D-22): %s", e)


def _sync_predict(input_dict: dict, explain: bool) -> dict:
    """CPU-bound prediction logic.

    This function runs inside ThreadPoolExecutor, NOT on the event loop.
    It handles inference, risk classification, metrics, and optional SHAP.
    """
    start = time.perf_counter()
    df = pd.DataFrame([input_dict])

    # --- Inference ---
    prob = float(_model_pipeline.predict_proba(df)[:, 1][0])

    # --- Risk level classification ---
    # TODO: Adjust thresholds for your domain (document in ADR)
    if prob >= 0.7:
        risk_level = "HIGH"
    elif prob >= 0.4:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    version = os.getenv("MODEL_VERSION", "0.1.0")
    predictions_total.labels(risk_level=risk_level, model_version=version).inc()
    prediction_score_distribution.observe(prob)

    response = {
        "prediction_score": round(prob, 4),
        "risk_level": risk_level,
        "model_version": version,
    }

    # --- Optional SHAP explanation ---
    if explain and _explainer is not None:
        try:
            shap_values = _explainer.shap_values(df.values, nsamples=100)
            base_value = float(_explainer.expected_value)

            contributions = {_feature_names[i]: round(float(shap_values[0][i]), 6) for i in range(len(_feature_names))}

            # Consistency check: base_value + sum(SHAP) ≈ prediction
            reconstructed = base_value + sum(contributions.values())

            sorted_contribs = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
            top_risk = [f"{k} (+{v:.4f})" for k, v in sorted_contribs[:3] if v > 0]
            top_protective = [f"{k} ({v:.4f})" for k, v in sorted_contribs[-3:] if v < 0]

            response["explanation"] = {
                "method": "kernel_explainer",
                "base_value": round(base_value, 6),
                "feature_contributions": contributions,
                "top_risk_factors": top_risk,
                "top_protective_factors": top_protective,
                "consistency_check": {
                    "actual_score": round(prob, 6),
                    "reconstructed": round(reconstructed, 6),
                    "difference": round(abs(prob - reconstructed), 6),
                    "passed": abs(prob - reconstructed) < 0.01,
                },
                "computation_time_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        except Exception as e:
            logger.warning("SHAP explanation failed: %s", e)
            response["explanation"] = {"method": "error", "detail": str(e)}

    elapsed = time.perf_counter() - start
    request_latency.labels(endpoint="/predict").observe(elapsed)

    return response


def _sync_predict_batch(inputs: List[dict]) -> List[dict]:
    """Batch prediction — CPU-bound, runs in thread pool."""
    start = time.perf_counter()
    df = pd.DataFrame(inputs)

    probas = _model_pipeline.predict_proba(df)[:, 1]
    version = os.getenv("MODEL_VERSION", "0.1.0")

    results = []
    for prob in probas:
        prob = float(prob)
        risk_level = "HIGH" if prob >= 0.7 else ("MEDIUM" if prob >= 0.4 else "LOW")
        predictions_total.labels(risk_level=risk_level, model_version=version).inc()
        prediction_score_distribution.observe(prob)
        results.append(
            {
                "prediction_score": round(prob, 4),
                "risk_level": risk_level,
                "model_version": version,
            }
        )

    elapsed = time.perf_counter() - start
    request_latency.labels(endpoint="/predict_batch").observe(elapsed)
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/predict",
    response_model=PredictionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def predict(input_data: PredictionRequest, explain: bool = False) -> PredictionResponse:
    """Single prediction endpoint.

    Runs inference in ThreadPoolExecutor to avoid blocking the event loop.
    Add ``?explain=true`` for SHAP feature contributions.

    Closed-loop logging (ADR-006): after computing the prediction we enqueue a
    PredictionEvent for later JOIN with ground-truth labels. Logging is
    fire-and-forget — NEVER blocks the client response (D-21/D-22).
    """
    if _model_pipeline is None:
        requests_total.labels(status="503").inc()
        raise ServiceError(
            code=ErrorCode.MODEL_NOT_LOADED if ErrorCode else "MODEL_NOT_LOADED",
            message="Model not loaded; readiness probe should have caught this.",
            status_code=503,
        )

    loop = asyncio.get_running_loop()
    request_start = time.perf_counter()
    try:
        # Features for the model = request minus non-feature fields
        input_dict = input_data.model_dump()
        entity_id = input_dict.pop("entity_id")
        slices = input_dict.pop("slice_values", None) or {}

        # Pandera second-wall validation for the single payload (PR-R2-4
        # parity — /predict_batch already validates; /predict was missing
        # the call so a value that satisfies Pydantic but violates the
        # schema would reach the model. Phase 1.2 closes the gap.)
        validate_predict_payload(input_dict, get_pandera_schema())

        result = await loop.run_in_executor(
            _inference_executor,
            partial(_sync_predict, input_dict, explain),
        )
        requests_total.labels(status="200").inc()

        prediction_id = uuid4().hex
        result["prediction_id"] = prediction_id

        # Fire-and-forget prediction log (closed-loop monitoring)
        await _fire_and_forget_log(
            prediction_id=prediction_id,
            entity_id=entity_id,
            features=input_dict,
            slices=slices,
            score=result["prediction_score"],
            prediction_class=result["risk_level"],
            model_version=result["model_version"],
            latency_ms=(time.perf_counter() - request_start) * 1000,
        )

        return PredictionResponse(**result)
    except HTTPException:
        # 422 from validate_predict_payload (or any other deliberate
        # HTTPException) must propagate verbatim — converting it to a
        # 500 would mask schema bugs as platform errors (PR-R2-4).
        requests_total.labels(status="422").inc()
        raise
    except Exception as exc:
        requests_total.labels(status="500").inc()
        logger.exception("Prediction failed")
        raise ServiceError(
            code=ErrorCode.INTERNAL_PREDICTION_ERROR if ErrorCode else "INTERNAL_PREDICTION_ERROR",
            message="Internal prediction error.",
            status_code=500,
        ) from exc


@router.post(
    "/predict_batch",
    response_model=BatchPredictionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def predict_batch(request: BatchPredictionRequest) -> BatchPredictionResponse:
    """Batch prediction endpoint for multiple inputs.

    Runs all predictions in a single ThreadPoolExecutor call for efficiency.
    Each prediction gets its own prediction_id and is logged individually
    (ADR-006) so each row is joinable with ground-truth labels.
    """
    if _model_pipeline is None:
        requests_total.labels(status="503").inc()
        raise ServiceError(
            code=ErrorCode.MODEL_NOT_LOADED if ErrorCode else "MODEL_NOT_LOADED",
            message="Model not loaded; readiness probe should have caught this.",
            status_code=503,
        )

    loop = asyncio.get_running_loop()
    request_start = time.perf_counter()
    try:
        raw = [item.model_dump() for item in request.customers]
        # Separate non-feature fields per row
        entity_ids: list[str] = []
        slices_list: list[dict] = []
        feature_inputs: list[dict] = []
        for row in raw:
            entity_ids.append(row.pop("entity_id"))
            slices_list.append(row.pop("slice_values", None) or {})
            feature_inputs.append(row)

        # Pandera second-wall validation for the whole batch (PR-R2-4).
        # Atomic semantics — one bad row rejects the entire request, so
        # callers can rely on "200 ⇒ every prediction is schema-valid".
        validate_predict_batch(feature_inputs, get_pandera_schema())

        results = await loop.run_in_executor(
            _inference_executor,
            partial(_sync_predict_batch, feature_inputs),
        )
        requests_total.labels(status="200").inc()

        batch_latency_ms = (time.perf_counter() - request_start) * 1000
        predictions: list[PredictionResponse] = []
        for features, slices, entity_id, result in zip(feature_inputs, slices_list, entity_ids, results):
            prediction_id = uuid4().hex
            result["prediction_id"] = prediction_id
            await _fire_and_forget_log(
                prediction_id=prediction_id,
                entity_id=entity_id,
                features=features,
                slices=slices,
                score=result["prediction_score"],
                prediction_class=result["risk_level"],
                model_version=result["model_version"],
                latency_ms=batch_latency_ms,
            )
            predictions.append(PredictionResponse(**result))

        return BatchPredictionResponse(
            predictions=predictions,
            total_customers=len(predictions),
        )
    except HTTPException:
        requests_total.labels(status="422").inc()
        raise
    except Exception as exc:
        requests_total.labels(status="500").inc()
        logger.exception("Batch prediction failed")
        raise ServiceError(
            code=ErrorCode.INTERNAL_PREDICTION_ERROR if ErrorCode else "INTERNAL_PREDICTION_ERROR",
            message="Internal prediction error.",
            status_code=500,
        ) from exc


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint — scraped by prometheus.io/scrape annotation."""
    return Response(content=generate_latest(), media_type="text/plain")
