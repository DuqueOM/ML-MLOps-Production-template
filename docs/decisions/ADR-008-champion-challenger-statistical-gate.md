# ADR-008: Champion/Challenger Statistical Gate Before Promotion

## Status

Accepted

## Date

2026-04-23

## Context

The template already uses Argo Rollouts for canary deployments: traffic is
shifted progressively (10% → 30% → 60% → 100%) with automatic rollback on
HTTP error rate and p95 latency breaches. This is a **delivery** mechanism,
not a **model comparison** mechanism.

Concretely, a canary rollout does not answer the question "is the new model
statistically better than the current one?". It only answers "does the new
pod crash?". Two distinct failure modes are currently unguarded:

1. A new model that is measurably worse on ML metrics but has stable
   latency / error rate would pass the canary gate and replace a better
   champion.
2. A new model with a tiny, noisy improvement would be promoted even
   though the improvement is not statistically distinguishable from zero
   — adding deployment risk for no measurable benefit.

The underlying requirement is a **statistical comparison between champion
and challenger on the SAME holdout before any traffic-level rollout**.

## Decision

Introduce `service/src/{service}/evaluation/champion_challenger.py`
implementing a dual-test comparison:

1. **McNemar exact binomial test** for paired classification
   - Discordant pair counts: b (champion right, challenger wrong),
     c (champion wrong, challenger right)
   - Null hypothesis: identical error rates
   - Uses `scipy.stats.binomtest` for exact p-value (no chi-square
     approximation issues on small samples)

2. **Bootstrap ΔAUC with 95% confidence interval**
   - `n_bootstrap` (default 1000) paired resamples of the holdout
   - Degenerate single-class bootstrap folds are filtered
   - The lower bound of the CI is the decision driver, not the point
     estimate — this avoids promoting on a lucky run

The decision function combines both tests into a tri-state outcome:

| Decision | Conditions |
|----------|-----------|
| `block`    | CI lower bound < `-non_inferiority_margin` (challenger meaningfully worse) |
| `promote`  | Point ΔAUC > `superiority_margin` AND McNemar p < `alpha` |
| `keep`     | Improvement not statistically significant, but not worse either |

Configurable via `configs/champion_challenger.yaml` with default
`alpha=0.05`, `non_inferiority_margin=0.005`, `superiority_margin=0.005`.

Integration:
- New CI step in `cicd/retrain-service.yml` gates promotion on the C/C exit
  code (0 = promote, 1 = keep, 2 = block)
- The statistical report is posted to the GitHub Actions step summary for
  audit trail
- `model-retrain` skill documents Step 5.5 (C/C gate) between quality gates
  and promotion

## Rationale

**Why both McNemar AND bootstrap?**
McNemar is the sensitive test for CLASSIFICATION disagreement on
individual samples; bootstrap ΔAUC captures the ranking-quality change.
Neither alone is sufficient: McNemar can fire on a net-zero shuffle of
errors; bootstrap CI can be narrow on a lucky but not statistically
significant improvement. Requiring both to align prevents false
promotions on noise.

**Why non-inferiority margin (0.005 default)?**
Exact equality is unrealistic; every retrain produces small numerical
differences. A 0.5% band is lenient enough to pass trivially-different
models and strict enough to catch real regressions.

**Why tri-state (not just promote/reject)?**
`keep` is distinct from `block`: "keep" means the challenger is fine but
not measurably better — deploying it adds risk for no reward. "Block"
means the challenger is genuinely worse and must be investigated. Issue
labels (`champion-challenger`) allow routing to different teams.

**Why not shadow mode / traffic mirroring?**
Istio-based shadow deploys require a running control plane in every
target cluster, plus the application must be designed to handle duplicate
requests. Both are legitimate patterns but out of scope for the
template's target audience (1–5 classical ML models). Marked as
future-work trigger below.

## Consequences

### Positive

- Retraining without Champion/Challenger → outcome: "pass or fail gates"
  (binary, lots of false promotions)
- Retraining WITH Champion/Challenger → outcome: "promote / keep / block"
  (three meaningful states, fewer risky deploys)
- Exit codes allow CI to propagate the decision without bespoke parsing
- Statistical evidence is audit-able (`reports/champion_challenger.json`)

### Negative

- Requires a curated holdout set that both champion and challenger are
  evaluated on. This is a DVC-tracked artifact now — one more thing to
  maintain.
- Bootstrap (1000 iterations × 2 AUC computations) costs ~1–2 minutes on
  a typical holdout of 10k–100k rows. Acceptable for a retraining CI,
  not for live canary.
- Domain-dependent margins (`non_inferiority_margin`, `superiority_margin`)
  require human judgment; shipping defaults of 0.005 is a compromise that
  will not suit every service.

### Mitigations

- `configs/champion_challenger.yaml` is heavily commented so that each
  service consciously calibrates margins
- The `model-retrain` skill walks through exit codes and their meaning,
  reducing the risk of misinterpretation
- Holdout data is expected to be the same curated set used for quality
  gates — no NEW artifact is introduced

## Revisit When

- **Shadow mode becomes necessary** for any service (multi-tenant,
  high-stakes, or regulatory requirement) — open ADR-013 with Istio /
  traffic mirroring pattern
- **Sliced Champion/Challenger** (per-slice promotion decisions) is
  requested — natural extension once ADR-007 slicing stabilizes
- **Multi-objective comparison** (e.g., AUC gain vs latency regression
  trade-off) replaces single-metric ΔAUC
- **Non-classification models** enter the template scope (regression /
  ranking) — McNemar does not apply; add a regression-specific gate

## Related

- ADR-001 — Template scope (single-team classical ML — applies)
- ADR-002 — Model promotion governance (C/C is the automated part; the
  STOP-mode human approval remains)
- ADR-006 — Closed-loop monitoring (provides post-deploy performance
  tracking that C/C gates the pre-deploy step)
- ADR-007 — Sliced analysis (future sliced C/C extension)
- Rule `.windsurf/rules/13-closed-loop-monitoring.md` (D-22 covers the
  statistical gate as STOP-class operation)
- Skill `model-retrain` Step 5.5
