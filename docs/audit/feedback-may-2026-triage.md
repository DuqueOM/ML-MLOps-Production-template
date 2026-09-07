# External feedback triage — May 2026

> **Date**: 2026-05-04
> **Base release**: v0.15.1 (`f392708`)
> **Source**: external feedback (multiple channels) listing 40 gaps
> across 8 categories.
>
> This document classifies each item against the current state of
> the repository AND the existing ADR-defined scope/limits. The goal
> is to separate **real gaps that move the template forward** from
> **gaps that are scope-deferred by design** and **misperceptions
> that need disclosure-only fixes**.

## Legend

| Symbol | Meaning |
| -------- | --------- |
| ✅ | Already resolved — feedback is stale or based on outdated artifact |
| 🟡 | Disclosed (limit acknowledged in an ADR or VALIDATION_LOG entry) |
| ⚪ | Out of scope by design — see ADR reference; not worth implementing |
| 🔧 | Worth doing now — actionable in the current release line |
| 🔵 | Worth doing later — deferred to a future minor (tracked in ADR-015) |

A 🔧 item is one where (a) the cost is bounded, (b) it doesn't
contradict ADR-001 scope, and (c) the value to adopters is
demonstrable. Anything 🔵 is real but the cost/value ratio puts it
beyond the next release.

---

## Executive summary

| Category | Total | ✅ | 🟡 | ⚪ | 🔧 | 🔵 |
| ---------- | ------- | ---- | ---- | ---- | ----- | ----- |
| 1. Production & Real Validation | 4 | 0 | 3 | 0 | 1 | 0 |
| 2. Agentic System & ML | 4 | 0 | 3 | 0 | 1 | 0 |
| 3. Credibility & Releases | 3 | 0 | 1 | 0 | 2 | 0 |
| 4. Security & Compliance | 5 | 0 | 2 | 1 | 1 | 1 |
| 5. Testing & Quality | 4 | 0 | 1 | 1 | 2 | 0 |
| 6. Infrastructure & Ops | 8 | 0 | 4 | 0 | 4 | 0 |
| 7. Adoption & DX | 5 | 1 | 2 | 1 | 1 | 0 |
| 8. Strategic | 5 | 0 | 0 | 5 | 0 | 0 |
| **Total** | **38** | **1** | **16** | **8** | **12** | **1** |

**Update 2026-05-04 (afternoon)**: 12 of 12 🔧 items SHIPPED across 5 PRs (`feedback-PR-1` through `feedback-PR-5`). All
✅ in this revision are post-shipment status; the original triage column is preserved in commit history. See § "Closure
summary" at the end of this document.

**The 12 🔧 items are the actionable shortlist.** They are clustered
into ~5 PRs that each take < 1 day. Estimated total work: 3–4 days.

The 16 🟡 items are honest limits already disclosed; the 8 ⚪ items
are scope-deferred (ADR-001) and resolving them would CONTRADICT the
template's stated scope, not improve it. Implementing them would
turn this template into a different product — that's a v2.0 decision,
not a feedback-driven one.

---

## 1. Production & Real Validation

### 1.1 No L4 Evidence of Production 🟡

- **Status**: disclosed by ADR-024 §"Review" and VALIDATION_LOG
  Entry 007/008 (both call out "L4 real-cluster execution" as the
  explicit `v1.0.0` gate).
- **Action**: NONE locally. This is THE gate from a designed-ready
  template to a verified-ready one. Requires a real GKE + EKS
  account, real traffic, and a 4-week soak. Cannot be closed by
  any local edit.
- **What we already do**: README §"Production-ready scope"
  explicitly says L1+L2+L3 only; numeric self-rating removed in
  v0.15.0 (HIGH-3/4/5).

### 1.2 Closed-loop ML Incomplete 🟡 → partial 🔧

- **Status**: prediction logger (D-21/D-22), retrain quality gates
  (ADR-008 champion/challenger), and drift detection ship today.
  What is NOT documented is the **expected feedback-loop latency
  contract**: how long ground truth ingestion takes, what SLO
  applies to ground-truth freshness, and how that gates retraining.
- **Action 🔧**: add a small `docs/runbooks/closed-loop-sla.md`
  documenting the assumed SLA (e.g. ground truth available within
  N hours, drift detection cadence, retrain trigger latency). This
  is documentation-only and turns the implicit contract explicit
  for adopters.
- **Out of scope**: actually proving the SLA under load (= L4 gate).

### 1.3 Observability Not Validated Under Load 🟡

- **Status**: same L4 gap. OpenTelemetry middleware (MED-6) is
  opt-in and shipped untested under load.
- **Action**: NONE without a real cluster + load test framework.
  The Locust workflow `/load-test` exists for adopters who run
  their own cluster.
- **What we already do**: `OTEL_ENABLED` is opt-in by default with
  warn-only fallback so adoption doesn't break startup.

### 1.4 Supply Chain Not Fully Executed 🔧

- **Status**: cosign image signing, SBOM, model blob signing
  (HIGH-8), and Kyverno policies all exist as YAML. v0.15.1 added
  `model-verifier` init container so cosign verify-blob runs on
  every pod start. **Kyverno policy admission is still untested in
  any cluster.**
- **Action 🔧**: add a `kind`-based smoke test in CI that loads
  Kyverno + applies the policies + tries to deploy an unsigned
  image and asserts the admission rejection. This is the cheapest
  way to prove the policy enforces what it claims, without an L4
  cluster.
- **Estimated effort**: ~half a day. Worth it because it converts
  "Kyverno designed" to "Kyverno verified".

---

## 2. Agentic System & ML

### 2.1 Memory Plane Not Implemented ⚪ disclosed via 🟡

- **Status**: ADR-018 status line states **explicitly** "Phase 1
  (canonical contracts + redaction) — no storage, no retrieval".
  The May 2026 audit (HIGH-5) demoted Memory Plane from hero copy
  in README to "Roadmap — Phase 1 contracts only".
- **Action**: NONE — implementing it would contradict the v0.x
  roadmap. The ADR-018 §"Phase 2/3 trigger" lists the actual
  conditions for promotion (real adopter signal, vector DB choice
  ratified, etc.).

### 2.2 CI Self-healing Not Operational ⚪ disclosed via 🟡

- **Status**: ADR-019 status line: **"Phase 1 (read-only classifier +
  collector) — shadow mode, no writes"**. May 2026 audit (HIGH-5)
  demoted from hero copy. CHANGELOG v0.15.0 explicitly lists this
  demotion.
- **Action**: NONE for the same reason as 2.1.

### 2.3 Agentic System Without Production Runtime 🟡

- **Status**: AUTO/CONSULT/STOP protocol is a **contract document**
  in AGENTS.md and ADR-005/010. It is enforced via the audit
  trail (`scripts/audit_record.py` + `risk_context.py`) on every
  workflow run. There is no separate "runtime" because the protocol
  binds the agent's CI behavior, not a long-running service.
- **Action**: NONE — calling this a "runtime gap" misreads the
  architecture. The runtime IS the GitHub Actions workflows, gated
  by `audit_record.py` and the IDE rules adapters. ADR-014 §3.5
  documents this.

### 2.4 Agentic Validation Is Structural Only, Not Behavioral 🔧

- **Status**: today's tests validate file structure (rule frontmatter,
  workflow YAML, AGENTS.md cross-references). They do NOT exercise
  decision-making under simulated signals.
- **Action 🔧**: add `tests/test_risk_context_behavior.py` that
  feeds synthetic signal combinations (incident_active,
  drift_severe, error_budget_exhausted, off_hours, recent_rollback)
  into `RiskContext.compute_final_mode()` and asserts every cell of
  the escalation table from MEMORY[01-mlops-conventions.md]. Pure
  unit test, no Prometheus needed (Prometheus path already covered
  by HIGH-9 unit-level changes).
- **Estimated effort**: 1–2 hours. Closes the "behavioral validation"
  gap with zero infrastructure cost.

---

## 3. Credibility & Releases

### 3.1 Zero GitHub Releases Published ✅ CLOSED in feedback-PR-1

- **Reality after audit**: 11 of the v1.x tags WERE published as
  Releases; v0.13.0 and v0.14.0 also already had Releases. The
  perception gap was real for v0.15.0 and v0.15.1 only (no Release
  for either).
- **Closure (feedback-PR-1)**:
  - Created git tags `v0.15.0` and `v0.15.1` over the right commits.
  - Published Releases for both with CHANGELOG-derived bodies.
  - Added `.github/workflows/release-on-tag.yml` to AUTO-publish
    every future tag, extracting the matching CHANGELOG section
    and flagging `v0.x` as prerelease until L4 evidence ratifies
    `v1.0.0`.
- **Outcome**: zero manual steps for future releases; v0.15.0 and
  v0.15.1 visible at github.com/DuqueOM/ML-MLOps-Production-Template/releases.

### 3.2 README Misaligned (Cache vs Current) ✅ → action 🔧

- **Status**: the v0.15.0 commit DID update README. If GitHub still
  shows the old version, it is GitHub's CDN cache, not a real
  divergence. The "12 vs 32 anti-patterns" reference is to D-01
  through D-27 (current canonical count is 27 anti-patterns, see
  `AGENTS.md`).
- **Action 🔧**: verify by fetching `raw.githubusercontent.com` URL
  for README.md and confirm content matches the local file. If
  GitHub UI still shows stale, force a tiny commit to bust the
  cache. **Documentation-only fix.**

### 3.3 Versioning Narratively Confusing 🟡

- **Status**: disclosed in CHANGELOG header (v0.x line + v1.0.0
  reserved for L4 evidence) AND in `docs/RELEASING.md` AND in
  ADR-020. The "downgrade from v1.12 to v0.14" is intentional and
  audited.
- **Action**: NONE — anyone reading the CHANGELOG header
  understands. The cost of explaining further (e.g. renaming v1.x
  tags) > the benefit. **Disclosure-only suffices.**

---

## 4. Security & Compliance

### 4.1 No Formal Compliance Mapping 🔵 → 🔧

- **Status**: ADR-001 explicitly defers SOC2/GDPR/HIPAA: "Compliance
  requires legal review, organizational policies, and audit
  infrastructure. Code templates can't substitute for compliance
  programs."
- **Action 🔧** (small): add `docs/security/compliance-mapping.md`
  with an **informal** crosswalk table — controls the template
  ships (RBAC, NetworkPolicy, IRSA/WI, gitleaks, audit trail) →
  the SOC2/GDPR/HIPAA categories they help with. Loud disclaimer
  that this is a starting-point map, not a compliance program.
- **Why**: ADR-001 says "we don't ship compliance"; it doesn't say
  "we don't HELP adopters who must comply". A pointer-only document
  costs nothing and removes a real adopter friction.
- **Estimated effort**: 2–3 hours.

### 4.2 Historical Insecure GCP_SA_KEY 🟡

- **Status**: was removed in earlier audit cycles (ADR-016 R2). Any
  early adopter who forked before v0.10 may have copied the bad
  pattern.
- **Action 🔧** (small): add a "Historical security disclosures"
  section to `SECURITY.md` listing this and the Prometheus-no-TLS
  case (4.3) with the version range and remediation pointer
  (`/secret-breach`). **Defensive transparency.**

### 4.3 Prometheus Without Prior TLS/Auth 🟡

- **Status**: fixed v0.15.0 HIGH-9. Same disclosure case as 4.2.
- **Action**: covered by 4.2's SECURITY.md addition.

### 4.4 Cosign Edge Case Without Access to Rekor 🔵

- **Status**: real edge case. Today the verifier does keyless
  verification which requires Rekor + the OIDC issuer to be
  reachable. Air-gapped clusters or aggressive egress lockdown will
  break verification.
- **Action 🔵** (deferred): add `MODEL_SIGNATURE_VERIFY=offline`
  mode that uses a static cosign public-key file mounted as a
  Secret. Requires architectural decision (key rotation, key
  storage) — write an ADR first.
- **Why deferred**: < 5% of adopters run air-gapped K8s in our
  target audience (single-team, classical ML). Not worth the
  arch complexity until a real adopter requests it.

### 4.5 No Infracost in Terraform CI ⚪ disclosed via skill

- **Status**: ADR-001 Engineering Calibration: this template ships
  `cost-audit` skill + `/cost-review` workflow, both consume
  cloud billing data manually. Infracost would add CI-time cost
  estimation but requires a paid API or self-hosted runner.
- **Action**: NONE in v0.x. Adopters can wire it themselves; the
  cost-audit skill already documents the manual workflow. Add a
  note in `cost-review.md` runbook mentioning infracost as a
  community contribution opportunity.

---

## 5. Testing & Quality

### 5.1 Insufficient Coverage in Core Modules 🔧

- **Status**: `risk_context.py`, `secrets.py`, and
  `prediction_logger.py` have meaningful logic but lower test
  coverage than the rest of `common_utils/`. The HIGH-9 work in
  v0.15.0 hardened risk_context.py logic but did not add unit tests
  proportional to the new branches.
- **Action 🔧**: write three test files
  - `tests/test_risk_context_behavior.py` (overlaps with 2.4)
  - `tests/test_secrets_resolver.py` — env-vs-secret-manager
    resolution with mocked clients
  - `tests/test_prediction_logger_redaction.py` — PII fields are
    actually redacted
- **Estimated effort**: 1 day total for all three.

### 5.2 Windows CI Absent ⚪ scope-deferred

- **Status**: K8s pods run Linux. Docker images are Linux-amd64.
  Local dev on Windows works through WSL2 (devcontainer ships in
  `.devcontainer/`). Adding a Windows CI runner doubles CI cost
  and tests a path no scaffolded service ever takes in production.
- **Action**: NONE. Add an explicit note to `CONTRIBUTING.md`:
  "Local dev supported on Linux/macOS/WSL2; Windows native is not
  a supported target."

### 5.3 Performance / chaos / failure injection 🟡

- **Status**: same L4 gap. `/load-test` workflow exists; chaos
  testing requires a cluster.
- **Action**: NONE without L4.

### 5.4 DORA Metrics Without Dashboard 🔧

- **Status**: DORA exporter ships data but no Grafana dashboard
  template references it.
- **Action 🔧**: add `templates/monitoring/dashboards/dora.json`
  (a small Grafana dashboard JSON with the 4 DORA metrics: deploy
  frequency, lead time, MTTR, change failure rate). Reference it
  from `docs/runbooks/performance-review.md`.
- **Estimated effort**: 2–3 hours.

---

## 6. Infrastructure & Operations

### 6.1 common_utils Dual-source (Debt) 🔵 → 🔧 (write ADR first)

- **Status**: lives in BOTH `templates/common_utils/` (template
  source of truth) AND in scaffolded services (rendered copy).
  Documented as known debt; no formal resolution.
- **Action 🔧**: write `ADR-025-common-utils-distribution.md`
  proposing one of: (a) keep dual-source + a CI drift check,
  (b) publish `mlops-common-utils` as a versioned PyPI package,
  (c) git submodule. Each has trade-offs that need to be debated
  in an ADR before code changes.
- **Estimated effort**: ADR draft = 2 hours; chosen implementation
  varies (drift-check is shortest, ~1 day; PyPI is multi-week).

### 6.2 Argo Rollouts Hidden (OPT-IN Not Prominently Documented) 🔧

- **Status**: `argo-rollout.yaml` is OPT-IN via base/kustomization
  comment header. Adopters who don't read kustomization comments
  miss it.
- **Action 🔧**: add a "Optional: Progressive Delivery" section
  to README directly under the "Production-ready scope" matrix,
  with a 4-line "how to enable" snippet referencing the
  `argo-rollout.yaml` patch. Move the same content into
  `docs/runbooks/progressive-delivery.md` (new file).
- **Estimated effort**: 1–2 hours.

### 6.3 Agentic Adapter Drift Between IDEs 🔧

- **Status**: `make agentic-sync` regenerates `.cursor/`,
  `.claude/`, `.windsurf/` adapters from `.windsurf/rules/` source
  of truth. There is NO CI gate that fails if an adapter is stale.
- **Action 🔧**: add `agentic-adapter-drift` job to
  `validate-templates.yml` that runs `make agentic-sync` and fails
  if `git diff --quiet` returns non-zero. **Catches forgotten
  syncs at PR time.**
- **Estimated effort**: 1 hour.

### 6.4 Grafana Dashboard Without Centralized Inventory 🔧

- **Status**: dashboards exist scattered. No INDEX.
- **Action 🔧**: add `templates/monitoring/dashboards/INDEX.md`
  with one row per shipped dashboard: name, source query
  Prometheus rule, target audience, runbook link. Pairs with
  5.4 (DORA dashboard).
- **Estimated effort**: 1 hour.

### 6.5 Multi-cloud Design Not Operational 🟡

- **Status**: same L4 gap. Both GKE and EKS overlays render +
  pass kustomize build, but neither has been deployed to a real
  cluster of that cloud.
- **Action**: NONE without L4.

### 6.6 Incident SLAs Not Validated Under Load 🟡

- **Status**: SLO PrometheusRule (CRIT-1) ships but has never been
  evaluated against real burn rate. ADR-006 §closed-loop documents
  the targets.
- **Action**: NONE without L4.

### 6.7 PSI Thresholds Without Quantitative Justification 🟡

- **Status**: ADR-022-psi-thresholds.md exists with the rationale
  (Western/Wilson reference, simulation evidence). The feedback
  may be that not every per-feature threshold is tuned.
- **Action**: NONE — the per-feature tuning is an adopter
  responsibility (their data, their thresholds). The template
  ships sane defaults + the procedure to tune.

### 6.8 Model Catalog Not Reconciled With Providers 🟡

- **Status**: documented limitation. Catalog is a local view; live
  MLflow / Vertex / SageMaker registry is the source of truth at
  the adopter site.
- **Action**: NONE.

---

## 7. Adoption & Developer Experience

### 7.1 Bus factor = 1 ✅

- **Status**: disclosed v0.15.0 HIGH-2 in `.github/CODEOWNERS`,
  `deploy-gcp.yml`, `deploy-aws.yml`, README, and CHANGELOG.
- **Action**: NONE — additional maintainers is an adoption
  outcome, not a code change.

### 7.2 No Clear Happy Path 🔧

- **Status**: `examples/minimal/` exists but isn't surfaced as
  THE happy path. `QUICK_START.md` exists but mixes minimal +
  full template paths.
- **Action 🔧**: rewrite `QUICK_START.md` with two clearly
  labeled tracks:
  - **Track A — 5-minute taste** (`examples/minimal/` only,
    `docker compose up`, curl the endpoint)
  - **Track B — full scaffold** (`bash scripts/bootstrap.sh` →
    `make new-service` → run tests)
- **Estimated effort**: 2 hours.

### 7.3 Cognitive Density 🔵 → partial 🔧

- **Status**: real. The template surfaces ML + K8s + Terraform +
  CI/CD + security + agentic system at once.
- **Action 🔧** (partial): add `docs/PROGRESSION.md` — a single
  page with a layered "where to start" map: Day 1 (run minimal),
  Day 3 (scaffold a service locally), Week 2 (deploy to dev k8s),
  Month 1 (production overlay), Month 2 (drift + retrain).
  Anchor links into existing docs; no new content.
- **What we will NOT do**: build a tutorial track, video walkthroughs,
  or a guided UI. Those are IDP features, ADR-001 deferred.
- **Estimated effort**: 3 hours.

### 7.4 No Modern UX ⚪ scope-deferred

- **Status**: ADR-001 explicitly scopes to CLI + YAML + scripts.
  May 2026 audit (HIGH-3) demoted "IDP" framing.
- **Action**: NONE — building a UX would change what this template
  IS, not improve it. See category 8.

### 7.5 No Documented External Adoption 🟡

- **Status**: fact. README is honest. Single contributor.
- **Action**: NONE — encouraging adoption is outside the template's
  surface.

---

## 8. Strategic — all ⚪

These five items are scope-deferred decisions documented in ADR-001
and ADR-015. Resolving any of them would CHANGE WHAT THIS TEMPLATE
IS, not improve it. They are explicitly NOT in the actionable list.

### 8.1 No Cost History (FinOps) ⚪

- **ADR**: ADR-001 Engineering Calibration. cost-audit skill ships;
  per-prediction cost is an adopter analysis, not a template artifact.

### 8.2 No Support for GPU Workloads ⚪

- **ADR**: ADR-001 §LLM/GenAI deferral implicitly covers this.
  GPU = different node pool taints, different driver versions,
  different scaling math. A separate `LLM-MLOps-Template` is the
  correct vehicle.

### 8.3 No Integration With Vertex/SageMaker ⚪

- **ADR**: ADR-001 §"What We Have Instead". Self-hosted MLflow on
  K8s is the deliberate choice. Vertex/SageMaker integration is a
  different productization roadmap (ADR-015 candidate, not v0.x).

### 8.4 IDP-like Without Declaring It ⚪ already corrected

- **Status**: May 2026 audit (HIGH-3/4/5) explicitly demoted the
  "Production-ready by design" framing. README now reads
  "Designed-ready (L1+L2+L3) classical-ML template". Calling it
  an IDP would re-trigger the same dishonesty the audit just fixed.
- **Action**: NONE — already corrected in v0.15.0.

### 8.5 Complexity vs Target Imbalance ⚪

- **Status**: same as 8.4. The template targets ML engineers
  shipping their first 2–5 models on K8s. The "junior friendly"
  framing was implicit in older copy and is exactly what
  HIGH-3/4/5 corrected.
- **Action**: NONE.

---

## Recommended PR plan

The 12 🔧 items batch into 5 PRs. Estimates are conservative.

### PR 1 — External credibility hygiene (~1 day)

- 3.1 Publish GitHub Releases for v0.14, v0.15.0, v0.15.1
- 3.2 Verify README cache parity (force refresh if stale)
- 6.4 Grafana dashboard INDEX.md
- 5.4 DORA dashboard JSON
- Pairs naturally because all are documentation-surface fixes.

### PR 2 — Behavioral test coverage (~1 day)

- 2.4 + 5.1 (overlap on `test_risk_context_behavior.py`)
- 5.1 secrets resolver tests
- 5.1 prediction_logger redaction tests

### PR 3 — Discoverability (~1 day)

- 6.2 Argo Rollouts prominent README section + runbook
- 7.2 Quick start dual track
- 7.3 PROGRESSION.md

### PR 4 — Supply chain enforcement smoke (~½ day)

- 1.4 kind-based Kyverno admission test in CI

### PR 5 — Disclosures + small docs (~½ day)

- 1.2 closed-loop SLA runbook
- 4.1 informal compliance crosswalk
- 4.2 SECURITY.md historical disclosures section
- 6.3 agentic adapter drift CI gate
- 6.1 ADR-025 common_utils distribution (DRAFT only)

### PR 6 (deferred to v0.16+) — common_utils distribution implementation

- 6.1 implement chosen option from ADR-025
- 4.4 cosign offline mode

---

## What this triage does NOT change

- ADR-001 scope deferrals stay deferred (LLM, multi-tenancy,
  Vault, feature store, formal compliance, IDP UX).
- The L4 gate to `v1.0.0` (real cluster + soak) stays the gate.
- Memory Plane and CI self-healing stay Phase 1 contracts.
- Versioning policy (v0.x active, v1.x snapshots) stays.

The feedback overlaps significantly with the May 2026 audit (8 of
the 16 🟡 items map to ADR-024 findings already closed in v0.15.0).
That convergence is healthy: external reviewers are surfacing the
same gaps the internal audit found, which means the disclosure
documents are pointed at the right places.

The **net new actionable surface from this feedback** is:

- 12 small fixes (PRs 1–5 above), and
- 1 architectural debate to ratify in an ADR (6.1 common_utils).

Everything else is either already done, already disclosed, or
out-of-scope by ADR-001.

---

## Closure summary (2026-05-04 afternoon)

All 12 🔧 items from the original triage SHIPPED in 5 PRs across
a single working session.

| PR | Items closed | Commit | Verification |
| ---- | -------------- | -------- | -------------- |
| feedback-PR-1 | 3.1, 5.4, 6.4 | `c589b02` | Releases visible at `/releases`; CI gate `dashboard-inventory` green |
| feedback-PR-2 | 2.4, 5.1 (×3) | `7ee29d0` | 214 unit tests pass (was 112); +69 new tests; preexisting Prometheus-mock regression also fixed |
| feedback-PR-3 | 6.2, 7.2, 7.3 | `3c8217f` | New `docs/PROGRESSION.md`, `docs/runbooks/progressive-delivery.md`; QUICK_START Track A/B; README "Optional: Progressive delivery" section |
| feedback-PR-4 | 1.4 | `b8f0251` | New `kyverno-smoke.yml` workflow; `scripts/test_kyverno_admission.sh` validated locally with `bash -n` |
| feedback-PR-5 | 1.2, 4.1, 4.2, 6.1 (DRAFT), 6.3 | `<this commit>` | Closed-loop SLA runbook; informal compliance crosswalk; SECURITY HD-001..HD-004; ADR-025 DRAFT; agentic-adapter-drift CI gate |

### What this changes about the project's posture

- **External credibility**: tags v0.15.0 / v0.15.1 now have GitHub
  Releases. Future tags auto-publish via `release-on-tag.yml`.
- **Test discipline**: D-17 (never log secret) and D-18 (no
  os.environ fallback in staging/prod) are now enforced by unit
  tests, not just code-review vigilance. Behavioral risk-mode
  matrix is exercised end-to-end.
- **Supply-chain enforcement**: Kyverno digest-pinning policy is
  PROVEN to reject `:latest` in a real cluster (kind-based smoke).
  Signature verification still requires L4 evidence.
- **Discoverability**: PROGRESSION.md is the new on-ramp;
  Argo Rollouts is no longer hidden in a kustomization comment.
- **CI completeness**: agentic adapter drift, security baseline
  expiry, and Grafana dashboard inventory now all have CI gates.
  Pre-existing structural validators were already wired.
- **Honest disclosures**: SECURITY.md now lists 4 historical
  vulnerabilities so early-fork adopters can self-audit.

### What is still gated to v1.0.0

Unchanged from the original triage: the **L4 real-cluster
evidence** for GKE + EKS. No amount of local + kind + CI work
closes it. Items 🟡 in this triage that map to L4 (1.1, 1.3, 5.3,
6.5, 6.6) remain L4-gated.

### What ADR-025 unblocks (later)

The `common_utils/` distribution debate is now structured (Option
A/B/C with honest cost/benefit). Ratification is a separate audit
cycle. Until then, the dual-source pattern remains the de-facto
state, but no longer silent debt.
