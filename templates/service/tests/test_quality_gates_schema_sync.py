"""Behavioural-equivalence test: JSON Schema ↔ Pydantic model.

ADR-015 PR-B1 — keep ``configs/quality_gates.schema.json`` in lock-step
with ``{service}.config.QualityGatesConfig``.

We deliberately do NOT compare ``QualityGatesConfig.model_json_schema()``
output to the committed file byte-for-byte:

- Pydantic's schema export changes shape between minor versions
  (``$defs`` ordering, ``title`` casing, format hints).
- The committed schema is hand-written for tool ergonomics (richer
  descriptions, ``additionalProperties: false`` which Pydantic does not
  emit by default, custom regex anchors).

Instead, we run the SAME set of payloads through both validators and
assert they agree on every accept/reject decision. Drift then surfaces
as a concrete failing payload (e.g. "Pydantic accepted this but the
JSON Schema rejected it"), which is debuggable.

If you change a constraint, you change it in BOTH places; this test
fails until you do.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

# Resolve sibling module exactly the way the existing
# test_quality_gates_config.py does — keep the two tests symmetric.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_cfg_module = importlib.import_module("{service}.config")
QualityGatesConfig = _cfg_module.QualityGatesConfig

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "configs" / "quality_gates.schema.json"

# Each row is (label, payload, should_be_valid).
# Cover every constraint the schema declares so any drift surfaces here.
_CASES: list[tuple[str, dict[str, Any], bool]] = [
    (
        "minimal_valid",
        {
            "primary_metric": "roc_auc",
            "primary_threshold": 0.80,
            "secondary_metric": "f1",
            "secondary_threshold": 0.55,
            "protected_attributes": [],
        },
        True,
    ),
    (
        "full_valid",
        {
            "primary_metric": "roc_auc",
            "primary_threshold": 0.80,
            "secondary_metric": "f1",
            "secondary_threshold": 0.55,
            "fairness_threshold": 0.85,
            "latency_sla_ms": 250.0,
            "protected_attributes": ["gender", "age_group"],
            "promotion_threshold": 0.02,
        },
        True,
    ),
    ("missing_primary_metric", {
        "primary_threshold": 0.8,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }, False),
    ("missing_protected_attributes", {
        "primary_metric": "roc_auc",
        "primary_threshold": 0.8,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
    }, False),
    ("primary_threshold_too_high", {
        "primary_metric": "roc_auc",
        "primary_threshold": 1.5,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }, False),
    ("primary_threshold_negative", {
        "primary_metric": "roc_auc",
        "primary_threshold": -0.1,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }, False),
    ("latency_must_be_strictly_positive", {
        "primary_metric": "roc_auc",
        "primary_threshold": 0.8,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "latency_sla_ms": 0.0,
        "protected_attributes": [],
    }, False),
    ("metric_with_leading_space", {
        "primary_metric": " roc_auc",
        "primary_threshold": 0.8,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }, False),
    ("metric_with_trailing_space", {
        "primary_metric": "roc_auc",
        "primary_threshold": 0.8,
        "secondary_metric": "f1 ",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }, False),
    ("empty_metric_name", {
        "primary_metric": "",
        "primary_threshold": 0.8,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }, False),
    ("duplicate_protected_attributes", {
        "primary_metric": "roc_auc",
        "primary_threshold": 0.8,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": ["gender", "gender"],
    }, False),
    # PR-B3 — SplitConfig sub-block.
    # Both validators must accept all three legal strategies and reject
    # an unknown strategy / out-of-range fraction. ``acknowledge_iid``
    # is checked at runtime by ``validate_against_data`` (it's the
    # cross-config check), not at YAML-parse time, so a payload with
    # ``random`` + ``acknowledge_iid: false`` is structurally valid here.
    ("split_temporal", {
        "primary_metric": "roc_auc", "primary_threshold": 0.8,
        "secondary_metric": "f1", "secondary_threshold": 0.55,
        "protected_attributes": [],
        "split": {"strategy": "temporal", "timestamp_column": "ts", "test_fraction": 0.25},
    }, True),
    ("split_grouped", {
        "primary_metric": "roc_auc", "primary_threshold": 0.8,
        "secondary_metric": "f1", "secondary_threshold": 0.55,
        "protected_attributes": [],
        "split": {"strategy": "grouped", "entity_id_column": "customer_id"},
    }, True),
    ("split_random_with_ack", {
        "primary_metric": "roc_auc", "primary_threshold": 0.8,
        "secondary_metric": "f1", "secondary_threshold": 0.55,
        "protected_attributes": [],
        "split": {"strategy": "random", "acknowledge_iid": True},
    }, True),
    ("split_unknown_strategy", {
        "primary_metric": "roc_auc", "primary_threshold": 0.8,
        "secondary_metric": "f1", "secondary_threshold": 0.55,
        "protected_attributes": [],
        "split": {"strategy": "temproal"},  # typo
    }, False),
    ("split_test_fraction_out_of_range", {
        "primary_metric": "roc_auc", "primary_threshold": 0.8,
        "secondary_metric": "f1", "secondary_threshold": 0.55,
        "protected_attributes": [],
        "split": {"strategy": "random", "acknowledge_iid": True, "test_fraction": 1.5},
    }, False),
    ("split_unknown_field", {
        "primary_metric": "roc_auc", "primary_threshold": 0.8,
        "secondary_metric": "f1", "secondary_threshold": 0.55,
        "protected_attributes": [],
        "split": {"strategy": "random", "acknowledge_iid": True, "extraneous": True},
    }, False),
]


@pytest.fixture(scope="module")
def jsonschema_validator() -> Draft202012Validator:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pydantic_accepts(payload: dict[str, Any]) -> bool:
    try:
        QualityGatesConfig(**payload)
    except ValidationError:
        return False
    return True


def _jsonschema_accepts(validator: Draft202012Validator, payload: dict[str, Any]) -> bool:
    return validator.is_valid(payload)


def test_schema_file_exists_and_is_valid_jsonschema() -> None:
    """The committed schema file must itself be a legal Draft 2020-12 schema."""
    assert _SCHEMA_PATH.exists(), f"missing {_SCHEMA_PATH}"
    with _SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("label,payload,should_be_valid", _CASES, ids=[c[0] for c in _CASES])
def test_schema_and_pydantic_agree(
    jsonschema_validator: Draft202012Validator,
    label: str,
    payload: dict[str, Any],
    should_be_valid: bool,
) -> None:
    """Pydantic and the committed JSON Schema must give identical verdicts.

    A divergence here means somebody loosened a constraint in one place
    and forgot the other. Whichever is stricter wins; tighten the
    looser one and bump the description so adopters see the change.
    """
    py_ok = _pydantic_accepts(payload)
    js_ok = _jsonschema_accepts(jsonschema_validator, payload)

    assert py_ok == should_be_valid, (
        f"[{label}] Pydantic verdict {py_ok!r} != expected {should_be_valid!r}"
    )
    assert js_ok == should_be_valid, (
        f"[{label}] JSON Schema verdict {js_ok!r} != expected {should_be_valid!r}"
    )
    # Redundant given the two asserts above, but makes the failure
    # message obvious when adding new cases:
    assert py_ok == js_ok, (
        f"[{label}] Pydantic={py_ok} but JSONSchema={js_ok} — schemas have drifted"
    )


def test_committed_template_yaml_passes_both_validators(
    jsonschema_validator: Draft202012Validator,
) -> None:
    """The template's own configs/quality_gates.yaml must validate cleanly.

    Catches the trivial regression where editing the YAML breaks the
    contract its own schema declares.
    """
    yaml_path = Path(__file__).resolve().parent.parent / "configs" / "quality_gates.yaml"
    with yaml_path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)

    assert isinstance(payload, dict), f"{yaml_path}: top-level must be a mapping"
    assert _jsonschema_accepts(jsonschema_validator, payload), (
        f"{yaml_path} fails JSON Schema validation"
    )
    QualityGatesConfig(**payload)  # Pydantic; raises on failure.
