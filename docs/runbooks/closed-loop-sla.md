# Runbook — Closed-loop ML SLA

> **Closes external-feedback gap 1.2 (May 2026 triage).** The
> closed-loop primitives (prediction logger, drift CronJob,
> retrain workflow, champion/challenger gate) ship today. What was
> NOT explicit was the **expected feedback-loop latency contract** —
> how long ground-truth ingestion takes, what SLO applies to ground-
> truth freshness, and how that gates retraining. This runbook makes
> the implicit contract explicit so adopters can decide whether the
> shipped defaults match their domain.

This is a **documentation contract**, not an implementation. The
template ships sane defaults; the SLA values below are starting
points each adopter MUST tune to their own data realities.

---

## The contract

A closed-loop ML system has **four lagging stages** between a
prediction and the model that learns from it. Each stage has its own
latency target.

```text
[1] Prediction served             [2] Outcome materialized
    └─ logged within 1s     ─►        └─ ground truth available within T_gt
                                          │
[3] Drift / quality detected         [4] Retrain decision + promote
    └─ within 1 ground-truth window  ─►   └─ within 1 business day of trigger
```

| Stage | Latency target | Source of truth | Owner |
| ------- | --------------- | ----------------- | ------- |
| 1. Prediction logged | < 1 s after `/predict` returns | `prediction_logger.write_batch()` (D-21/D-22) | Service team |
| 2. Ground truth available | **`T_gt` ≤ 24 h** by default; tune per domain | Adopter's data warehouse / event stream | Data eng |
| 3. Drift / quality detected | Same day as ground truth lands | Drift CronJob + sliced-performance CronJob | ML team |
| 4. Retrain → promote | < 1 business day after the drift / regression alert | `templates/service/.github/workflows/retrain-service.yml` + champion/challenger gate (ADR-008) | ML team + SRE |

`T_gt` is the **single most important number** in your closed loop.
Domains where it is realistic:

| Domain | `T_gt` (typical) |
| -------- | ------------------ |
| Click-through-rate (CTR) | minutes |
| Fraud detection (chargeback) | 30–90 days |
| Credit default | 90 days – 2 years |
| Healthcare diagnosis | weeks – months |
| Recommendation conversion | 1–14 days |

If your `T_gt` exceeds 30 days, the closed loop becomes effectively
"open" for shorter time windows. The mitigation is **proxy
ground truth** (e.g. user dwell time as a CTR proxy) plus the
champion/challenger statistical gate, which can detect regressions
faster than waiting for full label arrival.

---

## What the template ships

Defaults set in the scaffolded service:

| Mechanism | Default | File |
| ----------- | --------- | ------ |
| Drift CronJob cadence | hourly | `templates/service/k8s/base/cronjob-drift.yaml` |
| Drift PSI per-feature alert | 0.20 | `templates/service/monitoring/prometheus/alerts-template.yaml` |
| Drift PSI severe threshold (escalation signal) | 0.40 (= 2× alert) | `risk_context.py` |
| Sliced-performance CronJob cadence | daily 02:00 UTC | `templates/service/k8s/base/cronjob-performance.yaml` |
| Performance regression alert | -2 % vs prior 7-day window | `slo-prometheusrule.yaml` |
| Retrain workflow trigger | manual + alert-driven (label `retrain-trigger`) | `templates/service/.github/workflows/retrain-service.yml` |
| Champion/challenger gate | DeLong superiority test, p < 0.05 + DIR ≥ 0.80 | `analysistemplate-champion-challenger.yaml` |

These defaults are tuned for `T_gt ≤ 24h` domains. For longer
`T_gt`, the cadences in the table above should be relaxed (drift
hourly is meaningless when ground truth lands monthly).

---

## What the template does NOT ship

Documenting the explicit gaps so adopters do not assume coverage:

- **`T_gt` measurement.** The template does not measure your actual
  ground-truth ingestion latency. Adopters MUST add a
  Prometheus metric (e.g. `ground_truth_ingestion_lag_seconds`) and
  alert when it exceeds the contracted SLO. A reference panel for
  this is in `templates/service/monitoring/grafana/dashboard-closed-loop.json`,
  but the metric source is adopter-side.

- **L4 validation under load.** The closed-loop chain has been
  exercised end-to-end in unit + integration tests
  (`tests/integration/test_train_serve_drift_e2e.py` since v0.15.1)
  but NOT under production traffic. That is the L4 gate to v1.0.0.

- **Cross-region eventual consistency.** If your prediction logger
  writes to a multi-region store and your drift job reads from a
  different region, the `T_gt` budget MUST account for the
  replication delay. The template assumes single-region.

---

## Recommended SLO objectives

For a domain with `T_gt = 24h`, a reasonable SLO triplet:

```yaml
# Edit per-service in templates/k8s/base/slo-prometheusrule.yaml
# (overlay the values for your domain).

ground_truth_freshness:
  objective: 99.0%   # (events with GT within 24h) / (total events)
  burn_rate_alert_fast: 14.4   # 1h window, 2% budget
  burn_rate_alert_slow: 6.0    # 6h window, 5% budget

drift_detection_freshness:
  objective: 99.5%   # drift CronJob ran in last 90 min
  burn_rate_alert_fast: 36.0   # 5min window
```

Rationale: the multipliers come from the Google SRE Workbook §"Multi-
window, multi-burn-rate alerts" canonical table.

---

## Failure modes and detection

| Failure | Detection | Triage entry point |
| --------- | ----------- | -------------------- |
| Ground truth never arrives | `ground_truth_ingestion_lag_seconds` exceeds SLO | `/incident` workflow |
| Drift CronJob silently failing | `drift_cronjob_last_success_timestamp_seconds` heartbeat alert | `docs/runbooks/incident-response.md` |
| Retrain produces a worse model | Champion/challenger gate FAILS in CI | `docs/decisions/ADR-008-champion-challenger-statistical-gate.md` |
| Retrain workflow fails before promotion | Audit entry with `result=failure` | `ops/audit.jsonl` |
| Model promoted but worse on a slice | Sliced-performance alert fires post-deploy | `concept-drift-analysis` skill |

The chain is intentionally over-instrumented at the alerting layer
because closed-loop failures are **silent by default**: a model that
slowly degrades looks fine until a downstream metric explodes.

---

## When to deviate from the defaults

- **Real-time fraud / payment systems**: tighten drift to per-15-min,
  performance window to 1h, and switch retraining to event-driven
  (no manual trigger).
- **Compliance-heavy regimes (healthcare, credit)**: relax retrain
  cadence to weekly with mandatory human-in-the-loop review (the
  CONSULT mode for the retraining-agent in AGENTS.md is already this).
- **Low-volume domains (<1000 predictions/day)**: PSI drift is
  noisier than informative below ~5000 events/window. Switch to
  Wasserstein distance or KS test (see `ADR-022-psi-thresholds.md`
  §"alternatives").
