"""PR-C2 — Alert routing contract.

Every alert rule shipped by the template (PrometheusRule CRDs in
``k8s/base/`` and the legacy plain-rule files under ``monitoring/``)
must carry both:

1. A ``runbook_url`` annotation. On-call humans cannot triage from a
   summary alone; without a link to the procedure the alert is just
   noise. Phase 1.3 already standardised this for two files; PR-C2
   makes it MANDATORY across every PrometheusRule the template ships,
   discovered automatically so a new rule file added later cannot
   silently bypass the gate.

2. An ``action`` label in ``{page, ticket, notify}``. AlertManager
   routes on labels, not annotations or severity strings (which differ
   between files — ``P1`` vs ``critical`` vs ``warning``). Pinning the
   routing decision to ``action`` decouples the routing config from the
   inevitable drift in severity vocabulary and makes each alert
   declare, at the point of definition, what the on-call response is.

In addition, the SLO file is required to follow the Google SRE
multi-window/multi-burn-rate pattern (PR-C2): at least one alert must
combine a long and a short window with ``and`` so that resolved
incidents stop paging within the short window.

This test is YAML-only — no Prometheus runtime, no jsonschema. It is
wired into the scaffold smoke chain.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# Repo root resolved relative to this test file. In a SCAFFOLDED
# service, ``parents[1]`` IS the service root and contains ``k8s/``,
# ``monitoring/``. In the TEMPLATE repo, this file lives at
# ``templates/service/tests/`` and the alert YAMLs live one level
# higher under ``templates/``. We try both prefixes so the same test
# runs unmodified in either layout (same convention as
# test_metrics_contract.py).
_THIS_FILE = Path(__file__).resolve()
_CANDIDATE_PREFIXES = [
    _THIS_FILE.parents[1],  # scaffolded service root
    _THIS_FILE.parents[2],  # template repo: `templates/`
]

# Auto-discovery roots: any matching ``*.yaml`` whose top-level shape
# is a PrometheusRule CRD or a bare ``groups: [...]`` document.
DISCOVERY_ROOTS = [
    prefix / sub
    for prefix in _CANDIDATE_PREFIXES
    for sub in ("k8s/base", "monitoring")
    if (prefix / sub).is_dir()
]

# Allowed values for the routing label. Keep this small on purpose —
# every additional value forces a corresponding AlertManager route.
ALLOWED_ACTIONS = frozenset({"page", "ticket", "notify"})

# Pattern that flags a multi-window burn-rate alert: a short window
# such as ``[5m]`` or ``[30m]`` AND a long window such as ``[1h]`` or
# ``[6h]`` joined by ``and``. We do not need promtool; ``and`` between
# two rate(...) expressions on the SAME stream is the canonical
# multi-burn-rate shape.
_BURN_RATE_AND = re.compile(
    r"\[(?:5m|10m|15m|30m)\].*?\band\b.*?\[(?:1h|6h|1d|3d)\]"
    r"|\[(?:1h|6h|1d|3d)\].*?\band\b.*?\[(?:5m|10m|15m|30m|2h|6h)\]",
    re.DOTALL,
)


def _is_alert_rule_doc(doc: object) -> bool:
    """Recognise both PrometheusRule CRD and bare ``groups`` documents."""
    if not isinstance(doc, dict):
        return False
    if doc.get("kind") == "PrometheusRule":
        return True
    if "groups" in doc and isinstance(doc["groups"], list):
        return True
    return False


def _iter_rules(doc: dict) -> list[dict]:
    """Yield every rule mapping inside a doc (alerts AND records)."""
    groups = doc.get("spec", {}).get("groups") if "spec" in doc else None
    if groups is None:
        groups = doc.get("groups", []) or []
    out: list[dict] = []
    for group in groups or []:
        for rule in group.get("rules", []) or []:
            if isinstance(rule, dict):
                out.append(rule)
    return out


def _discover_alert_files() -> list[Path]:
    found: list[Path] = []
    for root in DISCOVERY_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.yaml")):
            try:
                docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            except yaml.YAMLError:
                continue
            if any(_is_alert_rule_doc(d) for d in docs):
                found.append(path)
    return found


# Materialise once at import time so pytest can parametrise on the list.
_ALERT_FILES = _discover_alert_files()


def test_discovery_finds_expected_alert_files() -> None:
    """The discovery walk must find at least the canonical alert files.

    Hard-coded sentinel: if any of these are missing or renamed without
    updating this test, the gate would silently shrink. Listing them
    here makes that breakage visible.
    """
    assert _ALERT_FILES, (
        f"no PrometheusRule / alerting-groups files discovered under "
        f"{[str(r) for r in DISCOVERY_ROOTS]}"
    )
    names = {p.name for p in _ALERT_FILES}
    expected_subset = {
        "slo-prometheusrule.yaml",
        "performance-prometheusrule.yaml",
        "alertmanager-rules.yaml",
        "alerts-template.yaml",
    }
    missing = expected_subset - names
    assert not missing, (
        f"discovery missed canonical alert files: {sorted(missing)}\n"
        f"discovered: {sorted(names)}"
    )


@pytest.mark.parametrize(
    "yaml_path",
    _ALERT_FILES,
    ids=[p.name for p in _ALERT_FILES],
)
def test_every_alert_has_runbook_url(yaml_path: Path) -> None:
    """Every ``alert:`` rule MUST carry a non-empty ``runbook_url``."""
    docs = list(yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")))
    missing: list[str] = []
    for doc in docs:
        if not _is_alert_rule_doc(doc):
            continue
        for rule in _iter_rules(doc):
            if "alert" not in rule:
                continue  # recording rules do not need annotations
            annotations = rule.get("annotations") or {}
            url = annotations.get("runbook_url")
            if not isinstance(url, str) or not url.strip():
                missing.append(rule["alert"])
    assert not missing, (
        f"{yaml_path.name}: alerts missing or empty `runbook_url` annotation:\n  - "
        + "\n  - ".join(missing)
        + "\n\nFix: add `annotations.runbook_url` pointing at the section in "
        "docs/runbooks/ that explains the on-call procedure."
    )


@pytest.mark.parametrize(
    "yaml_path",
    _ALERT_FILES,
    ids=[p.name for p in _ALERT_FILES],
)
def test_every_alert_has_action_label(yaml_path: Path) -> None:
    """Every ``alert:`` rule MUST carry an ``action`` label in the
    allowed set so AlertManager can route deterministically.
    """
    docs = list(yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")))
    bad: list[str] = []
    for doc in docs:
        if not _is_alert_rule_doc(doc):
            continue
        for rule in _iter_rules(doc):
            if "alert" not in rule:
                continue
            labels = rule.get("labels") or {}
            action = labels.get("action")
            if action not in ALLOWED_ACTIONS:
                bad.append(f"{rule['alert']} (action={action!r})")
    assert not bad, (
        f"{yaml_path.name}: alerts missing or invalid `action` label "
        f"(must be one of {sorted(ALLOWED_ACTIONS)}):\n  - "
        + "\n  - ".join(bad)
    )


def test_slo_file_uses_multi_window_burn_rate() -> None:
    """The SLO file MUST contain at least one multi-window/multi-burn-rate
    alert (long-window AND short-window, both must agree).

    A pure single-window burn-rate alert keeps firing for the duration
    of its window after the incident resolves; the multi-window pattern
    recovers within the short window. PR-C2 standardises on this shape
    for any availability/latency burn-rate alert.
    """
    slo_path = next(
        (p for p in _ALERT_FILES if p.name == "slo-prometheusrule.yaml"),
        None,
    )
    if slo_path is None or not slo_path.is_file():
        pytest.skip("slo-prometheusrule.yaml not present in scaffolded layout")
    docs = list(yaml.safe_load_all(slo_path.read_text(encoding="utf-8")))
    matches: list[str] = []
    for doc in docs:
        if not _is_alert_rule_doc(doc):
            continue
        for rule in _iter_rules(doc):
            if "alert" not in rule:
                continue
            expr = rule.get("expr", "") or ""
            if isinstance(expr, str) and _BURN_RATE_AND.search(expr):
                matches.append(rule["alert"])
    assert matches, (
        "slo-prometheusrule.yaml has no multi-window burn-rate alert.\n"
        "Expected at least one alert combining a long window (1h/6h/1d/3d) "
        "with a short window (5m/30m/2h/6h) joined by `and`.\n"
        "See https://sre.google/workbook/alerting-on-slos/ for the canonical "
        "pattern."
    )


def test_action_label_consistent_with_severity() -> None:
    """Soft-coupled severity → action mapping.

    AlertManager routes off ``action``; severity is human-facing. They
    must not drift into nonsense pairings. The mapping below tolerates
    the two severity vocabularies in use across files (``P1..P4`` and
    ``critical|warning|info``) and rejects only IMPOSSIBLE pairs:
    a ``page`` cannot have ``severity=info`` (would never page), and
    a ``notify`` cannot have ``severity=critical`` (would never resolve).
    Everything else is judgment and stays out of the test.
    """
    forbidden_pairs = {
        ("page", "info"),
        ("page", "P4"),
        ("notify", "critical"),
        ("notify", "P1"),
    }
    bad: list[str] = []
    for path in _ALERT_FILES:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        for doc in docs:
            if not _is_alert_rule_doc(doc):
                continue
            for rule in _iter_rules(doc):
                if "alert" not in rule:
                    continue
                labels = rule.get("labels") or {}
                action = labels.get("action")
                severity = labels.get("severity")
                if (action, severity) in forbidden_pairs:
                    bad.append(
                        f"{path.name}::{rule['alert']} "
                        f"(action={action!r}, severity={severity!r})"
                    )
    assert not bad, (
        "alerts have incompatible action/severity pairs:\n  - "
        + "\n  - ".join(bad)
    )
