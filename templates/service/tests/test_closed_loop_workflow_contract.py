"""Contract test for golden-path-extended Stage 1 (PR-R2-9).

The closed-loop verification workflow posts a hardcoded JSON payload
against /predict in a freshly scaffolded service. If the workflow's
payload drifts from `PredictionRequest`'s required fields, Stage 1
silently posts garbage that gets 422'd 100 times and the closed-loop
counter assertion either:

  - false-passes (the previous fallback `requests_total{endpoint="/predict"}`
    matched NOTHING — silent green when nothing was actually verified)
  - false-fails (the schema legitimately rejects the payload, but the
    metric we read can't tell that from a real failure)

This contract test fails LOUD if the two drift apart, BEFORE Stage 1
runs. Cheap (parses two files, no scaffolding required).

Authority: ADR-016 §PR-R2-9, AGENTS.md D-32.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "golden-path-extended.yml"

# This module checks the TEMPLATE REPO's golden-path workflow. Inside a
# scaffolded service `parents[3]` walks above the service root and the
# workflow is absent, so every test here errored in the adopter's own repo.
# Skip the module there — it is a repo-only check living in the payload tree.
if not WORKFLOW.is_file():  # pragma: no cover — layout probe
    pytest.skip(
        "golden-path-extended.yml not found; this module checks the template "
        "repo's own workflow and does not apply to a scaffolded service",
        allow_module_level=True,
    )
SCHEMA = REPO_ROOT / "templates" / "service" / "app" / "schemas.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW.is_file(), f"PR-R2-9 violation: {WORKFLOW} missing"
    return WORKFLOW.read_text()


@pytest.fixture(scope="module")
def schema_text() -> str:
    assert SCHEMA.is_file(), f"PR-R2-9 violation: {SCHEMA} missing"
    return SCHEMA.read_text()


# ---------------------------------------------------------------------------
# 1. Payload field set matches schema required fields
# ---------------------------------------------------------------------------


def _required_pydantic_fields(text: str, model_name: str = "PredictionRequest") -> set[str]:
    """Extract field names declared with `Field(...,` (the `...` Ellipsis
    marker = required) inside the named Pydantic model."""
    # Find the class block
    cls_match = re.search(
        rf"^class {model_name}\(BaseModel\):.*?(?=^class |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not cls_match:
        return set()
    block = cls_match.group(0)
    # Match "<name>: <type> = Field(..., ..."
    return set(re.findall(r"^    ([a-z_][a-z0-9_]*)\s*:\s*[^=]+=\s*Field\(\s*\.\.\.", block, flags=re.MULTILINE))


def _payload_keys(workflow: str, var_name: str = "VALID_BODY") -> set[str]:
    """Extract top-level JSON keys from the bash assignment
    VALID_BODY='{"k1": ..., "k2": ...}' in the workflow.

    Uses json.loads so nested keys (e.g. slice_values.country) are
    correctly excluded.
    """
    import json

    m = re.search(rf"{var_name}='(\{{[^']+\}})'", workflow)
    if not m:
        return set()
    return set(json.loads(m.group(1)).keys())


def test_workflow_payload_includes_all_required_schema_fields(workflow_text: str, schema_text: str) -> None:
    """The valid payload posted by Stage 1 MUST include every field
    that PredictionRequest declares as required (Field(...,)).

    Drift here causes Stage 1 to 422-everything and the test to either
    false-pass via the fallback metric or fail without a useful signal.
    """
    required = _required_pydantic_fields(schema_text, "PredictionRequest")
    assert required, (
        "Sanity check failed: could not extract any required fields from PredictionRequest. Did the parser regex break?"
    )

    payload_keys = _payload_keys(workflow_text, "VALID_BODY")
    assert payload_keys, "VALID_BODY assignment not found in golden-path-extended.yml"

    missing = required - payload_keys
    extra = payload_keys - required - {"slice_values"}  # slice_values is optional but allowed

    assert not missing, (
        f"PR-R2-9 contract violation: golden-path-extended.yml VALID_BODY "
        f"is missing required schema fields: {sorted(missing)}. "
        f"Update the payload AND keep schemas.py json_schema_extra examples "
        f"in sync."
    )
    assert not extra, (
        f"PR-R2-9 contract violation: golden-path-extended.yml VALID_BODY "
        f"contains fields not declared in PredictionRequest: {sorted(extra)}. "
        f"Drift between schema and workflow."
    )


# ---------------------------------------------------------------------------
# 2. Metric label fallback is REAL (not the impossible endpoint=)
# ---------------------------------------------------------------------------


def test_workflow_does_not_use_impossible_metric_label(workflow_text: str) -> None:
    """The previous version of this workflow grepped for
    `requests_total{endpoint="/predict"}` — but the counter only has
    a `status` label (see fastapi_app.py:176). That fallback matched
    nothing and silently false-passed.

    Guard against the regression: the workflow MUST NOT match against
    `endpoint=` on requests_total.
    """
    # Find the awk fallback line(s) for requests_total
    fallback_lines = [line for line in workflow_text.splitlines() if "requests_total" in line and "endpoint=" in line]
    assert not fallback_lines, (
        "PR-R2-9 regression: golden-path-extended.yml uses an impossible "
        "label match on requests_total. Offending lines:\n"
        + "\n".join(f"  {ln.strip()}" for ln in fallback_lines)
        + "\n\nrequests_total has only the `status` label (see "
        "templates/service/app/fastapi_app.py:176). Match on status= instead."
    )


# ---------------------------------------------------------------------------
# 3. The workflow's metric selector matches a metric the app really exposes
# ---------------------------------------------------------------------------


def test_workflow_metric_selector_matches_a_declared_metric(workflow_text: str, schema_text: str) -> None:
    """The awk selector in the closed-loop proof must name a real metric.

    If it does not, `sum` stays 0, the workflow reports no predictions
    logged, and the closed-loop "proof" measures nothing — silently.

    This test previously asserted an awk fallback on `requests_total`, and
    `pytest.skip`ped when it was absent. The workflow dropped that fallback
    deliberately — its own comment says "Closed-loop proof requires
    prediction_log_total. A request counter alone proves HTTP traffic, not
    prediction logging." So the test was checking a contract the workflow had
    consciously replaced, and the skip meant nobody noticed for as long as it
    took someone to ask why it skipped.
    """
    fastapi_app = REPO_ROOT / "templates" / "service" / "app" / "fastapi_app.py"
    if not fastapi_app.is_file():
        pytest.skip(f"{fastapi_app} not present — skipping")
    app_text = fastapi_app.read_text()

    selectors = re.findall(r'\$1\s*~\s*"\^"svc"_(\w+)"', workflow_text)
    assert selectors, (
        "the closed-loop workflow has no awk metric selector of the form "
        '`$1 ~ "^"svc"_<metric>"`. Without one the proof step cannot sum a '
        "metric, and a green run would prove nothing."
    )

    for metric in sorted(set(selectors)):
        assert re.search(rf"\b{metric}\s*=\s*Counter\(", app_text), (
            f"the workflow sums `{metric}`, which fastapi_app.py does not declare "
            f"as a Counter. The selector would match nothing, sum would stay 0, "
            f"and the closed-loop proof would pass while measuring nothing."
        )
