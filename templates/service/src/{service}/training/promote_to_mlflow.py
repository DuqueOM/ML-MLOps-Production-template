"""Promote a trained model artifact to the MLflow Model Registry.

Called from ``retrain-service.yml`` after the Champion/Challenger
evaluation passes. The contract is intentionally minimal so the
workflow can be reasoned about without reading code:

  1. Read the joblib artifact from disk.
  2. Log it as a new MLflow run with metadata describing the
     promotion (source workflow run, sha, retrain reason).
  3. Register the resulting model under ``<service>`` in the
     MLflow Registry and move the new version to the requested
     alias (default: ``production``).

Failure modes are explicit:
  * Missing model artifact      → exit 1
  * MLFLOW_TRACKING_URI unset   → exit 2
  * MLflow API error            → exit 3 (retain previous champion)

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


def _err(msg: str, code: int = 1) -> int:
    print(f"::error::{msg}", file=sys.stderr)
    return code


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
    args = parser.parse_args()

    model_path = Path(args.model_path)
    if not model_path.is_file():
        return _err(f"Model artifact not found at {model_path}", 1)

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
