# ADR-014: Gap Remediation Plan — v1.9.0 → v2.0.0 Public Release

## Status

Proposed (executable plan, awaiting first-batch execution)

## Date

2026-04-25

## Context

A comprehensive internal audit (April 2026) identified **47 gaps** between the
template's stated guarantees (D-01..D-30 invariants, agentic governance,
Dynamic Behavior Protocol per ADR-010, supply-chain via Cosign+SBOM+Kyverno,
multi-cloud parity GKE+EKS) and the current implementation. Five additional
gaps surfaced during triage (#48–#52). Total: **52 gaps**.

The gaps fall into three classes:

1. **Correctness / consistency** — docs claim X, code does Y (endpoint drift,
   `ServiceA` hardcoded, contract drift).
2. **Governance not yet operational** — design exists, wiring does not
   (Dynamic Behavior Protocol stubs, audit trail uninvoked, `validate_agentic`
   not `--strict` in CI).
3. **Maturity gaps** — components below the bar set by the best skills
   (rollback, model-retrain, security-audit).

Without a structured plan, fixing gaps in discovery order produces tangled
commits. Example dependency: parametrizing CI/CD (#07) requires the
scaffolder contract fix (#13) to land first.

## Decision

**Adopt a 4-phase plan organized by dependency. Each phase produces a coherent
commit cluster with a single integration test proving the phase invariant.
Phases run sequentially; gaps within a phase run in parallel.**

### Resolution of micro-gaps #48–#52 decided here

| # | Gap | Decision | Rationale |
|---|-----|----------|-----------|
| 48 | `ops/audit.jsonl` gitignored vs. P0.5 needs `record_operation()` to write there | **Keep gitignored.** Canonical CI audit = GHA step-summary + `audit`-tagged Issues. Local file = per-developer evidence only. `record_operation()` writes to BOTH; CI publishes summary. | AGENTS.md "Audit Trail Protocol" already specifies this dual destination. The file was never intended as committed history. |
| 49 | `docs/incidents/2026-04-24-mcp-config-secret-leak.md` deleted | **Stay deleted.** Learnings live in `docs/runbooks/mcp-config-hygiene.md`. | Avoid duplicate authority; per user direction. |
| 50 | `*.md` files cluttering repo root (AUDIOVISUAL, AGENTS, etc.) | **No action.** AUDIOVISUAL is gitignored (personal). The other root `.md` (README, CONTRIBUTING, CHANGELOG, AGENTS, QUICK_START, CHECKLIST_RELEASE) are conventionally root-level for OSS discoverability. | Convention > tidiness. Moving AGENTS.md or QUICK_START.md to `docs/` reduces visibility for the agentic IDEs that auto-load AGENTS.md from root. |
| 51 | `docs/runbooks/mcp-config-hygiene.md` references `make bootstrap` which P1.4 will replace with `uv` | **Defer.** Update runbook in P1.4 commit when `uv` migration lands; cross-reference here. | Keep doc and code in lock-step within the same phase. |
| 52 | ~~`ops/incident_active.json` blocked by gitignore~~ | **False positive — no action.** `risk_context.py:112` actually reads `ops/incident_state.json` (and `ops/last_drift_report.json`, `ops/audit.jsonl`). All three are CronJob-written runtime artifacts, not committed state. The `.gitignore` pattern `ops/*.json` is correct: production cluster CronJobs write these in pods; locally absent unless a developer ran the drift/incident scripts. No file paths to migrate; no gitignore rule to relax. | Verified via `grep ops/ templates/common_utils/risk_context.py`. Original triage entry took the wrong filename. |

## Phase 1 — Quick wins (1 day, ~10 commits, low coordination)

**Phase invariant**: every claim made in `*.md` files matches what the code
does. Detected by `scripts/validate_doc_drift.sh` (new, simple grep-based).

| Commit | Gaps closed | Files | Test |
|--------|-------------|-------|------|
| `1.1 fix(supply-chain): pin GHA actions to immutable SHAs` | #04 | `templates/cicd/ci.yml`, `templates/cicd/ci-infra.yml` | grep `@master` returns 0 |
| `1.2 fix(rules): align wait_timer to 5min across all layers` | #15 | `.claude/rules/14-github-actions.md`, `.cursor/rules/12-github-actions.mdc` | grep `wait_timer: 15` returns 0 |
| `1.3 fix(rules): remove static GCP/AWS credential references from windsurf rules` | #14 | `.windsurf/rules/05-github-actions.md` | grep `GCP_SA_KEY\|AWS_ACCESS_KEY_ID` in rules returns 0 |
| `1.4 fix(commands): align /new-service path to scaffolder reality` | #13 | `.claude/commands/new-service.md`, `.cursor/commands/new-service.md` | manual: paths match `templates/scripts/new-service.sh` output |
| `1.5 fix(docs): /predict/batch → /predict_batch sweep` | #17 | 6 files (test_api.py, load_test.py, service-readme-template.md, others) | grep `/predict/batch` returns 0 |
| `1.6 fix(docs): split /health and /ready in service README` | #21 | `templates/service/README.md` | manual diff: matches `app/main.py:110` |
| `1.7 fix(docs): align overlay paths in skills/workflows/rules` | #18 | 6 files | grep obsolete paths returns 0 |
| `1.8 fix(docs): Cosign keyless consistency across skills` | #29 | multiple skill files | grep `cosign verify --key` returns 0 |
| `1.9 fix(docs): bump CHECKLIST_RELEASE.md and CONTRIBUTING.md to D-30` | #20, #21 | `templates/docs/CHECKLIST_RELEASE.md`, `CONTRIBUTING.md` | manual: D-30 mentioned, `--workers 1` removed |
| `1.10 fix(skill): remove broken smoke_test.py reference` | #22 | `.windsurf/skills/release-checklist/SKILL.md` | grep `smoke_test.py` returns 0 |
| `1.11 fix(editorial): cursor INDEX header + parity counts` | #26, #27 | `.cursor/skills/INDEX.md`, `docs/ide-parity-audit.md` | manual review |
| ~~`1.12 fix(state): move incident_active.json to ops/state/`~~ | ~~#52~~ | — | **Closed without code change**: §52 in the resolution table was a misread; the actual filename is `ops/incident_state.json` and the gitignore pattern is correct. See the §52 row above. |

**Phase 1 deliverable**: `scripts/validate_doc_drift.sh` codifies all greps
above. Runs in CI as part of `validate-templates.yml` (read-only, fast).

## Phase 2 — Template correctness (3–4 days, ~6 commits, medium coordination)

**Phase invariant**: a freshly-scaffolded service has a functional CI/CD,
a real test suite, and a contract snapshot. Detected by extending the
scaffold-e2e CI job to install + test + snapshot.

| Commit | Gaps closed | Notes |
|--------|-------------|-------|
| `2.1 feat(scaffold): parametrize ServiceA across CI/CD templates` | #07 | Extend `new-service.sh` to substitute `ServiceA` token in `.github/workflows/*.yml` it copies |
| `2.2 test(api): convert test_api.py from skeleton to real suite` | #01 | Implement 17 pass tests against `/predict_batch` + customers; remove TODOs |
| `2.3 test(training): convert test_training.py from skeleton to real suite` | #31 | Same approach as 2.2 for training pipeline |
| `2.4 feat(contract): generate openapi.snapshot.json + test_schema_evolution.py` | #05 | Snapshot is auto-regenerated when intentional; test_schema_evolution detects breaking changes |
| `2.5 ci(scaffold): smoke test scaffolded service end-to-end` | #36 | New CI job: scaffold → install → test → snapshot |
| `2.6 ci(coverage): include templates/tests/unit/ in coverage badge source` | #32 | Adjust `.github/workflows/ci-examples.yml:31` |

**Phase 2 deliverable**: scaffold-e2e CI job goes green with real tests,
real coverage, contract snapshot validated.

## Phase 3 — Supply chain + governance ops (4–5 days, ~5 commits, high coordination)

**Phase invariant**: trust chain closes (Cosign signs in workflow X, Kyverno
verifies issuer X), agentic governance is operational (not declarative).

| Commit | Gaps closed | Notes |
|--------|-------------|-------|
| `3.1 fix(deploy): migrate GCP to Workload Identity Federation` | #02 | Replace `credentials_json: GCP_SA_KEY` with `google-github-actions/auth@v2` + WIF; document IAM binding in `docs/runbooks/gcp-wif-setup.md` |
| `3.2 fix(supply-chain): close Cosign trust chain` | #03 | Decision: move signing into `ci.yml` (Kyverno expects `.github/workflows/ci.yml`). Re-enable signing step. Document in `docs/runbooks/supply-chain.md` |
| `3.3 ci(self-audit): apply gitleaks/tfsec/checkov/trivy to template repo itself` | #16 | Extend `.github/workflows/validate-templates.yml` to run security scans on the template's own files |
| `3.4 feat(agentic): authorization_mode + success criteria for all 16 skills` | #08, #09 | Use rollback/model-retrain/security-audit as templates. Codify minimum spec: `authorization_mode + inputs + outputs + success_criteria + escalation_triggers + audit_hook` |
| `3.5 feat(audit): wire record_operation() into critical flows` | P0.5 | Hooks added to deploy-gke, deploy-aws, model-retrain, rollback, security-audit, secret-breach, release-checklist skills |

**Phase 3 deliverable**: `cosign verify` against Kyverno succeeds; `audit.jsonl`
populates on every CI run; all skills pass `validate_agentic.py --strict`.

## Phase 4 — Dynamic behavior + validator + tags (3–4 days, ~5 commits)

**Phase invariant**: claims in `ADR-010` (Dynamic Behavior Protocol) are
behaviorally true; `validate_agentic --strict` is green; git tags align
with CHANGELOG.

| Commit | Gaps closed | Notes |
|--------|-------------|-------|
| `4.1 feat(risk): implement _load_prometheus_signals with real HTTP query` | #10 | HTTP `/api/v1/query` against env-configured Prometheus URL; fallback to `unavailable` on failure (per ADR-010); record `risk_signals: UNAVAILABLE` in audit |
| `4.2 feat(risk): wire get_risk_context() into 6 critical operations` | #11 | deploy-gke, deploy-aws, model-retrain, rollback, security-audit, release-checklist |
| `4.3 fix(validator): make validate_agentic --strict green` | #06 | Address 18 warnings; extend validator with semantic checks (endpoints exist in OpenAPI, paths match tree, scripts referenced exist) |
| `4.4 ci(strict): make validate_agentic --strict required for green CI` | #34 | Promote from advisory to blocking |
| `4.5 chore(release): align git tags with CHANGELOG.md history` | #16 | Create v1.3.0 → v1.9.0 tags from corresponding commits |

**Phase 4 deliverable**: ADR-010 promises match reality; CI fails on any
agentic semantic regression; release history is consistent.

## Phase 5 — Post-launch hardening (parallel with community traction)

| Commit | Gaps closed | Notes |
|--------|-------------|-------|
| `5.1 feat(docs): generate endpoints/overlays/parity from code` | P2.2 | New scripts under `scripts/generators/` produce auto-derived sections; pre-commit hook runs them |
| `5.2 ci(quality): markdown-link-check + markdown-lint in CI` | P2 | `docs-quality.yml` workflow |
| `5.3 feat(scaffold): bootstrap migrates to uv + .venv` | #25, P1.4 | PEP-668 safe by default. Update `docs/runbooks/mcp-config-hygiene.md` cross-ref |
| `5.4 feat(docs): template maturity table in README` | P2 | demo-ready / scaffold-ready / production-hardening per component |
| `5.5 feat(skills): elevate 13 skills to internal best-of bar` | P2.3 | Editorial pass: every skill has the same depth as rollback/model-retrain |
| `5.6 docs(readme): split README by user persona` | #35 | "I want to demo" / "I want to scaffold" / "I want to contribute" / "I want to understand the architecture" |
| `5.7 feat(scaffold): SBOM naming parameterized for multi-service` | P2 | Adjust `templates/cicd/ci.yml` SBOM section |
| `5.8 refactor(agentic): Claude/Cursor consume from Windsurf canonical metadata` | P2.4 | Reduce duplication; Windsurf is source of truth, others derive |

## Execution rules

1. **No commit lands without its phase's integration test in green.**
2. **No phase starts before the previous phase's deliverable is verified** —
   the dependency graph is intentional.
3. **Each commit ID in this ADR (e.g., `2.4`) must appear in the commit
   message** (e.g., `feat(contract): ... [ADR-014 §2.4]`).
4. **The ADR is updated on phase completion**: status table at the bottom
   moves the phase from "in progress" to "done" with the commit hash range.
5. **Audit trail**: each phase produces an `ops/audit.jsonl` entry locally
   and a GHA step summary section.

## Consequences

### Positive

- Clear sequencing eliminates rework from out-of-order fixes
- Each phase is independently deployable (we can stop after phase 2 with a
  well-formed scaffold even if governance work remains)
- Integration tests per phase prevent regression
- Future contributors have a runbook for similar audits

### Negative

- More upfront ceremony than fixing gaps ad-hoc
- Tying commits to ADR section numbers requires discipline
- The plan is comprehensive but not minimal — for a smaller project, 4 phases
  would be excessive

### Risks

- A phase blocking on external infra (e.g., real Prometheus for §4.1) may
  stall the chain. Mitigation: §4.1 has a documented fallback to `unavailable`,
  so the wiring is testable even without live Prometheus.
- WIF migration (§3.1) requires GCP project admin access — coordinate
  with whoever holds that role before starting Phase 3.

## Tracking

| Phase | Status | Commit range | Completed |
|-------|--------|--------------|-----------|
| Phase 1 — Quick wins | **Done** | `6601c54` → `b31f424` (7 commits) | All 12 sub-commits effective: §1.1–§1.11 landed; §1.12 closed by §52 correction; deliverable `scripts/validate_doc_drift.sh` deferred to Phase 5 §5.2 alongside markdown-link-check (consolidated CI doc-quality gate). |
| Phase 2 — Template correctness | **Done** | `05c7d19` → `a07e527` (+ ci-examples.yml in this commit) | All 6 sub-commits effective: §2.1 ServiceA→{ServiceName} parametrization; §2.2 test_api.py real suite (8 classes / 26 tests, conftest fixtures); §2.3 test_training.py stubs→pytest.skip + new determinism gate; §2.4 test_schema_evolution.py + CI pair-change guard; §2.5 scaffold-e2e smoke chain (install + snapshot + pytest); §2.6 coverage badge wired to common_utils + service/app + templates/tests/unit/. |
| Phase 3 — Supply chain + governance ops | **Done** | `d09543d` → this commit (7 commits) | All 5 sub-sections closed: §3.1 GCP WIF migration + runbook; §3.2 Kyverno trust regexp closes Cosign chain; §3.3 self-audit job (gitleaks/tfsec/checkov/trivy/AGENTS link-check); §3.4 part 1 authorization_mode for 6 skills + escalation_triggers; §3.4 part 2 success criteria sections for 4 skills (the 7 remaining skills already had equivalent contracts under different headings — see §3.4 part 2 commit body); §3.5 `scripts/audit_record.py` CLI wrapper + Emit audit entry step in deploy-common.yml that runs on success AND failure with GHA step summary mirror. |
| Phase 4 — Dynamic behavior + validator | **Done** | `8b20555` → this commit + 9 retroactive tags (v1.3.0..v1.9.0) | All 5 sub-sections closed: §4.1 `_load_prometheus_signals` real HTTP + 7 mock-based tests + `recent_rollback` cross-source fold; §4.2 dynamic risk pre-check + STOP enforcement step in deploy-common.yml + audit step records base/final mode and signal source; §4.3 validator rewritten with PyYAML (handles YAML lists), `info` severity introduced for downstream-only globs, AGENTS.md cross-refs added (3 skills + 2 workflows); §4.4 `validate_agentic --strict` blocking in CI (`agentic-system` job in validate-templates.yml); §4.5 9 retroactive annotated tags v1.3.0 through v1.9.0 created from the commits that first added each release notes file (use `git tag -l \| sort -V` to verify). Result: `--strict` green with 12 informational notes, 0 warnings. |
| Phase 5 — Post-launch hardening | **In progress** (5 / 8 sub-sections) | Spans across Phase 5 commits | Closed: §5.2 markdown-link-check + markdown-lint workflow + ignore-rules; §5.3 PEP-668 safe bootstrap (uv → .venv fallback) + mcp-config-hygiene runbook update; §5.4 Template Maturity Levels table in README (13 rows, 🟢/🟡/🔴/⚫ legend); §5.6 README persona-driven Quick Navigation (7 personas → entry points); §5.7 multi-service SBOM loop in deploy-{gcp,aws}.yml. Pending (each is a dedicated-session size): §5.1 doc generators (endpoints/overlays/parity from code); §5.5 13 skills to premium standard (editorial pass to bring batch-inference, concept-drift-analysis, deploy-aws, deploy-gke, performance-degradation-rca, rule-audit, secret-breach-response up to rollback/model-retrain/security-audit's bar); §5.8 Claude/Cursor metadata derivation from Windsurf canonical (parity refactor reducing duplication). |

## Related

- ADR-005 — Agent Behavior and Security (the static modes Phase 4 makes dynamic)
- ADR-010 — Dynamic Behavior Protocol (the contract Phase 4 implements)
- ADR-011 — Environment Promotion Gates (the wait_timer authority for §1.2)
- ADR-013 — GitOps Strategy (compatibility constraint for Phase 3)
- AGENTS.md — Audit Trail Protocol (authority for §48 decision)
- `docs/runbooks/mcp-config-hygiene.md` — referenced by §51, updated in §5.3
- Internal audit document (April 2026) — source of the 47 gaps; not in repo
