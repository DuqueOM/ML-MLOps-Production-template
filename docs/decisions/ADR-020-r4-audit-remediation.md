# ADR-020: External Audit R4 — Remediation Plan (master)

- **Status:** Accepted
- **Date:** 2026-04-29
- **Supersedes:** none (extends ADR-016 closure)
- **Related:** ADR-014 (gap remediation), ADR-015 (productization roadmap), ADR-016 (R2 remediation), ADR-018 (Memory
  Plane), ADR-019 (CI Self-Healing)
- **Authors:** Staff/Lead, AI staff engineer

## Context

A fourth-round external audit (R4), conducted post-`v1.12.0` (which closed R3),
surfaced 20 findings — 5 Critical, 7 High, 6 Medium, 3 Low — spanning credibility,
release discipline, execution evidence, runtime implementation gaps, and
governance evidence.

The R4 audit's central thesis is sharp and correct:

> The template's intellectual core is mature. The gap is between
> intellectual maturity and **verified-execution maturity**.

R3 found bugs of the form "the YAML looks right; it was never executed against
reality." R4 generalizes that finding into a release-discipline diagnosis and
asks for two structural changes: **(1) every component change requires execution
evidence**, and **(2) capabilities that are not implemented must say so on the
README at the section heading, not in a footnote.**

Beyond the runtime credibility gaps, R4 also asks the project to ship the runtime
Phase 1 of ADR-018 (Operational Memory Plane) and ADR-019 (Agentic CI
Self-Healing), which until now had been deferred behind explicit Phase 0 status.

## Decision

Adopt a **four-sprint plan** governed by this ADR with the following structure:

| Sprint | Focus | Mode mix |
| -------- | ------- | ---------- |
| 0 (days 1–7) | Credibility — close all 5 Criticals via documentation + policy + assertion tests; **no cloud runtime change** | AUTO + 1 CONSULT |
| 1 (days 8–14) | Execution hardening — per-PR smoke lane, PR-evidence policy, red-team log, ADR-019 Phase 1 read-only | AUTO + CONSULT + 2 STOP-delegated |
| 2 (days 15–21) | Memory Plane Phase 1 contracts + Mediums | AUTO + 1 CONSULT |
| 3 (days 22–28) | Lows + closure + Phase-1→Phase-2 gate | AUTO + CONSULT |

The full per-finding plan with severity scoring, owners, files touched, and
acceptance criteria lives in
[`docs/audit/ACTION_PLAN_R4.md`](../audit/ACTION_PLAN_R4.md). This ADR ratifies
the structure; the plan document is the operational artifact.

### Hard rules ratified by this ADR

1. **No retroactive re-tagging.** Existing `v1.x` tags remain immutable. Versioning
   discipline is reset forward via `docs/RELEASING.md`. The next breaking
   change in scaffolded output goes to `v2.0.0`, not `v1.13.0`.
2. **Phase-0 banners are non-negotiable.** Any capability that ships policy + tests
   but no runtime MUST carry a Phase-0 banner at the README section heading.
   Removing the banner without the corresponding ADR transitioning Phase
   status is blocked by `tests/test_phase0_disclosure.py`.
3. **Anticipated model names ≠ verified model names.** The README's model
   routing section labels names as cadence-anticipated until vendor verification
   is recorded with a `verified_at` field that links to a dashboard reference.
4. **Execution evidence is mandatory for new components.** `pr-evidence-check.yml`
   (Sprint 1) blocks PRs that introduce new template components without
   schema/contract test, real execution output, and CI run link.
5. **STOP-delegated actions never run inside the agent loop.** Three R4 items
   (gitleaks history scan, Kyverno admission validation against a real cluster,
   any prod IaC mutation) are documented but only Platform / Security can
   execute them, with audit trail.

## Consequences

### Positive

- The "production-ready" claim becomes defensible because every dimension is
  either backed by a `VALIDATION_LOG.md` entry, a contract test, or a STOP-mode
  delegation note. No more silent gaps.
- The Phase-0 / Phase-1 distinction is enforced by tests, not prose. Adopters
  who skim the README cannot mistakenly believe the runtime exists.
- The release discipline shift toward `v2.0.0` for the next breaking change
  recovers semver credibility without requiring a destructive re-tag.

### Negative / cost

- Sprint 1's smoke lane and PR-evidence workflow add CI minutes per PR. Bounded
  to ~6 minutes overhead based on sister-project measurements. Acceptable.
- Phase 1 runtime for ADR-019 ships in shadow only — no value extracted from
  it for ~14 days while data accumulates. This is the correct phasing per
  ADR-019 §"Why split policy from runtime"; we accept the calendar cost.
- Three STOP-delegated items (S1-3, S1-4) cannot close inside this ADR's
  4-sprint window unless Platform / Security capacity is allocated. Their
  evidence may land in `VALIDATION_LOG.md` after the calendar deadline.
  This is honest scope, not a hidden gap.

### Neutral

- ADR-018 and ADR-019 transition from "Phase 0 — runtime deferred" to
  "Phase 1 in shadow" — the deferral is no longer total.

## Acceptance criteria

| ID | Criterion |
| ---- | ----------- |
| AC-1 | All 5 Criticals (C1–C5) closed in Sprint 0 PR `audit-r4/sprint-0-credibility` |
| AC-2 | `tests/test_readme_model_names.py` and `tests/test_phase0_disclosure.py` green on `main` |
| AC-3 | `docs/RELEASING.md`, `MIGRATION.md`, `VALIDATION_LOG.md` exist and are linked from `README.md` and `CHANGELOG.md` |
| AC-4 | Sprint 1 ships smoke lane + PR-evidence policy + red-team log + ADR-019 Phase 1 read-only |
| AC-5 | Sprint 2 ships ADR-018 Phase 1 contracts (`memory_types.py`, `memory_redaction.py`) with green tests, plus Compliance gap analysis in `ADOPTION.md` |
| AC-6 | Phase-1 → Phase-2 transition gate decision is documented as a CONSULT operation with shadow-mode evidence linked |
| AC-7 | This ADR is updated at sprint boundaries with a `## Progress log` section listing closed findings and evidence |

## Revisit triggers

- A Critical finding from R4 is found to be only partially closed → re-open this ADR, escalate severity.
- ADR-019 Phase 1 shadow data shows classifier precision below the threshold defined at S1-6 acceptance → Phase 2
  deferred indefinitely; this ADR documents the pause.
- A new external audit (R5) lands during Sprint 0–3 → fold its findings into this ADR's progress log rather than opening
  a parallel ADR; sequence by severity.

## Progress log

_Updated at the close of each sprint with closed-finding evidence._

### Sprint 0 — closed 2026-04-29 (commit `39fbfb7`)

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| C1 | Closed | README §"Recommended baseline" reworded; `tests/test_readme_model_names.py` (3 invariants) green |
| C2 | Closed | Phase-0 banners on README §"Operational Memory Plane" + §"Agentic CI self-healing"; `tests/test_phase0_disclosure.py` (6 invariants) green |
| C3 | Closed | `docs/RELEASING.md` ratified; `### Breaking for adopters` blocks added retroactively to v1.10/v1.11/v1.12 |
| C4 | Closed | `VALIDATION_LOG.md` Entry 001 with binary inventory + gitleaks scan + R4 invariant test runs |
| C5 | Closed | `MIGRATION.md` with rows for v1.7→v1.12 (highest-impact: v1.9→v1.10) |

Sprint 0 mode mix executed as planned (4 AUTO + 1 CONSULT). Zero cloud
runtime touched. Net diff: +1236 / -7 lines across 9 files.

### Sprint 1 — closed 2026-04-29 (commit chain — see VALIDATION_LOG Entry 002)

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| H1 | Phase 1 closed | `scripts/ci_collect_context.py`, `scripts/ci_classify_failure.py`, `.github/workflows/ci-self-healing-shadow.yml`, `tests/test_ci_classify_failure_phase1.py` (27 invariants green). ADR-019 status: Phase 0 → Phase 1. Phase 2 gated on 14 days of shadow data. |
| H2 | Closed | `.github/workflows/pr-evidence-check.yml`, `.github/pull_request_template.md` updated, `CONTRIBUTING.md` §"Evidence policy for new components" |
| H3 | Closed | `.github/workflows/pr-smoke-lane.yml` — scaffold + 6 overlay renders + kubeconform + binary-presence audit per PR |
| H4 | Closed | `docs/agentic/red-team-log.md` with 5 documented evasion attempts + invariant index + 3 follow-ups |
| H5 | Runbook shipped | `docs/runbooks/secret-history-scan.md` — STOP-delegated to Platform / Security; execution pending |
| H6 | Runbook shipped | (same as H5; merged into single runbook) |
| H7 | Runbook shipped | `docs/runbooks/kyverno-admission-validation.md` — STOP-delegated to Platform; kind-cluster procedure documented; execution pending |

The three runbooks (H5 / H6 / H7) ship the operational procedure but the
**execution evidence** has not yet been recorded. Per ADR-020 §"Hard rules" # 5,
they are not executed inside the agent loop; their entry in
`VALIDATION_LOG.md` will be added by Platform / Security.

### Sprint 2 — closed 2026-04-29 (commit chain — see VALIDATION_LOG Entry 003)

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| H1 (part 2/2) | Phase 1 closed | `templates/common_utils/memory_types.py`, `templates/common_utils/memory_redaction.py`, `tests/test_memory_contracts.py` (21 invariants), `tests/test_memory_redaction.py` (38 invariants). ADR-018 status: Phase 0 → Phase 1. Phase 2 gated on 30 days of Phase 1 contract stability. |
| M3 | Closed | `docs/decisions/ADR-021-fairness-thresholds.md` — DIR ≥ 0.80 default + per-domain table + consultation band + calibration parity. |
| M4 | Closed | `docs/ADOPTION.md` §6 — Compliance gap analysis covering GDPR / SOC 2 / ISO 27001 / HIPAA + Out-of-scope-by-philosophy section. |
| M6 | Closed | `docs/decisions/ADR-022-psi-thresholds.md` — `psi_warn = 0.10` / `psi_alert = 0.25` defaults + per-feature override format + `drift_severe` mapping. |
| M1 | Runbook shipped | `docs/runbooks/secrets-integration-e2e.md` — execution pending Platform / Security. |
| M2 | Runbook shipped | `docs/runbooks/ground-truth-ingestion.md` — execution pending production deployment. |

S2-4 (Alertmanager routing test / M5) deferred to Sprint 3 — paired with
the observability-dashboard inventory work (L2). Defer rationale: M5
requires `amtool` + a representative `alertmanager.yaml`; the existing
template ships PrometheusRules but not a complete `alertmanager.yaml`,
so M5 ships alongside L2.

### Sprint 3 — open (R4 + R5 merged)

- **M5** Alertmanager routing test + runbook (paired with L2 dashboard inventory).
- **L1** Backfill `### Known follow-ons` blocks on `v1.0`–`v1.9` release notes.
- **L2** `docs/observability/dashboards-inventory.md` indexing every Grafana dashboard.
- **L3** Integrate `infracost diff` into `terraform-plan-nightly.yml`.
- **Phase-1 → Phase-2 gate** for ADR-019 (CI Self-Healing) — requires 14 days of shadow data; gated on R5-M1 landing.
- **F1, F2, F3** follow-ups from `docs/agentic/red-team-log.md`.
- **R5-H1** README "Production-ready by design" wording softening + new §"Verification status" mini-matrix.
- **R5-M1** Shadow workflow real log fetch + `log_artifact_url` wiring + PR-base diff (closes red-team F1 inline).
- **R5-M3** NetworkPolicy egress per cloud overlay + non-dev-overlay contract test.

See `docs/audit/ACTION_PLAN_R4.md` §7 and `docs/audit/ACTION_PLAN_R5.md`.

### R5 AUTO batch — closed 2026-05-03 (commit chain — see VALIDATION_LOG Entry 004)

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| R5-L4 | Closed | `.pre-commit-config.yaml` retired pre-push scaffold smoke; `Makefile` `smoke` alias; `CONTRIBUTING.md` §"Local validation cadence". |
| R5-M4 | Closed | `templates/service/tests/load_test.py` synced to canonical schema; new `test_load_payload_matches_schema.py` (5 invariants) blocks future drift. |
| R5-M2 | Closed | `scripts/validate_agentic.py` reconfigure-utf-8 + ASCII probe + `MARK_*` constants; verified on Linux + simulated cp1252. |
| R5-L1 | Closed | 6 secondary docs bumped from `D-30` to `D-32`; new `test_anti_pattern_count_consistency.py` (7 invariants) auto-derives canonical max from `AGENTS.md`. |

### R5 remainder — closed 2026-05-03 (VALIDATION_LOG Entry 005)

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| R5-H1 | Closed | `README.md` §"Production-ready scope" rewritten with "Production-ready by design" wording + 3-bullet preamble + new §"Verification status" 4-layer matrix (L1 contract / L2 smoke / L3 golden-path / L4 adopter-owned). Badge bumped to `anti--patterns-32`. `test_readme_verification_status.py` locks 9 wording invariants. |
| R5-M1 | Closed | `.github/workflows/ci-self-healing-shadow.yml` — `permissions: pull-requests: read` added; fetch-logs step does real `gh api /actions/runs/{id}/logs` with 50 MB cap + unzip + concat; `log_artifact_url` replay via `curl`; changed-files step resolves PR base via `pulls/{num}` and diffs `base...HEAD`, closing red-team F1. Step summary now carries 9 provenance fields. `test_shadow_workflow_phase1.py` locks 14 invariants including "no gh pr create / no git push". |
| R5-M3 | Closed | `templates/k8s/base/networkpolicy.yaml` carries OVERLAY-OVERRIDE-REQUIRED banner; 4 new `patch-networkpolicy.yaml` JSON 6902 patches in `overlays/{gcp,aws}-{staging,prod}` replace `0.0.0.0/0:443` with cloud-specific CIDR residuals (GCP private-googleapis VIPs; AWS 52./54. residuals with excepts). Each overlay's `kustomization.yaml` wires the patch with `target.kind: NetworkPolicy`. `test_networkpolicy_egress_hygiene.py` locks 19 invariants (14 structural + 4 kustomize-optional + 1 dev-negative). Follow-up: `docs/runbooks/egress-narrowing.md` queued for Sprint 3. |

All R5 findings closed. Sprint 3 scope now: R4 Mediums/Lows (M5/L1/L2/L3) + follow-ups from red-team (F1/F2/F3) +
`docs/runbooks/egress-narrowing.md` + ADR-019 Phase-1 → Phase-2 CONSULT decision.

### Sprint 3 — batch 2 closure 2026-05-03

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| R4-L1 | Closed | `releases/v1.0.0.md` – `releases/v1.10.0.md` backfilled with `## Known follow-ons (scoped, not regressions)` section mirroring v1.11.0/v1.12.0 format. Each bullet points to the subsequent release that closed the item. `test_release_notes_follow_ons.py` locks 26 invariants (heading presence + non-empty body) across 13 release files (4 hotfix-note skips by design). |
| R4-L3 | Closed | `templates/cicd/terraform-plan-nightly.yml` — new `infracost/actions/setup@v3` + `infracost breakdown` steps per cloud (gcp + aws). Guarded by `env.INFRACOST_API_KEY != ''` so forks without the secret degrade cleanly. JSON artifact (`infracost-<cloud>-<run_id>`, 14-day retention) + step summary table with `totalMonthlyCost`. Workflow header documents optional secret. `test_infracost_integration.py` locks 5 invariants (setup presence, guard, breakdown → summary + artifact, header documentation). |
| Red-team F2 | Closed | `templates/common_utils/risk_context.py` parser hardening rejects full-day (`00-24`), reversed, degenerate, malformed, and out-of-range MLOPS_ON_HOURS_UTC spans with fallback to default `08-18` + WARNING. `templates/tests/unit/test_risk_context.py::TestOnHoursOverrideHardening` adds 7 invariants covering every rejected shape. |
| Red-team F3 | Closed | `templates/tests/governance/test_red_team_regression.py` — 6 regression invariants covering Entries 2+3 (protected_paths short-circuit precedence), Entry 2 signature lock, Entry 4 (PR-level blast-radius aggregation), Entry 5 / F2 (off_hours cannot be suppressed), and red-team-log integrity check. Direct-import of `scripts/ci_classify_failure.classify(context, policy)`, no subprocess, runtime < 1 s. |

Sprint 3 remaining scope: R4-M5 (Alertmanager routing test, CONSULT — requires amtool + new alertmanager config) +
ADR-019 Phase-1 → Phase-2 CONSULT decision (gated on 14 days of shadow data post-merge).

### Sprint 3 — batch 3 closure 2026-05-03

| Finding | Status | Evidence |
| --------- | -------- | ---------- |
| R4-M5 | Closed | New `templates/monitoring/alertmanager.yml` (routing tree + 4 receivers + inhibit rule) — separate from the existing `alertmanager-rules.yaml` which only emits alerts. New `templates/monitoring/tests/test_alertmanager_routing.py` locks 14 invariants: 5 routing rows via `amtool config routes test` (authoritative) + 5 identical rows via a pure-Python simulator (always-runs fallback) + `amtool check-config` structural check + defined-receivers cross-check + sibling-file layout check + P1→P2/P3/P4 inhibit-rule existence. `amtool` auto-discovered from `$PATH` or `<repo>/alertmanager-*/amtool`; amtool-authoritative tests skip cleanly when the binary is absent. New `docs/runbooks/alertmanager-validation.md` documents the manual end-to-end exercise against a real cluster + audit-log template. |

Remaining Sprint 3 scope: only **ADR-019 Phase-1 → Phase-2 CONSULT decision**, which is time-gated on 14 days of shadow
data post-merge of PR #15 — not an actionable engineering task.
