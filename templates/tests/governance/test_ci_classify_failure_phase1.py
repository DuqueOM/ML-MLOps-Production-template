"""Contract test for ADR-019 Phase 1 read-only runtime.

Status: Phase 1 — shadow mode, NO writes.

Verifies invariants of ``scripts/ci_collect_context.py`` and
``scripts/ci_classify_failure.py``:

A. **Phase 1 read-only**: classifier output ``writes_allowed`` MUST always
   be ``False``.
B. **Schema stability**: collector and classifier output match the
   documented JSON schema.
C. **Protected paths short-circuit**: any change touching a path under
   ``policy.protected_paths`` is classified STOP regardless of signature.
D. **STOP signatures**: gitleaks, trivy, and other security signatures
   route to STOP failure classes — never AUTO or CONSULT.
E. **AUTO routing**: black format-drift on a single .py file routes to
   AUTO ``formatter_drift``.
F. **Blast radius escalation**: when blast radius exceeds AUTO limits,
   classifier escalates to STOP (``blast_radius_exceeded``).
G. **No-signature → STOP**: when no signature matches, classifier defaults
   to STOP (never silently passes).
H. **Memory cannot demote**: invariant covered structurally — the
   classifier has no memory hooks; this test asserts no `memory_*` field
   ever appears in the output schema.

Authority: ADR-019 §Phase 1 acceptance criteria, ADR-020 §S1-6.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 — invokes our own scripts only
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"
COLLECT = SCRIPTS / "ci_collect_context.py"
CLASSIFY = SCRIPTS / "ci_classify_failure.py"
POLICY = REPO_ROOT / "templates" / "config" / "ci_autofix_policy.yaml"


def _run_classify(context: dict, extra_args: list[str] | None = None) -> dict:
    """Invoke ci_classify_failure.py with `context` as JSON on stdin."""
    proc = subprocess.run(  # nosec B603 — trusted inputs
        [sys.executable, str(CLASSIFY), "--policy", str(POLICY), *(extra_args or [])],
        input=json.dumps(context),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"classifier failed: rc={proc.returncode}\nstderr={proc.stderr}"
    return json.loads(proc.stdout)


def _run_collect(*args: str, log: str = "") -> dict:
    proc = subprocess.run(  # nosec B603 — trusted inputs
        [sys.executable, str(COLLECT), *args],
        input=log,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"collector failed: rc={proc.returncode}\nstderr={proc.stderr}"
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Invariant A — Phase 1 is read-only.
# ---------------------------------------------------------------------------


def test_phase1_writes_allowed_is_always_false() -> None:
    """Classifier output MUST never declare writes allowed in Phase 1."""
    contexts = [
        {"error_signatures": ["black.format_drift"], "changed_files": ["foo.py"]},
        {"error_signatures": ["gitleaks.secret"], "changed_files": ["foo.py"]},
        {"error_signatures": [], "changed_files": ["foo.py"]},
        {"error_signatures": ["pytest.assertion"], "changed_files": ["templates/service/tests/test_x.py"]},
    ]
    for ctx in contexts:
        result = _run_classify(ctx)
        assert result["writes_allowed"] is False, f"writes_allowed must be False — got: {result}"


# ---------------------------------------------------------------------------
# Invariant B — schema stability.
# ---------------------------------------------------------------------------


REQUIRED_CLASSIFY_KEYS = {
    "schema_version",
    "phase",
    "input_signatures",
    "matched_class",
    "final_mode",
    "rationale",
    "blast_radius_match",
    "protected_paths_hit",
    "verifiers_required",
    "writes_allowed",
}


def test_classifier_output_schema_stable() -> None:
    result = _run_classify({"error_signatures": ["black.format_drift"], "changed_files": ["foo.py"]})
    assert set(result.keys()) == REQUIRED_CLASSIFY_KEYS, f"classifier schema drift — keys: {sorted(result.keys())}"
    assert result["schema_version"] == "1"
    assert result["phase"] == "shadow"


REQUIRED_COLLECTOR_KEYS = {
    "schema_version",
    "phase",
    "job_name",
    "workflow",
    "pr_number",
    "changed_files",
    "error_signatures",
    "log_excerpt",
    "log_excerpt_truncated",
    "blast_radius_lines",
}


def test_collector_output_schema_stable() -> None:
    result = _run_collect(
        "--job-name",
        "lint",
        "--workflow",
        "ci",
        "--changed-files",
        "foo.py",
        log="would reformat foo.py\n",
    )
    assert set(result.keys()) == REQUIRED_COLLECTOR_KEYS, f"collector schema drift — keys: {sorted(result.keys())}"
    assert "black.format_drift" in result["error_signatures"]


# ---------------------------------------------------------------------------
# Invariant C — protected paths short-circuit to STOP.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "protected_file",
    [
        "templates/service/common_utils/secrets.py",
        "templates/service/common_utils/risk_context.py",
        "scripts/audit_record.py",
        "templates/config/ci_autofix_policy.yaml",
        "templates/config/model_routing_policy.yaml",
        "templates/service/k8s/overlays/gcp-prod/deployment.yaml",
        "templates/service/infra/terraform/aws/iam.tf",
        ".github/workflows/deploy-gcp.yml",
        "templates/service/.github/workflows/deploy-aws.yml",
    ],
)
def test_protected_paths_force_stop(protected_file: str) -> None:
    """Even pure formatter drift on a protected path must STOP."""
    result = _run_classify(
        {
            "error_signatures": ["black.format_drift"],
            "changed_files": [protected_file],
        }
    )
    assert result["final_mode"] == "STOP", f"protected path {protected_file} routed to {result['final_mode']}"
    assert result["matched_class"] == "blast_radius_exceeded"
    assert protected_file in result["protected_paths_hit"]


# ---------------------------------------------------------------------------
# Invariant D — STOP signatures route to STOP.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sig", ["gitleaks.secret", "trivy.cve"])
def test_security_signatures_route_to_stop(sig: str) -> None:
    result = _run_classify({"error_signatures": [sig], "changed_files": ["foo.py"]})
    assert result["final_mode"] == "STOP", f"signature {sig} routed to {result['final_mode']}"
    assert result["matched_class"] == "security_or_auth"


# ---------------------------------------------------------------------------
# Invariant E — AUTO routing for safe formatter drift.
# ---------------------------------------------------------------------------


def test_black_drift_on_one_python_file_routes_auto() -> None:
    result = _run_classify(
        {
            "error_signatures": ["black.format_drift"],
            "changed_files": ["src/foo.py"],
            "blast_radius_lines": 10,
        }
    )
    assert result["final_mode"] == "AUTO"
    assert result["matched_class"] == "formatter_drift"
    assert result["writes_allowed"] is False  # still Phase 1, just classification


def test_markdown_link_routes_auto_docs() -> None:
    result = _run_classify(
        {
            "error_signatures": ["docs.markdownlint"],
            "changed_files": ["docs/RELEASING.md"],
            "blast_radius_lines": 4,
        }
    )
    assert result["final_mode"] == "AUTO"
    assert result["matched_class"] == "docs_quality_minor"


# ---------------------------------------------------------------------------
# Invariant F — blast radius escalation.
# ---------------------------------------------------------------------------


def test_blast_radius_lines_exceeds_auto_escalates_to_stop() -> None:
    # AUTO max_lines_changed = 120 in policy.
    result = _run_classify(
        {
            "error_signatures": ["black.format_drift"],
            "changed_files": ["src/foo.py"],
            "blast_radius_lines": 5_000,
        }
    )
    assert result["final_mode"] == "STOP"
    assert result["matched_class"] == "blast_radius_exceeded"
    assert result["blast_radius_match"]["exceeds_limit"] is True


def test_blast_radius_files_exceeds_auto_escalates_to_stop() -> None:
    # AUTO max_files_changed = 5 in policy.
    files = [f"src/foo_{i}.py" for i in range(50)]
    result = _run_classify(
        {
            "error_signatures": ["black.format_drift"],
            "changed_files": files,
            "blast_radius_lines": 50,
        }
    )
    assert result["final_mode"] == "STOP"
    assert result["matched_class"] == "blast_radius_exceeded"


# ---------------------------------------------------------------------------
# Invariant G — no-signature falls back to STOP.
# ---------------------------------------------------------------------------


def test_no_signature_falls_back_to_stop() -> None:
    result = _run_classify({"error_signatures": [], "changed_files": ["foo.py"]})
    assert result["final_mode"] == "STOP"
    assert result["matched_class"] is None


# ---------------------------------------------------------------------------
# Invariant H — no memory hooks in classifier output.
# ---------------------------------------------------------------------------


def test_classifier_has_no_memory_fields() -> None:
    """Phase 1 classifier MUST NOT expose any memory_* fields. Memory plane
    integration arrives no earlier than ADR-018 Phase 5 / ADR-019 Phase 4.
    """
    result = _run_classify({"error_signatures": ["black.format_drift"], "changed_files": ["foo.py"]})
    for key in result.keys():
        assert not key.startswith("memory"), f"unexpected memory field: {key}"


# ---------------------------------------------------------------------------
# Invariant — collector signature detection covers canonical patterns.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "log_fragment, expected_signature",
    [
        ("would reformat foo.py", "black.format_drift"),
        ("ModuleNotFoundError: No module named 'x'", "python.import_error"),
        ("SyntaxError: invalid syntax", "python.syntax_error"),
        ("E   AssertionError: expected", "pytest.assertion"),
        ("yaml.scanner.ScannerError: while scanning", "yaml.parse_error"),
        ("Total: 5 (UNKNOWN: 1, LOW: 1, MEDIUM: 1, HIGH: 1, CRITICAL: 1)", "trivy.cve"),
        ("gitleaks: 3 leaks found", "gitleaks.secret"),
    ],
)
def test_collector_detects_canonical_signatures(log_fragment: str, expected_signature: str) -> None:
    result = _run_collect("--job-name", "x", "--workflow", "y", log=log_fragment)
    assert expected_signature in result["error_signatures"], (
        f"expected {expected_signature!r} in {result['error_signatures']!r} for log {log_fragment!r}"
    )
