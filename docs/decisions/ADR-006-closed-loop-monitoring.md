# ADR-006: Closed-Loop Monitoring with Delayed Ground-Truth Labels

## Status

Accepted

## Date

2026-04-23

## Context

Prior to this ADR, the template detected **data drift** only — PSI on feature
distributions via a daily Kubernetes CronJob, alerting via GitHub Issues when
thresholds were crossed. This is a useful EARLY signal but does not answer
the only question the business actually cares about:

> *Is the model still performing well?*

Concretely:

- PSI can fire on benign seasonal changes → alert fatigue
- Performance can silently degrade without any feature distribution change
  (label shift, concept shift, adversarial behavior)
- Without a JOIN between predictions and the real outcomes, an AUC
  regression cannot be detected, segmented, or attributed

External reviewers consistently flagged this as the single biggest gap in
the template. The underlying requirement is a **feedback loop** that links
every served prediction to the eventual ground-truth label and computes
performance metrics over time.

## Decision

Introduce three cooperating components and an associated contract:

1. **`common_utils/prediction_logger.py`**
   - Asynchronous, buffered `PredictionLogger` with pluggable backends
     (parquet / BigQuery / SQLite / stdout) selected via
     `PREDICTION_LOG_BACKEND`
   - `PredictionEvent` frozen dataclass validates mandatory fields
     (`prediction_id`, `entity_id`, `model_version`) at construction
   - Fire-and-forget: backed into FastAPI via `run_in_executor` so the
     handler is never blocked (invariant D-21)
   - Failure-tolerant: enqueue + flush errors are swallowed and counted
     via `prediction_log_errors_total` (invariant D-22)

2. **`service/src/{service}/monitoring/ground_truth.py`**
   - `GroundTruthIngester` scheduled daily via CronJob
   - User-implemented `fetch_labels_from_source()` contract — CSV stub
     shipped for local tests; real services replace it with BigQuery /
     Postgres / REST / Snowflake queries
   - Writes to `labels_log` using the same partition scheme as
     predictions (year=/month=/day=) for symmetric parquet JOINs

3. **FastAPI integration**
   - `PredictionRequest.entity_id` is now a required field (business key)
   - `PredictionResponse.prediction_id` is returned so clients can
     reference the prediction in downstream systems

Three new anti-patterns codified:

- **D-20** — prediction log events without `prediction_id` / `entity_id`
- **D-21** — logging blocking the handler event loop
- **D-22** — observability backends leaking failures to HTTP responses

## Rationale

Per the **Engineering Calibration Principle** (AGENTS.md), we weighed
heavier alternatives and chose the minimum viable path:

| Alternative | Rejected because |
|---|---|
| Kafka + Bytewax streaming pipeline | Over-engineered for 1–5 model template; cognitive + ops burden out of scope |
| ClickHouse / Druid as the log store | Mandates a new infra component; parquet on GCS/S3 covers 90% of target audience |
| Evidently Monitoring service deployed cluster-wide | Multi-tenant ML ops product, not a per-service component; adds deploy surface |
| Feature store (Feast) extended to prediction logs | Conflates serving-time feature retrieval with post-hoc analytics |

Parquet + partitioned layout + pluggable backend gives the operator three
practical paths (local dev, GCP-native BigQuery, S3-based batch) without
coupling the template to any of them.

The **fire-and-forget + swallow-errors** semantics are non-negotiable: an
ML service that becomes unavailable because its telemetry backend is down
is a strictly worse outcome than one that serves normally with a gap in
the performance dashboard. This is why D-22 is an invariant, not a
guideline.

## Consequences

### Positive

- Performance degradation can now be measured, not just guessed at from
  PSI trends
- Downstream components (sliced performance monitor ADR-007,
  champion/challenger ADR-008) have a well-defined input schema
- Backends are swappable: local dev uses SQLite, CI uses stdout, prod
  uses parquet/BigQuery
- Observability failures are bounded — they cannot cascade into serving
  failures

### Negative

- Additional dependency: `pyarrow` (~3 MB extra in the container image)
- Every scaffolded service must provide an `entity_id` in its request
  schema (breaking change for any existing deployment following the
  previous template)
- User responsibility: the ground-truth ingester ships with a CSV stub;
  each real service must implement `fetch_labels_from_source()` against
  its actual source system

### Mitigations

- `entity_id` requirement is enforced via Pydantic `Field(..., min_length=1)`
  so violations surface immediately at deploy, not silently in production
- `.env.example` documents all four backends with their required env vars
- `configs/ground_truth_source.yaml` ships with commented examples for
  CSV, BigQuery, Postgres so users can adapt quickly

## Revisit When

- **Streaming**: when any hosted service in the target audience has
  > 100M predictions/day or requires sub-minute label latency (neither is
  true for classical ML in the template's scope)
- **Self-hosted monitoring stack**: when users consistently want a
  hosted Evidently / Arize equivalent and are willing to run it
  cluster-wide
- **Schema evolution**: if services need to version the `PredictionEvent`
  shape (adding fields), a contract-evolution ADR will supersede the
  frozen dataclass decision

## Related

- ADR-001 — Template scope boundaries (this feature stays within "1–5 models")
- ADR-007 — Sliced performance analysis (consumer of this log)
- ADR-008 — Champion/Challenger (uses the holdout, not the live log)
- Rule `.windsurf/rules/13-closed-loop-monitoring.md`
- Skill `concept-drift-analysis`
