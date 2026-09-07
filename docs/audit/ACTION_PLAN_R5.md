# ACTION_PLAN_R5 — Fifth-pass external audit remediation

- **Authority**: external R5 audit + user-raised pre-commit friction concern, May 2026.
- **Status**: open at Sprint 2 close (commit `0505551`).
- **Predecessor**: [`ACTION_PLAN_R4.md`](ACTION_PLAN_R4.md) (Sprint 0–2 closed at this commit; Sprint 3 of R4 still open).
- **Trigger**: user observed pre-commit scaffold-smoke hook taking >1 min and asked whether this is industry practice;
  the same pass surfaced 6 additional findings (1 High, 4 Medium, 1 Low).
- **Audit log**: every R5 closure adds a row to `VALIDATION_LOG.md` and a column to ADR-020 §"Progress log".

---

## Engineering judgement on pre-commit scaffold smoke

> **User question**: a pre-commit hook running scaffold smoke takes more
> than a minute. Is this enterprise practice or should it move to CI?

**Answer: it should move to CI / on-demand.** Industry baseline:

| Stage | Target latency | Acceptable scope |
| --- | --- | --- |
| pre-commit (per file save) | < 5 s | format, lint, typecheck on changed files |
| pre-push (per push) | < 30 s | unit tests on changed modules, secret scan |
| CI per-PR | 3–10 min | full unit + scaffold + integration + security |
| CI nightly | 30–60 min | E2E, load, drift simulation, infra plan |

Anything that consistently exceeds 1 minute on every commit produces
two failure modes:

1. **`--no-verify` normalization** — contributors learn to bypass the
   hook to keep flow; the invariant the hook protected silently dies.
2. **Local/CI duplication** — `pr-smoke-lane.yml` (S1-1, already merged)
   already runs scaffold + 6 overlay renders + kubeconform on every PR.
   Running it locally too is duplicate work without additive coverage.

**Decision**: track this as **R5-L4** below. Make the local entry point
opt-in via `make smoke` (or `scripts/smoke.sh`); remove from
`.pre-commit-config.yaml`; let `pr-smoke-lane.yml` be the authoritative
gate. Document in `CONTRIBUTING.md` why.

This decision is consistent with:

- Google's pre-commit guidance (Sec 4.2 *Software Engineering at Google*)
- GitHub's Branch Protection model (PR-level gate is the source of truth)
- ADR-019 §"Phase plan" — autonomous changes are CI-driven, not local-hook-driven

---

## R5 findings catalog

### R5-H1 — Verified-execution gap (High)

- **Area**: operational verification.
- **Finding**: the repo is now strong by **design** — contracts,
  classifier, runbooks, ADRs — but several hard guarantees still lack
  **executed evidence**: secrets E2E in real cloud projects, Kyverno
  admission test on a real cluster, full git-history secrets scan,
  Alertmanager routing with `amtool`, and a real ground-truth SLA
  measurement on a deployed service.
- **Impact**: the gap between "production-ready by design" and
  "production-ready by verified execution" is real and visible. An
  external buyer comparing this template to one with executed proofs
  will rate this template lower on operational confidence.
- **Evidence**:
  - `@/home/duque_om/projects/template_MLOps/README.md:70` — "Security
    and supply chain: Production-ready" without verified-execution caveat
  - `@/home/duque_om/projects/template_MLOps/VALIDATION_LOG.md:94` — H5/H6 runbook execution pending
  - `@/home/duque_om/projects/template_MLOps/VALIDATION_LOG.md:214` — H7 kind-cluster Kyverno test pending
  - `@/home/duque_om/projects/template_MLOps/VALIDATION_LOG.md:352` — M1 cloud secrets execution pending
  - `@/home/duque_om/projects/template_MLOps/VALIDATION_LOG.md:374` — M2 GT-SLA real-service evidence pending
- **Action**:
  1. Soften the README maturity-matrix wording: rows whose verification
     is delegated to STOP-mode runbooks must read "Production-ready by
     design (verified execution pending — see runbook)" until the
     execution evidence is recorded.
  2. Add a §"Verification status" mini-matrix to `README.md` listing
     each delegated runbook and its `VALIDATION_LOG.md` entry status
     (executed / pending). Refreshed on every commit that closes one.
  3. Refuse to use the phrase "fully enterprise-ready" anywhere in
     `README.md` until at least 4 of the 5 delegated runbooks have
     executed evidence rows in `VALIDATION_LOG.md`.
- **Mode**: AUTO for R5-H1.1 / R5-H1.2 (documentation hardening); STOP-
  delegated for R5-H1.3 (depends on Platform/Security cadence).
- **Acceptance**: README diff applies the wording change; new
  §"Verification status" exists; first delegated runbook execution lands
  → flip the corresponding row.

---

### R5-M1 — Shadow workflow log fetching is stubbed (Medium)

- **Area**: agentic / CI self-healing precision data quality.
- **Finding**: `ci-self-healing-shadow.yml` ships, but the "Download
  upstream failure logs" step writes an EMPTY `failure.log`
  (`@/home/duque_om/projects/template_MLOps/.github/workflows/ci-self-healing-shadow.yml:89`),
  and the `log_artifact_url` workflow input is declared but never read
  (`@/home/duque_om/projects/template_MLOps/.github/workflows/ci-self-healing-shadow.yml:31`).
  The classifier therefore receives no signature data on every shadow
  run; combined with the no-signature → STOP fallback documented in
  `test_ci_classify_failure_phase1.py`, this guarantees that 14 days of
  shadow data produces 14 days of "STOP, no signature" entries — a
  precision dataset biased to one outcome.
- **Impact**: the Phase 1 → Phase 2 gate (ADR-019 §Phase plan) requires
  measured precision. Without real log content, the gate cannot be
  closed honestly even if the calendar window passes.
- **Evidence**:
  - `@/home/duque_om/projects/template_MLOps/.github/workflows/ci-self-healing-shadow.yml:31` (`log_artifact_url` input
    declared)
  - `@/home/duque_om/projects/template_MLOps/.github/workflows/ci-self-healing-shadow.yml:68-89` (download step writes
    empty log)
  - `@/home/duque_om/projects/template_MLOps/.github/workflows/ci-self-healing-shadow.yml:103-107` (PR diff is "best
    effort" via last-commit only — covered by red-team Entry 4 follow-up F1)
- **Action**:
  1. Add a "Fetch upstream logs via GH API" step using `gh run view --log`
     (or `gh api /repos/.../actions/runs/{id}/logs`) into
     `./_shadow/failure.log`. On API failure, emit `::warning` and
     proceed with empty log (the conservative default still holds).
  2. Wire the `workflow_dispatch` input `log_artifact_url`: when set,
     bypass the API fetch and `curl` the URL into `failure.log` (replay
     mode for offline debugging).
  3. Replace the last-commit `git diff` with a real PR-base diff using
     `gh pr view --json baseRefOid` when the upstream run is a PR. This
     closes red-team follow-up F1 inline.
- **Mode**: CONSULT (touches CI surface; reviewer-gated by branch protection).
- **Acceptance**:
  - First post-merge real upstream failure produces a non-empty
    `failure.log`.
  - `workflow_dispatch` with `log_artifact_url` reads the URL and
    classifies it correctly.
  - Test fixture in `tests/test_ci_classify_failure_phase1.py`
    extended to cover at least one realistic log-derived signature.

---

### R5-M2 — `validate_agentic.py --strict` Windows / CP1252 break (Medium)

- **Area**: cross-platform / DX.
- **Finding**: the validator emits unicode bullets / box-drawing chars
  (`✓`, `✗`, `⚠`, `ℹ`) directly to `sys.stdout`. On Windows with the
  default `cp1252` console codec, these raise `UnicodeEncodeError` and
  the validator crashes before producing its summary; this affects
  contributors using PowerShell or `cmd.exe` without UTF-8 mode.
- **Impact**: a central, supposedly cross-platform validator is in
  reality unix-only. Contributors on Windows get an unfriendly
  `UnicodeEncodeError` traceback the first time they try the project's
  own gate.
- **Evidence**:
  - `@/home/duque_om/projects/template_MLOps/scripts/validate_agentic.py:292` (`print("ℹ ...")`)
  - `@/home/duque_om/projects/template_MLOps/scripts/validate_agentic.py:297` (`print("⚠ ...")`)
  - `@/home/duque_om/projects/template_MLOps/scripts/validate_agentic.py:302` (`print("✗ ...")`)
  - `@/home/duque_om/projects/template_MLOps/scripts/validate_agentic.py:308` (`print("\n✗ Strict mode: ...")`)
  - `@/home/duque_om/projects/template_MLOps/scripts/validate_agentic.py:311` (`print("\n✓ Agentic system valid")`)
  - `@/home/duque_om/projects/template_MLOps/CHANGELOG.md:58` mentions
    cross-platform compatibility as a goal but does not enforce it
- **Action**:
  1. Detect `sys.stdout.encoding`. If it cannot encode unicode bullets,
     fall back to ASCII (`[OK]` / `[!!]` / `[WARN]` / `[INFO]`).
     Alternative: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
     guarded by a Python-version check; fail-safe.
  2. Add a Windows-runner CI lane (single job, `windows-latest`) that
     runs `python scripts/validate_agentic.py --strict` and asserts
     exit code `0` on the canonical repo state.
  3. Document the Windows on-ramp in `CONTRIBUTING.md`.
- **Mode**: AUTO (`scripts/` is non-protected; reviewer-gated by PR).
- **Acceptance**: validator emits parseable output on `cp1252` consoles;
  Windows CI lane is green.

---

### R5-M3 — NetworkPolicy egress allows `0.0.0.0/0:443` (Medium)

- **Area**: Kubernetes / network security posture.
- **Finding**: `templates/k8s/base/networkpolicy.yaml` egress block
  permits TCP 443 to `0.0.0.0/0` (with RFC-1918 `except`). This is
  effectively "the whole internet on HTTPS", which contradicts the
  template's deny-default posture and is a notable gap relative to the
  rest of the security hardening.
- **Impact**: a compromised pod can exfiltrate to any HTTPS endpoint
  worldwide. Public-cloud IP ranges for GCS / S3 are well-known and
  enumerable; the broad egress is unnecessary.
- **Evidence**:
  - `@/home/duque_om/projects/template_MLOps/templates/k8s/base/networkpolicy.yaml:90-102` (TCP 443 to 0.0.0.0/0 except
    RFC-1918)
  - `@/home/duque_om/projects/template_MLOps/CHANGELOG.md:59` documents NetworkPolicy enforcement but does not address scope
- **Action**:
  1. Move the egress rule out of `base/networkpolicy.yaml` and into
     overlay-specific files: `overlays/gcp-{dev,staging,prod}/network/`
     and `overlays/aws-{dev,staging,prod}/network/`.
  2. Per-cloud allowlists: GCP overlays allow `private.googleapis.com`
     and `restricted.googleapis.com` ranges + the project's GCS
     subnets; AWS overlays allow VPC endpoints + the account's S3
     prefix-list IDs.
  3. For dev overlays, document the broader egress as an explicit
     opt-in, with a `# DEV ONLY` banner in the YAML.
  4. Add a contract test (`test_networkpolicy_no_anywhere_egress.py`)
     that fails if any non-dev overlay merges a `0.0.0.0/0` egress.
- **Mode**: CONSULT (touches deploy chain; cluster operators may have
  custom egress policies).
- **Acceptance**:
  - Staging + prod overlays render with cloud-specific egress.
  - Contract test green on the rendered manifests.
  - Dev overlays explicitly opt in via banner comment.

---

### R5-M4 — Locust load test out of contract with API (Medium)

- **Area**: tests / performance.
- **Finding**: `templates/service/tests/load_test.py` issues
  payloads using `feature_1`, `feature_2`, `feature_3`, `feature_4`
  for single requests and `instances` for batches. The actual API
  schema (`templates/service/app/schemas.py`) uses `entity_id`,
  `slice_values`, `feature_a`, `feature_b`, `feature_c` for single
  requests and `customers` for batches. The load test therefore
  measures a 4xx-validation pathway, not the real inference path.
- **Impact**: load-test latency / RPS numbers are not representative
  of production. A team using these numbers to capacity-plan would
  systematically under-provision (validation failures are cheaper
  than real inference).
- **Evidence**:
  - `@/home/duque_om/projects/template_MLOps/templates/service/tests/load_test.py:35` (`feature_1`...`feature_4`)
  - `@/home/duque_om/projects/template_MLOps/templates/service/tests/load_test.py:44-46` (`instances` batch key)
  - `@/home/duque_om/projects/template_MLOps/templates/service/app/schemas.py:46` (`entity_id` + `slice_values` + `feature_a/b/c`)
  - `@/home/duque_om/projects/template_MLOps/templates/service/app/schemas.py:125` (batch uses `customers`)
  - `@/home/duque_om/projects/template_MLOps/CHANGELOG.md:60` referenced as part of the load-test contract gap
- **Action**:
  1. Sync `load_test.py` with the canonical schema (`SAMPLE_PAYLOAD`
     uses `entity_id` + `feature_a/b/c`, batch uses `customers`).
  2. Add a contract test (`test_load_payload_matches_schema.py`) that
     imports both modules and asserts the load-test payload validates
     against the live `PredictionRequest` Pydantic model.
  3. Document in `load_test.py` docstring that the payloads must stay
     in sync with `schemas.py`; cite `service.yaml` as the authoritative
     source of feature names if the service overrides them.
- **Mode**: AUTO (test code; reversible).
- **Acceptance**: contract test passes; running Locust against the
  scaffolded service produces 2xx responses.

---

### R5-L1 — D-32 anti-pattern catalog drift (Low)

- **Area**: documentation / governance.
- **Finding**: the canon now has D-01..D-32, but secondary documentation
  still says D-01..D-30 in some places (notably the README badge and
  some Claude / IDE-parity reference docs). Drift is small but visible.
- **Impact**: contributors quoting "D-30 anti-patterns" while the
  template enforces 32 of them creates confusion in PR review.
- **Action**:
  1. `git grep -nE "D-01\.\.D-30|D-01-D-30|D-30 anti-pattern"` and bump
     each occurrence to the latest count.
  2. Add a `test_anti_pattern_count_consistency.py` invariant that
     reads the canon (`AGENTS.md`) for the highest D-NN tag and
     asserts every other reference cites the same maximum.
  3. README badge regenerated from the canon, not hard-coded.
- **Mode**: AUTO.
- **Acceptance**: contract test green; README badge auto-updates.

---

### R5-L4 — Move scaffold smoke from pre-commit to CI / `make smoke` (NEW, Medium-priority)

- **Area**: developer experience / CI cardinality.
- **Finding**: pre-commit scaffold smoke hook takes >1 minute on every
  commit; `pr-smoke-lane.yml` (S1-1) already covers the same
  invariant per PR. Local + CI is duplicative; the local hook is the
  one bypassed via `--no-verify`.
- **Impact**: contributors get into the habit of `--no-verify`; the
  invariant the hook protected effectively dies even though the line
  remains in `.pre-commit-config.yaml`.
- **Action**:
  1. Identify the pre-commit hook(s) that run scaffold smoke (likely
     a local repo hook — confirm via `.pre-commit-config.yaml`).
  2. Remove that hook from pre-commit.
  3. Add a `make smoke` target (or `scripts/smoke.sh`) so the hook is
     still runnable on demand.
  4. Document the change in `CONTRIBUTING.md` §"Local validation"
     pointing at `make smoke` and `pr-smoke-lane.yml`.
  5. Add a `git push` warning script (optional pre-push hook,
     opt-in via `pre-commit install --hook-type pre-push`) that
     reminds the contributor to run `make smoke` if the diff touches
     `templates/k8s/base/` or `templates/cicd/`.
- **Mode**: AUTO (DX hardening; reversible).
- **Acceptance**: pre-commit total runtime on a no-op commit drops to
  < 10 s; `make smoke` runs scaffold+6 overlays+kubeconform locally;
  `CONTRIBUTING.md` documents the new entry point.

---

## Sprint plan integration

R5 closures are added to the existing **Sprint 3** of R4
(`ACTION_PLAN_R4.md` §7) so we keep one active sprint, not two.
Updated Sprint 3 scope:

| Item | Source | Priority | Mode |
| --- | --- | --- | --- |
| M5 (Alertmanager routing test) | R4 | medium | CONSULT |
| L1 (release-notes follow-ons) | R4 | low | AUTO |
| L2 (dashboards inventory) | R4 | low | AUTO |
| L3 (`infracost` integration) | R4 | low | CONSULT |
| Phase-1 → Phase-2 ADR-019 gate | R4 | high | CONSULT (gated on R5-M1) |
| F1, F2, F3 red-team follow-ups | R4 | medium | AUTO |
| **R5-H1 verified-execution gap (doc)** | R5 | high | AUTO + STOP-delegated |
| **R5-M1 real log fetch in shadow** | R5 | medium | CONSULT (gates Phase-2 decision) |
| **R5-M2 Windows fallback** | R5 | medium | AUTO |
| **R5-M3 NetworkPolicy egress overlays** | R5 | medium | CONSULT |
| **R5-M4 Locust schema sync** | R5 | medium | AUTO |
| **R5-L1 D-32 doc drift sweep** | R5 | low | AUTO |
| **R5-L4 scaffold smoke off pre-commit** | R5 | medium | AUTO |

R5-M1 is **prerequisite** for closing the Phase-1 → Phase-2 ADR-019
gate: without real log content, the precision metric is meaningless.
That dependency is what justifies bumping R5-M1 above the other
mediums.

---

## Acceptance criteria for closing R5

- [ ] R5-H1: `README.md` §"Production-ready scope" wording softened on
      delegated rows; new §"Verification status" mini-matrix exists;
      `VALIDATION_LOG.md` Entry NNN records first delegated runbook
      execution.
- [ ] R5-M1: shadow workflow fetches real upstream logs; `log_artifact_url`
      input is read; PR-base diff replaces last-commit diff. Closes
      red-team F1 inline.
- [ ] R5-M2: `validate_agentic.py` runs to completion on Windows
      `cp1252` console; Windows CI lane green.
- [ ] R5-M3: staging + prod overlays use cloud-specific egress lists;
      contract test rejects `0.0.0.0/0` in non-dev overlays.
- [ ] R5-M4: Locust payload validates against `PredictionRequest`
      Pydantic model; contract test green.
- [ ] R5-L1: README badge says "D-32 anti-patterns enforced";
      consistency invariant green.
- [ ] R5-L4: pre-commit no-op runtime < 10 s; `make smoke` documented;
      `CONTRIBUTING.md` updated.

## Revisit triggers

- An R6 audit identifies further pre-commit / CI cardinality issues.
- ADR-019 Phase 1 → Phase 2 gate review reveals shadow data is still
  biased after R5-M1 lands.
- A user-reported Windows / WSL issue surfaces another encoding break.

## References

- ADR-020 §"Progress log" — the Sprint 2 closure that motivated this
  pass.
- `docs/agentic/red-team-log.md` Entry 4 follow-up F1 — converges with
  R5-M1.
- *Software Engineering at Google* (Winters, Manshreck, Wright) §4.2 on
  pre-commit / pre-submit cadence.
- `docs/RELEASING.md` §"Local validation" — target for R5-L4 doc update.
