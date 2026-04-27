# Correlation IDs

The template threads a single canonical ID through every operation that
produces or consumes a record so post-mortem investigation is JOIN-able
instead of fuzzy-matched. ADR-015 PR-C1 codifies the contract.

## The ID family

| ID | Where minted | Where it lands | Joins to |
|----|--------------|----------------|----------|
| `request_id` | `RequestIDMiddleware` (FastAPI) | `X-Request-ID` response header; structured log lines; error envelope | One HTTP request lifecycle |
| `prediction_id` | `_sync_predict` (`uuid4().hex` per inference) | `PredictionResponse.prediction_id`; `PredictionEvent.prediction_id` | Inference ↔ ground-truth label JOIN (D-20) |
| `model_version` | `train.py` → MLflow tag → pod env `MODEL_VERSION` | `PredictionEvent.model_version`; `*_predictions_total{model_version}` Counter label | Which model produced this prediction |
| `deployment_id` | `deploy-common.yml` (`<env>-<run_id>-<run_attempt>`) | K8s Deployment annotation `windsurf.io/deployment-id`; pod env `DEPLOYMENT_ID`; `PredictionEvent.deployment_id`; `AuditEntry.outputs.deployment_id` | Deploy run ↔ pod ↔ prediction line JOIN |
| `audit_id` | `audit_record.py` CLI (env `AUDIT_ID` or auto uuid hex) | `AuditEntry.audit_id`; `$GITHUB_OUTPUT.audit_id`; CI step summary | Audit log entry ↔ workflow run |
| `drift_run_id` | `drift_detection.detect_drift` (env `DRIFT_RUN_ID` or uuid hex) | drift report JSON; `{service}_drift_run_info{drift_run_id}` Gauge; GitHub Issue body | One drift evaluation across report, metrics, and incident issue |
| `retrain_run_id` | retrain workflow (`${{ github.run_id }}`) | MLflow run tag; `AuditEntry.outputs.retrain_run_id`; promotion packet | Retraining run ↔ promoted model ↔ deploy that picks it up |
| `trace_id` | inbound `X-Trace-ID` header (optional) | Forwarded in error envelope and response header | OpenTelemetry-compatible distributed trace |

## Format

All template-minted IDs are 32-char lowercase hex (`uuid4().hex`) by
default. Workflow-supplied values use a structured shape that already
embeds the GitHub Actions run id:

- `deployment_id`: `<env>-<run_id>-<run_attempt>` (e.g. `production-12345678-1`).
- `audit_id`: same shape as `deployment_id` for deploy operations; uuid hex
  for ad-hoc local skill executions.
- `drift_run_id` and `retrain_run_id`: same shape when minted from a
  workflow; uuid hex for local executions.

Structured shapes are preferred over opaque hex when the producer is a
workflow because the embedded `run_id` is debuggable from the GHA UI
without a JOIN.

## End-to-end flow (deploy → prediction → drift)

```
GitHub Actions run #12345 attempt 1 (deploy-common.yml)
│
├── Generates AUDIT_ID = "production-12345-1"
├── Generates DEPLOYMENT_ID = "production-12345-1"
│
├── kubectl apply -k overlays/production
├── kubectl patch deployment <svc>-predictor
│   --patch '{"spec":{"template":{"metadata":{"annotations":
│     {"windsurf.io/deployment-id":"production-12345-1"}}}}}'
│
├── audit_record.py
│     --audit-id "production-12345-1"
│     --deployment-id "production-12345-1"
│   → ops/audit.jsonl entry: {audit_id, outputs.deployment_id, ...}
│   → $GITHUB_OUTPUT: audit_id=production-12345-1
│
└── Pods come up; Downward API exposes DEPLOYMENT_ID=production-12345-1
      │
      └── FastAPI handler enqueues PredictionEvent
            with deployment_id="production-12345-1",
                 prediction_id=<uuid>,
                 model_version="v1.0.0"
            → BigQuery / Parquet / SQLite predictions_log

Later: drift CronJob (cronjob-drift.yaml) — separate workflow run
│
├── DRIFT_RUN_ID = "drift-67890-1" (env or auto-mint)
├── detect_drift() emits {drift_run_id: "drift-67890-1", ...}
├── push_metrics() pushes {service}_drift_run_info{drift_run_id="drift-67890-1"} = 1
└── If alert: GitHub Issue body opens with "drift_run_id: drift-67890-1"
```

A post-mortem then JOINs:

- `ops/audit.jsonl WHERE outputs.deployment_id = X` → which deploy
- `BigQuery predictions_log WHERE deployment_id = X` → which predictions
- `Prometheus {service}_drift_run_info` → which drift run
- `MLflow runs WHERE tags.deployment_id = X` → which model

Without these IDs each hop is a guess. With them, the ADR-015 promise
"correlate everything by one key" holds.

## Stability contract (DO NOT change without ADR)

- The set of ID names IS A PUBLIC API. Adding a new ID is fine; renaming
  or removing one breaks every post-mortem query that references the old
  name. If you need to change a name, write a deprecation ADR with a
  6-month dual-write window.
- The ID format (32-char hex / structured `<env>-<run>-<attempt>`) IS
  also part of the contract. Log aggregators have regex extractors keyed
  on the shape.
- `deployment_id="local"` is the canonical sentinel for "ran outside
  the deploy chain" (host-mode tests, local docker compose, ad-hoc kube
  apply). Queries should treat it as a distinct value, not as missing.

## Out of scope

- W3C Trace Context propagation (`traceparent`). The middleware honours
  `X-Trace-ID` for OpenTelemetry compat but does not yet convert to/from
  the W3C spec. Add when we adopt OTel collector.
- Cross-cluster federation: each cluster's audit log is local. A
  multi-cluster JOIN requires a central log sink (out of ADR-001 scope).
- ULID/Snowflake instead of uuid4. uuid4 is fine for our scale; the
  monotonicity properties of ULID don't pay back the migration cost
  for 2-5 services.
