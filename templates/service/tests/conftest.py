"""Shared pytest fixtures for {ServiceName} test suite.

The fastapi app (`app.main`) uses a lifespan that loads model artifacts
from disk and runs a warm-up. Tests cannot rely on real artifacts being
present, so we patch the loader + warmup at module level BEFORE the
lifespan runs (i.e., before TestClient is instantiated).

The ``client`` fixture here is the canonical test client; individual
tests should depend on it rather than constructing their own.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Mock model: behaves enough like a sklearn pipeline that fastapi_app does
# not crash. Returns deterministic predictions so assertions can be exact.
# ---------------------------------------------------------------------------
class _MockPipeline:
    """Stand-in for a fitted sklearn Pipeline. predict_proba returns
    P(positive)=0.7 always; predict returns class 1 always. Sufficient for
    structural tests of the API contract — not for model behavior tests.
    """

    feature_names_in_ = np.array(["feature_a", "feature_b", "feature_c"])

    def predict_proba(self, X: Any) -> np.ndarray:
        n = len(X) if hasattr(X, "__len__") else 1
        return np.tile([0.3, 0.7], (n, 1))

    def predict(self, X: Any) -> np.ndarray:
        n = len(X) if hasattr(X, "__len__") else 1
        return np.ones(n, dtype=int)


@pytest.fixture(scope="session", autouse=True)
def _patch_model_loading() -> Iterator[None]:
    """Patch load_model_artifacts so the FastAPI lifespan does not require
    real files. Active for the whole test session.

    NOTE: We deliberately do NOT patch ``warm_up_model``. The real function
    returns ``{"status": "skipped", ...}`` cleanly when ``_background_data``
    is None (the mock does not set it), which is the desired behaviour for
    these structural tests AND lets the dedicated unit tests in
    ``templates/tests/unit/test_warmup.py`` exercise the real implementation
    even when both test directories are collected in the same pytest
    session (see CI: .github/workflows/ci-examples.yml).

    Patching ``warm_up_model`` here previously leaked across the session
    boundary because session-scope autouse fixtures stay active until
    teardown, making the contract-level fake visible to tests outside this
    conftest's directory.
    """
    from unittest.mock import patch

    import app.fastapi_app as fastapi_app_mod

    mock_pipeline = _MockPipeline()

    def _fake_load() -> None:
        fastapi_app_mod._model_pipeline = mock_pipeline

    # Set MODEL_VERSION so the API exposes a deterministic value.
    os.environ.setdefault("MODEL_VERSION", "test-0.0.1")

    with patch.object(fastapi_app_mod, "load_model_artifacts", _fake_load), patch.object(
        fastapi_app_mod, "_start_prediction_logger", MagicMock()
    ), patch.object(fastapi_app_mod, "_stop_prediction_logger", MagicMock()):
        # Pre-populate the global so endpoints that read it directly succeed.
        fastapi_app_mod._model_pipeline = mock_pipeline
        yield


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """Single TestClient bound to the FastAPI app. Used as a context
    manager so the lifespan (load + warmup) runs before tests execute.
    """
    # Import inside the fixture so the autouse patch is active first.
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Sample payloads matching templates/service/app/schemas.py
# ---------------------------------------------------------------------------
@pytest.fixture
def valid_payload() -> dict:
    """Minimal valid PredictionRequest. Customize per service."""
    return {
        "entity_id": "test_entity_001",
        "slice_values": {"country": "MX", "channel": "mobile"},
        "feature_a": 42.0,
        "feature_b": 50000.0,
        "feature_c": "category_A",
    }


@pytest.fixture
def batch_payload(valid_payload: dict) -> dict:
    """Minimal valid BatchPredictionRequest with 2 customers."""
    return {"customers": [valid_payload, {**valid_payload, "entity_id": "test_entity_002"}]}
