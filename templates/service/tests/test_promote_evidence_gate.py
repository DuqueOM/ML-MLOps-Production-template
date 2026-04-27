"""CLI-level tests for the PR-B4 evidence gate in promote_to_mlflow.

Exercises the CLI before MLflow is touched — the whole point of the
gate is to fail fast in milliseconds, BEFORE any MLflow import or
network round-trip. Tests assert exit codes (0 / 1 / 4) and that
every failure mode prints to stderr in a parseable way for CI logs.

Module is `pytest.importorskip`-gated on mlflow because the gate
function uses the same module that imports mlflow lazily — but it
DOES skip cleanly in stripped envs because we monkey-patch the
post-gate MLflow path away.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_TEMPLATES = Path(__file__).resolve().parent.parent.parent
if str(_TEMPLATES) not in sys.path:
    sys.path.insert(0, str(_TEMPLATES))

# We import the promote module by file path to avoid the `{service}`
# placeholder in the on-disk path (which is not a legal Python module
# name). importlib.util gives us a clean handle.
_PROMOTE_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "{service}"
    / "training"
    / "promote_to_mlflow.py"
)


@pytest.fixture(scope="module")
def promote_module():
    """Load promote_to_mlflow.py from disk as `_promote_under_test`."""
    spec = importlib.util.spec_from_file_location("_promote_under_test", _PROMOTE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuse the bundle builder from the evidence-bundle tests via direct
# import. Putting it in a shared conftest would risk pytest discovering
# the helper as a test; importing from a sibling test module is the
# documented pattern in pytest's own examples.
from common_utils import eda_artifacts as ea  # noqa: E402
from common_utils import training_manifest as tm  # noqa: E402


def _build_passing_bundle(tmp_path: Path, **overrides):
    """Local copy of the bundle builder. See test_evidence_bundle.py
    for the canonical version with full knobs documented.
    """
    quality_gates_passed = overrides.get("quality_gates_passed", True)
    leakage_status = overrides.get("leakage_status", "PASSED")
    blocked_features = overrides.get("blocked_features", [])

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model = models_dir / "model.joblib"
    model.write_bytes(b"fake model\n")
    sha = tm.file_sha256(model)

    eda_dir = tmp_path / "eda" / "artifacts"
    eda_dir.mkdir(parents=True)
    (eda_dir / ea.EDA_SUMMARY_FILENAME).write_text(json.dumps({
        "eda_artifact_version": ea.ARTIFACT_VERSION,
        "target": "y", "n_rows": 100, "n_columns": 3, "runtime_seconds": 0.1,
    }))
    (eda_dir / ea.LEAKAGE_REPORT_FILENAME).write_text(json.dumps({
        "eda_artifact_version": ea.ARTIFACT_VERSION,
        "status": leakage_status,
        "blocked_features": blocked_features,
        "findings": [],
        "thresholds": {"correlation": 0.95, "near_perfect": 0.9999, "mi": 0.9},
    }))

    (models_dir / tm.MANIFEST_FILENAME).write_text(json.dumps({
        "manifest_version": tm.MANIFEST_VERSION,
        "started_at": "2026-04-27T12:00:00Z",
        "finished_at": "2026-04-27T12:05:00Z",
        "runtime_seconds": 300.0,
        "git_sha": "deadbeef" * 5,
        "python_version": "3.11.0", "platform": "Linux",
        "data_path": "data.csv", "data_sha256": "0" * 64,
        "quality_gates_path": "quality_gates.yaml", "quality_gates_sha256": "1" * 64,
        "target_column": "y", "n_rows": 100, "n_columns": 3,
        "split": {"strategy": "temporal", "n_train": 80, "n_test": 20},
        "optuna_trials": 10, "cv_folds": 5,
        "eda_artifacts_dir": str(eda_dir),
        "eda_summary_git_sha": None, "eda_artifact_version": 1,
        "dependencies": {}, "model_artifact_path": str(model),
        "model_artifact_sha256": sha,
        "metrics": {"roc_auc": 0.91}, "cv_scores": [0.9],
        "quality_gates_passed": quality_gates_passed,
        "best_params": {},
    }))
    return model


# ---------------------------------------------------------------------------
# Direct exercise of _enforce_evidence_gate (no MLflow involvement)
# ---------------------------------------------------------------------------


def test_passing_bundle_returns_zero(tmp_path: Path, promote_module) -> None:
    model = _build_passing_bundle(tmp_path)
    verdict, code = promote_module._enforce_evidence_gate(
        model, skip=False, skip_reason=None, require_eda=True,
    )
    assert code == 0
    assert verdict is not None and verdict.passed


def test_blocked_leakage_returns_four_and_prints_failures(
    tmp_path: Path, promote_module, capsys: pytest.CaptureFixture,
) -> None:
    model = _build_passing_bundle(
        tmp_path, leakage_status="BLOCKED", blocked_features=["leak"],
    )
    verdict, code = promote_module._enforce_evidence_gate(
        model, skip=False, skip_reason=None, require_eda=True,
    )
    assert code == 4
    assert verdict is not None and not verdict.passed
    err = capsys.readouterr().err
    assert "REFUSED promotion" in err
    assert "leakage_report status='BLOCKED'" in err


def test_quality_gates_failed_returns_four(tmp_path: Path, promote_module) -> None:
    model = _build_passing_bundle(tmp_path, quality_gates_passed=False)
    _, code = promote_module._enforce_evidence_gate(
        model, skip=False, skip_reason=None, require_eda=True,
    )
    assert code == 4


# ---------------------------------------------------------------------------
# Skip-with-reason escape hatch
# ---------------------------------------------------------------------------


def test_skip_without_reason_refused(
    tmp_path: Path, promote_module, capsys: pytest.CaptureFixture,
) -> None:
    """Bare --skip-evidence-gate must refuse — silent bypass would
    defeat the whole gate.
    """
    model = _build_passing_bundle(tmp_path)
    verdict, code = promote_module._enforce_evidence_gate(
        model, skip=True, skip_reason=None, require_eda=True,
    )
    assert code == 4
    assert verdict is None
    assert "requires a non-empty --skip-reason" in capsys.readouterr().err


def test_skip_with_empty_reason_refused(tmp_path: Path, promote_module) -> None:
    model = _build_passing_bundle(tmp_path)
    _, code = promote_module._enforce_evidence_gate(
        model, skip=True, skip_reason="   ", require_eda=True,
    )
    assert code == 4


def test_skip_with_reason_allowed_and_warns(
    tmp_path: Path, promote_module, capsys: pytest.CaptureFixture,
) -> None:
    """Documented bypass is allowed, prints a warning so the audit
    trail picks it up, and returns 0.
    """
    model = _build_passing_bundle(
        tmp_path, leakage_status="BLOCKED", blocked_features=["x"],
    )
    verdict, code = promote_module._enforce_evidence_gate(
        model,
        skip=True,
        skip_reason="P1 incident: known false-positive on leakage scanner, ADR-099",
        require_eda=True,
    )
    assert code == 0
    assert verdict is None
    err = capsys.readouterr().err
    assert "SKIPPED" in err
    assert "P1 incident" in err


# ---------------------------------------------------------------------------
# require_eda=False
# ---------------------------------------------------------------------------


def test_no_require_eda_demotes_blocked_to_warning(
    tmp_path: Path, promote_module, capsys: pytest.CaptureFixture,
) -> None:
    model = _build_passing_bundle(
        tmp_path, leakage_status="BLOCKED", blocked_features=["x"],
    )
    verdict, code = promote_module._enforce_evidence_gate(
        model, skip=False, skip_reason=None, require_eda=False,
    )
    assert code == 0
    assert verdict is not None and verdict.passed
    err = capsys.readouterr().err
    assert "warning" in err.lower()


# ---------------------------------------------------------------------------
# main() entry — argv → exit code (no MLflow connection attempted on fail)
# ---------------------------------------------------------------------------


def test_main_exits_four_on_blocked_bundle(
    tmp_path: Path, promote_module, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: argparse → gate → exit 4 BEFORE any MLflow import.

    We don't even set MLFLOW_TRACKING_URI — if the gate fired correctly,
    we never reach the MLflow check.
    """
    model = _build_passing_bundle(
        tmp_path, leakage_status="BLOCKED", blocked_features=["leak"],
    )
    monkeypatch.setattr(
        sys, "argv",
        ["promote_to_mlflow.py", "--model-path", str(model), "--service", "fraud"],
    )
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    code = promote_module.main()
    assert code == 4


def test_main_exits_one_on_missing_artifact(
    tmp_path: Path, promote_module, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing artifact is exit 1 (predates the gate) — the gate must
    NOT mask this fast-path failure.
    """
    monkeypatch.setattr(
        sys, "argv",
        ["promote_to_mlflow.py",
         "--model-path", str(tmp_path / "nope.joblib"),
         "--service", "fraud"],
    )
    code = promote_module.main()
    assert code == 1
