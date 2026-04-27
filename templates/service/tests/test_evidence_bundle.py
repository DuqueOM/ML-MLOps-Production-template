"""Promotion-gate evidence bundle tests (ADR-015 PR-B4).

The gate refuses to promote unless ALL of these hold:

1. ``training_manifest.json`` is present next to the model artifact.
2. The manifest parses at the current loader version.
3. ``manifest.quality_gates_passed`` is True.
4. ``manifest.split.strategy`` is one of {temporal, grouped, random}.
5. Model artifact SHA-256 matches ``manifest.model_artifact_sha256``.
6. ``manifest.eda_artifacts_dir`` points at a directory whose
   ``leakage_report.json`` shows ``status=PASSED``.

These tests exercise the gate with on-disk fixtures so every check
is reachable. The gate is pure-stdlib + common_utils peers, so this
test file runs in the audit venv with no MLflow / sklearn /
pandas dependency.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TEMPLATES = Path(__file__).resolve().parent.parent.parent
if str(_TEMPLATES) not in sys.path:
    sys.path.insert(0, str(_TEMPLATES))

from common_utils import eda_artifacts as ea  # noqa: E402
from common_utils import evidence_bundle as eb  # noqa: E402
from common_utils import training_manifest as tm  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builder — synthesise a fully-passing evidence bundle on disk
# ---------------------------------------------------------------------------


def _build_passing_bundle(
    tmp_path: Path,
    *,
    quality_gates_passed: bool = True,
    split_strategy: str | None = "temporal",
    leakage_status: str = "PASSED",
    blocked_features: list[str] | None = None,
    write_eda: bool = True,
    artifact_bytes: bytes = b"fake model bytes\n",
) -> dict:
    """Return a dict of the relevant paths for a fully-valid bundle.

    Knobs let individual tests flip ONE check to FAIL while every
    other dimension stays passing — that's how we localise each
    refusal to its own assertion.
    """
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model = models_dir / "model.joblib"
    model.write_bytes(artifact_bytes)
    artifact_sha = tm.file_sha256(model)

    eda_dir: Path | None = None
    if write_eda:
        eda_dir = tmp_path / "eda" / "artifacts"
        eda_dir.mkdir(parents=True)
        # Required summary so the manifest cross-reference works.
        (eda_dir / ea.EDA_SUMMARY_FILENAME).write_text(
            json.dumps(
                {
                    "eda_artifact_version": ea.ARTIFACT_VERSION,
                    "target": "y",
                    "n_rows": 100,
                    "n_columns": 3,
                    "runtime_seconds": 0.1,
                }
            )
        )
        (eda_dir / ea.LEAKAGE_REPORT_FILENAME).write_text(
            json.dumps(
                {
                    "eda_artifact_version": ea.ARTIFACT_VERSION,
                    "status": leakage_status,
                    "blocked_features": blocked_features or [],
                    "findings": [],
                    "thresholds": {"correlation": 0.95, "near_perfect": 0.9999, "mi": 0.9},
                }
            )
        )

    manifest_payload = {
        "manifest_version": tm.MANIFEST_VERSION,
        "started_at": "2026-04-27T12:00:00Z",
        "finished_at": "2026-04-27T12:05:00Z",
        "runtime_seconds": 300.0,
        "git_sha": "deadbeef" * 5,
        "python_version": "3.11.0",
        "platform": "Linux-x86_64",
        "data_path": "data.csv",
        "data_sha256": "0" * 64,
        "quality_gates_path": "quality_gates.yaml",
        "quality_gates_sha256": "1" * 64,
        "target_column": "y",
        "n_rows": 100,
        "n_columns": 3,
        "split": ({"strategy": split_strategy, "n_train": 80, "n_test": 20}
                  if split_strategy is not None else {}),
        "optuna_trials": 10,
        "cv_folds": 5,
        "eda_artifacts_dir": str(eda_dir) if eda_dir else None,
        "eda_summary_git_sha": None,
        "eda_artifact_version": 1,
        "dependencies": {"numpy": "1.0"},
        "model_artifact_path": str(model),
        "model_artifact_sha256": artifact_sha,
        "metrics": {"roc_auc": 0.91},
        "cv_scores": [0.90, 0.91, 0.92],
        "quality_gates_passed": quality_gates_passed,
        "best_params": {"n_estimators": 100},
    }
    manifest_path = models_dir / tm.MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest_payload))

    return {
        "model": model,
        "manifest": manifest_path,
        "eda_dir": eda_dir,
        "artifact_sha": artifact_sha,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_passing_bundle_returns_passed_verdict(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    verdict = eb.evaluate_evidence(paths["model"])
    assert verdict.passed, f"unexpected failures: {verdict.failures}"
    assert verdict.failures == []
    assert verdict.warnings == []
    assert verdict.model_artifact_path == str(paths["model"])
    assert verdict.manifest_path == str(paths["manifest"])
    assert verdict.leakage_report_path is not None


def test_verdict_to_dict_round_trip(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    verdict = eb.evaluate_evidence(paths["model"])
    payload = verdict.to_dict()
    assert payload["verdict_version"] == eb.VERDICT_VERSION
    assert payload["passed"] is True
    assert payload["failures"] == []


# ---------------------------------------------------------------------------
# Failure modes — one check each
# ---------------------------------------------------------------------------


def test_missing_model_artifact_fails(tmp_path: Path) -> None:
    nowhere = tmp_path / "nope.joblib"
    verdict = eb.evaluate_evidence(nowhere)
    assert not verdict.passed
    assert any("model artifact not found" in f for f in verdict.failures)


def test_missing_manifest_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    paths["manifest"].unlink()
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("training_manifest.json not found" in f for f in verdict.failures)


def test_invalid_manifest_version_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    payload = json.loads(paths["manifest"].read_text())
    payload["manifest_version"] = tm.MANIFEST_VERSION + 99
    paths["manifest"].write_text(json.dumps(payload))
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("manifest invalid" in f for f in verdict.failures)


def test_quality_gates_failed_blocks_promotion(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path, quality_gates_passed=False)
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("quality_gates_passed" in f for f in verdict.failures)


def test_missing_split_strategy_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path, split_strategy=None)
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("split.strategy is missing" in f for f in verdict.failures)


def test_invalid_split_strategy_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    payload = json.loads(paths["manifest"].read_text())
    payload["split"]["strategy"] = "bogus"
    paths["manifest"].write_text(json.dumps(payload))
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("not a valid strategy" in f for f in verdict.failures)


def test_artifact_sha_mismatch_blocks_promotion(tmp_path: Path) -> None:
    """The CORE provenance check: the file on disk MUST be the file
    that was hashed at training time. Swapping the artifact between
    train and promote is exactly the failure mode this gate exists
    to catch.
    """
    paths = _build_passing_bundle(tmp_path)
    paths["model"].write_bytes(b"different bytes - swapped artifact")
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("SHA mismatch" in f for f in verdict.failures)


def test_missing_artifact_sha_in_manifest_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    payload = json.loads(paths["manifest"].read_text())
    payload["model_artifact_sha256"] = None
    paths["manifest"].write_text(json.dumps(payload))
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("model_artifact_sha256 is missing" in f for f in verdict.failures)


def test_blocked_leakage_report_blocks_promotion(tmp_path: Path) -> None:
    paths = _build_passing_bundle(
        tmp_path,
        leakage_status="BLOCKED",
        blocked_features=["leaky_col"],
    )
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("leakage_report status='BLOCKED'" in f for f in verdict.failures)
    assert any("leaky_col" in f for f in verdict.failures)


def test_missing_eda_dir_in_manifest_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path, write_eda=False)
    payload = json.loads(paths["manifest"].read_text())
    payload["eda_artifacts_dir"] = None
    paths["manifest"].write_text(json.dumps(payload))
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("eda_artifacts_dir is null" in f for f in verdict.failures)


def test_missing_eda_dir_on_disk_fails(tmp_path: Path) -> None:
    paths = _build_passing_bundle(tmp_path)
    payload = json.loads(paths["manifest"].read_text())
    payload["eda_artifacts_dir"] = str(tmp_path / "nonexistent_eda")
    paths["manifest"].write_text(json.dumps(payload))
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    assert any("missing directory" in f for f in verdict.failures)


# ---------------------------------------------------------------------------
# require_eda=False → demoted to warning
# ---------------------------------------------------------------------------


def test_require_eda_false_demotes_blocked_to_warning(tmp_path: Path) -> None:
    paths = _build_passing_bundle(
        tmp_path,
        leakage_status="BLOCKED",
        blocked_features=["leaky_col"],
    )
    verdict = eb.evaluate_evidence(paths["model"], require_eda=False)
    # Still passing because every OTHER check is green and the EDA
    # failure is now a warning.
    assert verdict.passed, f"unexpected failures: {verdict.failures}"
    assert any("BLOCKED" in w for w in verdict.warnings)


def test_require_eda_false_does_not_excuse_other_failures(tmp_path: Path) -> None:
    """Disabling EDA enforcement must NOT mask other gate failures."""
    paths = _build_passing_bundle(
        tmp_path,
        quality_gates_passed=False,
        leakage_status="BLOCKED",
    )
    verdict = eb.evaluate_evidence(paths["model"], require_eda=False)
    assert not verdict.passed
    # Quality gates failure remains in failures, EDA in warnings.
    assert any("quality_gates_passed" in f for f in verdict.failures)


# ---------------------------------------------------------------------------
# Multiple failures collected, not bailed
# ---------------------------------------------------------------------------


def test_all_failures_reported_simultaneously(tmp_path: Path) -> None:
    """The CLI surface depends on every failure surfacing in one run.

    Otherwise an operator fixes one issue, re-runs, hits the next,
    repeats — the gate becomes a Whac-A-Mole.
    """
    paths = _build_passing_bundle(
        tmp_path,
        quality_gates_passed=False,
        split_strategy=None,
        leakage_status="BLOCKED",
        blocked_features=["x"],
    )
    # Plus break the SHA
    paths["model"].write_bytes(b"swapped")
    verdict = eb.evaluate_evidence(paths["model"])
    assert not verdict.passed
    # At least four distinct failures should appear.
    assert len(verdict.failures) >= 4, verdict.failures
