"""Promote a trained model artifact to the MLflow Model Registry.

Called from ``retrain-service.yml`` after the Champion/Challenger
evaluation passes. The contract is intentionally minimal so the
workflow can be reasoned about without reading code:

  1. Read the joblib artifact from disk.
  2. **PR-B4 evidence gate**: refuse to promote unless the
     ``training_manifest.json`` next to the artifact is present,
     valid, and proves quality gates + leakage gate passed and the
     artifact's SHA matches what was trained.
  3. Log the artifact as a new MLflow run with metadata describing
     the promotion (source workflow run, sha, retrain reason).
  4. Register the resulting model under ``<service>`` in the
     MLflow Registry and move the new version to the requested
     alias (default: ``production``).

Failure modes are explicit:
  * Missing model artifact      → exit 1
  * MLFLOW_TRACKING_URI unset   → exit 2
  * MLflow API error            → exit 3 (retain previous champion)
  * Evidence gate failed        → exit 4 (PR-B4)

The deploy chain reads ``models:/<service>@<alias>`` on next pod
startup; this script writes the contract that read depends on.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# MLflow is intentionally imported lazily so the module is importable
# (and `--help` works) on runners without MLflow installed. The retrain
# workflow always installs the requirements before invoking us.

# PR-B4: import the evidence-bundle gate. The module is pure stdlib +
# common_utils peers, so the import is fast and safe on any runner.
# Fail-soft: if common_utils isn't on the path we cannot enforce the
# gate and must refuse to promote rather than silently allowing it.
try:
    from common_utils.evidence_bundle import EvidenceVerdict, evaluate_evidence
except ImportError as _imp_exc:  # pragma: no cover
    EvidenceVerdict = None  # type: ignore[misc,assignment]
    evaluate_evidence = None  # type: ignore[assignment]
    _EVIDENCE_IMPORT_ERROR: Exception | None = _imp_exc
else:
    _EVIDENCE_IMPORT_ERROR = None


def _err(msg: str, code: int = 1) -> int:
    print(f"::error::{msg}", file=sys.stderr)
    return code


def _enforce_evidence_gate(
    model_path: Path,
    *,
    skip: bool,
    skip_reason: str | None,
    require_eda: bool,
):
    """Run the PR-B4 evidence gate; print every failure on rejection.

    Returns ``(verdict, exit_code)``. ``exit_code`` is 0 to proceed,
    4 to abort. ``verdict`` is None only when the gate is
    unenforceable (common_utils import failed) AND skip is set —
    that combination is the documented escape hatch and gets logged
    as a warning.
    """
    if skip:
        if not skip_reason or not skip_reason.strip():
            print(
                "::error::--skip-evidence-gate requires a non-empty "
                "--skip-reason. Refusing to silently bypass the gate.",
                file=sys.stderr,
            )
            return None, 4
        print(
            f"::warning::PR-B4 evidence gate SKIPPED. reason={skip_reason!r}. "
            "This bypass is recorded as an MLflow run tag and in the "
            "audit log; expect a manual review.",
            file=sys.stderr,
        )
        return None, 0

    if evaluate_evidence is None:
        # Cannot enforce. The conservative choice is REFUSE — the
        # whole point of this gate is that absence of enforcement
        # equals presence of risk.
        print(
            "::error::common_utils.evidence_bundle could not be imported "
            f"({_EVIDENCE_IMPORT_ERROR!r}); cannot evaluate the PR-B4 gate. "
            "Either install common_utils or use --skip-evidence-gate "
            "with a documented reason.",
            file=sys.stderr,
        )
        return None, 4

    verdict = evaluate_evidence(model_path, require_eda=require_eda)
    if verdict.passed:
        if verdict.warnings:
            for w in verdict.warnings:
                print(f"::warning::evidence gate: {w}", file=sys.stderr)
        return verdict, 0

    # Failure path — print EVERY check that failed, not just the first.
    print(
        "::error::PR-B4 evidence gate REFUSED promotion. Failures:",
        file=sys.stderr,
    )
    for f in verdict.failures:
        print(f"  - {f}", file=sys.stderr)
    if verdict.warnings:
        for w in verdict.warnings:
            print(f"  (warning) {w}", file=sys.stderr)
    return verdict, 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a model to MLflow Registry")
    parser.add_argument("--model-path", required=True, help="Path to model.joblib")
    parser.add_argument("--service", required=True, help="Service slug (registry name)")
    parser.add_argument("--alias", default="production", help="Alias to attach (default: production)")
    parser.add_argument(
        "--metadata-path",
        default="models/model_metadata.json",
        help="Optional metadata JSON to attach as run tags + params",
    )
    # PR-B4 — evidence gate flags.
    parser.add_argument(
        "--skip-evidence-gate",
        action="store_true",
        help=(
            "Bypass the PR-B4 evidence gate. Requires --skip-reason. "
            "Use ONLY for documented emergency promotions; the bypass "
            "is recorded as an MLflow tag for audit."
        ),
    )
    parser.add_argument(
        "--skip-reason",
        default=None,
        help="Required when --skip-evidence-gate is set. Recorded as a tag.",
    )
    parser.add_argument(
        "--no-require-eda",
        action="store_true",
        help=(
            "Treat a missing/blocked EDA leakage report as a warning "
            "instead of a hard failure. Use ONLY with an ADR exempting "
            "this service from the EDA contract."
        ),
    )
    args = parser.parse_args()

    model_path = Path(args.model_path)
    if not model_path.is_file():
        return _err(f"Model artifact not found at {model_path}", 1)

    # PR-B4 evidence gate runs BEFORE the MLflow connection so a
    # missing manifest fails in milliseconds, not after a 30-second
    # MLflow handshake. The gate's verdict (and any skip reason) is
    # threaded into the MLflow run tags below for the audit trail.
    verdict, gate_code = _enforce_evidence_gate(
        model_path,
        skip=args.skip_evidence_gate,
        skip_reason=args.skip_reason,
        require_eda=not args.no_require_eda,
    )
    if gate_code != 0:
        return gate_code

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        return _err("MLFLOW_TRACKING_URI is not set; cannot promote", 2)

    try:
        import mlflow  # noqa: WPS433 — lazy import keeps --help usable
        from mlflow.tracking import MlflowClient
    except ImportError as exc:
        return _err(f"mlflow is not installed: {exc}", 3)

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()

    # Best-effort metadata enrichment: workflow context + training metrics
    metadata: dict = {}
    meta_file = Path(args.metadata_path)
    if meta_file.is_file():
        try:
            metadata = json.loads(meta_file.read_text())
        except json.JSONDecodeError as exc:
            print(f"::warning::Could not parse {meta_file}: {exc}", file=sys.stderr)

    run_tags = {
        "service": args.service,
        "promotion.alias": args.alias,
        "promotion.source": "retrain-service.yml",
        "github.run_id": os.getenv("GITHUB_RUN_ID", ""),
        "github.sha": os.getenv("GITHUB_SHA", ""),
        "retrain.reason": os.getenv("RETRAIN_REASON", ""),
        # PR-B4: record the evidence-gate outcome on every promotion.
        # Auditors / dashboards can query these tags to find skipped
        # gates without re-reading the manifest.
        "evidence_gate.passed": "true" if (verdict and verdict.passed) else "skipped",
        "evidence_gate.skip_reason": args.skip_reason or "",
        "evidence_gate.warnings": (
            "; ".join(verdict.warnings) if verdict and verdict.warnings else ""
        ),
    }

    experiment_name = f"{args.service}-promotions"
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=f"promote-{args.alias}") as run:
        mlflow.set_tags({k: v for k, v in run_tags.items() if v})
        if metadata:
            for k, v in metadata.items():
                # Numeric → metric, otherwise → tag (MLflow rejects mixed types)
                if isinstance(v, (int, float)):
                    mlflow.log_metric(k, v)
                else:
                    mlflow.set_tag(k, str(v))
        mlflow.log_artifact(str(model_path), artifact_path="model")

        try:
            registered = mlflow.register_model(
                model_uri=f"runs:/{run.info.run_id}/model",
                name=args.service,
            )
        except Exception as exc:  # noqa: BLE001 — surface to CI
            return _err(f"register_model failed: {exc}", 3)

        try:
            client.set_registered_model_alias(
                name=args.service,
                alias=args.alias,
                version=registered.version,
            )
        except Exception as exc:  # noqa: BLE001
            return _err(f"set_registered_model_alias failed: {exc}", 3)

    print(f"Promoted {args.service} v{registered.version} \u2192 " f"alias '{args.alias}' (run_id={run.info.run_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
