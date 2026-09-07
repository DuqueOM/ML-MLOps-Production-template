# ADR-038 — Compliance Mapping (NIST AI RMF / ISO 42001 / EU AI Act)

- **Status**: Accepted
- **Date**: 2026-07-02
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none. Executes item R9-03 of
  `docs/audit/ACTION_PLAN_R9_ENTERPRISE_BENCHMARK.md`.
- **Superseded by**: none
- **Related artifacts**:
  - `docs/COMPLIANCE_MAPPING.md` — the mapping document itself.
  - `docs/model-card-template.md`, `RUNBOOK.md` — the primary artifacts it
    indexes.

## 1. Context

The R9 enterprise benchmark (`docs/audit/ACTION_PLAN_R9_ENTERPRISE_BENCHMARK.md`
§2.2) compared this template against the practice an enterprise evaluator
actually uses to decide whether to adopt a tool: not "does it have
features," but "can I use its artifacts as evidence in my own governance
process." The finding: the template already produces the artifacts that
NIST AI RMF, ISO/IEC 42001, and the EU AI Act's high-risk obligations
(Arts. 9–15) ask for — quality gates with a fairness floor, drift
monitoring, an append-only audit trail, human-in-the-loop promotion gates,
signed/attested supply chain — but **nothing states this explicitly**. An
adopter's risk/compliance team has to reverse-engineer the mapping
themselves, which is exactly the kind of legibility gap that keeps an
otherwise-compliant template out of a procurement shortlist.

No open-source MLOps template in the reference set (CCDS, Kedro, ZenML,
Metaflow, Kubeflow) publishes this kind of mapping — it is a genuine,
low-cost differentiator, not table stakes.

The risk of doing this badly is real: an adopter who reads
"NIST AI RMF" and "EU AI Act" next to this template's name could reasonably
infer a *certification* claim that no open-source template can honestly
make. The decision below exists specifically to prevent that inference.

## 2. Decision

Publish `docs/COMPLIANCE_MAPPING.md`: a table-form mapping from framework
control questions to the template artifact that answers them, for:

1. **NIST AI RMF 1.0** — GOVERN / MAP / MEASURE / MANAGE functions.
2. **ISO/IEC 42001:2023** — Annex A control areas (A.4–A.10, the areas with
   a direct engineering artifact; organizational-only controls like
   management review cadence are out of scope by design, §3 below).
3. **EU AI Act** Arts. 9–15 (risk management, data governance, technical
   documentation, record-keeping, transparency, human oversight, accuracy/
   robustness/cybersecurity) + a pointer from Annex IV to the three
   artifacts (`model-card-template.md`, ADRs, `RUNBOOK.md`) that jointly
   cover it.

### 2.1 Explicit non-claims (the load-bearing part of this ADR)

The document itself, not just this ADR, states in its own header:

- This is a **mapping of artifacts to evidence**, never a certification,
  attestation, or legal opinion.
- **No framework certifies a template.** Only a specific deployed system,
  operated by a specific organization, can be assessed or certified.
- Risk classification of the adopter's specific use case, organizational
  governance roles beyond the template's default `ROLES.md`, conformity
  assessment, and legal review are explicitly out of scope and remain the
  adopter's responsibility.

### 2.2 Freshness discipline

The mapping includes a verified-in-place timeline note (Digital Omnibus
agreement, 2026-05-07, moving Annex III high-risk obligations from
2026-08-02 to 2027-12-02) and a Revisit-triggers section so the document
does not silently fossilize the way `llms.txt` did before ADR-031 (rule 16
doc-coherence). It is NOT registered as a rule-16 tracked fact (no version
number or count lives in it) — it is prose that ages by regulatory event,
not by release, so it is reviewed on trigger rather than gated on every
release.

## 3. Scope

**In scope**: the mapping document; this ADR; a link from `README.md` and
`docs/ADOPTION.md`.

**Out of scope** (deliberately):

- Organizational-only ISO/IEC 42001 controls (A.1–A.3, management
  commitment/policy/roles) that no template artifact can satisfy — listing
  them would imply a false completeness.
- Any change to the underlying gates/artifacts themselves — this ADR
  documents what exists; it does not add new invariants. If a mapped
  control turns out to be unmet, the fix is a new ADR for the gap, not an
  edit to this mapping to paper over it.
- Automated compliance tooling (a GRC platform integration, evidence
  export API) — no signal yet that an adopter needs it (Engineering
  Calibration Principle).

## 4. Consequences

### Positive

- An adopter's compliance/risk team can complete a first-pass gap
  assessment in minutes instead of days.
- Makes explicit (and therefore reviewable) a claim that was previously
  implicit and un-auditable: "this template's gates happen to be
  compliance-relevant."
- Differentiates against every open-source reference template in the
  benchmark, none of which publish this.

### Negative

- One more document that could theoretically drift from the code it
  references. Mitigated by the Revisit-triggers section and by the
  document's own instruction: "if this document and the code ever
  disagree, the code wins."
- Requires periodic attention to regulatory calendar changes (mitigated:
  the timeline note is dated and the trigger is explicit).

### Neutral

- Adds no code, no CI job, no new dependency — pure documentation.

## 5. Revisit triggers

- The Digital Omnibus is formally adopted/published in the Official
  Journal → re-verify and update the Art. 9–15 timeline note.
- A new NIST AI RMF profile (e.g., a Generative AI profile revision) or an
  ISO/IEC 42001 amendment ships → re-audit control coverage.
- Any artifact referenced in the mapping is renamed, removed, or its
  behavior changes materially → update the mapping in the SAME PR (same
  discipline ADR-034's CCDS mapping already established).
- An adopter reports using this document in an actual audit/procurement
  process → capture what worked/didn't as a follow-up note; consider
  promoting specific sections to `docs/ADOPTION.md`.

## 6. Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Do nothing; let adopters do their own mapping | Repeats work every serious adopter would otherwise redo independently; the R9 benchmark found this is a real, common gap |
| Claim ISO 42001 / AI Act "compliance" or "readiness" outright | False and legally risky — no template can BE compliant, only a deployed system can; would damage credibility the moment a careful reader checked |
| Build a GRC-platform integration or automated evidence exporter | Over-engineering at this scale — no adopter has asked for it (Engineering Calibration Principle); a well-written static mapping serves the same first-pass need |
| Fold the mapping into `README.md` directly | `README.md` is already dense; a dedicated file with its own revisit cadence is more honest about the fact that this content ages on a different clock than a release |

## 7. Related

- `docs/audit/ACTION_PLAN_R9_ENTERPRISE_BENCHMARK.md` — the benchmark that
  identified this gap (item R9-03).
- `docs/decisions/ADR-031-documentation-coherence-system.md` — the
  precedent this ADR deliberately does NOT fully inherit (this mapping is
  reviewed by trigger, not gated by rule 16, per §2.2).
- `docs/decisions/ADR-034-ccds-aligned-generated-layout.md` — the
  "documentation-only mapping, same-PR-update discipline" pattern this ADR
  reuses.
