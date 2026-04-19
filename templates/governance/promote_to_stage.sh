#!/usr/bin/env bash
# promote_to_stage.sh — Transition a model version between MLflow stages
#
# Usage:
#   ./promote_to_stage.sh --model-name fraud_detector --version 42 --stage Staging
#   ./promote_to_stage.sh --model-name fraud_detector --version 42 --stage Production --archive-existing
#
# Requires: MLFLOW_TRACKING_URI environment variable, mlflow Python package.
#
# Valid stages: None, Staging, Production, Archived

set -euo pipefail

MODEL_NAME=""
VERSION=""
STAGE=""
ARCHIVE_EXISTING="false"
REASON=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --model-name)        MODEL_NAME="$2"; shift 2 ;;
    --version)           VERSION="$2"; shift 2 ;;
    --stage)             STAGE="$2"; shift 2 ;;
    --archive-existing)  ARCHIVE_EXISTING="true"; shift ;;
    --reason)            REASON="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | head -15
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$MODEL_NAME" || -z "$VERSION" || -z "$STAGE" ]]; then
  echo "Usage: $0 --model-name <name> --version <n> --stage <None|Staging|Production|Archived>" >&2
  exit 1
fi

if [[ -z "${MLFLOW_TRACKING_URI:-}" ]]; then
  echo "MLFLOW_TRACKING_URI environment variable is required" >&2
  exit 1
fi

# shellcheck disable=SC2016
python3 - "$MODEL_NAME" "$VERSION" "$STAGE" "$ARCHIVE_EXISTING" "$REASON" <<'PYEOF'
import os
import sys
from mlflow.tracking import MlflowClient

name, version, stage, archive_existing, reason = sys.argv[1:6]
archive_existing = archive_existing == "true"

valid_stages = {"None", "Staging", "Production", "Archived"}
if stage not in valid_stages:
    print(f"✗ Invalid stage: {stage}. Must be one of {valid_stages}", file=sys.stderr)
    sys.exit(1)

client = MlflowClient()

try:
    mv = client.get_model_version(name, version)
except Exception as e:
    print(f"✗ Model {name} v{version} not found: {e}", file=sys.stderr)
    sys.exit(1)

current = mv.current_stage
print(f"Current stage: {current}")

if current == stage:
    print(f"Already in stage '{stage}', no-op.")
    sys.exit(0)

client.transition_model_version_stage(
    name=name,
    version=version,
    stage=stage,
    archive_existing_versions=archive_existing,
)

# Audit trail
user = os.environ.get("USER", "unknown")
client.set_model_version_tag(name, version, "transitioned_by", user)
if reason:
    client.set_model_version_tag(name, version, "transition_reason", reason)

print(f"✓ {name} v{version}: {current} → {stage}")
if archive_existing:
    print(f"  (archived prior '{stage}' versions)")
PYEOF
