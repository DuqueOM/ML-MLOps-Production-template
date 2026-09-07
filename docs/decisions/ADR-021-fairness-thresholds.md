# ADR-021: Fairness Thresholds — Disparate Impact Ratio Floor

- **Status**: Accepted
- **Date**: 2026-04-29
- **Supersedes**: none (formalizes the previously implicit DIR ≥ 0.80 used in `AGENTS.md`)
- **Related**: ADR-002 (model promotion governance), ADR-008 (champion/challenger), ADR-020 (R4 audit remediation
  §S2-3), AGENTS.md §"Model Quality Invariants"
- **Authors**: Staff/Lead, AI staff engineer

## Context

The template has enforced `Disparate Impact Ratio (DIR) ≥ 0.80` as a
quality gate before model promotion since v1.7.x via the
`templates/service/tests/test_quality_gates_config.py` contract test
and the `AGENTS.md` invariant. The threshold has not had a dedicated
ADR. R4 audit finding M3 flagged the gap: a number that gates
production decisions must carry an explicit justification per domain,
not be a literal pulled from generic guidance.

The DIR is defined as:

```text
DIR(group_A, group_B) = P(positive outcome | group_A) / P(positive outcome | group_B)
```

normalized so the ratio is ≤ 1 (i.e. DIR closer to 1 is more equitable).

## Decision

Adopt **DIR ≥ 0.80** as the **default** quality-gate floor for all
services, with **per-domain overrides documented as ADR addenda or
service-level service.yaml entries**.

### Hard rules

1. The default floor is `0.80`. This is the legal "four-fifths rule"
   articulated by the EEOC's *Uniform Guidelines on Employee Selection
   Procedures* (29 CFR §1607.4(D)) and adopted as a baseline in
   ML-fairness practice (Barocas, Hardt & Narayanan, *Fairness and
   Machine Learning*, Ch. 3; Friedler et al., 2016).

2. **Domain-elevated thresholds.** Some domains require a floor higher
   than 0.80. The following table is the canonical starting point; each
   service may override via a service-level ADR addendum:

   | Domain | DIR floor | Rationale |
   | --- | --- | --- |
   | Credit / lending | ≥ 0.85 | ECOA + Reg B; FFIEC examiner expectations on adverse-action consistency |
   | Employment / hiring | ≥ 0.80 (with documented BFOQ exceptions) | Title VII + EEOC four-fifths rule |
   | Healthcare allocation | ≥ 0.90 | Institutional review + ACA §1557 |
   | Insurance underwriting | ≥ 0.85 | State-level rate-discrimination filings |
   | Advertising / engagement | ≥ 0.75 | Lower stakes; tradeoff with relevance |
   | Fraud / abuse detection | ≥ 0.80 | False-positive incidence shouldn't fall asymmetrically on protected groups |

3. **The floor is an OR-of-pairs**: for a protected attribute with K
   levels, the gate fires if ANY pair (i, j) has `DIR(i, j) < floor`.
   This catches the "majority looks fine, minority-vs-minority is
   broken" pattern that single-pair tests miss.

4. **The DIR check is paired with calibration parity**. A model can pass
   DIR while having unequal calibration; the quality gate also checks
   `|calibration_error_group_A − calibration_error_group_B| ≤ 0.05` per
   pair. ADR-007 (sliced performance analysis) defines the calibration
   metric.

5. **Fairness gate is BLOCKING for promotion.** A service whose latest
   evaluation fails DIR cannot be promoted to staging or prod. Override
   requires an ADR documenting the rationale + business sign-off,
   following the AGENTS.md `[AGENT MODE: STOP]` protocol.

6. **`[0.80, 0.85)` is the consultation band.** When DIR falls in this
   band, the agent emits `[AGENT MODE: CONSULT]` and waits for human
   review even though the gate technically passes. The band exists
   because crossing 0.80 is a legal threshold, not a moral boundary;
   margin matters.

### Threshold review cadence

- Re-evaluate the per-domain table annually OR after any material
  regulatory change (e.g. EEOC guidance update, Reg B amendment, EU AI
  Act enforcement).
- Document re-evaluations as ADR addenda; do not silently change the
  defaults.

## Consequences

### Positive

- Default floor matches the most-cited regulatory standard (four-fifths
  rule) so adopters in any jurisdiction have a defensible baseline.
- Per-domain overrides prevent one-size-fits-all under-protection
  (healthcare) AND over-blocking (advertising).
- Pair-wise OR test catches K > 2 protected-attribute failures.
- Calibration parity check closes the well-known DIR + calibration gap.

### Negative / cost

- Per-domain overrides require adopter judgment; the template cannot
  pick the right floor for every service.
- The consultation band (`[0.80, 0.85)`) adds a CONSULT operation that
  reviewers must process; this is intentional friction.

### Neutral

- The numeric floor is the same as before; this ADR makes the rationale
  explicit and the override mechanism formal.

## Acceptance criteria

- [x] `AGENTS.md` §"Model Quality Invariants" cross-references this ADR.
- [x] `templates/service/tests/test_quality_gates_config.py` enforces
      DIR ≥ 0.80 by default and reads service-level overrides.
- [x] The per-domain override mechanism is documented (`service.yaml`
      `quality_gates.fairness.dir_floor`).
- [ ] First service to use a non-default floor MUST publish an addendum
      ADR citing this one.

## Revisit triggers

- EEOC issues updated guidance affecting the four-fifths rule.
- EU AI Act enforcement defines a different floor for high-risk systems.
- A domain in the table sees a regulatory update changing its floor.
- An adopter publishes a study showing the floor is too lax / too strict
  for a domain we list.

## References

- EEOC, *Uniform Guidelines on Employee Selection Procedures*, 29 CFR §1607.4(D).
- Barocas, Hardt, Narayanan, *Fairness and Machine Learning*, Ch. 3, fairmlbook.org.
- Friedler, Scheidegger, Venkatasubramanian (2016), "On the (im)possibility of fairness."
- Pleiss et al. (2017), "On fairness and calibration."
