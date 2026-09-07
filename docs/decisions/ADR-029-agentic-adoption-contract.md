# ADR-029 — Agentic Adoption Contract & Interoperability Strategy

- **Status**: Accepted
- **Date**: 2026-06-29
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none. Complements ADR-001 (scope boundaries),
  ADR-023 (portability layer), ADR-027 (vendor-neutral canonical surface),
  ADR-005 / ADR-010 (agent behavior + dynamic risk).
- **Superseded by**: none
- **Related artifacts**:
  - `docs/audit/ACTION_PLAN_ADAPTABILITY.md` — the living execution tracker.
  - `templates/config/agentic_manifest.yaml` — cross-surface index.
  - `scripts/sync_agentic_adapters.py`, `scripts/validate_agentic_manifest.py`.
  - `AGENTS.md` — behavior authority (unchanged by this ADR).

## 1. Context

The template wins on production discipline, governance, multi-cloud parity, and
the agentic spine (AUTO/CONSULT/STOP + dynamic risk + 32 encoded anti-patterns).
It trails the de-facto industry references on three adoption levers:

1. **Standardized scaffolding** — adopters expect `cookiecutter`/`copier`, not a
   bespoke `new-service.sh` (Cookiecutter Data Science is the de-facto standard).
2. **Low-friction local-first on-ramp** — the template assumes Kubernetes and
   Terraform from day one; ZenML's "run locally, swap stacks to cloud" gradient
   is the recognized entry pattern.
3. **Recognizable layout + pedagogy** — Made With ML teaches the *why*; CCDS
   gives an instantly recognizable directory shape.

The risk in closing these gaps is structural: a naive adoption of an external
convention could **bypass the canonical agentic store** (`agentic/` + `AGENTS.md`)
and silently fork the very governance layer that differentiates this template.
For example, a scaffolding tool that templated `.cursor/` or `.claude/` directly
would violate ADR-027 I-027-2 / I-027-4 (those surfaces are generated-only).

We need a single, enforceable principle that lets every future adoption
improvement land **through** the canon rather than around it.

## 2. Decision

Adopt the **Agentic Adoption Contract**: a binding five-condition gate that every
adaptability or interoperability change MUST satisfy, governed by one principle.

### 2.1 Governing principle (from ADR-027)

> **Tools adapt to our canon, not the reverse.**

Every external convention enters the template as one of:

- a **renderer** over the canonical store (e.g. Copier templating `agentic/` +
  `AGENTS.md`, then running the sync script), or
- a **generated view** (e.g. a CCDS-recognizable layout produced at scaffold
  time), or
- a **governed profile** under the existing behavior modes (e.g. ZenML-style
  `local/staging/prod` stack profiles bound to AUTO/CONSULT/STOP).

Never as a parallel system that writes agent surfaces or behavior rules directly.

### 2.2 The five-condition contract

A change is mergeable only if ALL hold:

1. **ADR first** — any non-trivial adoption decision is recorded as an ADR.
2. **Canonical-only edits** — agent rules/skills/workflows are edited in
   `agentic/`, and invariants/modes/permissions in `AGENTS.md`. A change MUST NOT
   hand-edit a generated surface (`.cursor/`, `.claude/`, `.codex/`, `.devin/`).
3. **Manifest entry with `authority:`** — any policy-bearing asset is indexed in
   `agentic_manifest.yaml` with an `authority:` anchor resolving to an
   `AGENTS.md#<section>` heading or an existing ADR; `validate_agentic_manifest.py
   --strict` passes.
4. **Sync + validators green** — `sync_agentic_adapters.py --check`,
   `validate_agentic.py`, and `validate_agentic_manifest.py --strict` pass in CI.
5. **Adopter parameters via the context layer** — adopter-specific values live in
   `*_context.local.yaml` (gitignored, ADR-023 I-2), never as a fork.

### 2.3 Preservation set (non-negotiable)

These survive every change executed under `ACTION_PLAN_ADAPTABILITY.md`:

- `AGENTS.md` stays at repository root (native discovery by Cursor, Devin/
  Windsurf, Claude Code, Codex).
- `agentic/{rules,skills,workflows}/` is the single canonical, human-edited store.
- `.devin/` (mirror) and `.cursor/ .claude/ .codex/` (pointers) are
  generated-only, written exclusively by `sync_agentic_adapters.py`.
- Every manifest claim keeps its `authority:` anchor.

### 2.4 License & provenance

Adoption borrows **ideas and conventions** (not copyrightable) and **vendors no
literal third-party code**. The repository license is unaffected: it remains
**Apache-2.0**. The full provenance guardrail — including the STOP-class
vendoring gate and the reference-license verification step — lives in
`docs/audit/ACTION_PLAN_ADAPTABILITY.md` §1.1 and is binding on every wave.

## 3. Invariants (contract-enforced)

- **I-029-1** — No adoption change hand-edits a generated agent surface. The fix
  for any rule/skill/workflow change is to edit `agentic/...` then run sync.
  (Promoted to detectable anti-pattern **D-33** in Wave 1.)
- **I-029-2** — No literal third-party source is vendored without (a) inbound
  license compatibility with Apache-2.0, (b) a `NOTICE` entry, and (c) an upstream
  citation in the PR. (Provenance gate, STOP-class.)
- **I-029-3** — Every new policy-bearing asset introduced by an adoption wave
  carries an `authority:` anchor in the manifest. Enforced by the existing strict
  validator.

## 4. Scope

**In scope**: the governance contract itself; the principle that adoption flows
through the canon; the preservation set; the pointer to the provenance guardrail.

**Out of scope** (deferred to their own ADRs):

- ADR-030 — Copier-based scaffolding migration (Wave 1).
- ADR-031 — Local-first stack profiles (Wave 2).
- ADR-032 — CCDS-aligned generated layout (Wave 3).
- Any change to `AGENTS.md` invariants, modes, or permissions beyond adding the
  Wave-scheduled anti-patterns (D-33..D-35) in their respective ADRs.

## 5. Consequences

### Positive

- Modernization cannot erode the agentic spine: the contract makes "bypass the
  canon" a reviewable, blockable event rather than a silent fork.
- Adopters gain industry-standard ergonomics (Copier, local-first, recognizable
  layout) while the governance differentiator stays intact.
- A single, citable principle anchors four downstream ADRs and the execution
  tracker.

### Negative

- One more governance gate for contributors to internalize. Mitigated: it
  formalizes practices ADR-023/ADR-027 already imply; no new CI job is added at
  this scale (calibration principle).

### Neutral

- The contract is process, not code. Its teeth come from existing validators plus
  PR review.

## 6. Revisit triggers

- **An adoption wave forces an edit to a generated surface to "make it work"** →
  STOP; the contract was violated; fix the renderer instead.
- **A reference project relicenses to copyleft** → the provenance gate escalates
  to a required ADR before any borrowing continues.
- **A future IDE reads a neutral directory natively** → point it at `agentic/`,
  per ADR-027 revisit triggers; the contract is unchanged.
- **Contributors repeatedly trip condition 2 or 3** → consider promoting the
  social gate to a CI check (`sync --check` already exists; tighten to required).

## 7. Alternatives considered

| Alternative | Why rejected |
| ------------- | -------------- |
| No contract; review each adoption ad hoc | Re-introduces silent-fork risk ADR-023/027 exist to remove; not auditable |
| Encode the contract directly in `AGENTS.md` only | `AGENTS.md` is the behavior authority for *agents at runtime*; a *maintenance governance* contract belongs in an ADR that `AGENTS.md` and the manifest can anchor to |
| Add a new CI job to enforce the five conditions now | Over-engineering at current scale; existing validators + review cover it (calibration principle) |
| Fork external templates (CCDS/ZenML) and merge upstream | Maximizes drift and license surface; contradicts "tools adapt to our canon" |

## 8. Related

- `docs/audit/ACTION_PLAN_ADAPTABILITY.md` — execution tracker this ADR governs.
- `docs/decisions/ADR-001-template-scope-boundaries.md` — keeps adoption from
  drifting into framework/platform territory.
- `docs/decisions/ADR-023-agentic-portability-and-context.md` — portability layer.
- `docs/decisions/ADR-027-vendor-neutral-canonical-surface.md` — canonical store
  and the "tools adapt to our canon" principle this ADR generalizes.
- `AGENTS.md` — behavior authority, unchanged by this ADR.
