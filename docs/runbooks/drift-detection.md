# Drift Detection Runbook

## Trigger

Use this when PSI, sliced AUC, input-quality, or ground-truth freshness alerts fire.

## Procedure

1. Confirm the active model version and deployment id from `ops/audit.jsonl`.
2. Run `make drift-check` or `python templates/service/scripts/drills/run_drift_drill.py`.
3. Compare current features against `data/reference/` and the last accepted EDA baseline.
4. If PSI exceeds the configured threshold, open a CONSULT review for retraining.
5. Attach the drift report, affected slices, and rollback/retrain decision to the incident ticket.

## Exit Criteria

The alert is closed only after the drift report is stored, the decision is recorded, and either retraining or explicit
human acceptance is linked.
