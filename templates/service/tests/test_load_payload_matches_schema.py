"""Contract test — Locust payload <-> Pydantic schema parity (R5-M4).

This test enforces that the load test (``templates/service/tests/load_test.py``)
sends payloads that the live API (``templates/service/app/schemas.py``)
will actually accept. Without this contract, load tests can drift to
hitting validation errors and report misleading latency / RPS numbers.

The test imports both modules and validates the load test's
``SAMPLE_PAYLOAD`` against ``PredictionRequest`` and ``BATCH_PAYLOAD``
against ``BatchPredictionRequest``. If a future change to ``schemas.py``
renames or adds a required field, the load test must be updated in the
same commit; this test catches the drift at PR-time, not at first
real load run.

Authority: ACTION_PLAN_R5 §R5-M4.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The load test + schema modules live at the service root. Add it to
# sys.path so `import app.schemas` and `import tests.load_test` resolve
# regardless of pytest's rootdir. Addressed relatively, so this works
# identically in the template repo and in a generated service — it used
# to climb to the repo root and come back down through `templates/service`,
# a path an adopter does not have.
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))


# Importing locust gevent-monkey-patches ssl/socket process-wide, which
# deadlocks anyio/TestClient lifespans in any test that runs AFTER this
# module in the same pytest process (observed: suite hung in epoll_wait).
# The marker routes this module to its OWN pytest invocation in the
# template-context CI lane; never run it in-process with TestClient tests.
pytestmark = pytest.mark.locust_parity

# Locust is an optional dev dep. The file imports it transitively. If it
# is not installed (or its install is broken in the current env, which
# happens when urllib3/ssl on Python 3.13 recurses on locust 2.43.x), we
# skip rather than fail — CI installs a known-good locust version.
try:  # pragma: no cover — environment probe
    import locust  # noqa: F401
except Exception as _import_err:  # noqa: BLE001 — broad on purpose
    pytest.skip(
        f"locust unavailable in this env ({_import_err.__class__.__name__}); "
        "test runs in CI with a pinned locust install.",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def schemas_mod():
    return pytest.importorskip("app.schemas")


@pytest.fixture(scope="module")
def load_test_mod():
    """Import the load test module without instantiating Locust users."""
    import importlib

    return importlib.import_module("tests.load_test")


def test_sample_payload_validates_against_prediction_request(schemas_mod, load_test_mod) -> None:
    """``SAMPLE_PAYLOAD`` must construct a valid ``PredictionRequest``."""
    schemas_mod.PredictionRequest(**load_test_mod.SAMPLE_PAYLOAD)


def test_batch_payload_validates_against_batch_request(schemas_mod, load_test_mod) -> None:
    """``BATCH_PAYLOAD`` must construct a valid ``BatchPredictionRequest``."""
    schemas_mod.BatchPredictionRequest(**load_test_mod.BATCH_PAYLOAD)


def test_batch_uses_canonical_customers_key(load_test_mod) -> None:
    """The batch wrapper key must be ``customers`` (per
    ``BatchPredictionRequest.customers``), not the legacy ``instances``
    that earlier versions of this load test used. This is the specific
    drift R5-M4 was opened to prevent.
    """
    assert "customers" in load_test_mod.BATCH_PAYLOAD, (
        "Locust BATCH_PAYLOAD must use 'customers' (canonical schema key); "
        f"got keys={list(load_test_mod.BATCH_PAYLOAD)!r}"
    )
    assert "instances" not in load_test_mod.BATCH_PAYLOAD, (
        "Legacy 'instances' key is forbidden — would silently 4xx in load runs."
    )


def test_batch_entity_ids_are_unique(load_test_mod) -> None:
    """Each batch entry must carry a unique ``entity_id``. Closed-loop
    monitoring (D-20) joins predictions to ground-truth labels via
    ``entity_id``; collapsed ids would corrupt the offline metrics
    pipeline.
    """
    customers = load_test_mod.BATCH_PAYLOAD["customers"]
    ids = [c["entity_id"] for c in customers]
    assert len(set(ids)) == len(ids), (
        "BATCH_PAYLOAD has duplicate entity_id values; closed-loop join (D-20) would collapse rows. Got: " + repr(ids)
    )


def test_sample_payload_carries_entity_id(load_test_mod) -> None:
    """``entity_id`` is the join key required by ADR-006 and is mandatory
    in the canonical schema. Forgetting it is the most common drift
    when contributors copy this file from older templates."""
    assert "entity_id" in load_test_mod.SAMPLE_PAYLOAD, (
        "SAMPLE_PAYLOAD must include 'entity_id' (D-20 closed-loop join key)."
    )
