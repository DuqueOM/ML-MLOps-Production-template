"""Promotion-gate evidence bundle (ADR-015 PR-B4).

The "evidence bundle" is the set of files + facts that MUST exist
and MUST agree before a model is promoted to the MLflow Registry:

1. ``training_manifest.json`` (PR-B3) is present next to the model
   artifact and parses cleanly at the current loader version.
2. ``manifest.quality_gates_passed`` is ``True``.
3. ``manifest.split.strategy`` is set (a deliberate split was chosen,
   not the unacknowledged-random default that ``Trainer._split_data``
   would have rejected).
4. ``manifest.eda_artifacts_dir`` is set, points at a real directory,
   and the ``leakage_report.json`` it contains has
   ``status == "PASSED"`` (PR-B2 contract).
5. The model artifact's SHA-256 matches ``manifest.model_artifact_sha256``
   — provenance integrity, no swap between training and promotion.

This module is pure stdlib + the two ``common_utils`` peers
(``training_manifest``, ``eda_artifacts``). It does NOT import MLflow,
sklearn, pandas, or any heavy ML dependency, so:

- Unit tests run fast in any environment.
- ``promote_to_mlflow.py`` can call ``evaluate_evidence`` BEFORE its
  lazy MLflow import — a missing artifact fails in milliseconds with
  exit code 4 instead of after a 30-second MLflow connection.

Why a separate module from ``promote_to_mlflow.py``?
The same gate is reused by:
- ``promote_to_mlflow.py`` (the CLI gate).
- The retrain workflow's evaluation step (``Agent-RetrainingAgent``)
  which uses ``evaluate_evidence`` to decide whether to even attempt
  registration.
- Future post-incident audit tooling that reconstructs "was the
  promotion criteria met at promotion time?" from a saved verdict.

Out of scope
------------
- Cosign image signature verification: signing is a different gate
  (PR-A5 / D-19) — happens at deploy time, on the IMAGE that ships
  this manifest. The two gates compose; neither subsumes the other.
- Cross-run lineage (parent_model_uri, comparison to current
  champion). The retrain workflow already evaluates Champion vs
  Challenger using metrics; this module is the EVIDENCE gate, not
  the comparison gate.
- "Soft" failures with severity levels. Every check here is binary:
  it passes or it blocks promotion. A check that warned-but-allowed
  would defeat the gate's purpose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bumped only when the verdict shape itself changes. Independent of
# the manifest / artifact versions; consumers of the verdict (audit
# tooling, dashboards) compare strict equality.
VERDICT_VERSION = 1


# ---------------------------------------------------------------------------
# Verdict dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvidenceVerdict:
    """Outcome of evaluating the evidence bundle for one model artifact.

    ``failures`` and ``warnings`` are populated alongside ``passed``
    so the caller (promote_to_mlflow CLI, audit tool) can produce a
    SINGLE error message listing every problem, not the
    fail-on-first-issue pattern that would force operators through
    multiple round-trips.
    """

    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Deterministic facts captured at evaluation time so the verdict
    # is self-contained — an operator reading the JSON later doesn't
    # need to re-run the gate against potentially-mutated files.
    model_artifact_path: str | None = None
    manifest_path: str | None = None
    leakage_report_path: str | None = None
    eda_artifacts_dir: str | None = None
    verdict_version: int = VERDICT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict_version": self.verdict_version,
            "passed": self.passed,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "model_artifact_path": self.model_artifact_path,
            "manifest_path": self.manifest_path,
            "leakage_report_path": self.leakage_report_path,
            "eda_artifacts_dir": self.eda_artifacts_dir,
        }


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def evaluate_evidence(
    model_path: Path | str,
    *,
    manifest_filename: str = "training_manifest.json",
    require_eda: bool = True,
) -> EvidenceVerdict:
    """Run every check on the evidence bundle.

    Args:
        model_path: Path to the model artifact (joblib / pickle). The
            manifest is expected to live in the same directory under
            ``manifest_filename``.
        manifest_filename: Override only if a service uses a non-
            default manifest name (the default matches
            ``common_utils.training_manifest.MANIFEST_FILENAME``).
        require_eda: When True (default), an absent or BLOCKED EDA
            leakage report is a hard failure. Pass False ONLY for
            services that have a documented ADR exempting them from
            the EDA contract — even then, the verdict carries a
            warning so the audit trail records the exemption.

    Returns:
        ``EvidenceVerdict``. ``passed`` is True only if every check
        cleared. Caller decides what to do (refuse promotion,
        attach the verdict to MLflow, etc.).

    Why this returns a verdict instead of raising:
    The CLI wants to print EVERY failure, not the first one. Tests
    want to assert on the failure list. Audit tooling wants to
    persist the verdict. A raise-on-first-failure model would force
    every consumer to wrap try/except around partial state.
    """
    # Lazy imports keep this module's import graph tiny — important
    # for the CLI's fast-path "missing model" exit.
    try:
        from common_utils.training_manifest import (
            MANIFEST_VERSION,
            ManifestError,
            file_sha256,
            load_manifest,
        )
    except ImportError as exc:  # pragma: no cover
        return EvidenceVerdict(
            passed=False,
            failures=[
                f"common_utils.training_manifest is not importable ({exc}). "
                "PR-B3 was not adopted; the gate cannot evaluate."
            ],
        )

    try:
        from common_utils.eda_artifacts import (
            EDAArtifactError,
            load_leakage_report,
        )
    except ImportError:  # pragma: no cover
        load_leakage_report = None  # type: ignore[assignment]
        EDAArtifactError = RuntimeError  # type: ignore[misc,assignment]

    failures: list[str] = []
    warnings: list[str] = []
    verdict = EvidenceVerdict(passed=False, failures=failures, warnings=warnings)

    model = Path(model_path)
    verdict.model_artifact_path = str(model)
    if not model.is_file():
        failures.append(f"model artifact not found: {model}")
        return verdict  # subsequent checks all depend on this; bail.

    manifest_path = model.parent / manifest_filename
    verdict.manifest_path = str(manifest_path)
    if not manifest_path.is_file():
        failures.append(
            f"training_manifest.json not found at {manifest_path}. "
            "PR-B3 manifest writer must run before promotion."
        )
        return verdict

    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        failures.append(f"manifest invalid: {exc}")
        return verdict

    # 2. Quality-gates verdict
    if manifest.get("quality_gates_passed") is not True:
        failures.append(
            f"manifest.quality_gates_passed={manifest.get('quality_gates_passed')!r} — "
            "model failed quality gates at training time."
        )

    # 3. Split policy actually applied
    split = manifest.get("split") or {}
    strategy = split.get("strategy")
    if not strategy:
        failures.append(
            "manifest.split.strategy is missing — the run did not record a "
            "split policy (PR-B3 wiring incomplete)."
        )
    elif strategy not in {"temporal", "grouped", "random"}:
        failures.append(f"manifest.split.strategy={strategy!r} is not a valid strategy")

    # 4. Model artifact integrity (provenance)
    expected_sha = manifest.get("model_artifact_sha256")
    if not expected_sha:
        failures.append(
            "manifest.model_artifact_sha256 is missing — the manifest finalizer "
            "did not hash the model artifact, so we cannot prove this file is "
            "the one that was trained."
        )
    else:
        actual_sha = file_sha256(model)
        if actual_sha != expected_sha:
            failures.append(
                f"model artifact SHA mismatch: manifest expects {expected_sha[:16]}…, "
                f"file is {actual_sha[:16]}…. Has the artifact been swapped since training?"
            )

    # 5. EDA leakage report (PR-B2 contract)
    eda_dir_str = manifest.get("eda_artifacts_dir")
    verdict.eda_artifacts_dir = eda_dir_str
    if eda_dir_str:
        eda_dir = Path(eda_dir_str)
        leakage_path = eda_dir / "leakage_report.json"
        verdict.leakage_report_path = str(leakage_path)
        if load_leakage_report is None:
            (failures if require_eda else warnings).append(
                "common_utils.eda_artifacts is not importable; cannot "
                "verify leakage_report.json"
            )
        elif not eda_dir.is_dir():
            (failures if require_eda else warnings).append(
                f"manifest.eda_artifacts_dir points to a missing directory: {eda_dir}"
            )
        else:
            try:
                report = load_leakage_report(eda_dir)
            except EDAArtifactError as exc:
                (failures if require_eda else warnings).append(
                    f"leakage_report.json could not be loaded: {exc}"
                )
            else:
                if not report.passed:
                    (failures if require_eda else warnings).append(
                        f"leakage_report status={report.status!r}, "
                        f"blocked features: {list(report.blocked_features)}. "
                        "Promotion blocked."
                    )
    else:
        # Manifest didn't carry an EDA cross-reference at all. With
        # require_eda=True this is a hard fail; otherwise a warning
        # so the verdict records the exemption was used.
        (failures if require_eda else warnings).append(
            "manifest.eda_artifacts_dir is null — no EDA evidence linked "
            "to this run."
        )

    verdict.passed = not failures
    return verdict


__all__ = [
    "VERDICT_VERSION",
    "EvidenceVerdict",
    "evaluate_evidence",
]
