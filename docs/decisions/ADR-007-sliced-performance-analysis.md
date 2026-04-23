# ADR-007: Sliced Performance Analysis as First-Class Monitoring

## Status

Accepted

## Date

2026-04-23

## Context

Global metrics (aggregate AUC, F1, Brier) are necessary but profoundly
incomplete. In any real service, degradation almost always appears first in
a subpopulation — a country, a channel, a specific product segment — while
the global metric remains misleadingly healthy because that segment is a
small share of traffic.

Without slicing, the monitoring story is:

> "AUC dropped from 0.87 to 0.83 — *somewhere, for some reason*."

Engineers then spend days grep-ing through logs and tables. This is a
well-known MLOps failure mode; every serious on-call playbook treats the
inability to slice as a structural defect.

## Decision

Treat slicing as a first-class citizen of the monitoring pipeline, not a
nice-to-have dashboard feature:

1. **Slice declaration** is config-driven in `configs/slices.yaml`.
   Unknown slice names in incoming requests are silently ignored.
2. **Slice cardinality is bounded.** Only low-cardinality categoricals
   (country, channel, segment) or explicitly-bucketed numeric features
   (via `bins:`) are allowed. Unbounded free-text slices are FORBIDDEN —
   they explode Prometheus label cardinality and make grouping meaningless.
3. **Every sliced metric is pushed to Prometheus** with labels
   `{slice_name, slice_value, metric}` so Grafana can filter on any
   dimension and Alertmanager can route per slice.
4. **Below `min_samples_per_slice` (default 50), the slice status is
   reported as `insufficient_data`** — never a spurious alert based on
   small-sample noise.
5. **Alerts discriminate global vs sliced causes.** `GlobalAUCBelowAlert`
   and `SlicedAUCBelowAlert` carry different meanings: the first is a
   population-wide concept drift; the second is a subpopulation issue
   likely rooted in the data pipeline for that segment.

Concretely, `performance_monitor.py` iterates over every slice defined in
`slices.yaml`, groups the joined predictions+labels, and emits per-slice
metrics. The output JSON is consumed by:

- `PrometheusRule` alerts (performance-prometheusrule.yaml)
- The `concept-drift-analysis` skill (RCA procedure)
- The monthly `/performance-review` workflow (trend analysis)

## Rationale

**Why slice at monitoring time, not at training time?**
Training evaluations often include subgroup metrics, but they freeze at
release. Slicing in production lets us detect that a slice
*became* problematic after deploy (new market, new channel, new feature
interaction) even if it was healthy at training time.

**Why a YAML config rather than auto-discovery?**
Auto-discovery of slices from request payloads would give unbounded
cardinality — every novel `transaction_id` would become a slice. Explicit
declaration forces the engineer to think about which dimensions are
actionable.

**Why report `insufficient_data` rather than skipping silently?**
Silent skipping hides monitoring gaps. Explicit `insufficient_data` status
surfaces the fact that the slice exists but cannot be evaluated — the
engineer knows to widen the window or lower the threshold consciously.

## Consequences

### Positive

- Alerts become actionable: "AUC=0.58 for country=ES" is diagnosable;
  "AUC=0.83" is not.
- Root-cause analysis follows a decision tree (global vs sliced × data
  drift vs label noise vs real concept drift) rather than blind search.
- Monthly performance reviews can detect slow, silent degradations that
  never cross a hard threshold but compound over quarters.

### Negative

- Every service scaffolded from the template must fill out `slices.yaml`
  with its actual dimensions. An empty slices list means global-only
  monitoring — which is worse than the previous state in terms of
  actionability.
- Adding a slice requires updating `PredictionRequest.slice_values` field
  population (clients must pass the slice values).
- Prometheus label cardinality must be manually budgeted by the operator;
  4–6 slices with 3–8 values each is the template's calibrated scale.

### Mitigations

- `slices.yaml` ships with realistic examples (country, channel,
  model_version, score_bucket) so users start from a working baseline
- The `concept-drift-analysis` skill explicitly warns against
  high-cardinality slices (rule 13)
- Sample-size gate defaults to 50 — adjustable via `min_samples_per_slice`
  per service

## Revisit When

- **Automatic slice discovery** with bounded cardinality (e.g., top-K
  frequent values) becomes a validated pattern from operators
- **Multi-objective slicing** (intersections like country × channel) is
  required in >50% of target audience services
- **ML-based segmentation** (cluster the feature space, slice by cluster)
  replaces or augments config-declared slices

## Related

- ADR-001 — Template scope (slicing is classical ML — applies)
- ADR-006 — Closed-loop monitoring (provides the predictions + labels)
- ADR-008 — Champion/Challenger (sliced comparisons can be a future extension)
- Rule `.windsurf/rules/13-closed-loop-monitoring.md`
- Skill `concept-drift-analysis`
- Workflow `/performance-review`
