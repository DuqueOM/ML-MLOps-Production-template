"""Contract tests for ADR-018 Phase 1 — MemoryUnit + redaction.

Status: Phase 1 — contracts and redaction only.

Invariants exercised:

A. **Frozen** — `MemoryUnit` is immutable; setattr raises.
B. **id MUST be UUID**.
C. **summary non-empty + bounded**.
D. **severity / kind / sensitivity must be enum instances**.
E. **sensitivity ≥ bucket minimum** (no PUBLIC label on RESTRICTED bucket).
F. **evidence_uri must include scheme**.
G. **tenant_key must be 'default' in Phase 1**.
H. **timestamp must be ISO 8601 UTC**.
I. **Round-trip** — `to_dict()` produces stable wire format.
J. **No /predict path coupling** — `service/` Python files do not import
   `common_utils.memory_types` (structural enforcement of ADR-018
   "Not in the synchronous /predict path").

Authority: ADR-018 §"Phase plan", ADR-020 §S2-1.
"""

from __future__ import annotations

import dataclasses
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# common_utils sits at the service root — templates/service/ in this repo,
# the repo root in a scaffolded service; parents[1] is that root in both.
# Adding it to sys.path lets `import common_utils.memory_types` resolve
# without repo-wide pyproject.toml pythonpath configuration. It pointed at
# templates/ until ADR-030 moved the tree in June 2026.
_TEMPLATES_DIR = Path(__file__).resolve().parents[1]
if (_TEMPLATES_DIR / "common_utils" / "__init__.py").exists() and str(_TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(_TEMPLATES_DIR))

from common_utils.memory_types import (  # noqa: E402  type: ignore[import-not-found]
    DEFAULT_BUCKET_MIN_SENSITIVITY,
    SENSITIVITY_RANK,
    MemoryKind,
    MemoryUnit,
    Sensitivity,
    Severity,
    minimum_sensitivity_for_uri,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make(**overrides) -> MemoryUnit:
    base = dict(
        id=str(uuid.uuid4()),
        kind=MemoryKind.INCIDENT_POSTMORTEM,
        summary="Drift event in fraud_detector after upstream payload change.",
        evidence_uri="s3://incidents/2026/04/29/incident-001.md",
        severity=Severity.HIGH,
        sensitivity=Sensitivity.RESTRICTED,
        tenant_key="default",
        human_authored=False,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    base.update(overrides)
    return MemoryUnit(**base)


# ---------------------------------------------------------------------------
# A — frozen
# ---------------------------------------------------------------------------


def test_memory_unit_is_frozen() -> None:
    unit = _make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        unit.summary = "tamper"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# B — id must be UUID
# ---------------------------------------------------------------------------


def test_id_must_be_uuid() -> None:
    with pytest.raises(ValueError, match="must be a UUID"):
        _make(id="not-a-uuid")


def test_id_uuid_round_trip() -> None:
    unit = _make()
    # Should not raise.
    uuid.UUID(unit.id)


# ---------------------------------------------------------------------------
# C — summary
# ---------------------------------------------------------------------------


def test_summary_non_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _make(summary="")
    with pytest.raises(ValueError, match="non-empty"):
        _make(summary="    ")


def test_summary_bounded() -> None:
    with pytest.raises(ValueError, match="2000-char"):
        _make(summary="x" * 2_001)


# ---------------------------------------------------------------------------
# D — enum types
# ---------------------------------------------------------------------------


def test_severity_must_be_enum() -> None:
    with pytest.raises(TypeError, match="severity must be Severity"):
        _make(severity="critical")  # raw string forbidden


def test_kind_must_be_enum() -> None:
    with pytest.raises(TypeError, match="kind must be MemoryKind"):
        _make(kind="incident_postmortem")


def test_sensitivity_must_be_enum() -> None:
    with pytest.raises(TypeError, match="sensitivity must be Sensitivity"):
        _make(sensitivity="restricted")


# ---------------------------------------------------------------------------
# E — sensitivity ≥ bucket minimum
# ---------------------------------------------------------------------------


def test_sensitivity_below_bucket_minimum_rejected() -> None:
    # incidents bucket → minimum RESTRICTED. PUBLIC label MUST be refused.
    with pytest.raises(ValueError, match="below the minimum"):
        _make(
            evidence_uri="s3://incidents/2026/04/01/p1.md",
            sensitivity=Sensitivity.PUBLIC,
        )


def test_sensitivity_at_bucket_minimum_accepted() -> None:
    unit = _make(
        evidence_uri="s3://audit/audit.jsonl",
        sensitivity=Sensitivity.CONFIDENTIAL,
    )
    assert unit.sensitivity is Sensitivity.CONFIDENTIAL


def test_sensitivity_above_bucket_minimum_accepted() -> None:
    unit = _make(
        evidence_uri="s3://public/blog.md",
        sensitivity=Sensitivity.INTERNAL,  # bucket min PUBLIC, label INTERNAL
    )
    assert unit.sensitivity is Sensitivity.INTERNAL


def test_unknown_bucket_defaults_to_internal() -> None:
    assert minimum_sensitivity_for_uri("file:///tmp/foo.md") is Sensitivity.INTERNAL


def test_sensitivity_rank_strict_ordering() -> None:
    ranks = list(SENSITIVITY_RANK.values())
    assert ranks == sorted(ranks)  # strictly increasing
    assert SENSITIVITY_RANK[Sensitivity.PUBLIC] < SENSITIVITY_RANK[Sensitivity.RESTRICTED]


# ---------------------------------------------------------------------------
# F — evidence_uri must include scheme
# ---------------------------------------------------------------------------


def test_evidence_uri_must_have_scheme() -> None:
    with pytest.raises(ValueError, match="scheme"):
        _make(evidence_uri="/tmp/foo.md")


# ---------------------------------------------------------------------------
# G — tenant_key Phase 1 only 'default'
# ---------------------------------------------------------------------------


def test_tenant_key_phase1_only_default() -> None:
    with pytest.raises(ValueError, match="Phase 1 only accepts"):
        _make(tenant_key="acme-corp")


# ---------------------------------------------------------------------------
# H — timestamp ISO 8601 UTC
# ---------------------------------------------------------------------------


def test_timestamp_must_be_iso_utc() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        _make(timestamp="not-a-timestamp")


def test_timestamp_must_be_utc() -> None:
    naive = datetime(2026, 4, 29, 10, 0, 0).isoformat()
    with pytest.raises(ValueError, match="UTC"):
        _make(timestamp=naive)


# ---------------------------------------------------------------------------
# I — to_dict round-trip wire format
# ---------------------------------------------------------------------------


def test_to_dict_emits_string_enum_values() -> None:
    unit = _make()
    d = unit.to_dict()
    assert d["kind"] == "incident_postmortem"
    assert d["severity"] == "high"
    assert d["sensitivity"] == "restricted"
    assert d["tenant_key"] == "default"
    assert d["human_authored"] is False
    # Wire format includes id + timestamp as strings.
    assert isinstance(d["id"], str)
    assert isinstance(d["timestamp"], str)


def test_factory_new_fills_defaults() -> None:
    unit = MemoryUnit.new(
        kind=MemoryKind.DRIFT_EVENT,
        summary="PSI breach on amount feature",
        evidence_uri="s3://audit/drift/2026-04-29.json",
        severity=Severity.WARN,
    )
    # sensitivity defaulted from bucket minimum (audit → confidential).
    assert unit.sensitivity is Sensitivity.CONFIDENTIAL
    assert unit.tenant_key == "default"
    assert unit.human_authored is False
    # timestamp parses as UTC.
    parsed = datetime.fromisoformat(unit.timestamp)
    assert parsed.utcoffset() is not None


# ---------------------------------------------------------------------------
# J — structural: no /predict path coupling
# ---------------------------------------------------------------------------


def test_no_service_python_imports_memory_types() -> None:
    """Phase 1 invariant: serving / training Python MUST NOT import
    `common_utils.memory_types`. The plane is a companion, not a runtime
    dependency of /predict.
    """
    # parents[1] is the service root in BOTH layouts: templates/service/ in
    # the template repo, the repo root in a scaffolded service. This used to
    # hard-code REPO_ROOT/"templates"/"service", which does not exist inside
    # an adopter's service — so the invariant silently SKIPPED in exactly the
    # environment it exists to protect.
    service_root = Path(__file__).resolve().parents[1]
    if not (service_root / "app").is_dir():  # pragma: no cover
        pytest.skip(f"no service tree at {service_root}")

    pat = re.compile(
        r"\bfrom\s+common_utils\.memory_types\b|\bimport\s+common_utils\.memory_types\b"
        r"|\bfrom\s+common_utils\.memory_redaction\b|\bimport\s+common_utils\.memory_redaction\b"
    )
    offenders: list[Path] = []
    for path in service_root.rglob("*.py"):
        if "/tests/" in str(path):
            continue  # test files may import memory modules — that's fine
        # Skip the memory plane modules themselves — they reference
        # their own import path in docstrings but are not serving/training.
        if path.name in ("memory_types.py", "memory_redaction.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if pat.search(text):
            offenders.append(path)

    assert not offenders, (
        f"Phase 1 invariant violated: serving/training files import memory plane: "
        f"{[str(p.relative_to(_TEMPLATES_DIR)) for p in offenders]}"
    )


def test_default_bucket_map_includes_known_buckets() -> None:
    """Sanity check on the canonical bucket → minimum-sensitivity table."""
    assert DEFAULT_BUCKET_MIN_SENSITIVITY["s3://incidents/"] is Sensitivity.RESTRICTED
    assert DEFAULT_BUCKET_MIN_SENSITIVITY["gs://audit/"] is Sensitivity.CONFIDENTIAL
    assert DEFAULT_BUCKET_MIN_SENSITIVITY["s3://public/"] is Sensitivity.PUBLIC
