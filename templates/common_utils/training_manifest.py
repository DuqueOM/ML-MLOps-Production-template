"""Reproducibility manifest for a single training run (ADR-015 PR-B3).

Every ``Trainer.run()`` writes a ``training_manifest.json`` next to
its model artifact. The manifest is the single document that lets a
reviewer (or a future agent) answer:

- *Which* code, *which* data, *which* config produced this model?
- *Which* split strategy was used? (was leakage even possible?)
- *Which* EDA artifacts blessed it?
- *Which* dependency versions were in scope?
- *Which* metrics did it post and which gates did it clear?

Why a separate module instead of inlining in ``train.py``
---------------------------------------------------------
The retraining workflow (``Agent-RetrainingAgent``) and the
post-incident audit tooling both need to load manifests without
importing the whole training stack. Putting the dataclass + writer in
``common_utils`` makes the format consumable by any service.

Versioning is identical to the EDA contract (PR-B2): a
``manifest_version`` integer is bumped on breaking schema changes;
loaders compare strict equality and raise on mismatch.

Out of scope
------------
- Storing the entire dataset alongside the manifest (DVC handles
  that — the manifest records the SHA only).
- Cryptographic signing of the manifest (Cosign signs the model image,
  which references the manifest by digest).
- Cross-run lineage graphs (a manifest is per-run; lineage emerges
  from MLflow + git + the manifest's ``parent_model_uri`` field).
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import time
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bumped only on breaking schema changes. New optional fields keep the
# same version. Consumers compare with `==`.
MANIFEST_VERSION = 1

MANIFEST_FILENAME = "training_manifest.json"

# Packages whose version we record in every manifest. Ordered to match
# the typical ML stack: a missing one is logged and skipped, not fatal —
# stripped CI environments may not have every package installed.
TRACKED_DEPENDENCIES: tuple[str, ...] = (
    "scikit-learn",
    "xgboost",
    "lightgbm",
    "pandas",
    "numpy",
    "pandera",
    "mlflow",
    "optuna",
    "shap",
    "fastapi",
)


class ManifestError(RuntimeError):
    """Base class for every error this module raises."""


class ManifestVersionError(ManifestError):
    """Loaded manifest has a ``manifest_version`` we don't understand."""


# ---------------------------------------------------------------------------
# Helpers — deterministic provenance facts
# ---------------------------------------------------------------------------


def file_sha256(path: Path | str, *, chunk_size: int = 1 << 20) -> str:
    """Return the hex SHA-256 of a file, streaming to handle large CSVs.

    1 MiB chunks keep memory bounded for multi-GB training sets. Failure
    propagates — a manifest writer that cannot hash its own input is not
    a manifest worth keeping.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha(repo: Path | str | None = None) -> str | None:
    """Return current ``HEAD`` SHA or ``None`` outside a git checkout.

    Same fail-soft contract as ``eda_pipeline._git_sha``: training in
    a tarball CI run is normal and shouldn't crash the manifest write.
    """
    cwd = str(repo) if repo else None
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=cwd,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def collect_dependency_versions(packages: tuple[str, ...] = TRACKED_DEPENDENCIES) -> dict[str, str]:
    """Return ``{package -> version}`` for the ML stack.

    Missing packages are silently skipped. The set is intentionally
    small: pinning every transitive in the manifest produces noise
    without value (the lockfile already does that). The caller can
    pass a service-specific tuple to extend.
    """
    versions: dict[str, str] = {}
    for pkg in packages:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            continue
    return versions


# ---------------------------------------------------------------------------
# Manifest dataclass
# ---------------------------------------------------------------------------


@dataclass
class TrainingManifest:
    """One row in the training audit log, written next to every model.

    Mutable on purpose — ``Trainer.run`` builds it incrementally
    (split metadata after the split, model SHA after save). The
    ``write()`` method serialises it deterministically.
    """

    # Provenance — identifies what produced this model
    started_at: str
    finished_at: str | None
    runtime_seconds: float | None
    git_sha: str | None
    python_version: str
    platform: str

    # Inputs
    data_path: str
    data_sha256: str
    quality_gates_path: str
    quality_gates_sha256: str
    target_column: str

    # Data shape
    n_rows: int
    n_columns: int

    # Split policy (PR-B3)
    split: dict[str, Any]

    # Hyperparameters / search budget
    optuna_trials: int
    cv_folds: int

    # EDA cross-reference (PR-B2 contract)
    eda_artifacts_dir: str | None
    eda_summary_git_sha: str | None
    eda_artifact_version: int | None

    # Dependency versions
    dependencies: dict[str, str]

    # Outputs (filled in by ``run()`` after training completes)
    model_artifact_path: str | None = None
    model_artifact_sha256: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    cv_scores: list[float] = field(default_factory=list)
    quality_gates_passed: bool | None = None
    best_params: dict[str, Any] = field(default_factory=dict)

    manifest_version: int = MANIFEST_VERSION

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        # dataclasses.asdict would deep-copy nested structures we
        # actually want by reference (split is a plain dict). The
        # explicit ordered dict here also keeps JSON keys sorted in a
        # human-friendly order (provenance → inputs → outputs).
        return {
            "manifest_version": self.manifest_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "runtime_seconds": self.runtime_seconds,
            "git_sha": self.git_sha,
            "python_version": self.python_version,
            "platform": self.platform,
            "data_path": self.data_path,
            "data_sha256": self.data_sha256,
            "quality_gates_path": self.quality_gates_path,
            "quality_gates_sha256": self.quality_gates_sha256,
            "target_column": self.target_column,
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "split": self.split,
            "optuna_trials": self.optuna_trials,
            "cv_folds": self.cv_folds,
            "eda_artifacts_dir": self.eda_artifacts_dir,
            "eda_summary_git_sha": self.eda_summary_git_sha,
            "eda_artifact_version": self.eda_artifact_version,
            "dependencies": dict(sorted(self.dependencies.items())),
            "model_artifact_path": self.model_artifact_path,
            "model_artifact_sha256": self.model_artifact_sha256,
            "metrics": dict(sorted(self.metrics.items())),
            "cv_scores": list(self.cv_scores),
            "quality_gates_passed": self.quality_gates_passed,
            "best_params": dict(sorted(self.best_params.items())),
        }

    def write(self, path: Path | str) -> Path:
        """Persist the manifest to ``path`` (creates parent dirs)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, default=str) + "\n")
        logger.info("Training manifest written to %s", out)
        return out


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Load and version-check a manifest file.

    Returns the raw dict (downstream consumers — retrain workflow,
    post-incident audit — generally want the JSON-y view, not a
    re-hydrated dataclass with frozen fields). Raises
    ``ManifestVersionError`` on version mismatch so silent format
    breakage surfaces here, not three layers deep.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    found = payload.get("manifest_version")
    if found is None:
        raise ManifestError(f"{p}: missing 'manifest_version' (loader expects {MANIFEST_VERSION})")
    if found != MANIFEST_VERSION:
        raise ManifestVersionError(
            f"{p}: manifest_version={found} != loader version {MANIFEST_VERSION}"
        )
    return payload


# ---------------------------------------------------------------------------
# Constructor — gathers the deterministic facts in one call
# ---------------------------------------------------------------------------


def build_initial_manifest(
    *,
    data_path: str | Path,
    quality_gates_path: str | Path,
    target_column: str,
    n_rows: int,
    n_columns: int,
    optuna_trials: int,
    cv_folds: int,
    eda_artifacts_dir: str | Path | None = None,
) -> TrainingManifest:
    """Build a ``TrainingManifest`` populated with everything we know
    BEFORE the model is trained.

    The output / metric fields are filled in by ``Trainer.run()`` as
    each step completes. Splitting construction (provenance) from
    completion (results) keeps the call site readable and lets the
    manifest be written even on a partial / failed run for forensics.
    """
    data_path = Path(data_path)
    quality_gates_path = Path(quality_gates_path)

    eda_summary_sha: str | None = None
    eda_version: int | None = None
    if eda_artifacts_dir is not None:
        # Read the EDA git SHA + version directly from eda_summary.json
        # rather than re-running git in a possibly-different working
        # directory. The PR-B2 contract guarantees these fields exist.
        summary_path = Path(eda_artifacts_dir) / "eda_summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text())
                eda_summary_sha = summary.get("pipeline_git_sha")
                eda_version = summary.get("eda_artifact_version")
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not parse %s for manifest cross-reference: %s", summary_path, exc)

    return TrainingManifest(
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        finished_at=None,
        runtime_seconds=None,
        git_sha=git_sha(),
        python_version=platform.python_version(),
        platform=platform.platform(),
        data_path=str(data_path),
        data_sha256=file_sha256(data_path),
        quality_gates_path=str(quality_gates_path),
        quality_gates_sha256=file_sha256(quality_gates_path),
        target_column=target_column,
        n_rows=n_rows,
        n_columns=n_columns,
        split={},  # filled in after _split_data
        optuna_trials=optuna_trials,
        cv_folds=cv_folds,
        eda_artifacts_dir=str(eda_artifacts_dir) if eda_artifacts_dir else None,
        eda_summary_git_sha=eda_summary_sha,
        eda_artifact_version=eda_version,
        dependencies=collect_dependency_versions(),
    )


__all__ = [
    "MANIFEST_VERSION",
    "MANIFEST_FILENAME",
    "TRACKED_DEPENDENCIES",
    "ManifestError",
    "ManifestVersionError",
    "TrainingManifest",
    "file_sha256",
    "git_sha",
    "collect_dependency_versions",
    "build_initial_manifest",
    "load_manifest",
]
