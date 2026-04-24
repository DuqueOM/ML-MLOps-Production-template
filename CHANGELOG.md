# Changelog

All notable changes to the ML-MLOps Production Template are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

---

## [1.9.0] - 2026-04-24

### Added

- **Batch inference skill** — `.windsurf/skills/batch-inference/SKILL.md`
  scaffolds CronJob-based scoring that reuses the exact same
  `predictor.predict_batch()` function and Pandera schema as the live
  API; includes PSS restricted container, `concurrencyPolicy: Forbid`,
  and `activeDeadlineSeconds` hard cap
- **ADR-013 — GitOps strategy** — codifies the current
  `kubectl apply` posture and the four revisit triggers for
  migrating to ArgoCD
- **DORA metrics exporter** — `templates/scripts/dora_metrics.py`
  aggregates deployment_frequency, lead_time_for_changes,
  change_failure_rate, and mttr from the GitHub REST API +
  `ops/audit.jsonl`. Writes `ops/dora/{YYYY-MM}-metrics.json`.
  Graceful degradation without `GITHUB_TOKEN`. 9 unit tests
- **Devcontainer** — `.devcontainer/devcontainer.json` +
  `post-create.sh` give contributors a reproducible environment
  matching the CI runner (Python 3.11 bookworm + docker-in-docker +
  kubectl/helm + terraform + cosign + conftest + syft + gitleaks)
- **Secret rotation runbook** — `docs/runbooks/secret-rotation.md`
  covers SCHEDULED rotation (complement to `secret-breach-response`
  which handles emergencies): per-credential cadence table, STOP per
  env, 7-day soak on OLD version, quarterly calendar

### Scope note

v1.9.0 was planned as a 10-item roadmap. Delivered the 5 highest-
impact items; deferred D2 (GPU), D5 (more reusable GHA), D6
(Terraform tests), D8 (template repo publish) to future releases.

### Total test count

- Unit tests: **127 passing** (was 118 in v1.8.1)

---

## [1.8.1] - 2026-04-24

### Added

- **Pod Security Standards** (D-29) — `templates/k8s/policies/pod-security-standards.yaml`
  with Namespace definitions per environment; base `deployment.yaml`
  now ships pod + container `securityContext` compatible with PSS
  `restricted` (`runAsNonRoot`, `capabilities.drop: [ALL]`,
  `seccompProfile: RuntimeDefault`). Rule 02 §Pod Security Standards
- **SBOM attestation** (D-30) — `deploy-gcp.yml` + `deploy-aws.yml`
  generate a CycloneDX SBOM via Syft and attach it as a Cosign
  attestation. Full SLSA L3 provenance via `slsa-github-generator`
  documented as ROADMAP template block
- **ThreadPoolExecutor sizing** — `docs/threadpool-sizing.md` operator
  guide + `templates/service/scripts/benchmark_executor.py` executable
  sweep script (writes `ops/benchmarks/{ts}-executor.json`)
- **Input quality** — `common_utils/input_quality.py` opt-in checker
  against training-time `[p01, p99]` quantiles. Emits
  `{service}_input_out_of_range_total` labels without blocking the
  request. 14 unit tests
- **Closed-loop Grafana dashboard** —
  `templates/monitoring/grafana/dashboard-closed-loop.json` (10 panels:
  SLO availability + burn, per-version AUC, sliced-AUC heatmap, C/C
  error rate, score-distribution p50, logger errors, input-quality
  flags, monitor heartbeat, PSI top 10)
- **Intersectional fairness** — `fairness.py::compute_intersectional_fairness()`
  evaluates all 2-way combinations of protected attributes. New
  parameters on `run_fairness_audit(intersectional=False,
  min_intersectional_samples=30)`. 4 unit tests
- **Anti-patterns D-29, D-30** in AGENTS.md

### Changed

- `templates/k8s/base/deployment.yaml` — pod/container securityContext;
  init container resource requests/limits
- `templates/cicd/deploy-gcp.yml` + `deploy-aws.yml` — SBOM generation
  and attestation steps
- `templates/service/src/{service}/fairness.py` —
  `run_fairness_audit(intersectional=..., min_intersectional_samples=...)`
  parameters; `_summary.intersectional_evaluated` flag; `_intersectional`
  report block
- `.windsurf/rules/02-kubernetes.md` — new Pod Security Standards section

### Total test count

- Unit tests: **118 passing** (was 100 in v1.8.0)

---

## [1.8.0] - 2026-04-24

### Added

- **AuditLog** — thread-safe append-only JSONL writer in
  `common_utils/agent_context.py` for `ops/audit.jsonl`. Integrates with
  `RiskContext` via `record_operation()` to automatically persist the
  five ADR-010 signals plus `base_mode` whenever dynamic escalation
  changed the operation's mode
- **AuditEntry hardening** — now validates `result ∈ {success, failure,
  halted}` and requires an `approver` for CONSULT/STOP success entries
  (human-accountability invariant)
- **Skill `rule-audit`** — READ-ONLY automated compliance scanner
  against AGENTS.md anti-patterns D-01..D-28. Per-invariant query,
  evidence-backed findings, `--subset` scoping, AuditLog integration
- **Skill `performance-degradation-rca`** — multi-stream RCA
  correlating sliced metrics, drift, deploys, upstream data, and
  logger health. Produces R1..R5 root-cause classification and
  `docs/incidents/{date}-{service}.md` blameless RCA template
- **Rule 14 `14-api-contracts.md`** — API contract versioning policy:
  committed `openapi.snapshot.json`, semver table for schema evolution,
  CI guard enforcing version bump alongside snapshot changes
- **`templates/service/tests/contract/`** — scaffolded contract-test
  layout: `test_openapi_snapshot.py` (3 tests) + `openapi.snapshot.json`
  (regenerated via `scripts/refresh_contract.py`)
- **`templates/service/scripts/refresh_contract.py`** — operator
  regeneration script (executable)
- **Anti-pattern D-28** in AGENTS.md — breaking API change without
  version bump + snapshot update
- **25 unit tests** in `test_agent_context.py` covering every typed
  handoff + AuditLog semantics

### Changed

- `common_utils/agent_context.py`: `AuditEntry` gains `risk_signals:
  list[str]` and `base_mode: AgentMode | None` fields (omitted from
  JSONL when None)

### Total test count

- Unit tests: **100 passing** (was 75 in v1.7.1)

---

## [1.7.1] - 2026-04-24

### Added

- **Model warm-up** (`warm_up_model` in `fastapi_app.py`) forces a dummy
  predict and builds the SHAP `KernelExplainer` once during lifespan,
  before `_warmed_up=True`. Cached on app state (D-24)
- **Probe split** — `livenessProbe: /health` (always 200 while alive),
  `readinessProbe: /ready` (503 until warmed), `startupProbe: /health`
  with `failureThreshold: 24` to absorb cold start (D-23)
- **Graceful shutdown** — `terminationGracePeriodSeconds: 30` coordinated
  with uvicorn `--timeout-graceful-shutdown=20` (D-25)
- **PodDisruptionBudget** (`k8s/base/pdb.yaml`) with `minAvailable: 1`
  and HPA `minReplicas: 2` (D-27)
- **Champion/Challenger Argo Rollouts** — two AnalysisTemplates:
  `{service}-cc-online` (4 proxy metrics during canary, auto-rollback)
  and `{service}-cc-post-deploy` (3 business metrics from performance_monitor,
  human-gated rollback). Closes G-02b
- **Rollback skill + /rollback workflow** — STOP-class emergency revert
  procedure: Argo Rollouts abort+undo, MLflow registry revert, alert
  silencing, audit issue. Closes G-05
- **Environment promotion chain** — dev→staging→prod with GitHub
  Environment Protection Rules. Reusable `deploy-common.yml` workflow;
  `deploy-gcp.yml` and `deploy-aws.yml` rewritten as 4-job chains.
  `docs/environment-promotion.md` operator setup guide (ADR-011, D-26)
- **Dynamic Behavior Protocol** — `common_utils/risk_context.py` with
  19 unit tests. Reads `mcp-prometheus` for 5 live signals
  (incident_active, drift_severe, error_budget_exhausted, off_hours,
  recent_rollback); escalates AUTO→CONSULT or CONSULT→STOP per
  ADR-010. Fallback to `ops/*.json` files keeps template usable
  without the MCP
- **mcp-prometheus promoted to CORE MCP** in AGENTS.md §MCP Integrations
- **ADR-010** — Dynamic Behavior Protocol via mcp-prometheus
- **ADR-011** — Environment Promotion Gates (dev→staging→prod)
- **Anti-patterns D-23..D-27** added to AGENTS.md table with corrective
  actions

### Changed

- `templates/tests/infra/policies/kubernetes.rego` converted from Rego
  v0 (legacy `deny[msg] { }`) to Rego v1 (`deny contains msg if { }`).
  Pre-existing technical debt — current versions of conftest reject the
  old syntax. Content preserved; only syntax updated.
- `.windsurf/rules/01-mlops-conventions.md` — invariants list grows to
  6 (adds warm-up/probe-split); new Dynamic Behavior Protocol section
- `.windsurf/rules/02-kubernetes.md` — new sections for probe split,
  graceful shutdown, PodDisruptionBudget
- `.windsurf/rules/05-github-actions.md` — Environment Promotion Gates
  (D-26) and Reusable Workflows sections
- HPA `minReplicas: 1 → 2` (required for PDB `minAvailable: 1` to be
  non-trivially effective)
- Rollout's canary `analysis.templates` references the new
  `{service}-cc-online` template in dedicated file (previously inline)

### Fixed

- `templates/tests/infra/policies/kubernetes.rego` now parses with
  current conftest/OPA (Rego v1 strict mode)
- Argo Rollout canary no longer serves traffic to pods that have passed
  `/health` but have not finished warming their SHAP explainer

### Total test count

- Unit tests: **75 passing** (was 56 in v1.7.0)

---

## [1.7.0] - 2026-04-23

### Added

#### Closed-Loop Monitoring — Ground Truth + Sliced Performance + Champion/Challenger

Closes the largest remaining gap in the template: concept drift went silent
because the system only tracked feature distributions (PSI). This release
wires predictions to their eventual ground-truth labels, computes sliced
performance metrics, and gates promotion on statistical superiority.

See **ADR-006** (closed-loop monitoring), **ADR-007** (sliced analysis),
**ADR-008** (champion/challenger), and **ADR-009** (retraining orchestration
triggers) for the full rationale.

**Prediction logger (ADR-006):**
- `templates/common_utils/prediction_logger.py` — async buffered logger with
  4 pluggable backends (parquet, BigQuery, SQLite, stdout) via
  `PREDICTION_LOG_BACKEND` env var
- `PredictionEvent` frozen dataclass validates `prediction_id`,
  `entity_id`, and `model_version` at construction (invariant D-20)
- Fire-and-forget semantics: handler never blocks on log I/O (D-21)
- Failure-tolerant: flush errors swallowed + counted via
  `prediction_log_errors_total` (D-22)
- Integrated into `fastapi_app.py` and `main.py` lifespan; gracefully
  degrades if backend fails to start

**Ground truth ingestion (ADR-006):**
- `templates/service/src/{service}/monitoring/ground_truth.py` — daily
  CronJob with user-implemented `fetch_labels_from_source()` contract
- Ships CSV stub for local dev + documented examples for BigQuery, Postgres
- Writes idempotent daily parquet partitions (`year=/month=/day=`)
- `configs/ground_truth_source.yaml` — declarative source config

**Sliced performance monitor (ADR-007):**
- `templates/service/src/{service}/monitoring/performance_monitor.py` —
  JOINs predictions with labels on `entity_id` with causality constraint
  (`label_ts >= prediction_ts`), computes AUC/F1/precision/recall/Brier
  globally AND per slice
- Baseline comparison for concept drift (`auc_drop_warning/alert`)
- Tri-state status: `ok` / `warning` / `alert` / `insufficient_data`
- Prometheus Pushgateway metrics with labels
  `{slice_name, slice_value, metric}` for Grafana filtering
- `configs/slices.yaml` — bounded-cardinality slice declarations
  (country, channel, model_version, score_bucket examples)

**K8s manifests:**
- `k8s/base/cronjob-performance.yaml` — two CronJobs:
  - `{service}-ground-truth-ingester` at 03:00 UTC
  - `{service}-performance-monitor` at 04:00 UTC
- `k8s/base/performance-prometheusrule.yaml` — 5 alerts:
  - `GlobalAUCBelowAlert` (concept drift)
  - `SlicedAUCBelowAlert` (subpopulation degradation)
  - `F1BelowAlert` (threshold calibration)
  - `PerformanceMonitorStale` (heartbeat)
  - `PredictionLogErrorsHigh` (D-22 degradation visibility)

**Champion/Challenger statistical gate (ADR-008):**
- `templates/service/src/{service}/evaluation/champion_challenger.py` —
  McNemar exact binomial test + bootstrap ΔAUC 95% CI combined into
  tri-state decision (promote / keep / block)
- `configs/champion_challenger.yaml` — alpha, n_bootstrap,
  non_inferiority_margin, superiority_margin
- `cicd/retrain-service.yml` — new C/C gate between quality gates and
  promotion; posts decision to Actions step summary; opens issue on
  keep/block
- Exit codes: 0 (promote) / 1 (keep) / 2 (block)

**Anti-patterns (D-20, D-21, D-22):**
- D-20 — prediction log events without `prediction_id` / `entity_id`
- D-21 — prediction logging blocking the async inference event loop
- D-22 — logging backend failure propagating to the HTTP response
- Added to `AGENTS.md` anti-pattern table (now D-01 → D-22)

**Agentic system:**
- `.windsurf/rules/13-closed-loop-monitoring.md` — invariants + slicing /
  ground-truth / C/C contracts + agent behavior by file (AUTO/CONSULT/STOP)
- `.windsurf/skills/concept-drift-analysis/` — new skill with RCA decision
  tree (global vs sliced, drift vs labels vs noise)
- `.windsurf/skills/drift-detection/` — extended to cover BOTH data drift
  (PSI) AND concept drift (sliced performance)
- `.windsurf/skills/model-retrain/` — new Step 5.5 for C/C statistical gate
- `.windsurf/workflows/performance-review.md` — monthly review workflow
  with multi-window metric collection + degrading-slice detection

**IDE parity:**
- `.cursor/rules/08-closed-loop.mdc` — parity with Windsurf rule 13
- `.claude/rules/08-closed-loop.md` — parity with Windsurf rule 13

**ADRs:**
- `docs/decisions/ADR-006-closed-loop-monitoring.md`
- `docs/decisions/ADR-007-sliced-performance-analysis.md`
- `docs/decisions/ADR-008-champion-challenger-statistical-gate.md`
- `docs/decisions/ADR-009-retraining-orchestration-triggers.md` —
  documents measurable triggers for migrating retraining beyond GHA;
  explicitly rejects premature Argo Workflows adoption

**Tests (50 total passing, 25 new):**
- `templates/tests/unit/test_prediction_logger.py` — 20 tests covering
  `PredictionEvent` invariants, 3 backends, D-21/D-22 contract
- `templates/tests/unit/test_ground_truth.py` — 6 tests for LabelRecord
  invariants and CSV stub
- `templates/tests/unit/test_performance_monitor.py` — 14 tests for
  metrics, slicing, thresholds, full pipeline with sliced subpopulations
- `templates/tests/unit/test_champion_challenger.py` — 10 tests for
  McNemar, bootstrap CI, decide() logic, end-to-end sklearn comparison

**Schema changes (BREAKING for services on v1.6.x):**
- `PredictionRequest.entity_id` is now REQUIRED (`min_length=1`)
- `PredictionResponse.prediction_id` is now REQUIRED (UUID hex)
- Optional: `PredictionRequest.slice_values: dict[str, str]` for sliced
  monitoring

**Dependencies:**
- `pyarrow ~=18.0` — parquet backend for prediction_logger
- `pyyaml ~=6.0` — config loaders

**Scope respected:**
- No Argo Workflows (ADR-009 documents triggers; GHA remains default)
- No Bytewax / streaming (parquet batch covers target audience)
- No ClickHouse default (parquet is default; BigQuery optional; ClickHouse
  mentioned as future trigger at >100M predictions/day)
- No Istio shadow mode (ADR-008 future-work section)
- ADR-001 scope honored throughout

---

## [1.6.0] - 2026-04-23

### Added

#### Agent Behavior Protocol + Supply Chain Security

Closes two latent gaps: agents now know **when to pause and ask**, and the supply
chain has first-class controls (Cosign signing + SBOM + admission policy). See
**ADR-005** for full rationale.

**Agent Behavior Protocol (3 modes):**
- `AGENTS.md` — new **Agent Behavior Protocol** section with AUTO / CONSULT / STOP modes
- **Operation → Mode mapping table** (21 operations, canonical)
- **Escalation triggers** — automatic STOP even from AUTO/CONSULT (marginal fairness,
  drift PSI > 2× threshold, cost > 1.2× budget, credential detected, etc.)
- Structured mode transition signal format for handoffs

**Authorization checkpoints in skills:**
- `.windsurf/skills/deploy-gke/SKILL.md` — `authorization_mode` frontmatter + protocol section (dev=AUTO, staging=CONSULT, prod=STOP)
- `.windsurf/skills/deploy-aws/SKILL.md` — same pattern
- `.windsurf/skills/model-retrain/SKILL.md` — train=AUTO, to_staging=CONSULT, to_production=STOP + automatic STOP on D-06 / marginal fairness / regression > 5%

**New Layer 2 agent: Agent-SecurityAuditor**
- Runs **before** Agent-DockerBuilder and Agent-K8sBuilder
- Blocks pipeline on findings (never silent)
- Chains to `/secret-breach` on secret leaks

**Agent Permissions Matrix** — capability boundaries per agent × environment.
"Blocked" entries cannot be bypassed by human insistence.

**Agent Handoff Schema** — typed dataclass contracts replacing ad-hoc dicts:
- `templates/common_utils/agent_context.py` — `AgentMode`, `Environment`,
  `EDAHandoff`, `TrainingArtifact`, `BuildArtifact`, `SecurityAuditResult`,
  `DeploymentRequest`, `AuditEntry`
- All `frozen=True`, validate invariants at construction (fail-fast)
- `DeploymentRequest` refuses to construct if `env=production` + `audit.passed=False`

**Audit Trail Protocol:**
- Every agentic operation → `ops/audit.jsonl` (append-only)
- Mirrored to GitHub Actions step summary
- CONSULT/STOP operations additionally open a GitHub issue tagged `audit`
- Failures open an issue tagged `audit` + `incident`

#### Supply Chain Security (SLSA L2 components)

**New anti-patterns D-17 / D-18 / D-19:**
- D-17: Hardcoded credentials / direct `os.environ` for secrets in prod
- D-18: Static AWS keys or GCP JSON keys in production
- D-19: Unsigned images or missing SBOM in production

**`.windsurf/rules/12-security-secrets.md` (NEW, `always_on`):**
- Non-negotiable invariants D-17/D-18/D-19
- Pre-commit gitleaks + credential-pattern grep
- Python module guidance: `common_utils.secrets.get_secret`, never log values
- K8s: `envFrom.secretRef`, IRSA/WI annotations, image digests in staging/prod
- Terraform: secret manager data sources, no literals
- Environment separation table (local / ci / staging / prod)
- Explicitly documents what it does NOT cover (Vault, SLSA L3+, compliance — per ADR-001)

**`templates/common_utils/secrets.py` (NEW):**
- Cloud-native secret loader with environment-aware resolution
- Backends: dotenv (local), `os.environ` (CI), AWS Secrets Manager, GCP Secret Manager
- **Refuses to fall through to `os.environ` in staging/production** (D-18)
- Never logs secret values (D-17)

**`templates/cicd/ci.yml` updates:**
- New `security-audit` job: gitleaks + credential-pattern grep + IRSA/WI enforcement
- `build` job renamed to "Build, Sign & Attest":
  - Syft SBOM generation (CycloneDX + SPDX) with 90-day retention
  - Cosign keyless signing via GitHub OIDC (commented until registry wired)
  - `cosign attest` for SBOM as CycloneDX attestation
  - `permissions.id-token: write` for keyless signing
  - Build provenance summary in GHA step summary

**`templates/k8s/policies/kyverno-image-verification.yaml` (NEW):**
- ClusterPolicy `verify-image-signatures` — reject unsigned images in
  `environment=production` namespaces
- Keyless Cosign: GitHub OIDC identity + Rekor transparency log
- Requires CycloneDX SBOM attestation (max 90 days old)
- Companion ClusterPolicy `require-image-digest` — forbids tag-only refs in staging/prod

**Incident response:**
- `.windsurf/skills/security-audit/SKILL.md` (NEW) — pre-build/pre-deploy scans
- `.windsurf/skills/secret-breach-response/SKILL.md` (NEW) — 7-phase playbook
  (halt → classify → revoke → audit → rotate → clean history → notify → post-mortem)
- `.windsurf/workflows/secret-breach.md` (NEW, `/secret-breach` slash command)

**Documentation:**
- `docs/decisions/ADR-005-agent-behavior-and-security.md` (NEW)
  - Why 3 modes (not binary)
  - Why keyless Cosign (not keypair)
  - Why Kyverno (not OPA Gatekeeper)
  - Why refuse `os.environ` in prod
  - Why not Vault (ADR-001 deferred)
  - Why JSONL audit log (not GitHub issues per op)
  - Why dataclasses (not JSON Schema)
  - 4 alternatives considered + rejected
  - Revisit triggers

### Changed

- `AGENTS.md`: new sections (Behavior Protocol, Handoff Schema, Audit Trail, Permissions Matrix)
- Agent list in Layer 2 now includes Agent-SecurityAuditor
- Skills inventory adds `security-audit`, `secret-breach-response`
- Workflow inventory adds `/secret-breach`
- Cross-references table adds: pre-build/pre-deploy, secret-leak-detected

### Smoke tests

- Handoff dataclasses enforce invariants at construction:
  - `TrainingArtifact.requires_consult()` returns True for marginal fairness (0.80–0.85) or metric > 0.99
  - `SecurityAuditResult` raises `ValueError` if `passed` flag disagrees with component fields
  - `DeploymentRequest` raises `ValueError` on production + failed audit

### The consultative gap is now closed

```
Before:  Agent executes all the way to kubectl apply — human sees only results.
After:   Agent emits [AGENT MODE: CONSULT] before staging apply, [AGENT MODE: STOP]
         before production apply, presents plan, waits for explicit approval.
```

### The supply chain gap is now closed

```
Before:  Trivy scan → push → deploy (no signature, no SBOM, no admission gate)
After:   Trivy + Gitleaks → SBOM (CycloneDX + SPDX) → Cosign sign (keyless OIDC)
         → Cosign attest SBOM → push → Kyverno admission verifies at cluster entry
```

---

## [1.5.0] - 2026-04-23

### Added

#### EDA Phase Integration (closes data-to-training gap)

The template now has a first-class Exploratory Data Analysis phase that connects
raw data → trained model through 6 structured phases with 4 agentic invariants.

**Agentic configuration:**
- **`AGENTS.md`**: new Agent-EDAProfiler (Layer 2); anti-patterns D-13 through D-16;
  updated skill/workflow inventories with `eda-analysis` and `/eda`
- **`.windsurf/rules/11-data-eda.md`**: enforces snake_case, sandbox isolation,
  baseline persistence, structural layout. Glob: `**/eda/**`, `**/notebooks/**/*.ipynb`
- **`.windsurf/skills/eda-analysis/SKILL.md`**: 6-phase procedure with hard gate on
  phase 4 (leakage detection) — chains to `/incident` on block
- **`.windsurf/workflows/eda.md`**: `/eda` slash command; chains to `/new-service`
  on pass or `/incident` on leakage block

**Template module `templates/eda/`:**
- **`eda_pipeline.py`** (500 lines): scriptable pipeline
  - Phase 0: ingest + snake_case normalization (D-13 sandbox check)
  - Phase 1: structural profile → `01_dtypes_map.json`
  - Phase 2: univariate + **`02_baseline_distributions.pkl`** (D-15) with
    quantile bins for PSI compatibility (D-08)
  - Phase 3: correlations + feature ranking
  - Phase 4: leakage detection HARD GATE (exit 1 if `BLOCKED_FEATURES` non-empty)
  - Phase 5: feature proposals with rationale (D-16)
  - Phase 6: `schema_proposal.py` with observed ranges (D-14) + summary markdown
- **`notebook_template.ipynb`**: interactive companion (13 cells, one per phase)
- **`requirements.txt`**: lightweight mode (~50MB, pandas + scipy + pandera)
- **`requirements-heavy.txt`**: opt-in ydata-profiling + plotly (~500MB)
- **`README.md`**: conventions, phase artifacts reference, drift loop diagram

**Anti-patterns D-13 to D-16:**
- D-13: EDA on production data without sandbox
- D-14: Pandera schema without observed ranges from EDA
- D-15: Baseline distributions not persisted (silently breaks drift detection)
- D-16: Feature engineering without documented rationale

**Integration:**
- `new-service.sh` now copies `eda/` to scaffolded services + creates
  `reports/`, `artifacts/`, `notebooks/` subdirs
- Updated scaffolder next-steps walk users through EDA before `schemas.py`/`features.py`
- `test_scaffold.sh` validates 5 new `eda/` paths exist in scaffolded output
- `make eda-validate` target (syntax + `py_compile`); chained into `make validate-templates`

**Documentation:**
- **`docs/decisions/ADR-004-eda-phase-integration.md`**: documents the design,
  rationale for 6 phases (not fewer), hard gate on leakage, lightweight vs heavy
  modes, and why `schemas.py` is never auto-overwritten

**Validation:**
Tested end-to-end against `examples/minimal` fraud data (400 rows × 6 cols): all
6 phases pass in <1s, `baseline_distributions.pkl` produced with quantile bins,
leakage gate correctly PASSED, 3 transforms proposed each with rationale.

**The drift detection loop now closes:**
```
EDA phase 2 → 02_baseline_distributions.pkl (DVC-tracked)
           → Drift CronJob (production, consumes the pkl)
           → PSI per feature using quantile bins (D-08)
           → Alert if PSI > threshold → /drift-check → /retrain
```

---

## [1.4.0] - 2026-04-19

### Added

#### One-Command Bootstrap
- **`scripts/bootstrap.sh`** — Detects OS (Linux/macOS/WSL), verifies required tools (Python 3.11+, Docker, kubectl, terraform, git, make), installs Python dependencies, configures MCPs interactively, installs pre-commit hooks, and validates by running the minimal example end-to-end. Idempotent; supports `--skip-mcp`, `--skip-demo`, `--check-only`.
- **`scripts/_lib/detect_os.sh`** — OS detection helper
- **`scripts/_lib/install_deps.sh`** — Python + system dependency installer
- **`scripts/_lib/configure_mcp.sh`** — Interactive MCP configuration (github, git, kubectl-mcp-server, terraform-mcp-server)
- **Makefile targets**: `make bootstrap`, `make bootstrap-check`

#### Agentic System Validator
- **`scripts/validate_agentic.py`** — Validates `.windsurf/` structure:
  - Rule frontmatter (`trigger`, `description`, `globs`)
  - Glob patterns match real files (catches dead rules)
  - Skill `SKILL.md` contracts (`name`, `description`, `allowed-tools`)
  - Workflow frontmatter
  - AGENTS.md cross-references (no orphan skills/workflows)
- **CI job**: `agentic-system` in `validate-templates.yml` runs on every PR
- **Makefile target**: `make validate-agentic` (chained into `make validate-templates`)

#### Governance Module (opt-in)
- **`templates/governance/README.md`** — When/how to enable approval gates
- **`templates/governance/ROLES.md`** — ML Engineer / Tech Lead / Platform Engineer responsibilities
- **`templates/governance/github-environments.yml`** — GitHub Environments configuration reference (staging + production with `required_reviewers` and 24h soak)
- **`templates/governance/promote-with-approval.yml`** — GitHub Actions workflow for Staging → Production promotion with MLflow stage transitions and audit tags
- **`templates/governance/promote_to_stage.sh`** — CLI for MLflow Model Registry stage transitions with audit trail
- **`docs/decisions/ADR-002-model-promotion-governance.md`** — Documents why governance is opt-in, why GitHub Environments + MLflow stages over custom infrastructure, and how it respects ADR-001

#### Scaffolder End-to-End Test
- **`scripts/test_scaffold.sh`** — Runs `new-service.sh` in an isolated temp dir and validates:
  - Zero remaining `{ServiceName}`/`{service}`/`{SERVICE}` placeholders
  - All critical files and directories present
  - `src/{service}/` renamed correctly to `src/<slug>/`
  - All generated Python files parse (syntax check)
  - Both Kustomize overlays render (GCP + AWS)
  - `pytest` can collect scaffolded tests
- **CI job**: `scaffold-e2e` in `validate-templates.yml` runs on every PR
- **Makefile target**: `make test-scaffold` (also chained into `make validate-templates`)

#### Feast Integration Pattern
- **`docs/decisions/ADR-003-feast-integration-pattern.md`** — Documents the pattern for
  integrating Feast without modifying the core template. Uses external feature repo
  approach; service becomes a Feast client. Preserves Pandera validation (solves a
  different problem). Migration checklist (4 phases) and invariants maintained.

### Changed

#### Makefile (root)
- `validate-templates` now includes `validate-agentic` and `test-scaffold` steps
- Added `bootstrap`, `bootstrap-check`, `validate-agentic`, `test-scaffold` as first-class targets

---

## [1.3.0] - 2026-04-16

### Added

#### Standalone Documentation (root)
- **`QUICK_START.md`** — 10-minute setup guide: Option A (example demo), Option B (scaffold service), Option C (full MLflow stack)
- **`RUNBOOK.md`** — Template operations reference: scaffolding, validation, MLflow, contributing, release process
- **`LICENSE`** — MIT License (was referenced in README but file was missing)
- **`docker-compose.yml`** — Local dev stack: example fraud detection API + MLflow (one command: `docker compose up`)
- **`releases/`** — GitHub Release notes directory: `v1.0.0.md`, `v1.1.0.md`, `v1.2.0.md` ready to publish

#### DVC Templates (new)
- **`templates/service/dvc.yaml`** — DVC pipeline with 4 stages: validate → featurize → train → evaluate
- **`templates/service/.dvc/config`** — DVC remote configuration template for GCS/S3 storage

#### Infrastructure (from portfolio)
- **`templates/infra/docker-compose.mlflow.yml`** — Production-like MLflow stack: PostgreSQL + MinIO (S3-compatible) + MLflow server with health checks

#### Documentation Templates (new)
- **`templates/docs/CHECKLIST_RELEASE.md`** — Pre-deployment release checklist: quality gates, Docker, K8s, infra, monitoring, multi-cloud
- **`templates/docs/mkdocs.yml`** — MkDocs Material configuration template with navigation, plugins, theme, and docstring support

#### Integration Test Templates (new)
- **`templates/tests/integration/conftest.py`** — Service health wait fixture, auto-skip if unavailable
- **`templates/tests/integration/test_service_integration.py`** — Full service validation: health, predictions, SHAP, latency SLA, metrics, model info

#### Enterprise K8s & Security (new)
- **`templates/tests/infra/policies/kubernetes.rego`** — OPA/Conftest policies (ported from portfolio): non-root, resource limits, health probes, no :latest, namespace, HPA scaleDown + ML-specific D-01/D-02 enforcement
- **`templates/k8s/base/slo-prometheusrule.yaml`** — SLO/SLA definitions as PrometheusRule:
  - Availability SLI (99.5% non-5xx), Latency SLI (95% < 500ms)
  - Error budget recording rules (30-day window)
  - Multi-window burn rate alerts: P1 (14.4x/1h), P2 (6x/6h), P3 (budget < 25%)

#### Service Template Additions
- **`templates/service/codecov.yml`** — Codecov configuration template with per-service coverage flags

#### Example Improvements
- **`examples/minimal/Dockerfile`** — Docker image for the fraud detection example (used by root docker-compose.yml)

#### Architecture Decision Records
- **`docs/decisions/ADR-001-template-scope-boundaries.md`** — Documents why LLM/GenAI, multi-tenancy, Vault, feature store, data contracts, SOC2/GDPR, and audit logs are deferred. Includes revisit triggers and Engineering Calibration rationale.

#### CI: End-to-End Example Proof
- **`validate-templates.yml`** — New `example-e2e` job: install → train → verify artifacts → start server → run tests → drift check → verify quality gates. Proves the template works in CI, not just locally.

### Changed

#### README — Major Restructure
- **Concise hook at top** — Problem statement + differentiator in 3 lines, replacing verbose intro
- **Quick Navigation** — Replaced bullet list with 3-column table (Getting Started | Architecture | Development)
- **Quick Start** — Removed manual `sed -i` commands, now uses `new-service.sh` exclusively (fixes inconsistency with CHANGELOG v1.1.0)
- **"Try It in 5 Minutes"** — Added `make demo-minimal` one-liner and Docker Compose alternative
- **Repository Structure** — Updated tree with all new files: QUICK_START.md, RUNBOOK.md, LICENSE, docker-compose.yml, releases/, DVC, integration tests, SLO, mkdocs, checklist, MLflow compose
- **Templates Detail** — Added sections for DVC, integration tests, SLO, MLflow, release checklist, MkDocs
- **MkDocs section** — Now references `templates/docs/mkdocs.yml` template instead of just the portfolio
- Added links to QUICK_START.md and RUNBOOK.md at top of README

#### AGENTS.md
- Updated Template System tree with DVC, pyproject.toml, integration tests, SLO, MLflow compose, mkdocs, checklist

#### CLAUDE.md
- Updated File Structure with all new files and directories

#### `new-service.sh`
- Added DVC template copying step
- Added integration test template copying
- Added `data/validated/`, `data/processed/`, `reports/` to standard directories

#### Fairness Module
- **`templates/service/src/{service}/fairness.py`** — Added domain guidance: protected attribute selection by industry (Finance, Healthcare, Employment, GDPR), threshold customization, DIR limitations, proxy detection references

#### common_utils Distribution Strategy
- **`templates/common_utils/__init__.py`** — Documented the copy-in pattern, trade-offs, and PyPI graduation path (>5 services)

#### README: Claude Code & Cursor Rules
- **Agentic System section** — Added dedicated subsections for `.claude/rules/` (5 rules, `paths:` triggers) and `.cursor/rules/` (5 MDC rules, `globs:` triggers) with per-file tables

#### RUNBOOK: Secret Management
- **`RUNBOOK.md`** — Added Secret Management section: GCP/AWS Secrets Manager commands, anti-pattern D-10 guidance

### Notes

#### Claude-code-main Assessment
- Evaluated `/home/duque_om/projects/Claude-code-main` — TypeScript CLI rebuild of Claude Code, **no reusable content** for this MLOps template

#### Enterprise Gap Assessment
- **Already present**: RBAC (`rbac.yaml`), NetworkPolicy, Workload Identity/IRSA, SHAP `/predict?explain=true`, JSONFormatter, Prometheus/Grafana (9 panels), Pandera (3 validation points), Makefile x2, MLflow+DVC, Codecov badge (dynamic), `make demo-minimal`
- **Added in v1.3.0**: SLO/SLA PrometheusRule, ADR-001, e2e CI job, fairness domain guidance, Claude/Cursor docs
- **Deferred by design** (ADR-001): LLM/GenAI, multi-tenancy, HashiCorp Vault, feature store, SOC2/GDPR — documented with revisit triggers

---

## [1.2.0] - 2026-04-15

### Added

#### Developer Experience (root DX files)
- **`Makefile`** (root) — Contributor entry point with template-specific targets:
  - `make validate-templates` — lint + K8s validation in one command
  - `make lint-all` / `make format-all` — operate on all Python across `templates/` and `examples/`
  - `make demo-minimal` — run fraud detection example end-to-end (install → train → test → drift)
  - `make test-examples` — regression tests for examples/
  - `make new-service NAME=X SLUG=y` — scaffold wrapper around `new-service.sh`
- **`.pre-commit-config.yaml`** (root) — Contributor hooks: black, isort, flake8, `pre-commit-hooks` (yaml, merge conflicts, large files), gitleaks
- **`.gitleaks.toml`** (root) — Secret detection config shared between root and `templates/`, with allowlists for template placeholder tokens (`{ServiceName}`, `{service}`)

#### Multi-IDE Cursor Parity
- **`.cursor/rules/02-kubernetes.mdc`** — K8s rules: 1 worker, CPU HPA, init container pattern with code example
- **`.cursor/rules/03-python-serving.mdc`** — Serving rules: async inference, SHAP KernelExplainer, Prometheus metrics
- **`.cursor/rules/04-python-training.mdc`** — Training rules: pipeline sequence, quality gate table, required tests
- **`.cursor/rules/05-docker.mdc`** — Docker rules: multi-stage, non-root USER, HEALTHCHECK, no model artifacts

#### GitHub Releases
- **v1.0.0** — tag pushed to remote (was created locally, not published)
- **v1.1.0** — annotated tag created and pushed with full release notes

### Changed

#### CI Template (`templates/cicd/ci.yml`)
- Added **Python 3.12 matrix** — test job now runs `["3.11", "3.12"]` in parallel
- Added **Codecov integration** — uploads `coverage.xml` on `3.11` run via `codecov/codecov-action@v4`
- Coverage report format changed from `term-missing` only → `xml` + `term-missing`

#### README
- Added **Release badge** with dynamic version from GitHub Releases
- Updated **Python badge** to `3.11 | 3.12`
- Added **Codecov badge**
- Updated `.cursor/rules/` entry to reflect 5 MDC rules (was 1)
- Updated repo tree with root DX files (`Makefile`, `.pre-commit-config.yaml`, `.gitleaks.toml`)

#### AGENTS.md / CLAUDE.md / .cursor/rules/
- Updated Multi-IDE Support section in AGENTS.md to show all 5 cursor rules

---

## [1.1.0] - 2026-04-15

### Added

#### Working Example (`examples/minimal/`)
- **Fraud detection service** — fully functional end-to-end demo (train → serve → predict → test → drift)
- `train.py` — synthetic data generation, Pandera validation, sklearn pipeline, quality gates
- `serve.py` — FastAPI with async inference (ThreadPoolExecutor), SHAP KernelExplainer, Prometheus metrics
- `test_service.py` — regression tests: data leakage, SHAP consistency, latency SLA, fairness DIR
- `drift_check.py` — PSI drift detection with quantile bins and exit codes (0/1/2)

#### Scaffolding
- **`new-service.sh`** — automated scaffolding script: copies templates, replaces placeholders ({ServiceName}, {service}, {SERVICE}), creates directory structure

#### Monitoring
- **`alertmanager-rules.yaml`** — production AlertManager rules with P1–P4 severity:
  - Service down + error rate spike (P1)
  - Inference latency degradation (P2)
  - **Drift heartbeat missing** (P2) — fires if CronJob hasn't run in 48h
  - PSI drift alert/warning (P3)
  - CPU approaching limit + pod restarts (P4)

### Changed

#### drift_detection.py — Production CronJob Integration
- Added **exit codes** (0=ok, 1=warning, 2=alert) for K8s CronJob integration
- Added **GitHub Issue creation** on alert-level drift via GitHub API
- Added **reference data update** with timestamped backups
- Added proper `main()` function with `sys.exit()` for clean process control

#### test_explainer.py — Self-Contained SHAP Tests
- Replaced stub tests with **runnable, self-contained regression tests**
- Tests use synthetic data + simple pipeline (no service dependency)
- Covers: all-zero SHAP detection, consistency property, original feature space, background representativeness, latency SLA

#### Kustomize Structure
- Moved manifests to `k8s/base/` (standard Kustomize pattern)
- Fixed `commonLabels` (deprecated) → `labels` with pairs syntax
- Fixed `patchesStrategicMerge` (deprecated) → `patches` in overlays
- Replaced `kubeval` (abandoned) with `kubeconform` in CI

#### README
- Added **"Try It in 5 Minutes"** section with copy-paste commands
- Added **"What's Different From Other Templates"** comparison table
- Updated Quick Start to use `new-service.sh` scaffolding script
- Updated repo structure tree with all new files

#### Agentic System Improvements
- **Split `04-python-ml.md`** into `04a-python-serving.md` (app/) and `04b-python-training.md` (training/) — reduces unnecessary context loading
- **Added `10-examples.md`** — prevents production rules from firing in `examples/` directory
- **Added `.claude/rules/`** — 5 context-aware rules with `paths:` frontmatter for Claude Code IDE
- **AGENTS.md** — added Session Initialization Protocol, How to Invoke Skills, Multi-IDE Support sections
- **01-mlops-conventions.md** — slimmed from 75 to 43 lines, references `AGENTS.md` for detail
- **CLAUDE.md** — comprehensive rewrite: session protocol, full anti-pattern table, key commands
- **`.cursor/rules/`** — enhanced with session protocol, full D-01→D-12 table, key commands
- **Skill `new-service`** — now invokes `new-service.sh`, verifies zero remaining placeholders
- **Skill `debug-ml-inference`** — added D-01→D-12 anti-pattern checklist as Step 1
- **Skill `drift-detection`** — added PSI interpretation table with exit codes, special cases for time series/NLP/categorical
- **Workflow `/new-service`** — uses `new-service.sh` with manual fallback
- **Workflow `/incident`** — added Step 0: severity classification decision tree (P1–P4)
- **Workflow `/retrain`** — added explicit quality gate table with typical thresholds and verification script
- **Workflow `/cost-review`** — added PromQL queries for CPU/memory/throughput/HPA utilization

### Fixed
- black formatting: reformatted `test_explainer.py` and `drift_detection.py`
- flake8 F401: removed unused imports across 7 files
- flake8 E501/F841: fixed long lines and unused variable in cli.py
- Kustomize cycle error: restructured to standard `base/` + `overlays/` layout

---

## [1.0.0] - 2026-04-15

### Added

#### Agentic System
- **AGENTS.md** - Root-level agent architecture with 3-layer design (Orchestrator, 11 Specialist Agents, 4 Maintenance Agents), 12 anti-pattern detectors (D-01 to D-12), and Engineering Calibration Principle
- **10 context-aware rules** (`.windsurf/rules/`) - Behavioral constraints for K8s, Terraform, Python serving/training (split), CI/CD, Docker, docs, data validation, monitoring, examples
- **8 operational skills** (`.windsurf/skills/`) - Structured frontmatter with `allowed-tools`, `when_to_use`, `argument-hint`, per-step `Success criteria`
- **8 slash-command workflows** (`.windsurf/workflows/`) - `/release`, `/retrain`, `/load-test`, `/new-adr`, `/incident`, `/drift-check`, `/new-service`, `/cost-review`

#### Service Template (`templates/service/`)
- FastAPI app with async inference via ThreadPoolExecutor
- SHAP KernelExplainer integration with consistency checks
- Prometheus metrics (counter, histogram, summary)
- Pandera DataFrameModel for training, API, and drift validation
- Optuna hyperparameter tuning with configurable trials
- Quality gates (primary metric, secondary metric, fairness DIR >= 0.80)
- MLflow experiment tracking and model registry integration
- Comprehensive pytest tests (leakage, quality gates, API, SHAP, latency SLA)
- Locust load test template (100 concurrent users, < 1% error rate)
- Multi-stage Dockerfile with non-root USER and HEALTHCHECK

#### Common Utils (`templates/common_utils/`)
- `seed.py` - Reproducibility across Python, NumPy, PyTorch, TensorFlow
- `logging.py` - JSON formatter (production K8s) + colored human-readable (dev)
- `model_persistence.py` - joblib save/load with SHA256 integrity validation
- `telemetry.py` - OpenTelemetry tracing with graceful no-op fallback

#### Kubernetes (`templates/k8s/`)
- Deployment with init container for model download from GCS/S3
- CPU-only HPA (never memory for ML pods)
- Kustomize base + GCP-production and AWS-production overlays
- Argo Rollouts canary deployment with Prometheus-based AnalysisTemplate
- ServiceAccount with Workload Identity (GCP) and IRSA (AWS) annotations

#### Infrastructure (`templates/infra/`)
- Terraform GCP: GKE cluster, Workload Identity, GCS buckets, Artifact Registry
- Terraform AWS: EKS cluster, OIDC for IRSA, managed node group, IAM roles

#### CI/CD (`templates/cicd/`)
- CI: flake8 + black + isort + mypy, pytest (90% coverage), Docker build + Trivy
- Infrastructure CI: terraform validate + tfsec + Checkov + kubeval
- Deploy GCP/AWS: tag-triggered with cluster verification and smoke tests
- Drift Detection: daily scheduled + manual trigger, auto-creates GitHub issue
- Retraining: manual trigger with data validation, quality gates, artifact upload

#### Scripts (`templates/scripts/`)
- `deploy.sh` - Build, push, deploy with kubectl context verification and tag immutability
- `promote_model.sh` - Quality gates (metric, fairness, leakage, integrity) before promotion
- `health_check.sh` - Pod status + /health and /model/info endpoint checks

#### Developer Experience
- `docker-compose.demo.yml` - Demo stack with MLflow + Pushgateway + optional monitoring
- `Makefile` - Standard targets: train, test, serve, build, deploy, health-check, demo
- `.pre-commit-config.yaml` - black, isort, flake8, mypy, bandit, gitleaks
- `.gitleaks.toml` - Secret detection configuration
- `.env.example` - Environment variable documentation

#### Documentation Templates
- ADR template with Context, Options, Decision, Rationale, Consequences, Revisit When
- Runbook template with P1-P4 severity procedures
- Service README template with measured data slots
- Model card template for ML transparency
- Dependency analysis template for conflict documentation

#### Monitoring Templates
- Prometheus alerts: error rate, service down, drift heartbeat, latency, resources
- Grafana dashboard: request rate, latency percentiles, PSI scores, HPA, CPU/memory

#### Open Source Maturity
- `SECURITY.md` - Vulnerability reporting policy and security measures
- `CONTRIBUTING.md` - Contribution guidelines with Engineering Calibration awareness
- `CODE_OF_CONDUCT.md` - Contributor Covenant v2.0
- `.github/ISSUE_TEMPLATE/` - Bug report and feature request templates
- `.github/pull_request_template.md` - PR checklist with anti-pattern verification
- `.github/dependabot.yml` - Automated dependency updates
- `.gitattributes` - Git LFS for model artifacts, line ending normalization
- CI workflow `validate-templates.yml` - Validates K8s, Terraform, and Python templates

---

*This template was extracted from [ML-MLOps-Portfolio](https://github.com/DuqueOM/ML-MLOps-Portfolio), a production portfolio with 3 live ML services.*
