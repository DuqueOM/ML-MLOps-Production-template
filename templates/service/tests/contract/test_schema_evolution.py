"""Detect breaking changes in the API contract (rule 14 / D-28).

Complements `test_openapi_snapshot.py`:
- `test_openapi_snapshot.py` fails on ANY divergence from the snapshot.
- `test_schema_evolution.py` runs ONLY when the snapshot has been
  intentionally updated in this PR. It then classifies the change as
  ADDITIVE (minor/patch bump) or BREAKING (major bump required).

Breaking-change taxonomy (rule 14 §semver):
  * Path removed
  * Required request field added
  * Required response field removed
  * Type narrowed on an existing field (e.g. ``str`` → ``int``)
  * Enum value removed

Additive (non-breaking):
  * New path
  * New optional request field
  * New response field (clients ignore unknown)
  * Enum value added
  * Description-only change

Run::

    pytest tests/contract/test_schema_evolution.py -v

The test reads the current `openapi.snapshot.json` and the previous
version from git (HEAD~1) so it can diff. If git history is not
available (fresh clone, CI without fetch-depth=2) it self-skips —
the snapshot test still catches drift.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SNAP = Path(__file__).parent / "openapi.snapshot.json"


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------
def _previous_snapshot() -> dict | None:
    """Read the previous committed snapshot via ``git show HEAD~1``.

    Returns None if git is unavailable, the file did not exist in the
    previous commit, or the parent commit is not reachable. None
    triggers a pytest skip — non-fatal.
    """
    if shutil.which("git") is None:
        return None
    try:
        rel = SNAP.relative_to(Path.cwd())
    except ValueError:
        rel = SNAP
    try:
        out = subprocess.check_output(
            ["git", "show", f"HEAD~1:{rel}"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------
def _paths(spec: dict) -> set[str]:
    return set(spec.get("paths", {}).keys())


def _required_fields(schema: dict, name: str) -> set[str]:
    """Required fields of a component schema, by name."""
    components = schema.get("components", {}).get("schemas", {})
    s = components.get(name, {})
    return set(s.get("required", []))


def _schema_names(spec: dict) -> set[str]:
    return set(spec.get("components", {}).get("schemas", {}).keys())


def _field_type(spec: dict, schema_name: str, field: str) -> str | None:
    """Return the declared type of a field, or None if absent."""
    s = spec.get("components", {}).get("schemas", {}).get(schema_name, {})
    props = s.get("properties", {})
    field_def = props.get(field)
    if not isinstance(field_def, dict):
        return None
    # Pydantic v2 emits anyOf for optional fields; first non-null branch is the type.
    if "type" in field_def:
        return field_def["type"]
    if "anyOf" in field_def:
        for branch in field_def["anyOf"]:
            if isinstance(branch, dict) and branch.get("type") and branch["type"] != "null":
                return branch["type"]
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def current() -> dict:
    if not SNAP.exists():
        pytest.skip("openapi.snapshot.json missing — run scripts/refresh_contract.py first")
    return json.loads(SNAP.read_text())


@pytest.fixture(scope="module")
def previous() -> dict:
    prev = _previous_snapshot()
    if prev is None:
        pytest.skip(
            "Previous snapshot unavailable (no git history or first commit). "
            "Schema-evolution check is non-fatal in this case; the snapshot "
            "test in test_openapi_snapshot.py still guards drift."
        )
    return prev


def test_no_path_removed(previous: dict, current: dict) -> None:
    """Removing a path is BREAKING — bump major or restore the path."""
    removed = _paths(previous) - _paths(current)
    assert not removed, (
        f"BREAKING: path(s) removed: {sorted(removed)}. " "Either restore them or bump app.version major (X.0.0)."
    )


def test_no_required_request_field_added(previous: dict, current: dict) -> None:
    """Adding a required request field BREAKS existing clients."""
    breakages: list[str] = []
    for name in _schema_names(previous) & _schema_names(current):
        added = _required_fields(current, name) - _required_fields(previous, name)
        if added:
            breakages.append(f"{name}: +{sorted(added)}")
    assert not breakages, (
        "BREAKING: required request field(s) added: " f"{breakages}. Either make them optional or bump major."
    )


def test_no_required_response_field_removed(previous: dict, current: dict) -> None:
    """Removing a required response field BREAKS existing clients
    that depend on the field being present."""
    breakages: list[str] = []
    for name in _schema_names(previous) & _schema_names(current):
        removed = _required_fields(previous, name) - _required_fields(current, name)
        if removed:
            breakages.append(f"{name}: -{sorted(removed)}")
    assert not breakages, "BREAKING: required response field(s) removed: " f"{breakages}. Either restore or bump major."


def test_no_field_type_narrowed(previous: dict, current: dict) -> None:
    """Changing a field's declared type is BREAKING for typed clients."""
    narrowings: list[str] = []
    for name in _schema_names(previous) & _schema_names(current):
        prev_props = previous.get("components", {}).get("schemas", {}).get(name, {}).get("properties", {})
        for field in prev_props:
            prev_t = _field_type(previous, name, field)
            curr_t = _field_type(current, name, field)
            if prev_t and curr_t and prev_t != curr_t:
                narrowings.append(f"{name}.{field}: {prev_t} -> {curr_t}")
    assert not narrowings, "BREAKING: field type changed: " f"{narrowings}. Either revert or bump major."


def test_version_bump_when_contract_changed(previous: dict, current: dict) -> None:
    """If the contract changed AT ALL since HEAD~1, app.version must
    be different too. Catches the case where someone runs
    refresh_contract.py and forgets the version bump."""
    contract_changed = previous != current
    if not contract_changed:
        pytest.skip("Snapshot unchanged — nothing to validate")
    prev_version = previous.get("info", {}).get("version", "")
    curr_version = current.get("info", {}).get("version", "")
    assert curr_version != prev_version, (
        f"Snapshot changed but app.version is still {curr_version!r}. " "Bump it in app/main.py per rule 14 §semver."
    )


def _is_compatible_minor_bump(prev_v: str, curr_v: str) -> bool:
    """Return True iff curr_v is a compatible (minor/patch) bump of prev_v."""

    def _parts(v: str) -> tuple[int, int, int] | None:
        head = v.split("+")[0].split("-")[0]
        bits = head.split(".")
        try:
            return (int(bits[0]), int(bits[1]) if len(bits) > 1 else 0, int(bits[2]) if len(bits) > 2 else 0)
        except (ValueError, IndexError):
            return None

    p, c = _parts(prev_v), _parts(curr_v)
    if p is None or c is None:
        return True  # cannot evaluate; do not block
    return c[0] == p[0] and (c[1] > p[1] or (c[1] == p[1] and c[2] > p[2]))


def test_additive_changes_get_minor_bump(previous: dict, current: dict) -> None:
    """If the only changes are ADDITIVE (new optional path/field), the
    bump should be minor or patch, not major. Catches over-versioning
    (a major bump shouts 'breaking' to consumers when nothing broke)."""
    contract_changed = previous != current
    if not contract_changed:
        pytest.skip("Snapshot unchanged")

    breaking_signals = (
        _paths(previous) - _paths(current),  # path removed
        # other breaking checks happen in dedicated tests above; here we
        # only test the version-bump shape, not classify breakages
    )
    if any(breaking_signals):
        pytest.skip("Breaking change present — major bump expected, handled by other tests")

    prev_v = previous.get("info", {}).get("version", "0.0.0")
    curr_v = current.get("info", {}).get("version", "0.0.0")
    if not _is_compatible_minor_bump(prev_v, curr_v):
        pytest.fail(
            f"Contract changes are additive but version went {prev_v} -> {curr_v}. "
            "Use a minor or patch bump for additive changes."
        )
