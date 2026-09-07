# Monitoring Stations — Enterprise Coverage Map

- **Authority**: monitoring-stations audit (2026-07), requested against
  six named stations: Edge, Infrastructure, Inference, Models, Logs &
  Traces, Business KPIs.
- **Scope**: for each station — what covers it today (file:line), what
  is intentionally delegated to the adopter's platform, and what is
  explicitly N/A with the condition that would revisit it.
- **Owner**: Platform Engineering.
- **Method**: every claim below was verified against current code at
  audit time (`grep`/`read`, not memory of a prior audit) — see
  [16-doc-coherence](../../agentic/rules/16-doc-coherence.md) for why
  this template requires evidence-backed documentation.

## Summary

| Station | Status | Primary gap (if any) |
| --- | --- | --- |
| 🌐 Edge | ⚠️ Partial — WAF/rate-limit not wired by default | Closing in Wave B (`edge-protection` components) |
| ☁️ Infrastructure | ✅ Covered | Node-level metrics delegated (by design) |
| 🚀 Inference | ✅ Covered | GPU metrics N/A (CPU stack) |
| 🧠 Models | ✅ Covered | — |
| 📜 Logs & Traces | ✅ Covered (demo) / ⚠️ delegated (prod) | Prod log aggregation is the platform's job |
| 📈 Business KPIs | ✅ Covered | Custom adopter KPI names require 1 step (by design) |

---

## 🌐 Edge

**Status: partial.** This is the one real gap this audit found.

- `k8s/components/edge-gcp/` and `k8s/components/edge-aws/` (Kustomize
  Components, opt-in) wire a GCE/ALB Ingress with Cloud Armor /
  AWS WAF annotations — but as Components, they are **not referenced by
  any overlay's `kustomization.yaml`** until an adopter opts in. Today,
  a scaffolded service's default overlays ship with no edge protection
  at all: no WAF, no rate-limiting, no bot mitigation, no DDoS layer in
  front of the LB.
- Confirmed via repo-wide grep: no `NetworkPolicy` or K8s resource
  matches `rate.?limit|WAF|firewall` outside the two new edge
  components themselves.
- **Closing this gap is Wave B** (tasks in flight): ADR-042, anti-pattern
  D-38 ("never expose a public inference endpoint without an edge
  protection layer"), rule `17-edge-protection`, skill `edge-audit`,
  workflow `/edge-setup`, Terraform for `google_compute_security_policy`
  / AWS WAFv2 + an optional Cloudflare module, and an edge-specific
  Grafana dashboard + alerts.
- Until Wave B ships and an adopter runs `/edge-setup`, treat any
  production deployment of this template as **edge-unprotected** —
  call this out explicitly in any adopter-facing checklist.

## ☁️ Infrastructure

**Status: covered.**

| Signal | Source |
| --- | --- |
| Horizontal scale | [`k8s/base/hpa.yaml:29`](../../templates/service/k8s/base/hpa.yaml) — CPU-only `averageUtilization: 60` (D-01/D-02: never memory-based, since fixed RAM prevents scale-down) |
| Pod-level isolation | [`k8s/base/networkpolicy-deny-default.yaml`](../../templates/service/k8s/base/networkpolicy-deny-default.yaml) + [`networkpolicy.yaml`](../../templates/service/k8s/base/networkpolicy.yaml) — default-deny with explicit allows |
| Availability during disruption | [`k8s/base/pdb.yaml`](../../templates/service/k8s/base/pdb.yaml) — PodDisruptionBudget |
| Resource ceilings | [`k8s/base/deployment.yaml:225-231`](../../templates/service/k8s/base/deployment.yaml) — CPU/memory requests+limits on the main container (init containers scoped tighter, lines 97-99 and 163-165) |
| Dashboard panels | `dashboard-template.json` — "Pod CPU Usage", "Pod Memory Usage", "HPA Replicas" |
| Alerts | `alertmanager-rules.yaml` — `{@ service_slug @}HighCPU`, `{@ service_slug @}PodRestarting` |

**Delegated by design**: node-level metrics (kubelet/cAdvisor,
kube-state-metrics, cluster autoscaler events) are **not** shipped by
this template — they're the responsibility of the adopter's platform
`kube-prometheus-stack` or equivalent, which every production GKE/EKS
cluster is expected to already run cluster-wide. Duplicating that
per-service would be exactly the over-engineering the Engineering
Calibration Principle (`CLAUDE.md`) warns against.

## 🚀 Inference

**Status: covered**, including a gap closed this audit (saturation).

| Signal | Source |
| --- | --- |
| Throughput | `dashboard-template.json` — "Request Rate" panel |
| Latency | "Prediction Latency (Percentiles)" panel + `{@ service_slug @}HighLatency` alert |
| Saturation *(new, Wave A2)* | `app/fastapi_app.py` — `inference_in_flight` / `inference_executor_capacity` gauges, wrapped around both `run_in_executor` call sites in `predict()`/`predict_batch()`; "Saturation (in-flight / executor capacity)" panel; `{@ service_slug @}ExecutorSaturated` alert (`>= 1.0` for 5m, severity `info`, runbook §P4) |
| Queueing | the saturation ratio reaching `1.0` is itself the queueing signal — deliberately not read from `ThreadPoolExecutor._work_queue.qsize()` (a private CPython attribute), so the metric stays correct across Python versions |

**N/A by design**: GPU metrics (utilization, memory, temperature). This
template's stack (`CLAUDE.md`) is CPU-bound scikit-learn/XGBoost/
LightGBM — there is no GPU to instrument. **Revisit trigger**: if an
adopter adds GPU-backed serving (e.g., a deep-learning model needing
CUDA), add an `nvidia-smi`-exporter-based panel set at that point; do
not add it speculatively now.

## 🧠 Models

**Status: covered.**

| Signal | Source |
| --- | --- |
| Model version | `predictions_total{model_version=...}` label (`fastapi_app.py:557,618`, sourced from `MODEL_VERSION` env var); dedicated "Model Version" dashboard panel |
| Drift | PSI-based (`src/{@ service_slug @}/monitoring/drift_detection.py` — `calculate_psi`, `calculate_psi_from_bins`, quantile-binned per CLAUDE.md's calibration: "Simple drift → PSI with quantile bins, not feature store"); "PSI Drift Score (per feature)" panel; `{@ service_slug @}DriftAlert` / `DriftWarning` / `DriftDetectionHeartbeatMissing` alerts |
| Score distribution | "Prediction Score Distribution" panel |
| Experiment tracking | MLflow — `train.py:714-718` (`mlflow.set_experiment`, `start_run`, `log_params`, `log_metrics`) against `EXPERIMENT_NAME = "{@ service_name @}-Production"` |

**Accuracy in production** (vs. training-time metrics) is intentionally
a separate concern from this dashboard: ground truth usually arrives
late, and closing that loop is rule
[13-closed-loop-monitoring](../../agentic/rules/13-closed-loop-monitoring.md)'s
job (prediction logger + ground-truth join + sliced performance), not a
single Grafana panel.

## 📜 Logs & Traces

**Status: covered for the demo stack; delegated for production.** This
audit closed a real correlation gap here — see
[log-trace-correlation.md](log-trace-correlation.md) for the full
write-up. Summary:

- Structured JSON logs — `common_utils/logging.py` `JSONFormatter`.
- `request_id`/`trace_id` — `common_utils/errors.py`
  `RequestIDMiddleware`. **Fixed this audit**: previously `request_id`
  only reached the log stream on the unhandled-exception path; a
  successful request produced no correlatable log line at all. Now
  every non-probe request emits a structured access-log line
  (`request_id`, `trace_id`, `method`, `path`, `status_code`,
  `duration_ms`).
- Distributed tracing — `common_utils/tracing.py`, OTel, opt-in
  (`OTEL_ENABLED`), cloud-aware exporter selection (Cloud Trace / ADOT).
- Log aggregation — Loki + Promtail, **demo (docker-compose) only**
  (`docker-compose.demo.yml`, `monitoring profile`). Production log
  aggregation is the platform's job (Fluentd/Fluent Bit DaemonSet →
  the org's existing Cloud Logging/CloudWatch/ELK), not this template's
  — shipping a second one per-service would conflict with whatever the
  cluster already runs.

## 📈 Business KPIs

**Status: covered.** Closed this audit — see
[business-kpis.md](business-kpis.md) for the full mapping.

| Signal | Source |
| --- | --- |
| Request volume | `dashboard-business.json` — "Request Volume (daily)" |
| SLA compliance | "SLA Compliance (30d)" gauge, reusing the existing `{@ service_slug @}:sli:availability` recording rule (`k8s/base/slo-prometheusrule.yaml`) — no new SLO math, just a business-facing rollup of the SRE-facing one |
| Cost | "Monthly Cloud Cost vs. Budget" — new `{@ service_slug @}_monthly_cloud_cost_usd` metric, pushed by the `cost-audit` skill via Pushgateway (`agentic/skills/cost-audit/SKILL.md`, Step 2b) |
| Business mix | "Predictions by Risk Level", "Error Rate impact" |

**Deliberately does not**: render a generic panel for arbitrary
adopter-defined `kpis.business[].name` metrics. This template describes
what it ships and measures; it does not certify or auto-visualize
business metrics it has no way to validate the meaning of — the same
descriptive-not-certifying line `ADR-038-compliance-mapping.md` draws
for compliance claims. An adopter with a custom KPI adds one panel
using the existing dashboard as a template; that is a documented
one-step process, not a missing feature.

## Related

- [log-trace-correlation.md](log-trace-correlation.md)
- [business-kpis.md](business-kpis.md)
- [dashboards-inventory.md](dashboards-inventory.md)
- `agentic/rules/13-closed-loop-monitoring.md`
- `agentic/rules/09-monitoring.md`
