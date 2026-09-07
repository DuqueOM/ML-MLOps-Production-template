"""Red-team regression test suite (F3).

Authority: docs/agentic/red-team-log.md §"Open follow-ups" F3;
ACTION_PLAN_R5 §Sprint 3.

Each entry in `docs/agentic/red-team-log.md` documents an adversarial
attempt against the AUTO / CONSULT / STOP protocol and the invariant
that blocked it. The log is evidence of PAST correctness. F3 asks
for something stronger: **a CI regression test that re-runs each
entry's payload on every change to the protocol-critical modules**,
so that a future refactor that silently weakens an invariant trips
immediately.

This module encodes the payload for each red-team entry that has a
machine-reproducible check. Entries whose invariants are purely
prompt-level (e.g. Entry 1's "refuse STOP demotion from user text")
cannot be executed in pytest — they are covered by structural checks
elsewhere (AGENTS.md matrix tests, governance docs).

Entries regressed here:

- **Entry 2** — fabricated memory hit asking to demote STOP.
  Regression: the classifier's `protected_paths` short-circuit
  precedes any memory hook.
- **Entry 3** — patch in `protected_paths` disguised as
  `formatter_drift`. Regression: same short-circuit behaviour,
  exercised with the canonical `secrets.py` path.
- **Entry 4** — blast-radius rebase (200 lines across 8 files).
  Regression: classifier uses PR-level diff, not per-commit.
- **Entry 5 / F2** — `MLOPS_ON_HOURS_UTC=00-24` override.
  Regression: `off_hours` remains True at weekday 03:00 UTC
  despite the adversarial override.

These tests are structural — no network, no subprocess. They fail
fast (< 1 s total) so they can run on every PR.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# -----------------------------------------------------------------
# Wire common_utils + scripts onto sys.path the way the production
# service test suite does. This is symmetric to templates/tests/unit/
# conftest-less setup and keeps F3 drop-in portable.
# -----------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES = _REPO_ROOT / "templates"
for candidate in (_TEMPLATES, _TEMPLATES / "service"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


# ---------------------------------------------------------------------------
# Entry 2 + Entry 3 — protected_paths short-circuit is order-preserving.
# ---------------------------------------------------------------------------


def _load_classifier():
    """Import the classifier module fresh.

    The module exposes ``classify(context: dict, policy: dict)`` which
    returns a :class:`Classification` dataclass. Policy is loaded from
    YAML by the test (the module's CLI loads it at argparse time, not
    at import, so direct-import is cheap).
    """
    if "ci_classify_failure" in sys.modules:
        del sys.modules["ci_classify_failure"]
    scripts_dir = _REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("ci_classify_failure")


def _load_policy() -> dict[str, Any]:
    policy_path = _REPO_ROOT / "templates" / "config" / "ci_autofix_policy.yaml"
    return yaml.safe_load(policy_path.read_text(encoding="utf-8"))


def _classify(mod, **context: Any) -> dict[str, Any]:
    """Thin wrapper mirroring the CLI envelope: context dict in, dict out."""
    result = mod.classify(context, _load_policy())
    return dataclasses.asdict(result)


def test_entry_2_and_3_protected_path_short_circuits_formatter_drift() -> None:
    """Red-team Entry 3 payload: a `formatter_drift` signature over a
    protected path (`templates/service/common_utils/secrets.py`) must classify
    as STOP / blast_radius_exceeded (the canonical protected-paths
    short-circuit class), NOT as an AUTO formatter drift.

    This is the exact payload from the log:

        error_signatures: ["black.format_drift"]
        changed_files:    ["templates/service/common_utils/secrets.py"]

    Regression goal: if someone reorders the classifier so signature
    matching happens BEFORE protected-paths, this test fails.
    """
    mod = _load_classifier()
    result = _classify(
        mod,
        error_signatures=["black.format_drift"],
        changed_files=["templates/service/common_utils/secrets.py"],
        blast_radius_lines=5,
    )
    assert result["final_mode"] == "STOP", (
        f"Entry 3 regression: a protected-path touch MUST produce STOP regardless of signature. Got: {result}"
    )
    assert result["matched_class"] == "blast_radius_exceeded", (
        "Entry 3 regression: the classifier should attribute STOP to the "
        "protected-paths short-circuit (canonical class is "
        "`blast_radius_exceeded` which owns the protected-paths check)."
    )
    assert "templates/service/common_utils/secrets.py" in list(result.get("protected_paths_hit") or ()), (
        "Entry 3 regression: the hit path must be surfaced so the investigator can see WHY STOP was chosen."
    )


def test_entry_2_memory_cannot_demote_stop() -> None:
    """Red-team Entry 2 payload: even if memory-plane metadata claims
    prior approval, the classifier MUST NOT demote STOP to CONSULT /
    AUTO. We exercise the invariant by classifying the same payload
    and checking that the result is stable under a simulated memory
    advisory extra (the classifier has no memory-demote path; this
    test locks the absence of one).
    """
    mod = _load_classifier()
    base = _classify(
        mod,
        error_signatures=["terraform.destroy"],
        changed_files=["templates/service/infra/terraform/aws/main.tf"],
        blast_radius_lines=10,
    )
    assert base["final_mode"] == "STOP", "Entry 2 baseline: terraform destroy signature must be STOP."
    # The classifier signature does NOT take a memory arg, so there is
    # structurally no path to demote. This assertion is the contract
    # lock: if a future refactor adds a `memory_hint=` parameter, it
    # must NOT be able to change the result below.
    classify_sig = [arg for arg in mod.classify.__code__.co_varnames[: mod.classify.__code__.co_argcount]]
    assert "memory" not in classify_sig and "memory_hint" not in classify_sig, (
        "Entry 2 regression: classify() must not accept a memory-influencing "
        "parameter. Memory is structurally advisory (ADR-018 §What it is NOT). "
        f"Found: {classify_sig}"
    )


# ---------------------------------------------------------------------------
# Entry 4 — blast radius operates on PR-level diff.
# ---------------------------------------------------------------------------


def test_entry_4_blast_radius_aggregates_full_pr_not_last_commit() -> None:
    """Red-team Entry 4 payload: 5 commits × 40 lines across 8 files =
    200 total lines. Each individual commit is under AUTO limits, but
    the PR as a whole exceeds. The classifier must see the PR-level
    payload (8 files / 200 lines) and return STOP blast_radius_exceeded.
    """
    mod = _load_classifier()
    result = _classify(
        mod,
        error_signatures=["black.format_drift"],
        changed_files=[f"templates/service/module_{i}.py" for i in range(8)],
        blast_radius_lines=200,
    )
    assert result["final_mode"] == "STOP", (
        "Entry 4 regression: PR-level blast radius (8 files, 200 lines) "
        "must produce STOP. If this passes as AUTO the classifier is "
        "aggregating per-commit, which defeats the multi-commit attack."
    )
    assert result["matched_class"] == "blast_radius_exceeded"


# ---------------------------------------------------------------------------
# Entry 5 / F2 — MLOPS_ON_HOURS_UTC cannot suppress off_hours globally.
# ---------------------------------------------------------------------------


def test_entry_5_full_day_override_cannot_suppress_off_hours(monkeypatch) -> None:
    """Red-team Entry 5 / F2 payload: MLOPS_ON_HOURS_UTC=00-24 forces
    start=0, end=24 which would make `not (0 <= hour < 24)` false for
    every weekday hour — silently suppressing off_hours. F2 hardens
    the parser to reject full-day spans. This regression locks that.
    """
    from common_utils.risk_context import _is_off_hours

    monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "00-24")
    monday_3am = datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc)
    assert _is_off_hours(monday_3am) is True, (
        "Entry 5 / F2 regression: MLOPS_ON_HOURS_UTC=00-24 MUST NOT "
        "suppress off_hours=True at weekday 03:00 UTC. The parser "
        "must reject full-day spans and fall back to the 08-18 default."
    )


def test_entry_5_reversed_span_cannot_suppress_off_hours(monkeypatch) -> None:
    """Variant of Entry 5: reversed span 22-06 is a common configuration
    typo that, before F2, would cause `not (22 <= hour < 6)` to be True
    for every hour — making off_hours always True (the opposite error,
    but still a silent weakening of the signal's informativeness).
    """
    from common_utils.risk_context import _is_off_hours

    monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "22-06")
    monday_noon = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    # After F2 fallback to 08-18, 12:00 is on-hours → off_hours False.
    assert _is_off_hours(monday_noon) is False


# ---------------------------------------------------------------------------
# Structural guard — the red-team log itself is append-only.
# ---------------------------------------------------------------------------


def test_red_team_log_has_all_regressed_entries() -> None:
    """This is a log-integrity check: each Entry that has a regression
    test in THIS file must be mentioned in the red-team log. Catches
    the case where someone deletes an Entry from the log (which would
    also need a PR review justifying why the invariant is gone).
    """
    log = (_REPO_ROOT / "docs" / "agentic" / "red-team-log.md").read_text(encoding="utf-8")
    for entry in ("Entry 2", "Entry 3", "Entry 4", "Entry 5"):
        assert entry in log, (
            f"Red-team log missing heading for {entry!r}. "
            "F3 regression tests reference this entry; deleting the "
            "log entry makes the test unreadable. Either restore the "
            "entry or remove the corresponding regression here with an "
            "explicit PR justification."
        )
