"""Reproducibility manifest tests (ADR-015 PR-B3).

The manifest is the document a future agent (or an auditor) reads to
answer "what code, data, and config produced this model?". These
tests pin its shape and the determinism of every provenance fact.

The module under test (``common_utils.training_manifest``) has no
heavy ML deps — pandas, numpy, sklearn etc. are not imported. So
this test file runs in the audit venv directly, unlike the split /
EDA-gate tests that need the full ``train.py`` import graph.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TEMPLATES = Path(__file__).resolve().parent.parent.parent
if str(_TEMPLATES) not in sys.path:
    sys.path.insert(0, str(_TEMPLATES))

from common_utils import training_manifest as tm  # noqa: E402


# ---------------------------------------------------------------------------
# file_sha256
# ---------------------------------------------------------------------------


def test_file_sha256_is_deterministic(tmp_path: Path) -> None:
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    a = tm.file_sha256(f)
    b = tm.file_sha256(f)
    assert a == b
    assert len(a) == 64  # hex sha256


def test_file_sha256_changes_when_content_changes(tmp_path: Path) -> None:
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    a = tm.file_sha256(f)
    f.write_text("a,b\n1,3\n")
    b = tm.file_sha256(f)
    assert a != b


def test_file_sha256_streaming_handles_multi_chunk(tmp_path: Path) -> None:
    """Synthesise a 3-MiB file so the 1-MiB chunk loop iterates."""
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * (3 * 1024 * 1024))
    h = tm.file_sha256(f)
    assert len(h) == 64


# ---------------------------------------------------------------------------
# collect_dependency_versions
# ---------------------------------------------------------------------------


def test_collect_dependency_versions_returns_dict() -> None:
    out = tm.collect_dependency_versions(("pandas", "numpy"))
    # At least pandas + numpy should be present in this env.
    assert "pandas" in out or "numpy" in out
    for v in out.values():
        assert isinstance(v, str) and v


def test_collect_dependency_versions_skips_missing() -> None:
    out = tm.collect_dependency_versions(("definitely_not_a_real_pkg_xyz",))
    assert out == {}


# ---------------------------------------------------------------------------
# build_initial_manifest + write
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_inputs(tmp_path: Path) -> dict:
    """Synthesise the on-disk inputs the manifest builder hashes."""
    data = tmp_path / "data.csv"
    data.write_text("col1,col2\n1,2\n3,4\n")
    qg = tmp_path / "quality_gates.yaml"
    qg.write_text("primary_metric: roc_auc\n")
    return {"data": data, "qg": qg}


def test_build_initial_manifest_populates_provenance(fixture_inputs: dict) -> None:
    m = tm.build_initial_manifest(
        data_path=fixture_inputs["data"],
        quality_gates_path=fixture_inputs["qg"],
        target_column="target",
        n_rows=2,
        n_columns=2,
        optuna_trials=10,
        cv_folds=5,
    )
    assert m.manifest_version == tm.MANIFEST_VERSION
    assert m.target_column == "target"
    assert m.n_rows == 2
    assert m.n_columns == 2
    # Provenance facts
    assert len(m.data_sha256) == 64
    assert len(m.quality_gates_sha256) == 64
    assert m.python_version  # non-empty
    assert m.platform
    # Output fields are blank pre-finalisation
    assert m.metrics == {}
    assert m.cv_scores == []
    assert m.model_artifact_sha256 is None
    assert m.quality_gates_passed is None


def test_build_initial_manifest_cross_references_eda(tmp_path: Path, fixture_inputs: dict) -> None:
    """``eda_summary.json`` fields are pulled into the manifest for traceability."""
    eda_dir = tmp_path / "eda_artifacts"
    eda_dir.mkdir()
    (eda_dir / "eda_summary.json").write_text(
        json.dumps(
            {
                "eda_artifact_version": 1,
                "target": "target",
                "n_rows": 200,
                "n_columns": 6,
                "runtime_seconds": 0.5,
                "pipeline_git_sha": "deadbeef" * 5,
            }
        )
    )
    m = tm.build_initial_manifest(
        data_path=fixture_inputs["data"],
        quality_gates_path=fixture_inputs["qg"],
        target_column="target",
        n_rows=2, n_columns=2,
        optuna_trials=1, cv_folds=2,
        eda_artifacts_dir=eda_dir,
    )
    assert m.eda_summary_git_sha == "deadbeef" * 5
    assert m.eda_artifact_version == 1
    assert m.eda_artifacts_dir == str(eda_dir)


def test_build_initial_manifest_handles_missing_eda(fixture_inputs: dict, tmp_path: Path) -> None:
    """No EDA artifacts dir → eda_* fields are None, not raise."""
    m = tm.build_initial_manifest(
        data_path=fixture_inputs["data"],
        quality_gates_path=fixture_inputs["qg"],
        target_column="target",
        n_rows=2, n_columns=2,
        optuna_trials=1, cv_folds=2,
        eda_artifacts_dir=None,
    )
    assert m.eda_artifacts_dir is None
    assert m.eda_summary_git_sha is None
    assert m.eda_artifact_version is None


def test_build_initial_manifest_tolerates_corrupt_eda_summary(
    fixture_inputs: dict, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed eda_summary.json must NOT crash the manifest writer."""
    eda_dir = tmp_path / "eda_artifacts"
    eda_dir.mkdir()
    (eda_dir / "eda_summary.json").write_text("{not valid json")
    with caplog.at_level("WARNING"):
        m = tm.build_initial_manifest(
            data_path=fixture_inputs["data"],
            quality_gates_path=fixture_inputs["qg"],
            target_column="target",
            n_rows=2, n_columns=2,
            optuna_trials=1, cv_folds=2,
            eda_artifacts_dir=eda_dir,
        )
    assert m.eda_summary_git_sha is None
    assert any("manifest cross-reference" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Round-trip write + load
# ---------------------------------------------------------------------------


def test_write_round_trip_preserves_fields(fixture_inputs: dict, tmp_path: Path) -> None:
    m = tm.build_initial_manifest(
        data_path=fixture_inputs["data"],
        quality_gates_path=fixture_inputs["qg"],
        target_column="target",
        n_rows=2, n_columns=2,
        optuna_trials=1, cv_folds=2,
    )
    m.metrics = {"roc_auc": 0.92, "f1": 0.71}
    m.cv_scores = [0.91, 0.93, 0.92]
    m.quality_gates_passed = True
    m.split = {"strategy": "temporal", "n_train": 160, "n_test": 40}
    out = m.write(tmp_path / "models" / tm.MANIFEST_FILENAME)
    assert out.exists()

    loaded = tm.load_manifest(out)
    assert loaded["manifest_version"] == tm.MANIFEST_VERSION
    assert loaded["metrics"] == {"f1": 0.71, "roc_auc": 0.92}  # sorted by key
    assert loaded["cv_scores"] == [0.91, 0.93, 0.92]
    assert loaded["split"]["strategy"] == "temporal"
    assert loaded["quality_gates_passed"] is True


def test_load_manifest_rejects_version_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "training_manifest.json"
    p.write_text(json.dumps({"manifest_version": tm.MANIFEST_VERSION + 99}))
    with pytest.raises(tm.ManifestVersionError):
        tm.load_manifest(p)


def test_load_manifest_rejects_missing_version(tmp_path: Path) -> None:
    p = tmp_path / "training_manifest.json"
    p.write_text(json.dumps({}))
    with pytest.raises(tm.ManifestError, match="manifest_version"):
        tm.load_manifest(p)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_manifest_serialisation_is_byte_stable(fixture_inputs: dict, tmp_path: Path) -> None:
    """Two calls writing the same manifest produce IDENTICAL JSON.

    A reproducibility document whose serialisation is non-deterministic
    is a contradiction in terms — git diffs would flap, signatures
    over the file would break, and lineage tooling would treat byte-
    identical content as different.
    """
    m = tm.build_initial_manifest(
        data_path=fixture_inputs["data"],
        quality_gates_path=fixture_inputs["qg"],
        target_column="target",
        n_rows=2, n_columns=2,
        optuna_trials=1, cv_folds=2,
    )
    m.metrics = {"f1": 0.7, "roc_auc": 0.9}
    m.cv_scores = [0.91, 0.92]
    m.dependencies = {"numpy": "1.0", "pandas": "2.0"}
    m.best_params = {"lr": 0.01, "n_estimators": 100}

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    m.write(a)
    m.write(b)
    assert a.read_text() == b.read_text()
