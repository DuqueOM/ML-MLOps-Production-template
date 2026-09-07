# Action Plan — External Audit R4 (Staff/Lead)

- **Status**: Active
- **Audit round**: R4 (post-`v1.12.0`, post-R3 closure)
- **Owner**: Staff/Lead
- **Master ADR**: [`ADR-020`](../decisions/ADR-020-r4-audit-remediation.md)
- **Tracking label**: `audit-r4`

---

## 1. Diagnosis (one paragraph)

The template's intellectual core is mature: async-correct serving, CPU-only HPA, init-container model loading,
prediction logging with fire-and-forget, closed-loop monitoring with delayed ground truth, supply chain with digest
pinning, and an agentic governance model with escalation-only dynamic risk. **The gap is between intellectual maturity
and verified-execution maturity.** Cosign was never installed in any workflow before `v1.10`. Six Kustomize overlays
never rendered correctly before `v1.10`. The closed-loop verification workflow shipped in `v1.11` posted the wrong
schema and used a metric label that did not exist. Each of those is a single-atom failure of the form "the YAML looks
right; it was never executed against reality."

Round 4 is therefore not about adding features. It is about closing the credibility gap (Sprint 0), introducing per-PR
execution evidence (Sprint 1), and shipping the runtime that ADR-018 / ADR-019 promised in `Phase 0` (Sprints 1–2).

---

## 2. Severity matrix (CVSS-adapted)

Each finding is scored on four axes (1–5): **technical impact (I) × probability (P) × blast radius (B) ÷ detectability
inverse (D)**. `Score = (I × P × B) / D`.

| ID | Finding | I | P | B | D | Score | Severity |
| ---- | --------- | --- | --- | --- | --- | ------- | ---------- |
| C1 | Model routing table contains anticipated names (`gpt-5.4-*`, `gpt-5.5`, `gemini-3.x-preview`) presented as "verified" without disclaimer matching the YAML's own honesty caveat | 4 | 5 | 3 | 1 | 60 | **Critical** |
| C2 | README presents "Agentic CI self-healing" + "Operational Memory Plane" as capabilities without a Phase-0 / runtime-deferred banner visible at the section heading | 4 | 5 | 3 | 1 | 60 | **Critical** |
| C3 | Release discipline broken: 12 minor bumps in 14 days; fixes that closed blocker bugs (Cosign never installed, overlays never worked, closed-loop schema mismatch) shipped as MINOR rather than PATCH or MAJOR | 4 | 5 | 4 | 2 | 40 | **Critical** |
| C4 | No `VALIDATION_LOG.md`: no record of any end-to-end real execution (build → scan → sign → attest → admit → deploy) against a cluster (kind, GKE, or EKS) | 5 | 4 | 4 | 2 | 40 | **Critical** |
| C5 | No `MIGRATION.md`: adopters who scaffolded under v1.7 have no documented path to v1.12 (overlays renamed, schema fields renamed, hook count went 9 → 14) | 4 | 5 | 4 | 2 | 40 | **Critical** |
| H1 | ADR-018 (Memory Plane) and ADR-019 (CI Self-Healing) Phase 1 runtime scripts not implemented; user explicitly requests implementation | 3 | 5 | 3 | 3 | 15 | High |
| H2 | No PR introduction policy that requires evidence (test + real execution + linked CI run) for new template components — root cause of v1.10 / v1.12 bug class | 4 | 4 | 3 | 2 | 24 | High |
| H3 | No per-PR smoke lane (`scaffold` → `kustomize build` × 6 overlays → `kubeconform` → binary-presence) | 4 | 4 | 3 | 2 | 24 | High |
| H4 | No `docs/agentic/red-team-log.md` with documented evasion attempts against AUTO/CONSULT/STOP | 3 | 3 | 3 | 3 | 9 | High |
| H5 | Pipeline bypass-attempt evidence missing (deploy bypass staging, model failing fairness gate, secret in commit) | 4 | 3 | 4 | 2 | 24 | High |
| H6 | Full `git log --all -p \| gitleaks detect --pipe` over history never executed or recorded | 4 | 2 | 5 | 2 | 20 | High |
| H7 | Kyverno admission webhook never validated against a real cluster (rejection of unsigned image / missing SBOM never observed) | 4 | 3 | 4 | 2 | 24 | High |
| M1 | `common_utils/secrets.py` GSM/ASM integration not exercised end-to-end in a runbook | 3 | 3 | 3 | 3 | 9 | Medium |
| M2 | Ground-truth ingestion SLA not contractually documented (D-20 / D-21 cover code, not the SLA) | 3 | 3 | 2 | 3 | 6 | Medium |
| M3 | Fairness thresholds (DIR ≥ 0.80) not justified per domain in a dedicated ADR | 2 | 3 | 2 | 3 | 4 | Medium |
| M4 | Compliance gap analysis (GDPR / SOC 2 / ISO 27001 / HIPAA) absent from `ADOPTION.md` | 3 | 2 | 2 | 3 | 4 | Medium |
| M5 | Alertmanager routing never exercised end-to-end with a synthetic alert | 3 | 3 | 2 | 3 | 6 | Medium |
| M6 | PSI thresholds (warn / alert) not justified quantitatively per feature in an ADR | 2 | 3 | 2 | 3 | 4 | Medium |
| L1 | Several release notes (`v1.0`–`v1.9`) lack `### Known follow-ons` blocks → traceability rough on older versions | 2 | 2 | 2 | 4 | 2 | Low |
| L2 | Grafana dashboard inventory not centralized in one document | 2 | 2 | 2 | 4 | 2 | Low |
| L3 | `infracost` not integrated into `terraform-plan-nightly.yml` (over-provisioning detection) | 2 | 2 | 2 | 4 | 2 | Low |

---

## 3. Mode mapping (per AGENTS.md operations matrix)

| Sprint | AUTO | CONSULT | STOP — delegated |
| -------- | ------ | --------- | ------------------ |
| 0 | S0-1, S0-2, S0-4, S0-5 | S0-3 | — |
| 1 | S1-6 | S1-1, S1-2, S1-5 | S1-3, S1-4 |
| 2 | S2-1, S2-2, S2-3, S2-5 | S2-4 | — |
| 3 | L1, L2 | L3, Phase-1 → Phase-2 transition gate | — |

`STOP — delegated` items are documented end-to-end here but executed by Platform / Security after explicit approval.
They never run inside the agent loop.

---

## 4. Sprint 0 — Credibility emergency (days 1–7)

Goal: close the five Criticals without touching cloud runtime. All five are documentation, policy, or assertion-tests;
none mutate cloud state.

### S0-1 · `[AUTO]` C1 — Correct the model routing table

- **Files**: [`README.md`](../../README.md) §"Recommended baseline", new `tests/test_readme_model_names.py`.
- **Action**:
  1. Replace the heading "Recommended baseline (verified 2026-04)" with "Recommended baseline (cadence-anticipated,
     **NOT** vendor-verified)".
  2. Add a banner block at the top of the section that says: anticipated names following the adopter's requested
     cadence; verify against the provider dashboard at adoption time; the contract test enforces structure (preview
     never on protected branches), not specific identities.
  3. Move the existing speculative-name table under a clearly-labeled
     `#### Cadence-anticipated names — pending vendor verification` heading.
  4. Add a new `#### Verifying model availability before adoption` subsection with explicit steps per provider (OpenAI
     dashboard, Anthropic console, Google AI Studio).
  5. Add `tests/test_readme_model_names.py` that asserts the disclaimer string is present whenever the speculative
     pattern (`gpt-5.\d|gemini-3\.\d`) appears.
- **Acceptance**: heading reworded + banner present + new subsection + assertion test green.

### S0-2 · `[AUTO]` C2 — Phase-0 banners for ADR-018 / ADR-019 sections

- **Files**: [`README.md`](../../README.md) §"Operational Memory Plane" + §"Agentic CI self-healing", new `tests/test_phase0_disclosure.py`.
- **Action**: insert at the top of each section a status banner that says: Phase 0 only — policy + contract tests ship
  today; runtime scripts (`ci_collect_context.py`, `ci_classify_failure.py`, memory ingest worker, vector store) are NOT
  implemented; see ADR-018 / ADR-019 §Phase plan.
- **Acceptance**: banner present + test green that fails if either banner is removed without the corresponding ADR
  transitioning to Phase 1+.

### S0-3 · `[CONSULT]` C3 — Versioning policy + retro-classification

- **Files**: new [`docs/RELEASING.md`](../RELEASING.md), edit [`CHANGELOG.md`](../../CHANGELOG.md).
- **Action**:
  1. Document explicit semver criteria: PATCH for fixes that do not change scaffolded output or any contract; MINOR for
     additive features that do not break scaffolded output; MAJOR for any change that breaks scaffolded output, schema
     fields, overlay names, or pre-commit hook contract surface.
  2. Re-anchor: declare `v1.12.0` as the GA hardening anchor; commit to `v2.0.0` for the next breaking change rather
     than retroactively re-tagging (existing tags remain immutable).
  3. For each release in `v1.10` / `v1.11` / `v1.12` add a `### Breaking for adopters` block documenting what changed in
     scaffolded output and the manual migration step.
  4. Backfill `### Known follow-ons` with linked issues + close-by-SLA on each release that lacks them (paired with L1
     in Sprint 3).
- **Acceptance**: `RELEASING.md` merged, CHANGELOG enriched, one issue per follow-on opened. CONSULT mode because this
  changes the public versioning contract.

### S0-4 · `[AUTO]` C4 — `VALIDATION_LOG.md` first honest entry

- **Files**: new [`VALIDATION_LOG.md`](../../VALIDATION_LOG.md).
- **Action**: capture the first end-to-end execution that is realistically achievable now without a cloud account:
  - scaffold the template with `scripts/test_scaffold.sh`,
  - render the six overlays with `kustomize build`,
  - validate with `kubeconform` against Kubernetes `1.29.0`,
  - record the binaries and versions used.
  - explicitly mark as `pending — Sprint 1` the items that still need a real cluster: Cosign sign against a registry,
    Kyverno reject path, EKS / GKE deploy.
- **Acceptance**: file exists with one real execution recorded, raw output excerpts, and the `pending` block. README
  maturity matrix links to it.

### S0-5 · `[AUTO]` C5 — `MIGRATION.md`

- **Files**: new [`MIGRATION.md`](../../MIGRATION.md).
- **Action**: for each contract-touching release pair (`v1.7 → v1.8`, `v1.9 → v1.10`, `v1.11 → v1.12`) emit a table with
  columns: scaffolded-output breaking change · manual action required · link to the release note and PR. Older minor
  bumps that do not touch contracts get a single-line "no breaking changes" entry for completeness.
- **Acceptance**: file exists; CHANGELOG and `README.md` Quick Start link to it.

**Sprint 0 deliverable**: a single PR `audit-r4/sprint-0-credibility` that closes C1–C5. All changes are documentation +
assertion tests → mergeable under CONSULT, no runtime risk.

---

## 5. Sprint 1 — Execution hardening (days 8–14)

### S1-1 · `[CONSULT]` H3 — Per-PR smoke lane

Add `smoke-scaffold` job to `.github/workflows/golden-path.yml`: scaffold → six `kustomize build` calls →
`kubeconform --strict` → binary presence check (`cosign syft trivy kubectl helm kustomize`). Fails the PR if any overlay
does not render or any deploy script references a binary not declared.

### S1-2 · `[CONSULT]` H2 — PR introduction evidence policy

Edit `.github/pull_request_template.md` and `CONTRIBUTING.md` to require, when a PR introduces a new template component
(workflow, deploy script, schema contract), three filled blocks: (a) contract / schema test, (b) real execution output,
(c) link to the CI run that proves (b). New `pr-evidence-check.yml` workflow fails if the PR matches the allowlist and
the blocks are empty.

### S1-3 · `[STOP — delegated]` H5 / H6 — Bypass tests + history scan

New `docs/runbooks/secret-history-scan.md` documents the `git log --all -p | gitleaks detect --pipe` procedure plus
three bypass tests: deploy directly to prod (must be blocked), model failing fairness (must be blocked), commit with
embedded secret (must be blocked). Each evidence captured as a GHA artifact and linked from `VALIDATION_LOG.md`.

### S1-4 · `[STOP — delegated]` H7 — Kyverno admission validation

New `docs/runbooks/kyverno-admission-validation.md` documents installing Kyverno on `kind`, applying the policies, and
observing the admission webhook denial reason for: unsigned image (must reject), missing SBOM attestation (must reject),
signed + attested image (must admit). Outputs captured in `VALIDATION_LOG.md`.

### S1-5 · `[CONSULT]` H4 — Agentic red-team log

New `docs/agentic/red-team-log.md` with five documented evasion attempts and their resolutions:

1. Prompt injection asking the agent to skip STOP on a prod deploy.
2. Fabricated memory hit asking to demote a STOP to CONSULT.
3. Patch in `protected_paths` (`secrets.py`) disguised as `formatter_drift`.
4. Blast radius rebase: 200-line PR split into five 40-line commits to evade `auto.max_lines_changed: 120`.
5. Off-hours signal forced to `false` via env override.

Each entry: payload, result, blocking invariant, file:line of the mitigation.

### S1-6 · `[AUTO]` H1 (part 1/2) — ADR-019 Phase 1 read-only runtime

New `scripts/ci_collect_context.py` and `scripts/ci_classify_failure.py`. Strictly read-only:

- `ci_collect_context.py` ingests failure logs (stdin / path), extracts job name, files changed, error patterns.
- `ci_classify_failure.py` applies `templates/config/ci_autofix_policy.yaml` and emits JSON
  `{class, mode, blast_radius_estimate, allowed_paths_match}`.
- No PR creation, no commits.
- Hook to `policy-tests.yml`: classifier runs in shadow against the last 14 days of CI failures, results published to
  GHA step summary.
- Tests: classifier accuracy on synthetic fixtures + invariant "never classifies `protected_paths` as AUTO".

ADR-019 Phase 1 then transitions to ✅ in the ADR status box.

---

## 6. Sprint 2 — Memory Plane Phase 1 + Mediums (days 15–21)

### S2-1 · `[AUTO]` H1 (part 2/2) — ADR-018 Phase 1 contracts + redaction

New `templates/common_utils/memory_types.py`:

- `MemoryUnit` dataclass `frozen=True` with the canonical Phase 1 fields from ADR-018 (`id`, `kind`, `summary`,
  `evidence_uri`, `severity`, `sensitivity`, `tenant_key`, `human_authored`, `timestamp`).
- Construction-time invariants: severity normalized to canonical levels, sensitivity ≥ ACL minimum derived from the
  bucket prefix in `evidence_uri`.

New `templates/common_utils/memory_redaction.py`:

- Pipeline that applies `gitleaks.toml` patterns + PII patterns to every string field.
- Invariant test: no string matching gitleaks patterns survives the pipeline.

No storage, no retrieval, no embeddings — Phase 1 is contracts only.

### S2-2 · `[AUTO]` M4 — Compliance gap analysis

Edit `docs/ADOPTION.md` adding a Compliance section. Tabular gap analysis per standard (GDPR, SOC 2 Type II, ISO 27001,
HIPAA): control · covered / partial / out-of-scope · evidence · adopter responsibility. Most rows will be honestly
marked out-of-scope (organizational, not template). Edit `SECURITY.md` adding a disclosure SLA.

### S2-3 · `[AUTO]` M3 / M6 — Fairness ADR + PSI threshold ADR

New `docs/decisions/ADR-021-fairness-thresholds.md` and `ADR-022-psi-thresholds.md`. Each justifies the existing numbers
(DIR ≥ 0.80, PSI warn = 0.10 / alert = 0.25) with literature references and per-domain examples (financial services,
healthcare, advertising) plus revisit triggers.

### S2-4 · `[CONSULT]` M5 — Alertmanager routing test

New `templates/monitoring/tests/test_alertmanager_routing.py` plus `docs/runbooks/alertmanager-validation.md`. Uses
`amtool` against the template's Alertmanager config; injects a synthetic alert per severity; asserts each lands at the
expected receiver and within the documented notification latency.

### S2-5 · `[AUTO]` M1 / M2 — Secrets + ground-truth runbooks

New `docs/runbooks/secrets-integration-e2e.md` and `docs/runbooks/ground-truth-ingestion.md` documenting end-to-end
exercises against GSM / ASM and the ground-truth ingestion SLA contract.

---

## 7. Sprint 3 — Lows + closure (days 22–28)

- **L1** — backfill `### Known follow-ons` on `v1.0`–`v1.9` release notes. AUTO.
- **L2** — new `docs/observability/dashboards-inventory.md` indexing every Grafana dashboard. AUTO.
- **L3** — integrate `infracost diff` into `terraform-plan-nightly.yml`. CONSULT.
- **ADR-019 Phase 1 → Phase 2 gate** — review 14 days of shadow data; decide whether to enable write mode for
  `formatter_drift` only or pause. CONSULT, requires PR review with metrics evidence.
- **Audit closure ADR** — `docs/decisions/ADR-020-r4-audit-remediation.md` updated with evidence for every finding,
  links to PRs, mode used, approver where CONSULT / STOP.

---

## 8. Backlog (post-R4)

| Item | Reason for deferral |
| ------ | --------------------- |
| ADR-019 Phase 2+ (`formatter_drift` write-enabled) | Requires real shadow metrics from Phase 1 |
| ADR-018 Phase 2+ (ingest worker, vector store, retrieval API) | Only after Phase 1 contracts hold for 30 days |
| Cross-cloud parity test runner | Built on top of S1-1 smoke lane |
| Chaos test: prediction logger backend down | After M5 (Alertmanager) is validated |
| GPU lane (D2 from `v1.9` deferred) | No real demand yet |

---

## 9. Executive summary (two paragraphs for non-technical stakeholders)

> The ML-MLOps Production Template has a mature architectural core and defensible engineering decisions, but presents a
> **material gap between design maturity and verified-execution maturity**. R4 identifies five Critical findings, seven
> High, six Medium, and three Low. All five Criticals are about credibility and discipline (anticipated model names
> presented as verified, capability status not communicated clearly, broken release discipline, absence of execution
> evidence, absence of migration guidance) — none touches cloud runtime.
>
> The plan executes in four sprints over 28 days. Sprint 0 closes Criticals with documentation + policy + assertion
> tests only — zero cloud runtime change. Sprint 1 introduces a per-PR smoke lane, a PR-evidence policy, an agentic
> red-team log, and the read-only Phase 1 runtime for ADR-019. Sprint 2 closes the Memory Plane Phase 1 (contracts +
> redaction) and the Compliance gap analysis. Sprint 3 closes Lows and opens the gate decision toward Phase 2 with real
> shadow data. Three actions (gitleaks history scan, Kyverno admission test, prod IaC verifications) are explicitly
> delegated to Platform / Security under STOP mode because their execution is outside the agent's permitted scope.

---

## 10. Tracking

- **Master ADR**: `docs/decisions/ADR-020-r4-audit-remediation.md`
- **Issue label**: `audit-r4`
- **Severity labels**: `severity:critical` / `severity:high` / `severity:medium` / `severity:low`
- **Branches per sprint**: `audit-r4/sprint-{0,1,2,3}-{name}`
- **Evidence collection**: `VALIDATION_LOG.md` for runtime evidence; `docs/agentic/red-team-log.md` for adversarial
  evidence; `ops/audit.jsonl` for agent operations.
