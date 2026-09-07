# ADR-041 — Agentic Skill Expansion and Domain Taxonomy (External Landscape Review)

- **Status**: Accepted
- **Date**: 2026-07-02
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none.
- **Superseded by**: none
- **Related artifacts**:
  - `agentic/skills/pr-review/SKILL.md`, `agentic/skills/diagnose-bug/SKILL.md`,
    `agentic/skills/new-service-spec/SKILL.md`, `agentic/skills/incident-postmortem/SKILL.md`
    — the four new skills.
  - `templates/config/service_spec.schema.json`,
    `templates/config/service_spec.example.yaml` — the new pre-scaffolding
    ML-problem-spec artifact `new-service-spec` produces and validates.
  - `templates/config/agentic_manifest.yaml` — `domain:` field on every
    skill entry (25 total).
  - `scripts/validate_agentic_manifest.py` — `DOMAIN_VALUES` +
    `_validate_domain_enum`.
  - `AGENTS.md` — "How to Invoke Skills and Workflows" (model-invoked vs.
    user-invoked framing), the corrected agentic-surface ASCII tree.

## 1. Context

Five external repos were reviewed for patterns worth adopting into this
template's agentic governance system (rules/skills/workflows): a skills
catalog (`mattpocock/skills`), an agent-sandboxing runtime
(`mattpocock/sandcastle`), a 12+-persona orchestration framework
(`bmad-code-org/bmad-method`), a sequential spec-driven pipeline
(`github/spec-kit`), and a public skills-discovery tool
(`vercel-labs/skills` `find-skills`). The question was not "which of
these should we install" but "what, if anything, from each fills a real
gap in this repo's existing governance, evaluated against this
template's own Engineering Calibration Principle" — the same principle
that already rules out disproportionate tooling elsewhere in this repo
(`CLAUDE.md`: "2-3 models → CronJob, not Airflow").

## 2. Decision

Adopt four narrowly-scoped additions; reject the rest, each with a
recorded reason and (where applicable) a revisit trigger — the same
decision-annex discipline this repo's own audit rounds (R7-R10) already
apply to external comparisons.

### 2.1 Adopted

| Addition | Source of the idea | What gap it closes |
| --- | --- | --- |
| Skill `pr-review` | `mattpocock/skills` `code-review` (Standards + Spec, evaluated in isolation) | `rule-audit`/`security-audit` check fixed rubrics; nothing separated "violates a convention" from "implements the spec," evaluated independently so neither contaminates the other |
| Skill `diagnose-bug` | `mattpocock/skills` `diagnosing-bugs` (reproduce→minimize→hypothesize→instrument→fix→regression-test) | Only `debug-ml-inference` existed (ML-serving-specific); no generic systematic-debugging skill for CI/infra/tooling bugs — exactly the discipline used ad hoc to diagnose the R10 gitleaks false positive, now made reusable |
| Skill `new-service-spec` + `service_spec.schema.json`/`.example.yaml` | `github/spec-kit`'s spec-before-code discipline, NOT its tooling | `new-service.sh`/`copier copy` capture technical parameters but never the ML problem definition (label, fairness attribute, cost asymmetry) — `quality_gates.yaml` shipped with defaults nobody examined against a real answer |
| Skill `incident-postmortem` | `vercel-labs/skills` `find-skills` sourcing → `anthropics/knowledge-work-plugins@incident-response` (3.7K installs, official) as reference | `secret-breach-response` and `/incident` cover response; nothing covered structured, blameless review after closure |
| `domain:` field on all 25 skill manifest entries (`ml-data` / `platform-infra` / `security-compliance` / `sre-operations`) | `bmad-code-org/bmad-method`'s role specialization, NOT its persona/Party-Mode system | Role-based filtering/discoverability at ~5% of the cost of a persona system — orthogonal to and does not change AUTO/CONSULT/STOP |
| Explicit model-invoked (skill) vs. user-invoked (workflow) framing in `AGENTS.md` | `mattpocock/skills` taxonomy | The distinction already existed structurally (skills vs. workflows) but was never named, so new skill authors had no explicit prompt to decide which one they were writing |

### 2.2 Rejected

| Item | Verdict | Why | Revisit trigger |
| --- | --- | --- | --- |
| `mattpocock/sandcastle` (agent-execution sandboxing: Docker/Podman/Firecracker) | **Rejected, no trigger** | Solves a different layer than this repo governs. This template's AUTO/CONSULT/STOP decides *what* an agent may do; sandcastle decides *where* an agent's own process runs (OS/container level) — a concern for whoever hosts the coding agent, not for an ML service template. The sandboxing surface that matters for this repo's actual deliverable (an ML service) already exists and is calibrated: PSS, NetworkPolicy, non-root containers. | None — the mismatch is structural (wrong layer), not a maturity gap that closes over time |
| `bmad-code-org/bmad-method` full persona/Party-Mode system (12+ named domain-expert personas, multi-persona sessions) | **Rejected** | Violates this repo's own Engineering Calibration Principle. A parallel orchestration system for role specialization is the "Airflow for 2-3 models" mistake applied to agent governance. The `domain:` taxonomy (§2.1) captures the one part of the idea (specialization) worth having, without the orchestration layer. | Revisit only if the skill count grows large enough (order of 50+) that flat discoverability genuinely breaks down — not proactively |
| `github/spec-kit` full sequential pipeline (`/specify` → `/plan` → `/tasks` → `/implement`) | **Rejected** | This repo already converges on spec-kit's most valuable primitive without having imported it: `CLAUDE.md`'s "Critical Invariants" + `AGENTS.md`'s D-01..D-37 anti-patterns function as a "constitution," and the existing ADR + audit-wave-execution-verification-closure cycle (see the audit-methodology material this template's adopter-facing Guía cross-references) is functionally equivalent to specify→plan→tasks→implement. Importing spec-kit's tooling would duplicate an existing pattern under a different name. `new-service-spec` (§2.1) adopts the one genuine gap the comparison surfaced. | None identified — the two systems solve the same problem; a future revisit would only make sense if this repo's organic ADR/audit cycle broke down, which would be a different problem to solve on its own terms |
| `vercel-labs/skills` `find-skills` as a running tool in this repo | **Rejected as tooling; adopted as a one-time sourcing technique** | It is an external registry search, not something with a place in CI or the agentic surface itself. Real searches run this round confirmed the MLOps-specific skills market is immature (max ~410 installs, no reputable source) while Kubernetes/Terraform have strong official hits this repo's own coverage already exceeds in specificity (GKE/EKS parity, IRSA/WI, single-worker pattern) — adopting the generic official skill would be a downgrade, not an upgrade. | Re-run the search if a future gap can't be filled by an in-house skill and a reputable (official-source, high-install) hit exists that is *more* specific than what this repo already has — not met by any result found this round |

## 3. Invariants (contract-enforced)

- **I-041-1** — Every skill entry in `agentic_manifest.yaml` MAY declare
  `domain:`; if present it MUST be one of `ml-data`, `platform-infra`,
  `security-compliance`, `sre-operations` — enforced by
  `_validate_domain_enum` in `validate_agentic_manifest.py --strict`.
- **I-041-2** — `domain:` MUST NOT be read by any AUTO/CONSULT/STOP
  resolution logic — it is discoverability metadata only. A future
  change that makes `domain:` affect escalation is a new decision, not
  an extension of this one.
- **I-041-3** — `new-service-spec`'s output file MUST validate against
  `service_spec.schema.json` before the skill reports success, and a
  `null` `fairness_sensitive_attributes` MUST be paired with
  `fairness_attribute_confirmed_none: true` — an unconfirmed `null` is a
  schema violation, never a silent default (same non-guessing invariant
  `template-onboard` already applies to infra context).

## 4. Scope

**In scope**: the four skills, the domain taxonomy field + validator
check, the invocation-taxonomy documentation note, and the corrected
agentic-surface ASCII tree in `AGENTS.md` (a pre-existing drift —
`ci-green-verify`/`ci-green` were missing from that hand-maintained tree
since ADR-039 shipped — fixed in the same pass since this ADR already
touches that block).

**Out of scope**: any change to `agentic/rules/` or `agentic/workflows/`
(no new rule or workflow was warranted by this review); porting
`sandcastle`; any BMAD persona/Party-Mode system; the spec-kit pipeline
tooling; wiring `find-skills` into CI.

## 5. Consequences

### Positive

- Two concrete, currently-uncovered gaps close (`pr-review`'s dual-axis
  review, `diagnose-bug`'s systematic non-ML debugging) using patterns
  already proven inside this repo's own audit history, not speculative
  imports.
- `new-service-spec` gives `quality_gates.yaml` thresholds a documented
  origin — a real, examined answer instead of an unexamined default.
- `domain:` makes 25 skills filterable by role without adding a second
  orchestration system or touching AUTO/CONSULT/STOP semantics.
- Three external frameworks (sandcastle, BMAD Party-Mode, spec-kit
  pipeline) were evaluated with reasons on record — a future contributor
  proposing the same import again can be pointed at §2.2 instead of
  re-litigating it.

### Negative

- Four more skills to maintain (small — each is read-heavy/AUTO-mode,
  no new runtime dependency beyond what the repo already uses).
- One new schema/example-config pair (`service_spec.*`) is a new
  artifact class alongside `context.schema.json` and
  `adopter_context.schema.json` — a third pre-scaffolding file family
  for an adopter to learn, mitigated by `new-service-spec` interviewing
  rather than requiring the adopter to hand-author YAML.

### Neutral

- Surface counts move: skills 21→25 (rules and workflows unchanged at
  17 each). Cascaded through `AGENTS.md`, `CLAUDE.md` (root +
  `templates/service/` mirror), and `templates/config/agentic_manifest.yaml`
  in the same change (rule 16 / ADR-031 discipline).

## 6. Revisit triggers

See the per-rejected-item triggers in §2.2. Additionally:

- If `pr-review` or `diagnose-bug` prove to overlap too heavily with
  `rule-audit`/`debug-ml-inference` in practice (reviewers invoking the
  wrong one), merge rather than maintain four skills doing three jobs.
- If an adopter reports `new-service-spec`'s interview as friction
  rather than value on a genuinely trivial service, allow explicitly
  skipping it (documented opt-out), rather than removing the skill.

## 7. Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Adopt BMAD's full persona system to get role specialization | See §2.2 — violates the calibration principle; `domain:` gets the same benefit at a fraction of the cost |
| Adopt spec-kit's slash-command pipeline wholesale | See §2.2 — duplicates the ADR + audit-wave cycle this repo already runs |
| Wire `find-skills` into CI as a recurring "check for new skills" job | Registry search is a sourcing technique, not a gate; nothing in this repo's pipeline should depend on an external registry's uptime or content changing underneath it |
| Put `domain:` in each SKILL.md's frontmatter instead of the manifest | Would duplicate the same fact in 25 files with no single source of truth — the manifest is already the cross-surface index for `mode`/`authority`; `domain:` follows the same pattern instead of a new one |
| Do nothing; treat all five repos as "interesting but not applicable" | Two of the five surfaced gaps that were real regardless of the source repo's own merits (`pr-review`'s Standards/Spec split, `new-service-spec`'s missing ML-problem capture) — rejecting the framework does not mean rejecting the gap it revealed |

## 8. Related

- `docs/decisions/ADR-039-ci-green-verification-gate.md` — the most
  recent precedent for a narrowly-scoped skill addition with a verb/mode
  table, followed here for `pr-review`/`diagnose-bug`'s escalation design.
- `docs/decisions/ADR-023-agentic-portability-and-context.md` — the
  company/project context-file precedent `service_spec.*` follows for
  its own schema + example-config pair.
- `agentic/skills/template-onboard/SKILL.md` — the interview-and-validate
  pattern `new-service-spec` mirrors (never guess, escalate on
  ambiguity, secret-scan before reporting success).
