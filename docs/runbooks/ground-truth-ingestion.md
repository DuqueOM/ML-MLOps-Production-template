# Runbook — Ground-Truth Ingestion SLA

- **Authority**: ADR-020 §S2-5, R4 audit finding M2.
- **Mode**: CONSULT (ground-truth ingestion is per-domain; the SLA is template-level).
- **Scope**: define the contract between the closed-loop monitoring layer (ADR-006) and the per-service ground-truth
  ingestion pipeline. R4 M2 flagged that `D-20`/`D-21` cover code (prediction logger), not the **SLA** the ingestion
  side must meet for the closed loop to be meaningful.
- **Audit trail**: SLA breaches recorded in `VALIDATION_LOG.md`.

---

## Why this runbook exists

The closed-loop monitoring chain in this template depends on three SLAs:

1. **Prediction log durability** — the `prediction_logger` ships with
   four backends (parquet, BigQuery, SQLite, stdout). All four guarantee
   "at-least-once durability within 30 seconds of the request" (D-21
   fire-and-forget).
2. **Ground-truth ingestion freshness** — the per-domain CronJob in
   `templates/service/src/{@ service_slug @}/monitoring/ground_truth.py` is the adopter's
   responsibility to fill in. The SLA below defines what "good enough"
   means for the closed loop to detect concept drift.
3. **Sliced performance freshness** — the metrics that fire alerts
   depend on (1) and (2) being current.

This runbook codifies (2). Without it, an adopter could ship a
ground-truth pipeline that runs once a quarter and the closed-loop
metrics would silently lag.

---

## Canonical SLAs

| Tier | Ground-truth latency | Backfill window | Use case |
| --- | --- | --- | --- |
| Real-time domain (fraud, abuse) | ≤ 24 hours | ≤ 30 days | Prediction → outcome is observable same-day |
| Operational domain (churn, intent) | ≤ 7 days | ≤ 90 days | Outcome takes a billing cycle to materialize |
| Long-horizon domain (lifetime value, default) | ≤ 90 days | ≤ 365 days | Outcome takes a quarter or more |

**Default tier** (when the service docs do not declare): **operational
(7 days)**. This is the safest default because it is more conservative
than long-horizon while not over-promising real-time.

The tier MUST be declared in `service.yaml` under
`closed_loop.ground_truth_tier`. The drift-detection CronJob refuses to
generate sliced-performance reports older than the tier's freshness
window — stale reports are NOT silently surfaced.

## Per-tier obligations

For each tier, the adopter's ground-truth pipeline MUST:

1. Run on a CronJob with `concurrencyPolicy: Forbid` (overlap is meaningless).
2. Cover the tier's freshness window in every run.
3. Emit a `ground_truth_lag_hours` Prometheus gauge so the SLO rules
   can fire on staleness.
4. Write to the same backend as the prediction logger (parquet, BigQuery,
   etc) using a JOIN-stable schema:

   ```text
   {
     "prediction_id": "<uuid>",
     "entity_id": "<str>",
     "ground_truth_label": <int|float|bool>,
     "ground_truth_observed_at": "<ISO 8601 UTC>",
     "ground_truth_source": "<str — e.g. 'chargeback_table_v3'>"
   }
   ```

5. Be **idempotent**: re-running the job over the same window must not
   double-count outcomes.

## SLA monitoring

The `templates/service/k8s/base/slo-prometheusrule.yaml` ships these alerts:

- `GroundTruthIngestStale` — fires when `ground_truth_lag_hours` > tier
  freshness × 1.2 (20% slack). Severity: `warning`.
- `GroundTruthIngestSeverelyStale` — fires when lag > tier freshness ×
  2. Severity: `critical`. Routes to the on-call channel.
- `GroundTruthIngestHeartbeatMissing` — fires when no successful run in
  2× the CronJob schedule period. Severity: `critical`.

If the alerts are silenced or suppressed, the closed-loop monitoring
column of `README.md` § "Production-ready scope" silently degrades; do
NOT silence these alerts as a "false positive" without first verifying
the underlying lag.

## Validating against the SLA

For a service in production, the test below confirms the SLA is being
met. Run weekly:

```bash
SERVICE_SLUG="fraud_detector"
TIER_HOURS="24"  # from service.yaml

# Pull the gauge for the last 60 minutes from Prometheus.
curl -fsSL "$PROM_URL/api/v1/query?query=ground_truth_lag_hours{service=\"$SERVICE_SLUG\"}" | \
  python -c "
import json, sys
data = json.load(sys.stdin)
val = float(data['data']['result'][0]['value'][1])
limit = float($TIER_HOURS) * 1.2
status = 'OK' if val <= limit else 'BREACH'
print(f'{status}: lag={val:.1f}h, limit={limit:.1f}h')
"
```

A `BREACH` output triggers a CONSULT-mode investigation (do NOT
auto-clear; the alert is doing its job).

## Recording evidence

The first time a service crosses each tier boundary, record a
`VALIDATION_LOG.md` entry with:

- Service name + tier declared.
- Mean / p95 / p99 lag observed over a 7-day window.
- Backend used (parquet / BigQuery / SQLite).
- Confirmation that the JOIN-stable schema fields are present.

## Acceptance criteria for closing M2

- [ ] Default tier (`operational, 7 days`) declared in scaffolded `service.yaml`.
- [ ] PrometheusRule names match the alert names in this runbook.
- [ ] First service in production records a `VALIDATION_LOG.md` entry
      confirming compliance with its declared tier.

## Cadence

- Quarterly review of all services' `service.yaml` `ground_truth_tier`
  declarations.
- Re-evaluate after any change to `prediction_logger.py` schema.
