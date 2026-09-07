# AUDIT R8 — Staff/Lead Dual-Repo Audit: `template_MLOps` + `agent-local`

- **Date**: 2026-07-01
- **Scope**: full audit of the two repos in the ecosystem —
  `ML-MLOps-Production-Template` (on `main` @ `4cbf89b`, v0.20.0) and
  `agent-local` (on `main` @ `90d672a`, CHANGELOG v0.4.0+unreleased).
- **Level**: staff/lead — architecture, code, structure, testing, CI/CD,
  supply chain, security, observability, documentation/governance,
  agentic surface, adoptability, and competitiveness against reference
  projects.
- **Method**: primary evidence only. Every claim in this report is
  backed by (a) local execution of suites and validators, (b) live
  GitHub Actions state, (c) source code reading with `file:line`
  citations, or (d) **structural queries against a code knowledge
  graph** (tree-sitter + LSP; 9,854 nodes / 18,178 edges for the
  template, 784 / 2,055 for agent-local) — which allows invariants to be
  verified over 100% of call sites, not a sample.
- **Relationship to prior audits**: this succeeds `AUDIT_R7_STAFF_LEAD.md`
  (2026-06-30). The R7 findings were closed (Waves 1–4, ADR-029..036);
  this report audits the state *after* that closure and, for the first
  time, brings `agent-local` in as a full audit subject.

---

## 1. Executive summary

**Overall verdict**: the ecosystem is in the best state of its history
and above the industry standard for repos of its class. The template is
a mature product (9.1/10): CI green across 4 workflows, 661 test
functions, 6 deterministic validators green, zero dead code and zero
risk-level complexity verified by graph, and the most critical serving
invariant (D-24) demonstrated structurally over every call site in the
repo. `agent-local` is a young, well-designed platform (7.9/10) whose
`core/` stands at the same level as the template, but whose **app and
process surface has not yet earned the enforcement discipline its
sibling already has** — and that gap produced the most significant
finding of this round:

> **R8-01 (HIGH)**: `app/main.py` runs the full agent loop
> (multi-second, multi-LLM-call) **synchronously inside an `async def`
> endpoint**, blocking the event loop — exactly the class of defect the
> template catalogs as D-24 ("NEVER `model.predict()` directly in
> async endpoint") and gates with a contract test. The platform that
> generalizes the template's governance philosophy violates its
> flagship serving invariant.

No finding is Critical; none affect CI (both repos are green on
GitHub). The 12 findings share a single cross-cutting pattern, and it
is the thesis of this report: **`agent-local` adopted the template's
philosophy (policy-as-data, telemetry-as-contract, ADRs, fail-closed)
but not yet its *gates* (doc-coherence, secret-scan, serving contract
tests, full-surface lint scope)** — the difference between "designed
correctly" and "impossible to silently degrade" that the template
itself teaches.

### Scorecard

| Dimension | Weight | template_MLOps | agent-local |
| --- | :-: | :-: | :-: |
| Architecture and structure | 1.2 | **9.5** | **9.0** |
| Code quality | 1.2 | **8.5** | **7.0** |
| Testing and verification | 1.2 | **9.0** | **8.0** |
| CI/CD and supply chain | 1.0 | **9.5** | **6.5** |
| Security | 1.0 | **9.0** | **7.5** |
| IaC / K8s (template) · Telemetry/observability (agent-local) | 0.8 | **9.0** | **9.0** |
| Documentation and governance | 1.0 | **9.5** | **8.0** |
| Agentic surface (template) · Evals (agent-local) | 1.0 | **9.5** | **7.0** |
| Adoptability / DX | 0.8 | **8.5** | **8.5** |
| Competitiveness vs. reference projects | 0.8 | **9.0** | **8.5** |
| **Weighted overall** | | **9.1 / 10** | **7.9 / 10** |

Reading the delta (9.1 vs 7.9): this is not a difference in design
talent — agent-local's `core/` scores at the same level as the
template. It is a difference in **enforcement age**: the template has
spent 8 audit rounds converting social discipline into deterministic
gates; agent-local has spent zero. The action plan (§7) closes exactly
that gap.

---

## 2. Methodology and evidence base

| Source | template_MLOps | agent-local |
| --- | --- | --- |
| Local suite | `pytest -q` from root **fails at collection** (R8-05); scoped suites green via CI | 112 tests, **all green** locally |
| Validators | 6/6 green: doc-coherence (6 checks), validate_agentic, manifest `--strict`, sync `--check`, vendored-drift, common_utils-drift | none exist (finding R8-04/R8-06) |
| GitHub Actions (main) | 4/4 workflows green (pr-smoke-lane, CI-Examples 3m46s, Validate-Templates 2m26s, Template-Context 2m33s) | CI green (lint+mypy+tests, matrix py3.11/3.12) |
| Local lint | pre-commit (black/isort/flake8/mypy/bandit/gitleaks) green on latest commit | mypy 17 files clean; flake8 clean under CI config; **black fails on 2 files outside CI scope** |
| Knowledge graph | 9,854 nodes / 18,178 edges; dead-code, complexity, `.predict*` call-site, and clone queries | 784 nodes / 2,055 edges; same queries |
| Code reading | `fastapi_app.predict()` + deployment/Dockerfile/requirements configuration | `controller.py` (491 LOC) in full, `policy.py`, `telemetry.py`, `app/main.py`, `evals/run.py` in full |

**Notable structural verification** (impossible with grep): the query
`MATCH (caller:Function)-[:CALLS]->(callee) WHERE callee.name IN
['predict','predict_proba'] AND NOT caller.file_path CONTAINS '/tests/'`
against the template returns **exactly 10 call sites**, all 10 of them
legitimate by design: `_sync_predict`/`_sync_predict_batch` (run INSIDE
the `ThreadPoolExecutor`), `warm_up_model` (pre-traffic), and
`champion_challenger.compare_models` + `train.run_quality_gates`
(offline). Zero async handlers calling the model directly. This is a
repo-wide proof of D-24, stronger than the existing contract test
(`test_fastapi_template_contract._assert_no_direct_model_predict`),
which covers a single file.

---

## 3. `template_MLOps` — analysis by dimension

### 3.1 Architecture and structure — 9.5

- **Impeccable canonical/generated separation** (ADR-027): `agentic/` is
  the single hand-edited source; `.cursor/ .claude/ .codex/ .devin/` are
  rendered by `sync_agentic_adapters.py`, verified with `--check` in CI.
  17 rules / 20 skills / 16 workflows, each asset with an `authority:`
  anchor resolved by the `--strict` validator.
- **Faithful Copier render** (ADR-030): `templates/service/` mirrors the
  output layout; `{@ @}` delimiters with zero collisions verified across
  249 files; real `copier update` (not destructive re-scaffolding).
- **Footprint composition**: 167 Python / 125 YAML / 35 HCL / 14 Bash —
  the YAML+HCL ratio (≈49% of files) is consistent with a product whose
  identity is governed infrastructure, not a library.
- **Vendoring with a gate**: the 4 files Copier forced to duplicate are
  covered by `check_vendored_runtime_drift.py` (byte-identical or CI
  fails) — the ADR-025 pattern applied consistently. The graph confirms:
  **zero unexpected `SIMILAR_TO` edges** once declared vendored pairs
  are excluded.
- No over-architecture detected: 20 entry points, all CLI scripts with
  `main()`, no indirection layer without a consumer.

### 3.2 Code quality — 8.5

**Strengths (graph-verified, repo-wide scope):**

- **Zero dead code**: three distinct query cuts (templates/service
  without tests; common_utils+src; the whole repo with
  `is_entry_point=false`) all return zero uncalled functions.
- **Zero production functions with cyclomatic complexity ≥ 10**. The
  maximum transitive nested-loop depth in real code is 5
  (`sync_agentic_adapters.render`, `fairness.run_fairness_audit`) —
  both structurally justified (adapter-tree rendering; intersectional
  fairness), not smells.
- `fastapi_app.predict()` ([fastapi_app.py:626-693](../../templates/service/app/fastapi_app.py))
  is exemplary serving code: executor + `partial`, second-wall Pandera
  validation on the single-prediction path (parity with PR-R2-4), 422
  propagated verbatim (never masked as 500), fire-and-forget logging
  that never blocks the response (D-21/D-22), and per-status metrics.
- Textbook dependency pinning: `~=` everywhere, **with the rationale as
  a comment** (`numpy ~= 1.26.0  # numpy 2.x silently corrupts joblib models`).

**Weaknesses:**

- **R8-05 (MEDIUM)** — `pytest -q` from the repo root **breaks at
  collection** with `ModuleNotFoundError: No module named 'tests.conftest'` /
  `'tests.test_alertmanager_routing'`. Confirmed root cause: three
  sibling packages named `tests`, all three with `__init__.py`
  (`templates/service/tests/`, `templates/service/eda/tests/`,
  `templates/service/monitoring/tests/`), collide in `sys.modules`
  under the default `prepend` import mode. CI never sees this because it
  never runs pytest from the root (it uses scoped invocations with
  `--rootdir` and `-p no:locust`), but the root **does** declare
  `[tool.pytest.ini_options]` with `addopts` — this is a supported flow
  that regressed. Fix in §7 (P0-2).
- **R8-08 (LOW)** — when run from the root,
  `templates/tests/unit/test_prediction_logger.py` emits
  `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`: the root
  environment does not have `pytest-asyncio` (CI-Examples installs it
  explicitly). Without the plugin, a marked async test is collected and
  "passes" without executing the coroutine — silent in exactly the way
  this repo abhors.

### 3.3 Testing and verification — 9.0

- **661 test functions** across the repo, organized by intent: contract
  tests (API shape, metrics, alert-routing, K8s vocabulary, Terraform
  parity), policy tests (scaffold D-01..D-35), integration (real
  train→serve→drift e2e), red-team regression
  (`test_red_team_regression.py`), and unit tests.
- The most valuable class of test in the repo is the **contract test
  that codifies an anti-pattern**: `test_d35_local_profile_no_cloud_deps`,
  `_assert_no_direct_model_predict`, `test_predict_error_does_not_leak_exception_message` —
  every AGENTS.md invariant given executable teeth. This is the pattern
  agent-local has not yet vendored (§5).
- 4 CI lanes with healthy time budgets (25s smoke / 2–4 min full lanes)
  — fast feedback without sacrificing coverage.
- Discount (−1.0): the R8-05 regression shows that "the root suite" has
  no guardian of its own — no CI lane runs it as-is, so it can break
  without signal (and it did).

### 3.4 CI/CD and supply chain — 9.5

- **End-to-end pin-by-digest** deploy chain: push → resolve digest →
  Cosign sign+attest (SBOM) → Kyverno verify-by-digest. Immutable tags
  (D-09-adjacent). This is above what most reference ML templates
  publish.
- Idempotent `release-on-tag.yml` with verified extraction (recent fix
  audited in VALIDATION_LOG).
- Deterministic gates as a coherent family: `check_doc_coherence`,
  `check_vendored_runtime_drift`, `check_common_utils_drift`,
  `check_dashboard_inventory`, `check_cicd_template_drift`,
  `check_baselines_expiry` — a single pattern (`check_*.py`,
  fail-closed, seeded green) applied six times. Process architecture,
  not loose scripts.
- pre-commit with gitleaks + bandit + mypy + agentic validators.
- No findings in this dimension. The remaining 0.5 is headroom, not a
  defect.

### 3.5 Security — 9.0

- IRSA/WI instead of static credentials (D-17/D-18); 5 per-purpose
  identities (ADR-017); Pod Security Standards `restricted` with
  labeled namespaces (D-29); per-overlay NetworkPolicy **including the
  batch case whose base selector does not match** (ADR-036 — the kind
  of detail that separates a correct overlay from one that hangs init
  containers).
- Error sanitization with a dedicated test; optional auth with
  passthrough/enforcement tested in both modes.
- `.gitleaks.toml` + `.security-baselines/` (checkov, tfsec) versioned
  with an expiry check — security exceptions expire rather than
  accumulate.

### 3.6 IaC / K8s — 9.0

Verified at the file level (deployment.yaml): init containers for the
model (D-11, line 67), `terminationGracePeriodSeconds: 30` with preStop
and a headroom-vs-uvicorn-timeout comment (D-25, lines 172+196),
`readinessProbe → /ready` gated by warm-up **distinct from**
`livenessProbe → /health` (D-23, lines 256/264 — with a comment
explaining why liveness must not restart a pod during warm-up).
Non-root Dockerfile with `COPY --chown` and HEALTHCHECK. The overlays
(6 env×cloud + batch-only) build cleanly in the green `Validate
Templates` CI lane.

### 3.7 Documentation and governance — 9.5

- **36 active ADRs + 1 tombstone** (ADR-012, correct ID-immutability
  practice), all consistently formatted with alternatives and revisit
  triggers.
- Rule 16 + `check_doc_coherence.py` (6 checks) makes "shipped" and
  "documented" the same thing for version, counts, ADR index, llms.txt,
  and release notes — and it is **green today**.
- 26 release notes in `releases/`; disciplined Keep-a-Changelog
  [Unreleased] entries; VALIDATION_LOG as execution evidence. 9 prior
  audit/plan documents in `docs/audit/` — the repo has real
  institutional memory.

### 3.8 Agentic surface — 9.5

- 17/20/16 with a strict `authority:` manifest; AUTO/CONSULT/STOP with
  dynamic escalation (ADR-010, escalation-only); 35 anti-patterns with
  corrective actions and a `rule-audit` skill that verifies them with
  file:line evidence. The newly canonized `ADR-037` (dual retrieval
  namespace separation) maintains the standard: falsifiable controls,
  not promises.
- This is the product's competitive differentiator, and it is better
  governed than the rest of the repo — which is already well governed.

### 3.9 Adoptability / DX — 8.5

- Real `copier copy` + `copier update`; `local/staging/prod` profiles
  mapped to AUTO/CONSULT/STOP with D-35 tested; CCDS mapping; additive
  `uv`; batch-only overlay as an on-ramp; `new-service.sh` as a
  transitional wrapper with deprecation notice. All 6 levers from the
  adaptability audit are closed and verifiable.
- Discount: the first-time experience of a contributor TO THE REPO (not
  to the generated service) today includes a broken root `pytest`
  (R8-05) and a confusing async warning (R8-08) — internal onboarding
  friction, not adopter-facing.

### 3.10 Competitiveness — 9.0

| Reference | What it offers | What this template has that it doesn't |
| --- | --- | --- |
| Cookiecutter Data Science | recognizable layout | agentic governance, full CI/CD, signed supply chain, K8s/TF, quality gates |
| ZenML | stack profiles, orchestration | profiles without a heavy framework; fairness/leakage gates; Copier update; deterministic enforcement |
| Made With ML | pedagogy of the *why* | an executable product + a private, personal pedagogical companion (not part of this public repo) kept as a separate plane |
| Kedro | opinionated pipelines | hardened K8s serving (D-01..D-35), multi-cloud parity, governed promotion |
| BentoML | serving DX (batching) | evaluated against an invariants contract beforehand (ADR-032, Phase 0) — the correct relationship with a frontier tool |

No reference project combines updatable scaffolding + executable
agentic governance + attested supply chain. The niche is real and is
backed by evidence (README frontier comparison). The remaining
competitiveness gap is not one of features but of **social proof**
(external adopters, third-party issues) — outside the scope of code.

---

## 4. `agent-local` — analysis by dimension

### 4.1 Architecture and structure — 9.0

- **The repo's most telling ratio**: `core/` = 1,773 LOC across 11
  modules, no file > 500 LOC, and a new use case = ~130 LOC in a thin
  folder (`usecases/tienda/tools.py` 121 + YAMLs). The promise of
  ADR-001 ("new domain = folder, never fork") is measurable and holds.
- `ExecutiveController` ([controller.py:100-195](file:///home/duqueom/projects/agent-local/core/controller.py))
  with admit/execute/release is a genuinely thin facade: routing +
  budget in admit; an adaptive loop with a **deadline checked before
  each optional station** and a latency budget propagated as a
  per-call timeout (`call_tier`, lines 239-255); policy gate + telemetry
  in release. The circuit breaker degrades by `effective_tier`, and the
  "everything open" case degrades to a safe template instead of a 500.
  The graphs confirm this: cohesion clusters of 0.63-1.0, hotspots
  exactly where they should be (`check_policy` fan-in 17,
  `ToolRegistry.run` 16).
- ADR-007 structured parser with a **legacy fallback explicitly
  designed to be unable to regress** (`_parse_structured_calls` returns
  `None` ≠ `[]` to distinguish "not this format" from "zero tools") —
  a sign of contract-design maturity.

### 4.2 Code quality — 7.0

**Strengths**: mypy clean across 17 files; `_coerce` with a
quoted-string-never-numeric guard (the phone number `"+5215551234"`
does not become a float — documented with the example); `_split_args`
respects nesting and quoting; zero dead code and zero complexity ≥ 10
by graph (the `transitive_loop_depth` values of 3-5 are all tests or
`dev_message`).

**Findings** (full detail in §6):

- **R8-01 (HIGH)** — [app/main.py:78-108](file:///home/duqueom/projects/agent-local/app/main.py):
  `async def dev_message(...)` runs `AGENT.handle(...)` — a synchronous
  chain of N HTTP calls to llama-server (plan→tools→reflect→generate→
  critic, wall-clock seconds) — **directly on the event loop**. Every
  concurrent request (including `/health`) is blocked while one request
  is in flight. This is the template's D-24 class, in the repo that
  generalizes its governance. With a single dev user it doesn't hurt;
  as a platform ("teams can adopt across domains" — README) it is the
  first bug an adopter with 2 concurrent users will hit. Trivial fix
  (§7 P0-1): drop `async` (FastAPI runs `def` endpoints in a
  threadpool) or use `run_in_executor`. And — a lesson from the
  template — **pair it with a contract test** that prevents
  reintroduction.
- **R8-02 (MEDIUM)** — [app/main.py:108](file:///home/duqueom/projects/agent-local/app/main.py):
  `raise HTTPException(status_code=500, detail=str(e))` leaks the
  internal exception message to the client. The template has a
  dedicated test against exactly this
  (`test_predict_error_does_not_leak_exception_message`).
- **R8-03 (MEDIUM)** — [core/controller.py:353-366](file:///home/duqueom/projects/agent-local/core/controller.py):
  `reflect()` calls the tier (`max_tokens=128`), **discards the return
  value**, and only increments `reflections_made`. The reflection does
  not feed into `generate()` (which only reads `observations`) and is
  not recorded in telemetry. Today the station is a pure cost in
  tokens+latency on every medium/high-risk request, with no effect on
  the response. It should either be wired in (append as a synthetic
  observation / generator context) or removed — the current state is
  the worst of both worlds.
- **R8-04 (MEDIUM)** — triple version drift: `pyproject.toml:7` says
  `0.2.0`, [app/main.py:34](file:///home/duqueom/projects/agent-local/app/main.py)
  and `:62` hardcode `"0.2.0"`, while CHANGELOG and commits are at
  **v0.4.0**. This is exactly the class of drift that motivated the
  template's rule-16 gate (whose R7 audit found `llms.txt` frozen at an
  earlier era). agent-local has no gate to catch it.
- **R8-09 (LOW)** — [app/main.py:111-122](file:///home/duqueom/projects/agent-local/app/main.py):
  the webhook stub documents "returns 501" but responds with **200**
  and body `not_implemented` — a real WhatsApp client would interpret
  this as successful delivery. It should be
  `JSONResponse(status_code=501, ...)`.
- **R8-11 (INFO)** — Spanish docstrings in `app/` and `evals/` versus
  English in `core/` — a convention inconsistency (the template is
  English-first).
- **R8-10 (INFO)** — `Verdict.escalate_to_tier=3`
  ([policy.py:106](file:///home/duqueom/projects/agent-local/core/policy.py))
  is not consumed by anything: `release()` goes straight to
  safe_fallback. A dead contract field — either document it as reserved
  or wire it in.

### 4.3 Testing and verification — 8.0

- 94 functions / 112 tests collected, **100% green**, well targeted:
  breaker (half-open, open-skips-tiers), controller (degradation by
  downed tier, latency budget, structured parsing with
  fence/unknown-tool/fallback-legacy), policy (stock-claim requires a
  live lookup), verifier (judge on a higher tier, low-risk skip).
- What's missing is what the template has already learned to require:
  (a) an **event-loop-non-blocking contract test** (would have caught
  R8-01); (b) a coverage gate (the template declares ≥90/80); (c) a
  test pinning a single version (would have caught R8-04).

### 4.4 CI/CD — 6.5

- What exists is well reasoned: 3.11/3.12 matrix, lint+mypy+tests, and
  the header comment in `ci.yml` documents WHY models don't run on
  runners (ADR-002: self-hosted on a personal machine against a public
  repo = a known attack vector). That is a correct, citable security
  decision, not a gap.
- **R8-06 (LOW)** — the lint scope is `core app usecases tests`,
  leaving out `conftest.py` (root) and `evals/` — and today **both fail
  black**. The evals harness is a governance artifact (it produces the
  evidence for gates F0.3); its living outside lint scope is a leak
  through which drift has already entered.
- **R8-12 (LOW)** — no secret-scanning (gitleaks) or bandit in CI or
  pre-commit, in a repo whose `docker-compose` and `.env` touch model
  paths and (Phase 2) WhatsApp tokens. The current `.env.example` is
  clean; the gate is for the day it stops being clean.
- No release automation (no visible git tags despite CHANGELOG
  versions) — acceptable pre-1.0, but half of the R8-04 drift
  originates here.

### 4.5 Security — 7.5

- **Strong where it matters to the design**: read-only/dry-run
  fail-closed tools (ADR-006), a deterministic policy gate that no
  response can bypass, parsing with `ast.literal_eval` (never eval),
  telemetry without client payloads by schema. `.env.example` with
  correct hygiene.
- Weak at the edges: R8-02 (exception detail leak), R8-12 (no
  scanners), and `uvicorn.run(..., reload=True)` in the
  production-default `__main__` (reload is dev-only; minor since the
  README mandates docker-compose).

### 4.6 Telemetry / observability — 9.0

[telemetry.py](file:///home/duqueom/projects/agent-local/core/telemetry.py)
is the best file in the repo: a Pydantic contract validated before
writing, **PII redaction at write time, never after**, conservative
patterns with `_SAFE_KEYS` so trace_ids/timestamps are never corrupted
(with the rationale documented — ADR-005), OTel-aligned naming so
adopting OTel is a transport change only. `TelemetryEntry` captures
route, final tier, escalation with reason, tool failures, policy AND
critic verdicts, per-station latencies, per-tier tokens, exhausted
budget, and provenance with quarantine. Few commercial agent products
emit this much.

### 4.7 Documentation and governance — 8.0

- 8 ADRs of uniform quality (the most recent, ADR-008, with specific
  revisit triggers); Keep-a-Changelog CHANGELOG with the correct
  pre-1.0 note; README with a lineage narrative that positions the repo
  without overselling ("Phase 1", "gated") — the kind of status honesty
  the template's prior audits had to force, and which was native here
  from the start.
- Discounts: R8-04 (version drift with no gate) and the absence of a
  VALIDATION_LOG-style evidence index (eval reports exist in
  `evals/reports/` but nothing indexes or requires them).

### 4.8 Evals — 7.0

- A real harness exists, with cases versioned per use case
  (`usecases/tienda/evals/sets/`), timestamped JSON reports, and an F0.3
  gate historically at 20/20 — this is already more than most agent
  repos have.
- **R8-07 (LOW)** — [evals/run.py](file:///home/duqueom/projects/agent-local/evals/run.py):
  the gate is **hardcoded as an absolute `correct_intent >= 18`**
  (line 136) — with a 40-case set, 45% accuracy would "pass the gate";
  it should be a ratio (`>= 0.90`). Also `datetime.utcnow()` (deprecated
  in 3.12, naive) at lines 54/153, an off-by-one p95
  (`int(n*0.95)` with no clamp, line 119), and it's one of the 2 files
  that fail black (R8-06). The harness that produces the evidence for
  the gates deserves the same rigor as the gates.

### 4.9 Adoptability — 8.5

Fully config-as-data (budgets, versioned policy, per-use-case prompts),
`.env.example` + docker-compose with the official llama.cpp image, a
one-command quickstart. The real adoption barrier is inherent to the
domain (hardware for GGUF), not the repo.

### 4.10 Competitiveness — 8.5

| Reference | Its strength | What agent-local has that it doesn't |
| --- | --- | --- |
| LangGraph | state graphs, ecosystem | **deterministic** post-generation policy gate (not another LLM), per-station latency budget, per-tier breaker, contract telemetry with PII redaction — in 1.7k auditable LOC |
| CrewAI | fast multi-agent assembly | governed single-agent discipline: evals with a gate written BEFORE autonomy, objective escalation |
| Google ADK | full-stack managed, integrated evaluation | 100% local/air-gapped, zero vendor, zero marginal cost, and the same pattern (policy outside the model) with no platform |
| smolagents | minimalism | comparable in size but with a circuit breaker, budgets, cross-tier verification, and a policy gate that smolagents doesn't have |

The niche — "local multi-tier agent with deterministic governance and
contract telemetry" — is not occupied by any mainstream framework.
Google Cloud's data-agents guide (2026) validates the vocabulary
(context→reasoning→orchestration, pre-production evaluation, AgentOps)
without invalidating any local design decision. The competitive risk is
one of *visibility*, not design; the one reasonable emerging technical
gap is MCP interoperability (the de facto standard connector in 2026) —
an ADR candidate, not an urgent need.

---

## 5. Cross-repo comparative analysis: the governance-parity matrix

The ecosystem's thesis is "the same governance philosophy generalizes
to a new domain." This matrix measures how much of the philosophy
traveled **with enforcement** and how much traveled only as culture:

| Discipline | template_MLOps | agent-local | Gap |
| --- | :-: | :-: | --- |
| ADRs with format + revisit triggers | ✅ 36 | ✅ 8 | — |
| Keep-a-Changelog CHANGELOG | ✅ | ✅ | — |
| Versioned policy-as-data | ✅ (quality_gates.yaml) | ✅ (policy.yaml + decision_id) | — |
| Telemetry with PII redaction | ✅ (memory_redaction) | ✅ (write-time) | — |
| Fail-closed by default | ✅ | ✅ (tools, gate) | — |
| **Documentation-coherence gate** | ✅ rule 16 + 6 CI checks | ❌ | R8-04 live (version 0.2.0 vs 0.4.0) |
| **Secret scanning** | ✅ gitleaks + baselines with expiry | ❌ | R8-12 |
| **Serving contract test (event loop)** | ✅ D-24 + test | ❌ | R8-01 live |
| **Tested error sanitization** | ✅ dedicated test | ❌ | R8-02 live |
| **Full-surface lint** | ✅ repo-wide pre-commit | ❌ scoped | R8-06 live (2 files with drift) |
| Coverage gate | ✅ ≥90/80 | ❌ | — |
| Release notes + tags | ✅ 26 notes + signed tags | ❌ | half of R8-04 |

**Comparative conclusion**: every ❌ in the agent-local column has a
live R8 finding tied to its row. This is not coincidence — it is the
empirical demonstration of the template's own thesis: *disciplines
without a gate drift, always, even with the same author and the same
intent*. The action plan (§7) is, in essence, "vendor the missing
gates."

---

## 6. Findings register

| ID | Sev. | Repo | Evidence | Summary |
| --- | --- | --- | --- | --- |
| R8-01 | **HIGH** | agent-local | `app/main.py:78-108` | Synchronous multi-LLM loop inside `async def` — blocks the event loop (D-24 class) |
| R8-02 | MEDIUM | agent-local | `app/main.py:108` | `HTTPException(detail=str(e))` leaks internals to the client |
| R8-03 | MEDIUM | agent-local | `core/controller.py:353-366` | `reflect()` discards the tier's output — cost with no effect |
| R8-04 | MEDIUM | agent-local | `pyproject.toml:7`, `app/main.py:34,62` vs CHANGELOG | Version 0.2.0 in 3 places; CHANGELOG at v0.4.0; no gate |
| R8-05 | MEDIUM | template | 3× sibling `tests/__init__.py` | Root `pytest -q` breaks at collection; scoped CI doesn't cover it |
| R8-06 | LOW | agent-local | `ci.yml` lint scope vs `black --check .` | `conftest.py` + `evals/run.py` outside lint scope; both fail black today |
| R8-07 | LOW | agent-local | `evals/run.py:118-137,54,153` | Absolute 18/20 gate (not a ratio), deprecated `utcnow()`, off-by-one p95 |
| R8-08 | LOW | template | `templates/tests/unit/test_prediction_logger.py` at root | Without local `pytest-asyncio`, async tests "pass" without executing |
| R8-09 | LOW | agent-local | `app/main.py:111-122` | Webhook stub responds 200; docstring promises 501 |
| R8-10 | INFO | agent-local | `core/policy.py:106` | `escalate_to_tier` emitted and never consumed |
| R8-11 | INFO | agent-local | `app/`, `evals/` | Mixed ES/EN docstrings (core is EN) |
| R8-12 | LOW | agent-local | `.github/workflows/ci.yml` | No gitleaks/bandit in CI or pre-commit |

Zero Critical. Zero findings currently break CI. R8-01 is the only one
that would affect an adopter at runtime.

---

## 7. Prioritized action plan

### P0 — fix observable defects (≤ 1 session)

1. **[agent-local] R8-01 + R8-02 + contract test** — in `app/main.py`:
   convert `dev_message` to `def` (FastAPI threadpool) or wrap
   `AGENT.handle` in `run_in_executor`; replace `detail=str(e)` with a
   generic message + internal log with trace_id. Add
   `tests/test_app_serving_contract.py` with: (a) an assertion that no
   `async def` endpoint calls `Agent.handle` directly (AST inspection,
   the template's pattern), (b) an assertion that an internal error
   never appears in the body.
2. **[template] R8-05 + R8-08** — in the root `pyproject.toml` add
   `--import-mode=importlib` to `addopts` (the 3 `tests` packages
   coexist fine under importlib) and `pytest-asyncio` to the root dev
   extra with `asyncio_mode = "auto"`. Validate that the full root
   `pytest -q` is green and add a lightweight CI job (or extend
   pr-smoke-lane) that runs **collection** from the root
   (`pytest --collect-only -q`) so the root suite has a guardian.
3. **[agent-local] R8-09** — webhook stub → `JSONResponse(status_code=501)`.

### P1 — close the enforcement gap (the ❌ row in §5)

1. **[agent-local] R8-04** — a single source of version truth: read
   `importlib.metadata.version("agent-local")` in `app/main.py`; bump
   pyproject to the real CHANGELOG version; add a minimal
   `scripts/check_coherence.py` (pyproject version ==
   latest CHANGELOG heading == ADR count in README) as a CI job — the
   template's rule-16 ported to agent-local's scale (30 lines, not the
   full system).
2. **[agent-local] R8-06** — CI lint over the full surface:
   `black --check .` / `isort --check-only .` / `flake8 .` (with
   explicit excludes if needed) + apply pending formatting to
   `conftest.py` and `evals/run.py` in the same PR.
3. **[agent-local] R8-12** — gitleaks in CI (official action, 1 job) +
   a pre-commit config mirroring the template's, trimmed down
   (black/isort/flake8/mypy/gitleaks).
4. **[agent-local] R8-03** — a design decision via mini-ADR: (a) wire
   the reflection in (its output enters as a synthetic observation
   `Observation(tool="reflection", ...)` that `generate()` would
   already consume), or (b) remove the station and its budget.
   Recommendation: (a) — this is what plan §F2 promises — with a test
   asserting the reflection appears in the generator's context.

### P2 — hardening and minor debt

1. **[agent-local] R8-07** — ratio-based evals gate (`accuracy_intent >=
   0.90`), `datetime.now(timezone.utc)`, clamped p95
   (`min(idx, n-1)` or `statistics.quantiles`), black formatting (falls
   out of P1-5).
2. **[agent-local] R8-10/R8-11** — document `escalate_to_tier` as
   reserved (or consume it in `release()` by regenerating at tier 3
   before the fallback); unify docstrings to English in `app/` and
   `evals/`.
3. **[agent-local] tags + releases** — once P1-4 closes, tag the
    corrected version and adopt the template's `releases/` pattern (one
    note per version) — cheap now, expensive to reconstruct later.
4. **[ecosystem] MCP interop ADR** — evaluate exposing `ToolRegistry`
    as an MCP server / consuming MCP tools (validated as a de facto
    industry standard in 2026). Proposed-first, ADR-032 pattern: an
    invariants contract before code.

### Explicitly NOT recommended

- **Do not** port the template's full doc-coherence system into
  agent-local (6 checks, cascade map) — at 1.7k LOC, the minimal check
  in P1-4 satisfies the calibration principle; the full system would be
  over-engineering today.
- **Do not** add a coverage gate to agent-local yet — with 112 tests
  over 2k LOC, real coverage is already high; a number-gate with no
  history of regressions is ceremony. Revisit at the first bug a test
  would have caught.
- **Do not** run models in agent-local's CI — the ADR-002 stance is
  correct; model-quality evidence remains local and versioned in
  `evals/reports/`.

---

## 8. Closing

The template reaches R8 with no new architecture, security, or supply
chain findings — the 8 audit rounds have converged: what remains are
two local-DX rough edges (R8-05/R8-08) in a flow CI was not watching.
`agent-local` demonstrates that the philosophy generalizes (its core
scores at the template's level) and simultaneously demonstrates the
template's central theorem: **culture without gates drifts** — every
discipline that traveled without its enforcement now has a live finding
with a file:line. The P0/P1 plan converts that demonstration into
parity; executed, agent-local's projected score is ≈ 8.8 without
changing a single line of its design.

*Audit R8 conducted with primary evidence: suites and validators
executed locally, live GitHub Actions state, source code reading, and
structural verification via the code knowledge graph (tree-sitter +
LSP) over 100% of call sites for graph-checkable invariants.*

---

## Addendum — Remediation status (2026-07-01, same day)

All 12 findings were remediated the same day as the audit. Canonical
record: this repo's `CHANGELOG.md` [Unreleased] and agent-local's
`CHANGELOG.md` v0.6.0 (+ its `releases/v0.6.0.md`).

| ID | Status | How |
| --- | --- | --- |
| R8-01 | ✅ Fixed | `dev_message` → `def` (threadpool) + AST contract test (`tests/test_app_serving_contract.py`) |
| R8-02 | ✅ Fixed | Generic 500 with a correlation `error_id` + regression test |
| R8-03 | ✅ Fixed | `reflection_notes` channel → `generate()` (**ADR-009**) + 2 tests (incl. no-evidence-for-verifier) |
| R8-04 | ✅ Fixed | SSoT `core.__version__` (0.6.0), pyproject `dynamic`, surface imports it; **the new gate caught a 5th copy** in `app/__init__.py` on its first run |
| R8-05 | ✅ Fixed | `--import-mode=importlib` in root addopts **and in the service pyproject** (invokes with paths under `templates/service/` resolve rootdir there, and that pyproject travels with the scaffolded service — a second layer exposed by CI's first run) + `--collect-only` guard in CI. **Bonus**: the collision was masking a dead module — `test_alertmanager_routing.py` with pre-Stage-2a paths (`templates/templates/…`); revived (file-relative paths + `X_OK` guard for amtool), 14/14 green, and now run by the template-context lane |
| R8-06 | ✅ Fixed | CI lint extended to full surface (`conftest.py`, `evals/`, `scripts/`); black drift applied |
| R8-07 | ✅ Fixed | Ratio-based gate (≥0.90) + exit code, tz-aware, clamped p95, English |
| R8-08 | ✅ Fixed | Root `asyncio_mode="auto"` + plugin in lane. Root suite: **963 passed, 0 failed** |
| R8-09 | ✅ Fixed | Webhook stub → `JSONResponse(501)` + test |
| R8-10 | ✅ Documented | `escalate_to_tier` marked reserved in `policy.py` (Phase-2 decision) |
| R8-11 | ✅ Fixed | `app/` + `evals/` rewritten in English |
| R8-12 | ✅ Fixed | gitleaks job (full-history) in CI + mirrored `.pre-commit-config.yaml` |

Post-remediation result: agent-local **119 tests** (112→119), coherence
gate 4/4, lint/mypy clean, release **v0.6.0** tagged; template root
suite **963 passed**, 6 validators green. The parity matrix in §5 now
has no actionable ❌ (agent-local's coverage-gate and releases/: the
former remains deliberately out of scope by calibration; the latter is
now adopted via `releases/v0.6.0.md`). agent-local's projected score
after this remediation: **≈ 8.8** (to be confirmed in R9).
