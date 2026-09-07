# ADR-022: PSI Drift Thresholds — Warn / Alert Cutoffs

- **Status**: Accepted
- **Date**: 2026-04-29
- **Supersedes**: none (formalizes the previously implicit `psi_warn = 0.10`, `psi_alert = 0.25` defaults)
- **Related**: ADR-006 (closed-loop monitoring), ADR-009 (retraining triggers), ADR-020 (R4 audit remediation §S2-3)
- **Authors**: Staff/Lead, AI staff engineer

## Context

The template's drift detection (`templates/service/monitoring/drift_detection.py`)
computes Population Stability Index (PSI) per feature against the
training-time baseline distributions captured in
`templates/eda/baseline_distributions.parquet` (D-15). The thresholds
have been hard-coded as `psi_warn = 0.10` and `psi_alert = 0.25` since
v1.7.x. R4 audit finding M6 flagged that these are de-facto industry
constants but lacked a per-feature override mechanism and a written
rationale grounding the choice.

PSI between two distributions A and B over K bins is:

```text
PSI = Σ_k (p_A,k − p_B,k) · ln(p_A,k / p_B,k)
```

where `p_*,k` are the proportions in bin k of distributions A and B.

## Decision

Adopt **`psi_warn = 0.10`** and **`psi_alert = 0.25`** as the default
per-feature thresholds, with explicit per-feature overrides via
`templates/service/config/drift_thresholds.yaml`.

### Hard rules

1. **Defaults derive from the canonical PSI scale.**
   - `PSI < 0.10` → "no significant change"
   - `0.10 ≤ PSI < 0.25` → "moderate change; investigate"
   - `PSI ≥ 0.25` → "significant change; act"

   Source: Siddiqi (2006), *Credit Risk Scorecards*, p. 265, where the
   thresholds were introduced for credit-risk score monitoring and have
   become the de-facto standard across financial-services drift work.

2. **Quantile-based bins (D-08).** PSI with uniform-width bins is
   sensitive to long tails and skewed distributions; quantile bins
   (default 10 quantile bins from the training reference) make PSI
   stable across feature distributions. The
   `baseline_distributions.parquet` artifact stores the bin edges from
   training so drift evaluation uses the same partition.

3. **Per-feature override file.** The default thresholds are not
   appropriate for every feature. The override file is structured as:

   ```yaml
   # templates/service/config/drift_thresholds.yaml
   defaults:
     psi_warn: 0.10
     psi_alert: 0.25
   features:
     amount:
       psi_warn: 0.05
       psi_alert: 0.15
       rationale: "Heavy-tailed; small distribution shifts are economically meaningful."
     country_code:
       psi_warn: 0.20
       psi_alert: 0.40
       rationale: "Naturally lumpy; default thresholds produce too many false alerts."
   ```

   Every override MUST carry a `rationale` field. A drift threshold
   override without rationale is rejected at config-load time.

4. **The `2× alert` super-threshold maps to the dynamic-risk signal
   `drift_severe`** documented in `MEMORY[01-mlops-conventions.md]`
   §"Dynamic Behavior Protocol". When any feature's PSI exceeds
   `2 × psi_alert` (default `0.50`), the agent's `risk_context.py`
   raises the `drift_severe` signal, which automatically escalates
   AUTO operations to CONSULT.

5. **Drift on a non-feature variable** (e.g. label distribution drift)
   uses the SAME thresholds by default but is flagged separately in
   the alert payload — operators care about the difference.

6. **Heartbeat alerting (D-09)** is a precondition. PSI thresholds are
   meaningless without a heartbeat alert that fires when the drift
   CronJob fails to run. The drift PrometheusRule
   (`templates/k8s/policies/slo-prometheusrule.yaml`) ships heartbeat
   alerts alongside the PSI alerts.

### Threshold review cadence

- Re-evaluate quarterly on services in production.
- After any model retrain, the operator may freeze thresholds at the
  post-retrain reference and document the freeze decision in the
  service ADR.
- Per-feature overrides require a fresh rationale at every annual
  review; stale overrides without a current rationale revert to defaults.

## Consequences

### Positive

- Defaults match the most-cited industry source (Siddiqi 2006).
- Per-feature overrides handle the lumpy / heavy-tailed feature case
  without polluting the default.
- The `2× alert` super-threshold connects PSI to the dynamic-risk
  protocol cleanly — drift severe → escalate prudence.
- Quantile binning (D-08) is the antidote to the "PSI looks fine because
  bins are wrong" failure mode.

### Negative / cost

- Per-feature overrides require operator judgment per service; the
  template cannot tune thresholds for every feature in every domain.
- 10 quantile bins is a default; high-cardinality categorical features
  may need fewer.
- PSI does not detect every drift class — concept drift (relationship
  changes) is invisible to PSI but visible to ADR-007 sliced performance
  monitoring. PSI is a **necessary but not sufficient** drift signal.

### Neutral

- The numeric thresholds are the same as before; this ADR makes the
  rationale explicit and the override mechanism formal.

## Acceptance criteria

- [x] `templates/service/monitoring/drift_detection.py` uses the
      canonical defaults.
- [x] Per-feature override file format documented in this ADR and
      referenced from `monitoring/drift_detection.py` docstring.
- [ ] First service to use a non-default threshold publishes a service-level ADR
      citing this one.
- [ ] `risk_context.py` `drift_severe` signal computation cites this ADR.

## Revisit triggers

- A service publishes evidence that the defaults produce material false
  positive / false negative rates on its production data.
- A new public reference supersedes Siddiqi 2006 with empirically
  validated thresholds for a non-credit domain we need to support.
- The `risk_context.py` escalation table changes such that PSI no longer
  feeds `drift_severe`.

## References

- Siddiqi, Naeem (2006), *Credit Risk Scorecards*, Wiley, pp. 264–265.
- Yurdakul, B. (2018), "Statistical properties of population stability
  index" (review of PSI thresholds in credit scoring).
- ADR-008 §"Why quantile binning" — sister ADR explaining the bin
  construction; pinned by the same reference distribution artifact.
