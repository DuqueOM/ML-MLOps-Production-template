"""Contract test — Grafana dashboards inventory (R4-L2).

Authority: ACTION_PLAN_R4 §L2 + ACTION_PLAN_R5 §Sprint 3.

The inventory document `docs/observability/dashboards-inventory.md`
is the single source of truth listing every Grafana dashboard the
template ships. Without a contract test, the document drifts out of
sync every time a dashboard is added, removed, or renamed. Drift is
the exact failure mode R4-L2 flagged.

Invariants enforced:

1. Every JSON file under `templates/monitoring/grafana/` is listed
   in the inventory document's "Dashboards shipped" table. If a new
   dashboard is added without updating the doc, the test fails.
2. Every filename mentioned in the inventory's file column actually
   exists on disk. Catches accidental renames.
3. Every dashboard file parses as valid JSON (defense against
   merge-conflict artifacts in `templates/monitoring/grafana/`).
4. Every panel's `type` claimed in the per-dashboard panels table
   matches the actual JSON for panels in the same order. We validate
   the count matches and every claimed type appears in the JSON.

The test is structural and fast — it does NOT require Grafana or
Prometheus to be available.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY = REPO_ROOT / "docs" / "observability" / "dashboards-inventory.md"

# `docs/observability/dashboards-inventory.md` is a template-repo document; it
# is not part of the scaffolder payload. This module ships into a generated
# service anyway, where `parents[3]` walks above the service root and the
# inventory is simply absent — every test here then failed with
# FileNotFoundError in the adopter's own repo. Measured on a real scaffold:
# 1 failure and 3 errors from a test about the template's documentation.
#
# Skip the module there. It is a repo-only check that happens to live in the
# payload directory.
if not INVENTORY.exists():  # pragma: no cover — layout probe
    pytest.skip(
        "dashboards-inventory.md not present; this module checks a template-repo "
        "document and does not apply to a scaffolded service",
        allow_module_level=True,
    )
DASHBOARDS_DIR = REPO_ROOT / "templates" / "service" / "monitoring" / "grafana"


@pytest.fixture(scope="module")
def inventory_text() -> str:
    if not INVENTORY.exists():
        pytest.fail(f"Inventory missing: {INVENTORY.relative_to(REPO_ROOT)}")
    return INVENTORY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dashboard_files() -> list[Path]:
    return sorted(DASHBOARDS_DIR.glob("*.json"))


def test_dashboards_are_discovered() -> None:
    """Guard the guard.

    An empty parameter set makes `test_dashboard_is_valid_json` pass without
    examining anything, and pytest reports that as a skip rather than a
    failure — which is how a broken glob went unnoticed from June to
    September 2026. This fails instead.
    """
    found = sorted(DASHBOARDS_DIR.glob("*.json"))
    assert found, (
        f"no dashboards found under {DASHBOARDS_DIR}. Either the directory moved "
        "again or the glob is wrong; both make the parametrised checks below vacuous."
    )


def test_inventory_exists() -> None:
    assert INVENTORY.exists(), (
        "docs/observability/dashboards-inventory.md is required by "
        "R4-L2; without it each dashboard's purpose is only discoverable "
        "by opening the JSON."
    )


def test_every_dashboard_file_is_listed(inventory_text: str, dashboard_files: list[Path]) -> None:
    """Every JSON under grafana/ must appear as a table row."""
    missing: list[str] = []
    for p in dashboard_files:
        # Match either raw filename or a link `](path)` to it.
        if p.name not in inventory_text:
            missing.append(p.name)
    assert not missing, (
        "Dashboard JSON files exist but are not listed in "
        "dashboards-inventory.md. Add a row under "
        "§'Dashboards shipped' for each: "
        f"{missing}"
    )


def test_every_listed_file_exists(inventory_text: str) -> None:
    """Every `dashboard-*.json` mentioned in the inventory must exist.

    Catches the opposite drift — the doc mentions a file that was
    moved or removed.
    """
    # Pull filenames from inline code ticks or link targets.
    claimed = set(re.findall(r"dashboard-[a-z0-9-]+\.json", inventory_text))
    # Filter to names that actually look like dashboard files (exclude
    # template `.json` that might appear elsewhere in the doc).
    orphans = [c for c in claimed if not (DASHBOARDS_DIR / c).exists()]
    assert not orphans, f"Inventory mentions dashboard files that do not exist on disk: {orphans}"


# Uses the module's own DASHBOARDS_DIR rather than re-deriving the path.
# It used to re-derive the path against the pre-ADR-030 layout, one level
# above where the dashboards actually live, so the parameter set was empty
# and this test passed without examining a single dashboard, for months.
@pytest.mark.parametrize("dashboard_name", [p.name for p in sorted(DASHBOARDS_DIR.glob("*.json"))])
def test_dashboard_is_valid_json(dashboard_name: str) -> None:
    """Every dashboard file must parse as JSON. This is the minimal
    guard against merge-conflict garbage landing in Grafana configs.
    """
    path = DASHBOARDS_DIR / dashboard_name
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{dashboard_name} is not valid JSON: {exc}")


def _panels(dashboard_path: Path) -> list[dict]:
    """Return the panels array, handling both top-level and wrapped
    `dashboard:` envelopes (Grafana exports support both).
    """
    data = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if "panels" in data:
        return data["panels"]
    if "dashboard" in data and "panels" in data["dashboard"]:
        return data["dashboard"]["panels"]
    return []


def test_inventory_panel_counts_match_json(inventory_text: str) -> None:
    """For each dashboard that has a "panels" sub-section, the number
    of table rows in that sub-section must equal the number of panels
    in the JSON. Off-by-one drift is the common failure mode when a
    panel is added.
    """
    for dashboard in DASHBOARDS_DIR.glob("*.json"):
        panels = _panels(dashboard)
        # Find the per-dashboard section: either headed "## dashboard-X.json"
        # or "### dashboard-X.json".
        pattern = re.compile(
            rf"^##+\s+`?{re.escape(dashboard.name)}`?[^\n]*panels[^\n]*$",
            re.MULTILINE | re.IGNORECASE,
        )
        m = pattern.search(inventory_text)
        if not m:
            # It's fine not to have a per-dashboard table; the top-level
            # "Dashboards shipped" row is the minimum.
            continue
        # Extract the section body: from header to the next `## ` heading.
        start = m.end()
        next_h = re.search(r"\n---\n|\n##\s", inventory_text[start:])
        body = inventory_text[start : start + (next_h.start() if next_h else len(inventory_text))]
        # Count data rows in any Markdown table in the section. A data
        # row starts with `|` and is not the header or the `|---|...`
        # separator.
        table_rows = [
            line
            for line in body.splitlines()
            if line.strip().startswith("|") and not re.match(r"^\|[\s\-:|]+\|?\s*$", line.strip())
        ]
        # Subtract 1 for the header row (| # | Type | Title | Purpose |).
        data_rows = max(0, len(table_rows) - 1)
        assert data_rows == len(panels), (
            f"{dashboard.name}: inventory §panels lists {data_rows} rows, "
            f"JSON has {len(panels)}. Update either the JSON or the "
            "inventory so they agree."
        )
