---
paths:
  - "**/monitoring/*.py"
  - "**/prometheus*.yaml"
  - "**/grafana/**"
  - "**/alerts*.yaml"
---

# Monitoring Rules

## Mandatory Prometheus metrics (per service)
- `{service}_requests_total{status,model_version}` — Counter
- `{service}_request_duration_seconds` — Histogram (latency SLO)
- `{service}_prediction_score_bucket` — Histogram (C/C score distribution)
- `{service}_model_info{version,commit}` — Gauge (info metric)
- `prediction_log_total` + `prediction_log_errors_total` — D-22 logger health
- `{service}_performance_metric{slice_name,slice_value,metric}` — ADR-007
- `{service}_psi_score{feature}` — ADR-006 feature drift
- `{service}_performance_last_run_timestamp` — CronJob heartbeat (D-09)
- Optional: `{service}_input_out_of_range_total{feature,direction}` — edge quality (C4)

## Mandatory alerts (D-09 heartbeat pattern)
- `GlobalAUCBelowAlert` — concept drift (baseline compared)
- `SlicedAUCBelowAlert` — subpopulation regression
- `PerformanceMonitorStale` — CronJob heartbeat >48h
- `PredictionLogErrorsHigh` — D-22 degradation
- `SLOBurnRate` — error budget exhausted
- `PSIBreach` — data drift per feature

## Grafana dashboards
- `dashboard-template.json` — service basics (request rate, latency, HPA)
- `dashboard-closed-loop.json` — SLO burn, per-version AUC, sliced heatmap,
  C/C error rate, score distribution, logger health, input-quality flags,
  monitor heartbeat, PSI top 10

## Invariants (D-06, D-08, D-09, D-22)
- Alerts WITHOUT heartbeats are worse than no alerts — always pair an alert
  with a "CronJob hasn't run in 48h" alert
- PSI uses QUANTILE bins, never uniform (D-08)
- Metric > 0.99 triggers investigation before alerting (D-06)
- Logger errors are metered, never propagated to HTTP (D-22)

See `.windsurf/rules/09-monitoring.md`, `.windsurf/rules/13-closed-loop-monitoring.md`,
ADR-006, ADR-007.
