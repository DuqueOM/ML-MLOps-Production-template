"""Tests for the Pandera second-wall validation wired in PR-R2-4.

Coverage map
============

* :func:`common_utils.input_validation.validate_predict_payload`
    - schema=None → no-op (template-level guarantee)
    - missing required column → HTTPException(422), redacted body
    - bad categorical → HTTPException(422)

* :func:`common_utils.input_validation.validate_predict_batch`
    - one bad row in N → HTTPException(422), atomic semantics

* :func:`common_utils.input_validation.validate_drift_dataframe`
    - schema=None → no-op + warning
    - missing column → DriftSchemaError (no HTTPException — drift runs
      outside FastAPI)

* End-to-end through TestClient
    - Bad categorical at /predict surfaces as 422 (NOT 500), proving
      the outer except-Exception block does not swallow it.

The Pandera schema used here is a self-contained fixture so the test
file does not depend on the rendered ``{service}.schemas`` package
(template-level tests run before scaffolding).
"""

from __future__ import annotations

from typing import Iterator

import pandas as pd
import pandera as pa
import pytest
from common_utils.input_validation import (
    DriftSchemaError,
    validate_drift_dataframe,
    validate_predict_batch,
    validate_predict_payload,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Local Pandera fixture — mirrors templates/service/src/{service}/schemas.py
# without importing it (the package name is unrendered in template tests).
# ---------------------------------------------------------------------------
class _Schema(pa.DataFrameModel):
    feature_a: float = pa.Field(ge=0, le=150)
    feature_b: float = pa.Field(ge=0)
    feature_c: str = pa.Field(isin=["category_A", "category_B", "category_C"])

    class Config:
        coerce = True
        strict = False


# ---------------------------------------------------------------------------
# validate_predict_payload
# ---------------------------------------------------------------------------
def test_predict_payload_no_op_when_schema_is_none() -> None:
    """schema=None must be treated as a deliberate degraded mode."""
    # Should not raise even if the payload is total nonsense.
    validate_predict_payload({"unrelated": "garbage"}, None)


def test_predict_payload_passes_valid_input() -> None:
    payload = {"feature_a": 42.0, "feature_b": 50000.0, "feature_c": "category_A"}
    # No exception => pass
    validate_predict_payload(payload, _Schema)


def test_predict_payload_rejects_bad_categorical() -> None:
    payload = {"feature_a": 1.0, "feature_b": 1.0, "feature_c": "not_a_category"}
    with pytest.raises(HTTPException) as exc:
        validate_predict_payload(payload, _Schema)
    assert exc.value.status_code == 422
    body = exc.value.detail
    assert isinstance(body, dict)
    assert body["message"].startswith("Input failed")
    # The redacted body must NOT contain the rejected value (D-32).
    serialised = repr(body)
    assert "not_a_category" not in serialised


def test_predict_payload_rejects_missing_column() -> None:
    payload = {"feature_a": 1.0, "feature_c": "category_A"}  # missing feature_b
    with pytest.raises(HTTPException) as exc:
        validate_predict_payload(payload, _Schema)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# validate_predict_batch
# ---------------------------------------------------------------------------
def test_predict_batch_atomic_rejection() -> None:
    """One bad row must reject the entire batch; that's the contract."""
    rows = [
        {"feature_a": 1.0, "feature_b": 1.0, "feature_c": "category_A"},
        {"feature_a": 2.0, "feature_b": 2.0, "feature_c": "BAD"},
    ]
    with pytest.raises(HTTPException) as exc:
        validate_predict_batch(rows, _Schema)
    assert exc.value.status_code == 422


def test_predict_batch_empty_is_no_op() -> None:
    # An empty list is structurally invalid upstream (Pydantic rejects
    # min_length=1) but the helper must be defensive anyway.
    validate_predict_batch([], _Schema)


# ---------------------------------------------------------------------------
# validate_drift_dataframe
# ---------------------------------------------------------------------------
def test_drift_dataframe_passes_valid_frame() -> None:
    df = pd.DataFrame(
        {
            "feature_a": [1.0, 2.0],
            "feature_b": [10.0, 20.0],
            "feature_c": ["category_A", "category_B"],
        }
    )
    out = validate_drift_dataframe(df, _Schema, label="reference")
    assert out is not None
    assert list(out.columns) >= ["feature_a", "feature_b", "feature_c"]


def test_drift_dataframe_raises_on_missing_column() -> None:
    df = pd.DataFrame(
        {
            "feature_a": [1.0],
            # feature_b intentionally absent
            "feature_c": ["category_A"],
        }
    )
    with pytest.raises(DriftSchemaError):
        validate_drift_dataframe(df, _Schema, label="current")


def test_drift_dataframe_no_op_when_schema_is_none(caplog: pytest.LogCaptureFixture) -> None:
    df = pd.DataFrame({"x": [1]})
    out = validate_drift_dataframe(df, None, label="current")
    assert out is df  # passthrough
    # Must log a warning so a misconfigured deploy is still visible.
    assert any("schema is None" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Integration — /predict routes the 422 verbatim (does NOT 500-mask it)
# ---------------------------------------------------------------------------
@pytest.fixture
def schema_client(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> Iterator[TestClient]:
    """Inject the local _Schema as the resolved Pandera schema so the
    full /predict path is exercised end-to-end. Without this, the
    accessor returns ``None`` (template-test default) and validation
    is a no-op — fine for the unit tests above but does not prove the
    422 surfaces through FastAPI's exception machinery.
    """
    import app._pandera_schema as ps

    monkeypatch.setattr(ps, "ServiceInputSchema", _Schema, raising=True)
    yield client


def test_predict_returns_422_on_bad_categorical(schema_client: TestClient) -> None:
    payload = {
        "entity_id": "e1",
        "feature_a": 10.0,
        "feature_b": 100.0,
        "feature_c": "not_a_category",
    }
    resp = schema_client.post("/predict", json=payload)
    # Pydantic accepts the string (no enum on the Pydantic schema), so
    # the rejection comes from Pandera. 422 is the only acceptable
    # answer; 500 would mean the outer except-Exception swallowed it.
    assert resp.status_code == 422
    body = resp.json()
    # Phase 1.2: stable error envelope. Pandera failure cases live under
    # ``error.details.errors``; the legacy ``detail`` shape is gone (and
    # the back-compat opt-out via ``ERROR_ENVELOPE_ENABLED=false`` is the
    # only escape hatch — never enabled in CI).
    assert "error" in body, body
    assert body["error"]["code"] in {"UNPROCESSABLE_ENTITY", "SCHEMA_VALIDATION_FAILED"}
    assert body["error"]["request_id"], "request_id must be set by RequestIDMiddleware"
    assert "errors" in body["error"]["details"]


def test_predict_batch_returns_422_on_bad_row(schema_client: TestClient) -> None:
    payload = {
        "customers": [
            {
                "entity_id": "e1",
                "feature_a": 10.0,
                "feature_b": 100.0,
                "feature_c": "category_A",
            },
            {
                "entity_id": "e2",
                "feature_a": 10.0,
                "feature_b": 100.0,
                "feature_c": "BAD",
            },
        ]
    }
    resp = schema_client.post("/predict_batch", json=payload)
    assert resp.status_code == 422
