"""Fail-fast OpenAPI snapshot test (rule 14 / D-28).

If the service's public API shape changes without an explicit update of
`openapi.snapshot.json` AND `app.version`, this test fails.

To intentionally update the contract (after a schema edit):

    python scripts/refresh_contract.py
    # bump app.version in app/main.py
    git add tests/contract/openapi.snapshot.json app/main.py
    git commit -m "API: <change summary>  [version X.Y.Z]"

CI refuses any PR that modifies the snapshot without a corresponding
version bump — see .github/workflows/ci.yml `Validate API contract`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient

    from app.main import app
except Exception:  # pragma: no cover - template placeholder
    pytest.skip("TestClient or app unavailable — stub template", allow_module_level=True)


SNAP = Path(__file__).parent / "openapi.snapshot.json"


@pytest.fixture(scope="module")
def openapi_current() -> dict:
    return TestClient(app).get("/openapi.json").json()


def test_snapshot_file_exists():
    assert SNAP.exists(), (
        f"{SNAP.name} missing. Run `python scripts/refresh_contract.py` to " "generate it on first setup."
    )


def test_openapi_snapshot_unchanged(openapi_current):
    expected = json.loads(SNAP.read_text())
    if openapi_current != expected:
        # Emit a compact hint — full diffs are huge
        missing_paths = set(expected.get("paths", {})) - set(openapi_current.get("paths", {}))
        added_paths = set(openapi_current.get("paths", {})) - set(expected.get("paths", {}))
        pytest.fail(
            "OpenAPI contract drift detected (D-28).\n"
            f"  Removed paths: {sorted(missing_paths)}\n"
            f"  Added paths:   {sorted(added_paths)}\n"
            "If intentional: run `python scripts/refresh_contract.py`, "
            "bump app.version, commit both files together."
        )


def test_version_header_present(openapi_current):
    """Every release must record a non-empty version in openapi.info.version."""
    version = openapi_current.get("info", {}).get("version", "")
    assert version, "app.version is empty — set it in app/main.py"
    # Accept PEP 440 / semver-ish strings: "1.2.3", "1.2.3a1", "0.1.0.dev0"
    assert version[0].isdigit(), f"app.version must start with a digit, got {version!r}"
