# Observability — Log ↔ Trace Correlation

- **Authority**: monitoring-stations audit (2026-07) — the Logs &
  Traces station existed (structured logging + opt-in OTel tracing)
  but the correlation between the two was implicit and, for the common
  case, not actually wired end-to-end.
- **Scope**: how a `request_id` in a Loki log line reaches the matching
  distributed trace, in the demo stack and in a real deployment.
- **Owner**: Platform Engineering.

---

## The three pieces, and how they connect

1. **`RequestIDMiddleware`** (`common_utils/errors.py`) mints or honours
   `request_id` for every request and forwards an inbound `X-Trace-ID`
   into `request.state.trace_id`.
2. **The access-log line**: the same middleware now emits one
   structured `"request"` log record per request (excluding
   `/health`/`/ready`/`/metrics` — see the middleware docstring) with
   `request_id`, `trace_id`, `method`, `path`, `status_code`, and
   `duration_ms` in `extra`. `common_utils/logging.py`'s `JSONFormatter`
   passes every `extra` field straight through, so this becomes real
   JSON keys in the log stream, not just Python attributes.
3. **OTel tracing** (`common_utils/tracing.py`), when
   `OTEL_ENABLED=true`, exports spans with the same trace id to
   whatever OTLP collector `OTEL_EXPORTER_OTLP_ENDPOINT` points at.

**Before this audit**: `request_id` only reached the log stream on
unhandled exceptions (the exception handler explicitly logged it). A
successful `/predict` call — the common case — produced no log line
carrying `request_id` at all, so "grep the logs for a request, then
find its trace" was only possible for requests that had already failed.
The access-log line closes that gap.

## Correlating in the demo stack (Loki)

1. `docker compose -f templates/service/docker-compose.demo.yml --profile monitoring up --build`
2. Open Grafana at `http://localhost:3000` (admin/admin). Prometheus
   and Loki are pre-provisioned as datasources — no manual setup.
3. Explore → Loki → query:

   ```logql
   {container="ml-service-api"} | json | request_id="<the id you have>"
   ```

   Promtail's pipeline (`monitoring/promtail/promtail-config.yml`)
   parses each JSON log line and extracts `request_id`/`trace_id`/`level`
   so they're queryable directly, not buried in an opaque text blob.
4. If the matching line has a non-empty `trace_id`, that is the id to
   search in your tracing backend. The demo stack ships no tracing
   backend (`OTEL_ENABLED` defaults false — see `common_utils/tracing.py`
   for why it's opt-in); wiring one is the next step below.

## Wiring the trace jump for real (production)

Grafana's Loki datasource supports a **derived field**: a regex over the
log line that turns a matched value into a clickable link to your
tracing backend, so "found the log line" becomes "one click to the
trace" instead of a manual copy-paste-search.

`monitoring/grafana/provisioning/datasources/datasources.yml` already
declares the derived field shape (matching `trace_id=(\w+)`) with an
empty `url` — fill in the search-by-trace-ID URL pattern for whichever
backend you actually run:

| Backend | URL pattern shape |
| --- | --- |
| Jaeger | `http://jaeger:16686/trace/${__value.raw}` |
| Grafana Tempo | use Tempo as a linked datasource (`datasourceUid`), not a raw URL |
| GCP Cloud Trace | `https://console.cloud.google.com/traces/list?tid=${__value.raw}` (project-scoped) |
| AWS X-Ray | `https://console.aws.amazon.com/xray/home#/traces/${__value.raw}` (region-scoped) |

This template does not pick one for you — cloud-provider tracing
backends have specific exporters (`common_utils/tracing.py`'s own
docstring: "Cloud Trace for GCP, ADOT for AWS; a single hard-coded
exporter would not fit").

## What this does NOT do

- **Log aggregation in production is the platform's job**, not this
  template's. Loki + Promtail here are scoped to the docker-compose
  demo so a reviewer gets a working experience without provisioning a
  cluster. A real deployment typically already has Cloud Logging,
  CloudWatch Logs, or a Fluentd/Fluent Bit → Loki/ELK pipeline running
  cluster-wide — duplicating that per-service would be the same
  over-engineering this template's Engineering Calibration Principle
  (`CLAUDE.md`) already warns against elsewhere.
- **Trace sampling, baggage, and span attribute policy** are configured
  at the OTel collector layer, not in application code — see
  `common_utils/tracing.py`'s module docstring.

## Related

- `common_utils/errors.py` — `RequestIDMiddleware`, the access-log line,
  `_ACCESS_LOG_EXCLUDED_PATHS`.
- `common_utils/tracing.py` — opt-in OTel wiring, adopter installation steps.
- `docs/observability/monitoring-stations.md` — where this station fits
  among the other five.
