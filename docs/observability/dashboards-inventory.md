# Observability — Grafana Dashboards Inventory

- **Authority**: R4 audit finding L2; ACTION_PLAN_R4 §7.
- **Scope**: a single index of every Grafana dashboard the template
  ships, with title, purpose, panels, and the Prometheus metrics /
  recording rules each dashboard depends on.
- **Owner**: Platform Engineering.

Adopters consume dashboards by pointing Grafana at the JSON files
under `templates/service/monitoring/grafana/`. Every `{service}` placeholder
is substituted at scaffold time by `templates/scripts/new-service.sh`;
`{ServiceName}` becomes the Pascal-case variant in the title.

This document is regenerated (manually) whenever a new dashboard is
added. The contract test
[`test_dashboards_inventory.py`](../../templates/service/tests/test_dashboards_inventory.py)
fails if a JSON dashboard exists under `templates/service/monitoring/grafana/`
without a row in the table below, or if a listed dashboard references
a file that no longer exists.

---

## Dashboards shipped

| File | Title | Primary use | Tags |
| ------ | ------- | ------------- | ------ |
| [`dashboard-template.json`](../../templates/service/monitoring/grafana/dashboard-template.json) | `{ServiceName} — ML Service Dashboard` | Day-to-day operations view: request rate, error rate, latency, drift, capacity. This is the first dashboard to open when a P1/P2 alert fires. | `ml-service`, `{service}` |
| [`dashboard-closed-loop.json`](../../templates/service/monitoring/grafana/dashboard-closed-loop.json) | `{ServiceName} — Closed-Loop & SLO Dashboard` | Long-horizon health: SLO burn, champion/challenger, sliced AUC, prediction-logger error rate, PSI heatmap. Reviewed in the monthly performance review (see `/performance-review`). | `ml-service`, `{service}`, `closed-loop`, `slo` |
| [`dashboard-dora.json`](../../templates/service/monitoring/grafana/dashboard-dora.json) | `{ServiceName} — DORA Metrics` | Delivery-performance view: deployment frequency, lead time for changes, change failure rate, MTTR, deploys vs rollbacks. Reviewed in retros and the monthly cost/performance reviews. | `dora`, `delivery`, `{service}` |
| [`dashboard-business.json`](../../templates/service/monitoring/grafana/dashboard-business.json) | `{ServiceName} — Business KPIs Dashboard` | Business-facing view: request volume, SLA compliance, prediction mix by segment, monthly cloud cost vs. budget. Maps `project_context.kpis.business[]` to concrete panels — see `docs/observability/business-kpis.md`. | `business`, `kpi`, `{service}` |
| [`dashboard-edge.json`](../../templates/service/monitoring/grafana/dashboard-edge.json) | `{ServiceName} — Edge Protection Dashboard` | Edge-protection coverage view: is a WAF/rate-limit wired in (D-38), how stale is the last audit, traffic reaching the origin. Deliberately does NOT duplicate per-rule WAF hit analytics — see the dashboard's own "use the native console" panel. | `edge`, `waf`, `security`, `{service}` |

---

## `dashboard-template.json` — panels

Eleven panels, ordered top-to-bottom as they render:

| # | Type | Title | Purpose |
| --- | ------ | ------- | --------- |
| 1 | `timeseries` | Request Rate | Per-replica + aggregate `{service}_requests_total` rate. |
| 2 | `timeseries` | Error Rate (%) | Ratio of 5xx responses over total; ties to the P1 error-rate alert. |
| 3 | `timeseries` | Prediction Latency (Percentiles) | P50 / P95 / P99 of `{service}_request_duration_seconds`; ties to P2 latency alert. |
| 4 | `histogram` | Prediction Score Distribution | Shape check — narrowing = model collapse; widening = drift. |
| 5 | `timeseries` | PSI Drift Score (per feature) | Per-feature PSI from the drift CronJob. Ties to the drift alerts. |
| 6 | `piechart` | Predictions by Risk Level | Business-side view of score-bucket distribution. |
| 7 | `stat` | Model Version | Single-value panel showing the currently-served `model_version` label. |
| 8 | `timeseries` | Pod CPU Usage | `container_cpu_usage_seconds_total` per replica. |
| 9 | `timeseries` | Pod Memory Usage | `container_memory_working_set_bytes`. ML pods have fixed memory; watch for leaks. |
| 10 | `timeseries` | HPA Replicas | `kube_horizontalpodautoscaler_status_current_replicas` — validates CPU-based scaling is actually triggering. |
| 11 | `timeseries` | Saturation (in-flight / executor capacity) | `{service}_inference_in_flight` ÷ `{service}_inference_executor_capacity` — hits 1.0 exactly when a new request must queue. Ties to the `ExecutorSaturated` alert (monitoring-stations audit, Inference station). |

**Prometheus dependencies**:

- Service metrics: `{service}_requests_total`, `{service}_request_duration_seconds_bucket`,
  `{service}_prediction_score`, `{service}_psi_score`, `{service}_inference_in_flight`,
  `{service}_inference_executor_capacity`.
- Kubernetes metrics: `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `kube_horizontalpodautoscaler_status_current_replicas`.

---

## `dashboard-closed-loop.json` — panels

Ten panels covering the slower feedback loop. Consumed by the
`/performance-review` workflow and the drift incident playbook.

| # | Type | Title | Purpose |
| --- | ------ | ------- | --------- |
| 1 | `stat` | SLO — Availability (30-day) | 30-day rolling SLO; displays against target (default 99.5%). |
| 2 | `timeseries` | SLO Error Budget Burn (14d) | 14-day error budget burn; ties to the dynamic risk signal `error_budget_exhausted` (ADR-010). |
| 3 | `timeseries` | Global AUC (per model_version) | Ground-truth-backed performance over time, stratified by version. |
| 4 | `heatmap` | Sliced AUC heatmap (worst slices) | Per-slice AUC — catches silent concept drift that the global number hides. Inputs to `performance-degradation-rca`. |
| 5 | `timeseries` | Champion vs Challenger — error rate | Shadow-traffic comparison during model promotion. Ties to `/release`. |
| 6 | `timeseries` | Score distribution — p50 per version | Median score per version over time; distribution shift is a leading indicator of drift. |
| 7 | `timeseries` | Prediction logger — error rate (D-22) | Health of the async prediction logging pipeline (D-22 enforces it must run at < 1% error). |
| 8 | `timeseries` | Input quality flags (C4) | Schema-validation failures emitted by Pandera at the API boundary (C4 closure signal). |
| 9 | `stat` | `performance_monitor` heartbeat | Last-run timestamp of the performance monitor CronJob. Stale → silent concept drift. |
| 10 | `bargauge` | PSI per feature (drift) | Current PSI per feature against the reference window. Input to the drift alert routing. |

**Prometheus dependencies**:

- Recording rules: `slo:availability:ratio_30d`, `slo:error_budget:burn_14d`.
- Service metrics: `{service}_auc_global`, `{service}_auc_slice`, `{service}_prediction_score`, `{service}_psi_score`,
  `{service}_prediction_logger_errors_total`, `{service}_input_quality_flags_total`.
- Heartbeat: `performance_monitor_last_run_timestamp`.

---

## `dashboard-dora.json` — panels

Five panels measuring delivery performance (DORA four keys + trend):

| # | Type | Title | Purpose |
| --- | ------ | ------- | --------- |
| 1 | `stat` | Deployment Frequency (per week) | How often the service ships to production; derived from deploy audit events. |
| 2 | `stat` | Lead Time for Changes (hours, p50) | Median time from commit to production rollout. |
| 3 | `stat` | Change Failure Rate (%) | Share of deploys that triggered a rollback or incident. |
| 4 | `stat` | MTTR (minutes, p50) | Median time to restore after a failed change. |
| 5 | `timeseries` | Deploys vs Rollbacks (last 90d) | Trend view pairing deploy volume with rollback volume. |

---

## `dashboard-business.json` — panels

Five panels — see `docs/observability/business-kpis.md` for the full
mapping from `project_context.kpis.business[]` to these panels,
including which ones are proxies computed from data the template
already collects versus what an adopter must customize:

| # | Type | Title | Purpose |
| --- | ------ | ------- | --------- |
| 1 | `timeseries` | Request Volume (daily) | `{service}_requests_total` increase per day — the closest generic proxy for "usage" without knowing the adopter's actual business unit. |
| 2 | `gauge` | SLA Compliance (30d) | Reuses the `{service}:sli:availability` recording rule already computed for the SLO burn-rate alerts — no new metric, just a longer window and a business-legible unit (%). |
| 3 | `stat` | Monthly Cloud Cost vs. Budget | `{service}_monthly_cloud_cost_usd`, pushed by the `cost-audit` skill's Pushgateway step. The yellow/red thresholds are a manual, adopter-set value (not auto-synced to `company_context.monthly_budget_usd` — see the caveat in `business-kpis.md`). |
| 4 | `timeseries` | Predictions by Risk Level (business segment mix) | Same `{service}_predictions_total` series as `dashboard-template.json` panel 6, re-plotted as a trend instead of a point-in-time pie — the business-review question is "is the mix shifting," not "what is it right now." |
| 5 | `timeseries` | Error Rate impact on users (proxy) | Failed-request *count* per day, not a percentage — deliberately, since a business audience reads "140 failed requests today" faster than "0.3%". |

**Prometheus dependencies**:

- Service metrics: `{service}_requests_total`, `{service}_predictions_total`, `{service}_monthly_cloud_cost_usd` (new —
  see below).
- Recording rules: `{service}:sli:availability` (from `slo-prometheusrule.yaml`).

**What this dashboard deliberately does NOT do**: render the adopter's
own custom `kpis.business[].name` metric generically. That metric's
source (a Prometheus counter? a data-warehouse query? a weekly CSV
export?) is unknown at template-authoring time, and faking a panel for
an unspecified metric would be a worse claim-vs-reality gap than
leaving it as an explicit adopter TODO. See `business-kpis.md`.

---

## `dashboard-edge.json` — panels

Four panels — Edge station of the monitoring-stations audit
(`docs/observability/monitoring-stations.md`). Populated by the
`edge-audit` skill's Step 4b Pushgateway push (ADR-042, D-38):

| # | Type | Title | Purpose |
| --- | ------ | ------- | --------- |
| 1 | `stat` | Edge Protection Coverage | `edge_protection_enabled{overlay}` — 1 if the last audit found a valid, correctly-wired edge component; 0 if not. Ties to the `EdgeProtectionMissing` alert. |
| 2 | `stat` | Last Audit Age | `time() - edge_protection_last_audit_timestamp{overlay}` — staleness of the coverage verdict above. Ties to the `EdgeAuditHeartbeatMissing` alert. |
| 3 | `timeseries` | Requests Reaching Origin | `{service}_requests_total` rate — same series `dashboard-template.json` panel 1 shows, re-surfaced here as "traffic that made it past the edge layer." |
| 4 | `text` | Deep WAF / DDoS Analytics — use the native console | Explicit pointer to Cloud Armor / WAFv2 / Cloudflare's own analytics UI, with the reasoning for NOT duplicating per-rule hit counts here. |

**Prometheus dependencies**:

- New metrics (Pushgateway, `edge-audit` skill Step 4b): `edge_protection_enabled`, `edge_protection_last_audit_timestamp`.
- Service metrics: `{service}_requests_total` (panel 3, already collected).

**What this dashboard deliberately does NOT do**: recreate Cloud
Armor's / WAFv2's / Cloudflare's own per-rule hit-rate, bot-score, or
DDoS-timeline analytics. Each provider already ships a purpose-built
view for that, using that provider's own rule taxonomy — reimplementing
it in Grafana would drift out of sync with whichever provider an
adopter chose and duplicate a UI that already exists (Engineering
Calibration Principle, `CLAUDE.md`). What this dashboard adds is the one
signal none of those consoles can answer: whether this template's D-38
contract (an edge component correctly wired in) currently holds.

---

## How dashboards are used operationally

| Incident class | Open first | Then |
| ---------------- | ----------- | ------ |
| P1 service-down, error-rate, pod-restart | `dashboard-template.json` → panels 1, 2, 8–10 | Cross-check `dashboard-closed-loop.json` panel 7 (prediction logger) for async-side errors |
| P2 latency | `dashboard-template.json` → panel 3 | Prometheus query builder for per-endpoint breakdown |
| P2 drift-heartbeat-missing | `dashboard-closed-loop.json` → panels 9, 10 | `kubectl describe cronjob` |
| P2 edge-protection-missing | `dashboard-edge.json` → panel 1 | Run `/edge-setup --overlay <overlay>` |
| P3 PSI drift alert | `dashboard-template.json` → panel 5; `dashboard-closed-loop.json` → panel 10 | Run `/drift-check <service>` |
| Monthly performance review | `dashboard-closed-loop.json` → panels 1, 3, 4, 8 | [`performance-review` workflow](../../agentic/workflows/performance-review.md) |

---

## Adding a new dashboard

1. Place the JSON under `templates/service/monitoring/grafana/`.
2. Append a row to the "Dashboards shipped" table above (file, title, purpose, tags).
3. Add a per-dashboard "panels" subsection documenting each panel's type, title, and purpose. Keep it terse — the
   canonical source is the JSON.
4. Run `python -m pytest templates/service/tests/test_dashboards_inventory.py` to confirm the contract test still passes.
5. Open a PR. The PR evidence policy (ADR-020 §S1-2) applies because the dashboard file lives in the allow-listed
   `templates/service/monitoring/` surface.

---

## References

- ACTION_PLAN_R4 §R4 findings table (`L2`)
- `templates/service/monitoring/alertmanager-rules.yaml` — alerts these dashboards complement
- `docs/decisions/ADR-022-psi-thresholds.md` — PSI numbers surfaced in panel 5 / panel 10
