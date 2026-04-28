# ADR-019: Agentic CI Self-Healing

- **Status**: Proposed (Phase 0 — policy ratified, scripts deferred)
- **Date**: 2026-04-28
- **Deciders**: @DuqueOM, AI staff engineer
- **Related**: ADR-010 (Dynamic agent behavior),
  ADR-014 (Audit trail),
  ADR-016 (External audit R2 remediation),
  ADR-018 (Operational Memory Plane),
  AGENTS.md (Agent Permissions Matrix, Operation→Mode mapping),
  README §Agentic CI self-healing

## Context

CI failures fall into a long tail of root causes. A meaningful
fraction are **mechanical, deterministic, and reversible**:

- formatter drift (black / isort / ruff), markdown link rot
- non-prod YAML/TOML/JSON syntax errors
- snapshot regen for deterministic generated artifacts
- test fixture mocks misaligned with refactored signatures

These are exactly the cases an agent can repair under bounded
authority WITHOUT compromising production safety. The remaining
classes — anything touching deploy chains, Terraform, prod
overlays, secrets, fairness/drift gates — must NEVER be touched
by an autofix.

The README already references "Agentic CI self-healing" as a
documented capability. This ADR ratifies the **policy contract**
that makes it real: which failure classes map to which
AUTO/CONSULT/STOP mode, what the blast-radius limits are, and
what verification a fix MUST pass before being committed.

This ADR ships the policy artifacts (the canonical mapping). The
9 Python scripts that implement the runtime (`ci_collect_context`,
`ci_classify_failure`, etc.) are scoped as a **follow-on PR** — see
`§Phase plan` below — because they need 2-4 weeks of shadow-mode
data before any AUTO action gets enabled.

## Decision

### Two canonical policy artifacts

NEW `templates/config/ci_autofix_policy.yaml` — the failure-class
→ mode mapping, blast-radius limits, protected-paths list, and
verifier groups. Single source of truth: any future tooling
(scripts, agents, dashboards) reads from this file.

NEW `templates/config/model_routing_policy.yaml` — the
provider/model routing per task class (router / patcher / reviewer
/ escalation). Decouples model identity from the autofix flow so
adopters can swap providers without touching code.

Both files have a contract test (`test_ci_autofix_policy_contract.py`)
that enforces:

- `protected_paths` always includes deploy workflows, Terraform
  paths, and `risk_context.py` (the kill list)
- AUTO blast-radius limits never exceed 5 files / 120 lines
- STOP classes (`security_or_auth`, `infra_or_deploy`,
  `quality_gate`) have NO `allowed_paths` (they're STOP, not
  scoped-AUTO)
- Every `failure_classes.*.verifiers` reference exists in the
  `verifier_groups` map
- Every `tasks.*.route` references a real `routes` entry in the
  routing policy

### Failure-class table (canonical)

| Class | Mode | Examples | Allowed edits | Required verifier |
|-------|------|----------|---------------|-------------------|
| `formatter_drift` | AUTO | black, isort, ruff format, whitespace | `*.py *.md *.yaml *.toml` | `lint-style` |
| `docs_quality_minor` | AUTO | markdownlint, internal links, doc references | `docs/** README* CHANGELOG*` | `docs-quality` |
| `syntax_config_minor` | AUTO | invalid YAML/TOML/JSON in non-prod CI | non-prod configs, tests, doc workflows | `yaml-parse` + `workflow-lint` |
| `snapshot_regen_deterministic` | AUTO | regenerable fixtures | snapshot allowlist | `contract-tests` |
| `test_fixture_alignment` | CONSULT | fixtures, mocks, payloads | `tests/** conftest.py` | `targeted-tests` |
| `workflow_nonprod_fix` | CONSULT | non-deploy CI workflow path/artifact/matrix | `.github/workflows/*.yml templates/cicd/*.yml` (deploy excluded) | `workflow-lint` + `targeted-tests` |
| `build_harness_fix` | CONSULT | scaffolding, validation, contract tests | `scripts/** templates/cicd/**` | `targeted-tests` + `scaffold-e2e` |
| `dependency_pin_nonruntime` | CONSULT | CI/lint/docs tooling pins | tooling, no runtime deps | `targeted-tests` |
| `security_or_auth` | **STOP** | gitleaks, trivy, WIF, IRSA, secrets | none | human |
| `infra_or_deploy` | **STOP** | Terraform, K8s prod/staging, deploy chain | none | human |
| `quality_gate` | **STOP** | fairness, drift, retrain, contract break | none | human |
| `blast_radius_exceeded` | **STOP** | > AUTO limits, protected path | none | human |

### Hard rules from day one

- **AUTO never touches**: deploy workflows, Terraform, prod overlays,
  auth/secrets, fairness/drift/retrain gates, `risk_context.py`,
  `audit_record.py`. Codified in `protected_paths` + STOP classes.
- **AUTO max blast radius**: 5 files, 120 lines, 2 attempts. If the
  verifier doesn't go green in the first cycle, the fix escalates
  to CONSULT (matches ADR-010 escalation discipline).
- **Every action emits an audit entry** via `scripts/audit_record.py`
  with `agent="Agent-CIRepair"`, including the failure_class, mode,
  and verifier result.
- **Every memory query is audited** when the future memory plane
  (ADR-018) is wired in — `memory.enabled: true` already in the
  policy file flagged `mode: advisory` until Phase 5 of ADR-018.
- **Google preview models are restricted** to `workflow_dispatch`
  or non-protected benchmarking lanes only (never on auto-merge
  paths). Codified in `model_routing_policy.yaml`.

### Phase plan

| Phase | Title | Ships | Acceptance |
|-------|-------|-------|------------|
| 0 | Policy artifacts + contract test | this ADR + the two YAMLs + `test_ci_autofix_policy_contract.py` | contract test green |
| 1 | Context collection + classification | `scripts/ci_collect_context.py`, `scripts/ci_classify_failure.py` | classifier-only mode (NO writes), 2 weeks of dry-run data |
| 2 | Verifier helpers | `scripts/ci_verify_yaml.py`, `_workflows.py`, `_targeted.py` | verifiers callable from `make` and CI |
| 3 | Workflow scaffold (shadow mode) | `.github/workflows/agentic-ci-repair.yml` with all jobs gated on `if: false` | workflow validates parses |
| 4 | Enable AUTO for `formatter_drift` only | flip `if: false` on the autofix job, allowlist formatter_drift only | 2 weeks of green AUTO runs |
| 5 | Expand AUTO to `docs_quality_minor` + `syntax_config_minor` | extend allowlist | precision/recall measured |
| 6 | Enable CONSULT lane | open repair-proposal PRs as drafts | review burden measured |

Phases 1–6 each have their own PR with measurable acceptance.
Like ADR-018, we can pause at any boundary without leaving the
template in a half-shipped state.

## Why split policy from runtime

Two reasons:

1. **The policy is the safety contract.** Once `protected_paths`
   and the failure-class table are ratified by ADR + contract test,
   ANY future runtime implementation MUST conform. Inverting this
   order — shipping scripts before the contract — is exactly the
   anti-pattern the audit found in earlier rounds.
2. **Shadow-mode requires real data.** We need ~2 weeks of CI
   failures classified by the policy (without any writes) to
   calibrate the classifier's precision before letting it open
   PRs. That's Phase 1's job, scoped explicitly with a "no writes"
   acceptance gate.

## Consequences

### Positive

- A single audited source of truth for what an autofix may touch.
- Contract test prevents silent erosion of `protected_paths`.
- Decoupled model routing lets adopters swap providers without code
  changes.
- Phased rollout: Phase 0 ships value (the policy is meaningful on
  its own as governance) while runtime risk lives behind feature
  gates.

### Negative / cost

- 2 YAML files + 1 contract test add ~250 lines of governance
  surface adopters must understand. Mitigation: `docs/ADOPTION.md`
  links to this ADR; the surface is opt-in via the workflow file
  not existing yet.
- Future runtime implementation work (Phase 1+) is real — not
  pretending otherwise. ADR-016 acceptance criteria are unchanged
  by this; this is a new initiative.

### Neutral

- The two policy files are READ but not WRITTEN by this PR — they
  are pure data. No agent runtime is enabled yet.

## Acceptance criteria (Phase 0 only)

- [x] ADR approved with phase plan
- [x] `templates/config/ci_autofix_policy.yaml` ships with
      failure-class table + protected paths + blast-radius limits
- [x] `templates/config/model_routing_policy.yaml` ships with
      4 routes (router / patcher / reviewer / escalation) +
      preview lane
- [x] `test_ci_autofix_policy_contract.py` enforces invariants
      (passes locally + CI)
- [ ] Phase 1 PR opens within 30 days OR this ADR moves to
      `Withdrawn`

## Revisit triggers

- A real CI run produces a failure class not in the table → add to
  the YAML, re-run the contract test, ship in next PR.
- An adopter reports an autofix that touched a protected path →
  STOP-class incident; this ADR's contract test should have caught
  it. If it didn't, the contract test is broken.
- New provider models stabilize (e.g. successor to Sonnet 4.x) →
  update the routing policy; ADR doesn't need re-ratification
  unless the routing topology changes (e.g. introducing a 5th tier).
