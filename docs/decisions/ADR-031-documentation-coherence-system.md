# ADR-031 — Documentation Coherence System

- **Status**: Accepted
- **Date**: 2026-06-30 (accepted in v0.20.0 line)
- **Deciders**: Template maintainer (DuqueOM)
- **Related**: ADR-027 (vendor-neutral canonical surface), ADR-023 (agentic
  manifest), ADR-012 (ADR tombstone precedent), rule 06 (per-document
  standards), rule 16 (this system's policy)

## Context

The template's enterprise value rests on documentation that stays *coherent* as
the repo evolves fast: a version string, an anti-pattern count, an ADR index, a
surface count, and a `llms.txt` summary are each restated in several files. Rule
06 governs what an individual ADR/README must *contain*, but nothing governed
coherence *between* documents.

An R7 Staff/Lead audit (2026-06-30, `docs/audit/AUDIT_R7_STAFF_LEAD.md`) found
this drift had already accumulated — all Low severity, but exactly the class that
erodes enterprise credibility:

- `VERSION` (0.18.0) lagged the latest released `CHANGELOG.md` heading (v0.19.0).
- `llms.txt` was frozen in the **v1.3.0 era**: it advertised "12 anti-patterns
  (D-01 to D-12)", "5 Claude Code rules", "8 skills", "8 workflows" — when the
  repo had reached D-34, 17 rules, 18 skills, 14 workflows.
- The two `CLAUDE.md` files quoted "32 invariants" and surface counts
  "15 rules + 16 skills + 12 workflows" that no longer matched reality.

These are deterministic, machine-checkable facts. Catching them by eye at review
time does not scale and had already failed.

## Options Considered

| Option | Pros | Cons |
| -------- | ------ | ------ |
| **A. Adopt an external tool wholesale** (towncrier, release-please, semantic-release, Log4brains) | Battle-tested; community support | None covers *cross-document* coherence as a single gate; each owns one slice (changelog OR ADRs OR version) and adds a dependency + workflow the 2–3-person calibration target doesn't warrant |
| **B. Documentation-as-prose convention only** (a CONTRIBUTING note) | Zero code | Exactly what failed — conventions without a gate drift |
| **C. A coherence *contract* enforced by a deterministic gate + an agentic skill that fixes drift** (chosen) | Single source of truth per fact; CI-blocking; reuses the existing `check_*_drift.py` + agentic surface patterns; no new deps | We author and maintain the gate ourselves |

## Decision

Adopt **Option C**: encode a cross-document coherence *contract* and enforce it
the same way the repo already enforces every other invariant — a deterministic
gate plus an agentic surface that fixes drift.

Concretely:

1. **Rule 16 (`agentic/rules/16-doc-coherence.md`)** — the policy: a
   single-source-of-truth register, the SemVer/Keep-a-Changelog versioning
   policy, the change-traceability chain (decision → ADR → CHANGELOG → release →
   VERSION), and a "if you touch X, update Y" cascade map.
2. **`scripts/check_doc_coherence.py`** — the deterministic gate (sibling of the
   `check_*_drift.py` family): seven checks — version SSoT, llms.txt version,
   anti-pattern count, agentic surface counts, ADR traceability/no-silent-gaps,
   release note existence, and a documentation language + private-reference
   guard (added AUDIT R10, 2026-07-02).
3. **`doc-coherence` skill + `/doc-coherence` workflow** — the productivity
   multiplier that reads gate output and applies the cascade map, with
   CONSULT/STOP boundaries (never renumber an ADR, never rewrite a released
   heading).
4. **CI job `doc-coherence-gate`** in `validate-templates.yml` — **blocking**,
   consistent with the deterministic `check_*` family (the staged shadow→enforce
   pattern is reserved for *probabilistic/autonomous* features such as CI
   self-healing and the memory plane; a string-comparison gate carries no such
   risk and so enforces from day one, seeded green).

We **base the design on** industry patterns without taking a hard dependency on
any: Keep a Changelog + SemVer (already in use), towncrier/changesets
("one fragment per change" traceability), release-please / Conventional Commits
(version↔changelog coupling), MADR / Log4brains (ADR lifecycle), Vale (prose
consistency), Diátaxis (doc taxonomy). No single tool offers the *cross-document*
gate, so we compose the contract ourselves and keep the dependency surface flat.

We deliberately do **not** add a new MCP server (no external system to reach;
all work is intra-repo file edits already native to the agent) and do **not**
mint a new `D-NN` anti-pattern (D-01..D-34 catalogue *technical footguns in
scaffolded output* and are tested as absence-in-the-service; doc coherence is a
meta/process concern, correctly expressed as a rule + gate).

## Rationale

This makes "shipped" and "documented" identical for the facts that matter, the
same way ADR-025's gate did for `common_utils` and the dashboard-inventory gate
did for Grafana. It reuses three patterns the repo already trusts — the
`check_*_drift.py` gate, the canonical-`agentic/`-plus-generated-adapters surface
(ADR-027), and the AUTO/CONSULT/STOP behavior protocol — so it adds capability
without adding architecture.

## Consequences

**Positive**

- Version, anti-pattern count, surface count, ADR index, and `llms.txt` can no
  longer silently drift; a PR that desyncs them fails CI.
- A repeatable, agent-drivable procedure (`/doc-coherence`) to propagate any
  change across its mirror documents.
- The gate is self-demonstrating: on introduction it caught four real drift
  instances before they were fixed.

**Negative / costs**

- One more repo-root gate script and CI job to maintain.
- The checks are intentionally conservative (counts, versions, ADR gaps,
  language/privacy); full prose-level style consistency (Vale-style) is out
  of scope for v1 of the gate.

**Neutral**

- The scaffolded service (`templates/service/`) vendors rule 16 + the gate
  (mirrors the ADR-025 pattern) — `scripts/check_vendored_runtime_drift.py`
  keeps the vendored copy byte-identical to the canonical source.

## Revisit When

- Prose/style drift becomes a problem → add a Vale lane as check C8.
- The repo adopts Conventional Commits → wire release-please and let the gate
  verify its output instead of hand-maintained CHANGELOG headings.
