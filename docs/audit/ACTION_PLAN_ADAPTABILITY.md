# Action Plan — Industry-Standard Adaptability & Adoption

- **Date**: 2026-06-29
- **Authority**: Maintainer-initiated strategic review (`@DuqueOM`). Triggered by
  the question: *"how do we raise adoption to the level of the de-facto industry
  templates (Made With ML, Cookiecutter Data Science, ZenML) without losing what
  makes this repo special — above all, the agentic spine?"*
- **Scope**: Adoption ergonomics (scaffolding, layout, local-first on-ramp,
  pedagogy) routed **through** the vendor-neutral agentic core (ADR-027), not
  around it. Documentation to generate (ADRs) and to update (README, releases,
  CHANGELOG, QUICK_START, ADOPTION, PROGRESSION, CONTRIBUTING, AGENTS.md, manifest).
- **Method**: full read of `README.md`, `QUICK_START.md`, `docs/ADOPTION.md`,
  `AGENTS.md`, `templates/config/agentic_manifest.yaml`, ADR-023 / ADR-027, and
  the `agentic/{rules,skills,workflows}/` canonical store; comparison against the
  three reference benchmarks below.
- **Status**: CLOSED — Wave 0 + Wave 1 + Wave 2 + Wave 3 + Wave 4 shipped.
  This document is the living tracker; every closed item updates its checkbox
  here AND adds a row to `VALIDATION_LOG.md`.
- **Classification**: **PUBLIC / version-controlled.** Rationale: consistent with
  the existing `docs/audit/ACTION_PLAN_R4..R6.md` precedent and the repo's
  transparency posture (README §Verification status). No credentials, no
  customer data, no internal-only infrastructure identifiers appear here. If a
  future revision must reference a private cloud account or a customer name, that
  reference goes in a gitignored `*_context.local.yaml`, never in this file
  (ADR-023 I-2).

---

## 0. Executive thesis

This template already **wins** on production discipline, governance, multi-cloud
parity, and the agentic spine (AUTO/CONSULT/STOP + dynamic risk + 32 encoded
anti-patterns). It **loses** to the de-facto standards on three adoption levers:
standardized scaffolding, instantly recognizable layout, and a low-friction
local-first on-ramp.

The governing principle for closing that gap is the one already encoded in
**ADR-027**: *tools adapt to our canon, not the reverse.* Every adaptability
improvement enters as a **renderer / generated view / governed profile** over the
canonical agentic store — never as a parallel system that bypasses it.

**Non-negotiable preservation set** (must survive every change in this plan):

- `AGENTS.md` stays at repository root (native discovery by Cursor, Devin/Windsurf,
  Claude Code, Codex).
- `agentic/{rules,skills,workflows}/` remains the **single canonical, human-edited
  store** (ADR-027 I-027-1).
- `.devin/` (mirror) and `.cursor/ .claude/ .codex/` (pointers) remain
  **generated-only**, written exclusively by `scripts/sync_agentic_adapters.py`
  (I-027-2, I-027-4).
- Every manifest claim keeps its `authority:` anchor to `AGENTS.md#<section>` or
  an ADR (ADR-023 I-1).

---

## 1. Reference benchmarks & attribution

We explicitly study and credit the de-facto standards we borrow ergonomics from.
This attribution is intentional: it is enterprise good practice and consistent
with the repo's ADR culture of citing sources.

| Reference | Owner | What we adopt | What we do NOT adopt |
| --- | --- | --- | --- |
| [Made With ML](https://github.com/GokuMohandas/Made-With-ML) | Goku Mohandas | Pedagogical "why" narrative; guided end-to-end arc | Its single-project shape; Ray as a hard dependency |
| [Cookiecutter Data Science](https://github.com/drivendataorg/cookiecutter-data-science) | DrivenData | Recognizable directory layout; standard scaffolding CLI ergonomics | Its deployment-agnostic minimalism (we keep production depth) |
| [ZenML](https://github.com/zenml-io/zenml) | ZenML GmbH | Infra-agnostic "stack" concept (local → cloud) | Becoming a framework/runtime dependency |
| [Copier](https://github.com/copier-org/copier) | Copier org | Templating engine **with project-update support** (`copier update`) | — (this is the chosen tool, see ADR-030 below) |
| [Cruft](https://github.com/cruft/cruft) | Cruft org | Fallback update mechanism if we stay on Cookiecutter | — (Copier preferred) |

Supplementary references (studied, not adopted as dependencies):
[Kedro](https://github.com/kedro-org/kedro) (pipeline structure),
[full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)
(API service shape), [Azure mlops-v2](https://github.com/Azure/mlops-v2)
(environment-promotion patterns).

All trademarks belong to their respective owners. We reference these projects
under fair-use comparison; no code is vendored from them without its own license
notice in `NOTICE`.

### 1.1 License & provenance guardrail (auditable)

This plan borrows **ideas, conventions, and ergonomics** — none of which are
copyrightable — and **vendors no literal source code** from the reference repos.
The repository's own license is therefore **unaffected**: it remains
**Apache License 2.0**, Copyright 2026 Duque Ortega Mutis (`LICENSE`, `NOTICE`).

To keep this auditable rather than assumed, the following guardrail is binding on
every wave:

1. **Ideas-only by default.** Directory conventions (CCDS), the local→cloud
   "stack" concept (ZenML), and pedagogical structure (Made With ML) are adopted
   as patterns, not as copied expression.
2. **Tooling is a dependency, not a derivative.** Using `copier` (MIT) as a
   scaffolding engine does not make the scaffolded output a derivative work of
   Copier, exactly as using `git`/`pytest`/`black` does not. Tool licenses are
   recorded in the dependency manifests, not in `NOTICE`.
3. **Vendoring gate (STOP-class).** If any literal snippet is ever copied from a
   third-party repo, that PR MUST: (a) confirm the source license is
   Apache-2.0-inbound-compatible (MIT, BSD, Apache-2.0 are; copyleft is **not**
   without an ADR), (b) add the source's copyright + license notice to `NOTICE`,
   and (c) cite the upstream commit/permalink in the PR. Missing any of the three
   blocks the merge.
4. **Reference-license verification.** Before W1 ships, verify each reference
   repo's current published license (licenses can change between major versions)
   and record the verified SPDX identifier in ADR-030 §Related. As of this
   writing the published licenses are: Made With ML — MIT; Cookiecutter Data
   Science — MIT; full-stack-fastapi-template — MIT; Azure mlops-v2 — MIT;
   ZenML — Apache-2.0; Kedro — Apache-2.0; Copier — MIT; Cruft — MIT.

This guardrail is enforced socially via PR review and the existing `gitleaks` /
provenance discipline; it does not require a new CI job at this scale
(calibration principle).

---

## 2. What makes this repo special (the moat — preserve)

| Differentiator | Where it lives | None of the 3 references have it |
| --- | --- | --- |
| Encoded, contract-tested anti-patterns (D-01..D-32) | `AGENTS.md`, policy tests | ✅ unique |
| Agentic governance: AUTO/CONSULT/STOP + dynamic risk | `AGENTS.md`, ADR-010/014 | ✅ unique |
| Vendor-neutral canonical agentic surface | `agentic/`, ADR-027 | ✅ unique |
| Honest L1–L4 maturity disclosure | `README.md` §Verification | ✅ rare |
| Multi-cloud parity (GKE + EKS, same identity contract) | `templates/infra/` | partial in ZenML only |
| Closed-loop monitoring (logging→GT→sliced→C/C→retrain) | `templates/` + ADR-006/007/008/009 | partial in Made With ML |
| ADR-driven decisions with revisit triggers | 28 ADRs | ✅ rare |

---

## 3. Comparative analysis (axis by axis)

| Axis | This template | Made With ML | Cookiecutter DS | ZenML |
| --- | --- | --- | --- | --- |
| Scaffolding tool | custom bash | N/A | `cookiecutter`/`ccds` (standard) | `zenml init` |
| Template-update path | manual drift gate | ❌ | partial (Cruft) | versioned |
| Entry friction | high (K8s/TF day 1) | medium | **very low** | low |
| Layout recognizability | bespoke | bespoke | **de-facto** | bespoke |
| Production discipline | ✅✅✅ leader | medium | low | medium |
| Multi-cloud real | ✅✅ leader | ❌ | ❌ | ✅ |
| Governance/security | ✅✅✅ unique | low | ❌ | medium |
| Pedagogy | reviewer-oriented | ✅✅✅ leader | medium | good |
| Infra-agnostic | ❌ (K8s-opinionated) | partial | ✅ | ✅✅✅ leader |

**Reading**: dominate on production/governance/security; trail on entry friction,
recognizability, and standardized scaffolding/update. Those three are precisely
the levers that drive broad adoption.

---

## 4. Adaptability gaps (prioritized: impact / effort)

| ID | Gap | Impact | Effort | Lever |
| --- | --- | --- | --- | --- |
| **B1** | Non-standard scaffolding (`new-service.sh`) vs `copier`/`cookiecutter` | HIGH | MED | Copier migration + `copier update` replaces manual drift gate |
| **B2** | No local-first gradient (K8s/TF assumed from day 1) | HIGH | MED | ZenML-style stack profiles `local/staging/prod` |
| **B3** | Layout not recognizable to DS practitioners | MED | LOW | CCDS-aligned generated view (`data/ notebooks/ models/ references/`) |
| **B4** | No "why" learning arc (docs are reviewer-oriented) | MED | MED | `docs/TUTORIAL.md` + `template-onboard` skill |
| **B5** | `requirements.txt` + pip vs modern `uv`/`pyproject` | LOW | LOW | adopt `uv` in scaffolded service |
| **B6** | Discoverability (not indexed as a Copier template; no comparison table) | MED | LOW | README §"How this compares" + index publication |

---

## 5. The Agentic Adoption Contract (governing guardrail)

Every item in this plan MUST satisfy all five conditions before merge. This is
the mechanism that lets us modernize without eroding the agentic spine.

1. **ADR first** — non-trivial decision → ADR (repo invariant).
2. **Canonical-only edits** — touch `agentic/` + `AGENTS.md`; never a generated
   surface (`.cursor/ .claude/ .codex/ .devin/`).
3. **Manifest entry with `authority:`** anchored to `AGENTS.md#<section>` or an
   ADR; `validate_agentic_manifest.py --strict` must pass.
4. **Sync + validators + drift gate green** — `sync_agentic_adapters.py --check`,
   `validate_agentic.py`, `validate_agentic_manifest.py --strict` all pass in CI.
5. **Adopter parameters via context layer** — anything adopter-specific goes to
   `*_context.local.yaml` (gitignored), not a fork.

This contract itself is ratified in **ADR-029** (see §7).

---

## 6. Phased action plan

Status legend: `[ ]` pending · `[~]` in progress · `[x]` adapted · `[-]` deferred.

### Wave 0 — Positioning & guardrail (no runtime code)

- [x] **W0.1** Author **ADR-029 — Agentic Adoption Contract & Interoperability
  Strategy** (ratifies §5; declares "tools adapt to our canon" as the adoption
  principle; lists the preservation set). Shipped: `docs/decisions/ADR-029-agentic-adoption-contract.md`.
- [x] **W0.2** README §"How this compares" — honest comparison table vs Made With
  ML / Cookiecutter DS / ZenML (turns niche positioning into clarity). Shipped.
- [x] **W0.3** This tracker committed and linked from `ADR-029` + `VALIDATION_LOG.md`.

Acceptance: ADR-029 merged; README section live; all agentic validators still green.

### Wave 1 — Standard scaffolding via Copier (B1) — highest ROI

- [x] **W1.1** **ADR-030 — Copier-based scaffolding migration** (decision,
  alternatives, Jinja-delimiter collision mitigation, post-gen hook, retirement
  path for `new-service.sh`). Shipped: `docs/decisions/ADR-030-copier-scaffolding-migration.md`.
- [x] **W1.2** `copier.yml` at repo root with custom delimiters (`{@ @}` family,
  superseded the initial `[[ ]]` choice — see ADR-030 §2.2) to avoid collision
  with literal `{ServiceName}` placeholders; `_subdirectory` and `_tasks`
  (post-gen) defined. Shipped: `copier.yml`.
- [x] **W1.3** Post-generation task runs `scripts/sync_agentic_adapters.py` then
  `validate_agentic_manifest.py --strict` so generated projects nail surfaces and
  fail loud on drift. Shipped: `copier.yml` `_tasks` section.
- [x] **W1.4** `new-service.sh` becomes a thin wrapper over `copier copy`
  (backward compatibility; deprecation notice). Shipped:
  `templates/scripts/new-service.sh`.
- [x] **W1.5** `copier update` documented as the canonical template-upgrade path;
  evaluate demoting the manual `cicd-template-drift` gate to advisory. Shipped:
  `MIGRATION.md` §Copier scaffolding migration.
- [x] **W1.5b** License/provenance verification (§1.1): confirm + record each
  reference repo's SPDX license in ADR-030 §6; confirm no literal code was
  vendored; `NOTICE` unchanged (no snippet vendored).
- [x] **W1.6** New anti-pattern **D-33** (manual file copying or sed-based
  placeholder substitution in the scaffolder) and **D-34** (unquoted Jinja tokens
  in YAML list items) in `AGENTS.md`; `agentic/rules/15-template-lifecycle.md`
  added. Shipped: `AGENTS.md` anti-pattern table, rule file.
- [x] **W1.7** New skill `agentic/skills/scaffold-update/SKILL.md` (CONSULT): diff →
  re-sync → re-validate → run `rule-audit`. New workflow
  `agentic/workflows/scaffold-update.md` (`/scaffold-update`). Shipped.
- [x] **W1.8** Manifest entries for D-33/D-34, the new rule, skill, workflow — each
  with `authority:`. Sync run. `rule-audit` catalogue updated to D-34. Shipped:
  `templates/config/agentic_manifest.yaml`.

Acceptance: a fresh `copier copy` produces a service whose `.cursor/.claude/.codex/.devin`
surfaces pass `sync --check`; `copier update` re-syncs cleanly; all validators green.

### Wave 2 — Local-first stack profiles (B2)

- [x] **W2.1** **ADR-033 — Stack profiles (local / staging / prod)** inspired by
  ZenML; profile selection at scaffold time; profiles governed by AUTO/CONSULT/STOP.
- [x] **W2.2** `local` profile runs `train → serve → drift` with no Docker/K8s/TF
  requirement (extends the existing `examples/minimal` ergonomics to scaffolded
  services).
- [x] **W2.3** New anti-pattern **D-35** (a `local` profile that accepts cloud
  credentials or targets a cluster) + contract test.
- [x] **W2.4** New skill `agentic/skills/stack-switch/SKILL.md` (CONSULT) +
  workflow `/stack-switch`; manifest + sync.

Acceptance: scaffold with `--profile local` runs the full local loop on a laptop;
D-35 contract test fails a `local` profile that imports cloud creds.

### Wave 3 — Recognizability & pedagogy (B3, B4)

- [x] **W3.1** **ADR-034 — CCDS-aligned generated layout** (mapping of bespoke
  paths to recognizable `data/ notebooks/ models/ references/` as a generated
  view; no change to the production architecture).
- [x] **W3.2** `docs/TUTORIAL.md` — narrated "from notebook to production" arc that
  ties 6–8 key anti-patterns to the concrete failure each prevents (Made With ML
  lens).
- [x] **W3.3** New skill `agentic/skills/template-onboard/SKILL.md` (AUTO) +
  workflow `/onboard` that interviews the adopter and emits
  `*_context.local.yaml` (never writes secrets); manifest + sync.

Acceptance: `docs/TUTORIAL.md` linked from README + QUICK_START; `/onboard`
produces a valid context file that passes `context.schema.json`.

### Wave 4 — Modernization & discoverability (B5, B6)

- [x] **W4.1** Adopt `uv` + `pyproject` in the scaffolded service
  (`requirements.txt` retained as export for compatibility).
- [x] **W4.2** Publish as an indexable Copier template; add comparison badges.
- [x] **W4.3** `docs/PROGRESSION.md` + `docs/ADOPTION.md` updated to reference the
  new on-ramps (local-first, Copier update path).

Acceptance: `uv sync` works in a scaffolded service; template discoverable via
its Copier index entry.

---

## 7. ADR ledger to create

| ADR | Title | Wave | Status |
| --- | --- | --- | --- |
| **ADR-029** | Agentic Adoption Contract & Interoperability Strategy | W0 | [x] |
| **ADR-030** | Copier-based scaffolding migration | W1 | [x] |
| **ADR-033** | Local-first stack profiles | W2 | [x] |
| **ADR-034** | CCDS-aligned generated layout | W3 | [x] |
| **ADR-035** | uv adoption + Copier index publication | W4 | [x] |

Each ADR follows the house format (Status, Date, Deciders, Context, Decision,
Invariants, Scope, Consequences, Revisit triggers, Alternatives, Related) and is
indexed in `templates/config/agentic_manifest.yaml` where it carries policy.

---

## 8. Anti-pattern additions ledger

| ID | Anti-pattern | Corrective action | Wave | Status |
| --- | --- | --- | --- | --- |
| **D-33** | Manual file copying or sed-based placeholder substitution in the scaffolder | The scaffolder MUST delegate to `copier copy`; enforced by `scripts/test_scaffold.sh` | W1 | [x] |
| **D-34** | Unquoted Jinja tokens (`{@ @}`) in YAML list items | All `{@ @}` tokens in YAML lists MUST be quoted; enforced by `rg -n '^\s*- \{@'` returning zero hits | W1 | [x] |
| **D-35** | A `local` stack profile that accepts cloud credentials or targets a cluster | `local` profile refuses cloud creds; contract test asserts the boundary | W2 | [x] |

Adding these requires updating, in lockstep: `AGENTS.md` §Anti-Patterns table,
`README.md` anti-pattern badge/count, the `rule-audit` skill catalogue,
`agentic/rules/`, the manifest, and `test_anti_pattern_count_consistency.py`.

## 8b. New agentic surfaces ledger (skills / workflows / rules / MCPs)

| Kind | Name | Mode | Wave | Status |
| --- | --- | --- | --- | --- |
| rule | `agentic/rules/15-template-lifecycle.md` | always_on / glob | W1 | [x] |
| skill | `scaffold-update` | CONSULT | W1 | [x] |
| workflow | `/scaffold-update` | — | W1 | [x] |
| skill | `stack-switch` | CONSULT | W2 | [x] |
| workflow | `/stack-switch` | — | W2 | [x] |
| skill | `template-onboard` | AUTO | W3 | [x] |
| workflow | `/onboard` | — | W3 | [x] |
| **MCP** | **none** | — | — | **Intentional: registry already covers docker/postgres/prometheus/github/kubectl; Copier and local-first need no live capability. Adding an MCP here would violate the calibration principle and ADR-023 I-3 (CONSULT cost).** |

---

## 9. Documentation impact matrix (generate vs update)

| Document | Action | Driven by | Status |
| --- | --- | --- | --- |
| `docs/decisions/ADR-029..035` | **create** | W0–W4 | [x] (all shipped) |
| `docs/audit/ACTION_PLAN_ADAPTABILITY.md` (this file) | **maintain** (living tracker) | all | [x] (CLOSED) |
| `README.md` | update §"How this compares", anti-pattern count/badge, on-ramps, agentic table | W0, W1, W2 | [x] |
| `QUICK_START.md` | update Track A/B for Copier; add `--profile local`; link TUTORIAL | W1, W2, W3 | [x] |
| `docs/TUTORIAL.md` | **create** | W3 | [x] |
| `docs/ADOPTION.md` | update maturity matrix rows (scaffolding, update path, local profile) | W1, W2, W4 | [x] |
| `docs/PROGRESSION.md` | update Day-1→Month-2 arc with local-first entry | W2, W4 | [x] |
| `CONTRIBUTING.md` | document `copier`/`copier update` contributor workflow | W1 | [x] |
| `AGENTS.md` | add D-33..D-35; reference ADR-029..035; keep at root | W1, W2, W3 | [x] |
| `templates/config/agentic_manifest.yaml` | add rules/skills/workflows/ADR authorities | W1–W4 | [x] |
| `CHANGELOG.md` | one `### Added/Changed` block per wave under `[Unreleased]` | each wave | [x] |
| `releases/vX.Y.Z.md` | release note per shipped wave (per `docs/RELEASING.md`) | each release | [ ] (deferred to release cut) |
| `VALIDATION_LOG.md` | one evidence row per closed item | each item | [x] (Entries 012–014) |
| `MIGRATION.md` | adopter migration note for `new-service.sh` → `copier` | W1 | [x] |
| `NOTICE` | update **only if** literal third-party code is ever vendored (§1.1 gate) | W1+ | [ ] (no vendored code) |
| `CLAUDE.md` / `*_context.md` | refresh counts (rules/skills/workflows) after each surface addition | W1–W3 | [x] |

---

## 10. Release & changelog discipline

- Each wave ships as its own minor release on the active `v0.x` line, per
  `docs/RELEASING.md`. No wave is "done" until it has: (a) its ADR merged, (b) its
  CHANGELOG `[Unreleased]` block promoted to a dated version, (c) a
  `releases/vX.Y.Z.md` note, and (d) `VALIDATION_LOG.md` rows with reproducible
  evidence (the same standard R4–R6 used).
- The `v1.0.0` gate (real GKE+EKS L4 evidence) is **independent** of this plan and
  is not advanced or blocked by it.

---

## 11. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Copier Jinja `{{ }}` collides with literal `{ServiceName}` placeholders | Custom delimiters (`[[ ]]`) + `{% raw %}` blocks; contract test renders a fixture and diffs |
| `copier update` silently clobbers adopter agent-surface edits | D-34 + `scaffold-update` skill enforces commit + `sync --check` first |
| Generated surfaces drift from canonical after new features | Post-gen hook + CI `sync --check` (existing discipline, unchanged) |
| Scope creep into "framework" territory (becoming ZenML) | ADR-001 scope boundary holds; stack profiles are config, not a runtime dependency |
| Anti-pattern count drift across AGENTS.md/README/skill | `test_anti_pattern_count_consistency.py` extended to cover skill bodies (R6 S0-3 precedent) |

---

## 12. Revisit triggers

- **A reference benchmark publishes a materially better update mechanism than
  Copier** → re-evaluate W1 tooling in an ADR-030 amendment.
- **Adopters request a runtime orchestrator (Kubeflow/Metaflow)** → that is a new
  ADR under ADR-001 scope review, not part of this plan.
- **Any wave forces an edit to a generated surface to "make it work"** → STOP; the
  Agentic Adoption Contract (§5) was violated; fix the renderer instead.

---

## 13. Related

- `docs/decisions/ADR-023-agentic-portability-and-context.md` — portability layer.
- `docs/decisions/ADR-027-vendor-neutral-canonical-surface.md` — canonical store.
- `docs/decisions/ADR-001-template-scope-boundaries.md` — keeps this plan from
  drifting into "platform/framework" territory.
- `AGENTS.md` — authority for invariants, modes, permissions (unchanged spine).
- `docs/audit/ACTION_PLAN_R6.md` — most recent agentic-surface audit; this plan
  builds on its S3 strategic items.
