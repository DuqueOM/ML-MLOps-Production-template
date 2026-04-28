"""Contract test for ADR-019 — CI autofix + model routing policies.

The two YAML files in `templates/config/` are governance artifacts.
They define what an Agent-CIRepair runtime is allowed to touch, with
what blast radius, and which models route to which task class.

Once the runtime ships (ADR-019 Phase 1+), it will READ these files and
behave accordingly. THIS test guarantees the files themselves cannot
silently drift away from the safety contract ratified by ADR-019:

  1. STOP classes have NO allowed_paths (they refuse autofix entirely)
  2. AUTO blast-radius limits stay within the audit-ratified bounds
     (max 5 files, max 120 lines)
  3. `protected_paths` includes the kill list (deploy workflows,
     Terraform, prod overlays, secrets/risk-context modules)
  4. Every `failure_classes.*.verifiers` reference exists in the
     `verifier_groups` map (no dangling verifiers)
  5. Every `tasks.*.route` references a real `routes.*` entry
  6. Preview-maturity models never appear in production-adjacent tasks
  7. Memory plane (ADR-018) is wired in `mode: advisory` only — until
     that ADR's Phase 5 explicitly graduates it

Authority: ADR-019.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTOFIX_POLICY = REPO_ROOT / "templates" / "config" / "ci_autofix_policy.yaml"
ROUTING_POLICY = REPO_ROOT / "templates" / "config" / "model_routing_policy.yaml"

# The kill list: paths that NO autofix mode may ever touch.
# Drift here is a STOP-class incident.
REQUIRED_PROTECTED_PATTERNS = {
    ".github/workflows/deploy-",
    "templates/cicd/deploy-",
    "templates/infra/terraform/",
    "templates/k8s/overlays/",
    "templates/common_utils/secrets.py",
    "templates/common_utils/risk_context.py",
    "scripts/audit_record.py",
}

REQUIRED_STOP_CLASSES = {
    "security_or_auth",
    "infra_or_deploy",
    "quality_gate",
    "blast_radius_exceeded",
}

# Routes that may NOT contain preview-maturity models. These are the
# routes consumed by tasks that can land on protected branches.
PRODUCTION_ADJACENT_ROUTES = {
    "router_low_cost",
    "patch_worker",
    "reviewer_gatekeeper",
    "escalation_hard",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def autofix() -> dict:
    assert AUTOFIX_POLICY.is_file(), (
        "ADR-019 violation: ci_autofix_policy.yaml is missing. "
        "Phase 0 acceptance requires this file to exist."
    )
    return yaml.safe_load(AUTOFIX_POLICY.read_text())


@pytest.fixture(scope="module")
def routing() -> dict:
    assert ROUTING_POLICY.is_file(), (
        "ADR-019 violation: model_routing_policy.yaml is missing."
    )
    return yaml.safe_load(ROUTING_POLICY.read_text())


# ---------------------------------------------------------------------------
# 1. STOP classes have NO allowed_paths
# ---------------------------------------------------------------------------


def test_stop_classes_have_no_allowed_paths(autofix: dict) -> None:
    """STOP class with allowed_paths is a contradiction.

    A class is either STOP (refuse autofix entirely) OR scoped (AUTO/CONSULT
    with allowed_paths). Mixing them silently widens the autofix surface.
    """
    classes = autofix["failure_classes"]
    for stop_name in REQUIRED_STOP_CLASSES:
        assert stop_name in classes, (
            f"ADR-019 violation: STOP class {stop_name!r} missing from "
            f"ci_autofix_policy.yaml — the kill list is incomplete."
        )
        cls = classes[stop_name]
        assert cls["mode"] == "STOP", (
            f"ADR-019 violation: {stop_name!r} mode is {cls['mode']!r}, "
            f"must be STOP."
        )
        assert "allowed_paths" not in cls, (
            f"ADR-019 violation: STOP class {stop_name!r} has allowed_paths "
            f"({cls.get('allowed_paths')}); STOP classes refuse autofix entirely."
        )


# ---------------------------------------------------------------------------
# 2. AUTO blast-radius limits stay within audit-ratified bounds
# ---------------------------------------------------------------------------


def test_auto_blast_radius_within_bounds(autofix: dict) -> None:
    auto = autofix["limits"]["auto"]
    assert auto["max_files_changed"] <= 5, (
        f"ADR-019 violation: AUTO max_files_changed = {auto['max_files_changed']} "
        f"exceeds the audit-ratified ceiling of 5."
    )
    assert auto["max_lines_changed"] <= 120, (
        f"ADR-019 violation: AUTO max_lines_changed = {auto['max_lines_changed']} "
        f"exceeds the audit-ratified ceiling of 120."
    )


def test_consult_blast_radius_strictly_above_auto(autofix: dict) -> None:
    auto = autofix["limits"]["auto"]
    consult = autofix["limits"]["consult"]
    assert consult["max_files_changed"] > auto["max_files_changed"]
    assert consult["max_lines_changed"] > auto["max_lines_changed"]


# ---------------------------------------------------------------------------
# 3. protected_paths includes the kill list
# ---------------------------------------------------------------------------


def test_protected_paths_includes_kill_list(autofix: dict) -> None:
    protected = autofix["protected_paths"]
    protected_str = "\n".join(protected)
    missing = [p for p in REQUIRED_PROTECTED_PATTERNS if p not in protected_str]
    assert not missing, (
        f"ADR-019 violation: protected_paths missing kill-list entries: "
        f"{missing}. These paths must NEVER be touched by any autofix."
    )


# ---------------------------------------------------------------------------
# 4. Verifier references resolve
# ---------------------------------------------------------------------------


def test_failure_class_verifiers_resolve(autofix: dict) -> None:
    verifier_groups = set(autofix["verifier_groups"].keys())
    bad: list[str] = []
    for cls_name, cls in autofix["failure_classes"].items():
        for v in cls.get("verifiers", []):
            if v not in verifier_groups:
                bad.append(f"{cls_name} -> {v!r}")
    assert not bad, (
        f"ADR-019 violation: failure_classes.*.verifiers reference unknown "
        f"verifier_groups: {bad}"
    )


# ---------------------------------------------------------------------------
# 5. Task routes resolve
# ---------------------------------------------------------------------------


def test_tasks_routes_resolve(routing: dict) -> None:
    routes = set(routing["routes"].keys())
    bad: list[str] = []
    for task_name, task in routing["tasks"].items():
        if task["route"] not in routes:
            bad.append(f"{task_name} -> {task['route']!r}")
    assert not bad, (
        f"ADR-019 violation: tasks.*.route references unknown routes: {bad}"
    )


# ---------------------------------------------------------------------------
# 6. Preview models stay out of production-adjacent routes
# ---------------------------------------------------------------------------


def test_preview_models_not_in_production_routes(routing: dict) -> None:
    bad: list[str] = []
    for route_name in PRODUCTION_ADJACENT_ROUTES:
        if route_name not in routing["routes"]:
            continue  # tested elsewhere
        for cand in routing["routes"][route_name]["candidates"]:
            if cand.get("maturity") == "preview":
                bad.append(f"{route_name} -> {cand['provider']}/{cand['model']}")
    assert not bad, (
        f"ADR-019 violation: preview-maturity models found in "
        f"production-adjacent routes: {bad}. Previews are restricted to "
        f"frontier_preview_nonprod (workflow_dispatch lane only)."
    )


def test_preview_route_has_at_least_one_preview(routing: dict) -> None:
    """Symmetric check: the preview lane must actually contain preview models,
    otherwise it's just a duplicate of escalation_hard."""
    if "frontier_preview_nonprod" not in routing["routes"]:
        pytest.skip("preview lane not configured")
    candidates = routing["routes"]["frontier_preview_nonprod"]["candidates"]
    has_preview = any(c.get("maturity") == "preview" for c in candidates)
    assert has_preview, (
        "ADR-019 violation: frontier_preview_nonprod contains no "
        "preview-maturity model — the lane is misconfigured."
    )


# ---------------------------------------------------------------------------
# 7. Memory plane is advisory only (until ADR-018 Phase 5 graduates)
# ---------------------------------------------------------------------------


def test_memory_plane_advisory_only(autofix: dict) -> None:
    mem = autofix.get("memory", {})
    assert mem.get("mode") == "advisory", (
        f"ADR-019 + ADR-018 violation: memory plane mode is "
        f"{mem.get('mode')!r}; must be 'advisory' until ADR-018 Phase 5 "
        f"explicitly graduates it. This prevents memory hits from becoming "
        f"a covert decision channel."
    )


# ---------------------------------------------------------------------------
# 8. Self-protection: the policy files protect themselves
# ---------------------------------------------------------------------------


def test_policy_files_in_protected_paths(autofix: dict) -> None:
    """The two policy YAMLs MUST appear in protected_paths so that an
    autofix can never quietly rewrite the policy that governs it."""
    protected = "\n".join(autofix["protected_paths"])
    for required in (
        "templates/config/ci_autofix_policy.yaml",
        "templates/config/model_routing_policy.yaml",
    ):
        assert required in protected, (
            f"ADR-019 violation: policy file {required!r} is missing from "
            f"its own protected_paths list. Without self-protection, an "
            f"autofix could rewrite the safety contract."
        )
