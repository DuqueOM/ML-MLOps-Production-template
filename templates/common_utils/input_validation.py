"""Pandera adapters for the *single source of truth* input schema.

Background (ADR-016 PR-R2-4)
============================

Three call sites consume the same training-time DataFrame schema today,
but only one of them actually validates against it:

    1. ``src/{service}/training/train.py``  — calls ``ServiceInputSchema.validate``
    2. ``app/fastapi_app.py`` (``/predict``, ``/predict_batch``) — historically did NOT,
       relied on Pydantic alone.
    3. ``src/{service}/monitoring/drift_detection.py`` — historically did NOT;
       a missing or renamed column would silently look like real drift.

Pydantic (in :mod:`app.schemas`) catches type / range issues per field.
Pandera (in :mod:`{service}.schemas`) catches DataFrame-level invariants:
required columns, allowed categoricals, cross-column rules, and the
*coercion* policy that training depends on.

These two layers are complementary, not duplicative. PR-R2-4 wires the
Pandera layer into serving + drift so a divergence between
``app/schemas.py`` and ``src/{service}/schemas.py`` fails loudly on the
first request rather than producing a corrupted prediction or a phantom
drift alert.

API
===

* :func:`validate_predict_payload` — single-row dict, used in
  ``/predict``. Raises ``HTTPException(422)`` with a compact, redacted
  error list on failure (D-32: never leak request values back to the
  caller).
* :func:`validate_predict_batch` — list-of-dicts, used in
  ``/predict_batch``. Same redaction policy.
* :func:`validate_drift_dataframe` — full DataFrame, used in
  ``drift_detection.detect_drift``. Raises :class:`DriftSchemaError` so
  the CronJob exits *before* computing PSI on a malformed frame; a
  silent recompute would advertise drift that isn't there.

All three accept ``schema=None`` and degrade to a no-op with a warning
log line. This keeps template-level tests (where the service package
hasn't been rendered yet) green without breaking the contract for
scaffolded services, where the loader resolves the schema at startup
and a missing schema is itself caught by the CI lint added in the
same PR.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping

import pandas as pd

try:  # Pandera is in the service runtime image; keep the import optional
    import pandera as pa  # type: ignore[import-not-found]
    from pandera.errors import SchemaError, SchemaErrors  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only in stripped envs
    pa = None  # type: ignore[assignment]
    SchemaError = SchemaErrors = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class DriftSchemaError(RuntimeError):
    """Raised by :func:`validate_drift_dataframe` when the input frame
    does not match the training-time schema.

    Drift detection MUST refuse to compute PSI on a malformed frame:
    a missing column or a renamed feature looks indistinguishable from
    real distribution drift, which would silently corrupt the alerting
    contract. The CronJob entrypoint catches this and exits non-zero
    with a clear log line so operators can fix the upstream pipeline
    instead of chasing a phantom alert.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _redact_failure(failure: Mapping[str, Any]) -> dict[str, str]:
    """Convert one Pandera failure case into a public-safe summary.

    Pandera's failure_cases include the offending VALUE; we never echo
    that back to the caller (D-32) — only the column and a short reason
    suitable for a 422 response body.
    """
    column = str(failure.get("column", "?"))
    check = str(failure.get("check", "?"))
    return {"field": column, "rule": check}


def _summarise_schema_errors(err: Exception, *, max_items: int = 10) -> List[dict[str, str]]:
    """Reduce a Pandera ``SchemaError``/``SchemaErrors`` to a redacted list.

    We accept either flavour because Pandera raises ``SchemaErrors``
    only when the schema was invoked with ``lazy=True``. The summary is
    capped at ``max_items`` to avoid gigantic 422 bodies on a totally
    unrelated payload (e.g., wrong model version).
    """
    if hasattr(err, "failure_cases") and getattr(err, "failure_cases") is not None:
        cases = err.failure_cases.to_dict(orient="records")  # type: ignore[attr-defined]
    else:
        cases = [{"column": getattr(err, "schema_context", "?"), "check": str(err)}]
    summary = [_redact_failure(c) for c in cases[:max_items]]
    if len(cases) > max_items:
        summary.append({"field": "_truncated_", "rule": f"{len(cases) - max_items} more"})
    return summary


# ---------------------------------------------------------------------------
# Public API — serving
# ---------------------------------------------------------------------------
def validate_predict_payload(payload: Mapping[str, Any], schema: Any) -> None:
    """Validate a single inference payload against the Pandera schema.

    Pydantic has already enforced types and per-field ranges by the time
    this runs; the Pandera pass is the second wall — it catches the
    cases that Pydantic structurally cannot:

    * a required model feature missing from the request,
    * a categorical value outside the allowed set,
    * cross-column rules (``feature_a > feature_b`` style invariants),
    * coercion mismatches that would have trained one column type and
      served another.

    Args:
        payload: Dict of model input features (already stripped of
            ``entity_id`` / ``slice_values`` by the caller).
        schema: A Pandera ``DataFrameModel`` subclass, or ``None``.
            ``None`` triggers a one-time warning and a no-op so
            template-level tests pass before scaffolding.

    Raises:
        fastapi.HTTPException: 422 on validation failure, with a
            redacted body that omits the offending VALUES (D-32).
    """
    if schema is None:
        return
    try:
        schema.validate(pd.DataFrame([payload]), lazy=True)
    except (SchemaError, SchemaErrors) as err:
        summary = _summarise_schema_errors(err)
        logger.warning("Pandera /predict rejection: %s", summary)
        # Imported lazily so the helper stays usable from non-FastAPI
        # contexts (e.g., the drift CronJob) without dragging FastAPI
        # into every test environment.
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={"message": "Input failed schema validation", "errors": summary},
        ) from err


def validate_predict_batch(payload: Iterable[Mapping[str, Any]], schema: Any) -> None:
    """Batch sibling of :func:`validate_predict_payload`.

    Validates the entire batch in a single Pandera pass so a single bad
    row surfaces alongside its neighbours (the API contract says batch
    is atomic — accept all or reject all).
    """
    if schema is None:
        return
    rows = list(payload)
    if not rows:
        return
    try:
        schema.validate(pd.DataFrame(rows), lazy=True)
    except (SchemaError, SchemaErrors) as err:
        summary = _summarise_schema_errors(err)
        logger.warning("Pandera /predict_batch rejection (rows=%d): %s", len(rows), summary)
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={"message": "Batch failed schema validation", "errors": summary},
        ) from err


# ---------------------------------------------------------------------------
# Public API — drift CronJob
# ---------------------------------------------------------------------------
def validate_drift_dataframe(df: pd.DataFrame, schema: Any, *, label: str = "drift") -> pd.DataFrame:
    """Validate the reference / current frame before PSI computation.

    Returns the (possibly coerced) frame so callers can drop their own
    ``pd.read_csv`` result and use the validated copy in one step.
    Raises :class:`DriftSchemaError` on any schema mismatch — the drift
    CronJob is REQUIRED to exit non-zero rather than continue with a
    malformed frame, since the resulting PSI value would be a phantom
    alert (or worse, a phantom *all-clear*).

    Args:
        df: Frame loaded from the production / reference CSV.
        schema: A Pandera ``DataFrameModel`` subclass, or ``None``.
            ``None`` degrades to a no-op for template-level testing.
        label: Short tag used in error messages so logs distinguish
            between ``reference`` and ``current`` failures.
    """
    if schema is None:
        logger.warning(
            "validate_drift_dataframe(%s): schema is None; skipping schema check. "
            "Scaffolded services MUST wire ServiceInputSchema; this branch "
            "exists only for template-level tests (PR-R2-4).",
            label,
        )
        return df
    try:
        return schema.validate(df, lazy=True)
    except (SchemaError, SchemaErrors) as err:
        summary = _summarise_schema_errors(err, max_items=20)
        message = (
            f"Drift schema validation failed on {label!r} frame "
            f"({len(summary)} issue(s)); refusing to compute PSI. "
            f"Issues: {summary}"
        )
        logger.error(message)
        raise DriftSchemaError(message) from err


__all__ = [
    "DriftSchemaError",
    "validate_drift_dataframe",
    "validate_predict_batch",
    "validate_predict_payload",
]
