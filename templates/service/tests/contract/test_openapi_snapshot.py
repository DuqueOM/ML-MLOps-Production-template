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
import os
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient

    from app.main import app
except Exception:  # pragma: no cover - template placeholder
    pytest.skip("TestClient or app unavailable — stub template", allow_module_level=True)


SNAP = Path(__file__).parent / "openapi.snapshot.json"

# `CI` is set by GitHub Actions and every other mainstream runner.
_IN_CI = os.environ.get("CI", "").lower() in {"1", "true", "yes"}

# The snapshot is the service's API contract, and it does not exist in the
# template repo — there is no service to snapshot until one is rendered.
#
# It used to be an instruction: run `scripts/refresh_contract.py` on first
# setup. Nothing enforced that, so an adopter's very first `pytest` was two
# hard failures about a file they had never been told about at that moment,
# and until someone read the message the D-28 contract was simply not being
# checked. The service's own `ci.yml` only compares the snapshot when it
# *changes*, so a missing one is invisible there too.
#
# So: locally, the first run writes the baseline from the live app and skips,
# saying to commit it — the standard snapshot-test bootstrap, and from the
# second run onward the comparison is real. In CI a missing baseline stays a
# failure, because a machine must never invent the contract it is supposed to
# be guarding.
pytestmark = pytest.mark.scaffold_context


@pytest.fixture(scope="module")
def openapi_current() -> dict:
    return TestClient(app).get("/openapi.json").json()


def test_snapshot_file_exists(openapi_current):
    if SNAP.exists():
        return
    if _IN_CI:
        pytest.fail(
            f"{SNAP.name} is missing. The API contract (D-28) is unenforced without it, "
            f"and CI will not create one: run `python scripts/refresh_contract.py` "
            f"locally and commit the result."
        )
    SNAP.write_text(json.dumps(openapi_current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pytest.skip(
        f"{SNAP.name} did not exist; wrote the baseline from the running app. "
        f"Review it and commit it — from the next run this test compares against it."
    )


def test_openapi_snapshot_unchanged(openapi_current):
    if not SNAP.exists():
        # Only reachable when the bootstrap above skipped; comparing the live
        # app against a file just written from the live app would pass while
        # checking nothing.
        pytest.skip(f"{SNAP.name} was created in this run — commit it, then this compares.")
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
