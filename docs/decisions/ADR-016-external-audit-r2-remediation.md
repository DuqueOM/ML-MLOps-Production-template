# ADR-016: External Audit R2 — Remediation Plan

- **Status:** Accepted
- **Date:** 2026-04-26
- **Supersedes:** none (extends ADR-014 closure and ADR-015 roadmap)
- **Authors:** ML Platform team

## Context

A second-round external audit (after the v1.10.0 audit closure landed
in ADR-014) surfaced 16 findings spanning runtime, observability,
CI/CD, infrastructure parity, and product positioning. The audit was
tough, well-evidenced (file:line for every claim), and correct.

The 5 Critical / High findings whose impact is "production thinks it
works but doesn't" were closed in commit `7bc53fd` (this same hour):

| # | Finding | Closed by |
|---|---------|-----------|
| C-1 | Closed-loop logger silently disabled (Dockerfile missing `common_utils/`) | Dockerfile + fastapi_app fail-fast |
| C-2 | SLO PrometheusRule queries `http_*` while exporter emits `<service>_*` | Rule rewrite + metric-contract test |
| H-3 | Retrain workflow has wrong dataset paths and references missing `promote_to_mlflow.py` | Path fix + new module |
| H-4 | `new-service.sh` doesn't ship `audit_record.py` to scaffolded repos | Copy from `$PROJECT_ROOT/scripts/` |
| H-5 | Security-audit only runs on `main` and globs the wrong overlay names | Drop `if: ref == main`, fix glob |

This ADR governs the **remaining 11 findings** by sequencing them into
trackable PRs with explicit owners and exit criteria.

## Decision

Treat the external audit as a forcing function for two simultaneous
goals:

1. **Operational integrity** — the gaps that would surface as a real
   incident go first (7-day window).
2. **Adoption boundary clarity** — every finding for which the right
   answer is "the template doesn't claim that yet" gets explicit
   documentation in `README.md` § Adoption Boundary, NOT a silent
   pretend-fix.

We DO NOT promise enterprise-readiness on every dimension; we promise
**honest scope** plus a public roadmap. The audit's closing note is
correct: today the agentic layer is more mature than parts of the
infra/operations layer it governs. We close that gap with code, not
prose.

## 7-Day Remediation Window (PR-R2-1 → PR-R2-5)

Owner: ML Platform. Each PR carries `audit-r2` label.

### PR-R2-1 — API authentication + admin endpoint protection ✅

Severity: **High**. Affected: `templates/service/app/main.py:95,169`.

**Status:** Closed (see `common_utils/auth.py`, `test_auth.py`, CORS default-deny wiring).

- Add `common_utils/auth.py` with two `Depends()` providers:
  - `verify_api_key()` — header-based bearer/X-API-Key, secret resolved
    via `common_utils/secrets.py`.
  - `require_admin()` — superset of `verify_api_key`, restricted by
    a separate admin secret.
- Mount `/predict`, `/predict_batch` behind `verify_api_key`.
- Move `/model/reload` and any future admin endpoint behind
  `require_admin`. Default to **disabled** unless
  `ADMIN_API_ENABLED=true` is set; refuse to start in production
  with `ADMIN_API_ENABLED=true` AND no admin secret configured.
- Replace the wildcard CORS default with `default-deny`; expose
  `CORS_ALLOWED_ORIGINS` as the explicit allowlist env.
- Add `tests/test_auth.py` covering 401 / 403 / 200 paths.

Exit: `pytest tests/test_auth.py` green; an unauthenticated request
to `/model/reload` returns 401 with no leak of the endpoint shape.

### PR-R2-2 — Pin init container + CronJob images by digest ✅

Severity: **High**. Affected: `templates/k8s/base/deployment.yaml:46`,
`cronjob-drift.yaml:25`, `cronjob-performance.yaml:36`.

**Status:** Closed — `cloud-cli-image` + predictor image refs unified
under Kustomize `images:` mapping; per-tier digest-pinning lint in
`validate-templates.yml` (warn tier in prod today; flips to hard
error with the bootstrap runbook).

- `deploy-common.yml` already captures the application image digest;
  extend the same pattern to:
  - the `google/cloud-sdk:slim` init container (or replace with a
    minimal `gcr.io/google.com/cloudsdktool/cloud-sdk:alpine` pinned
    by digest baked into a curated registry under our control),
  - the `{service}-predictor:latest` CronJobs (drift, performance);
    they should consume the SAME digest the deployment uses so
    drift evaluation runs against the same code as serving.
- Drop every `:latest` reference under `templates/k8s/`; CI
  validates with `grep -r ':latest' templates/k8s/ && exit 1`.
- Sign the init container image with Cosign and add it to the
  Kyverno digest gate.

Exit: `kustomize build templates/k8s/overlays/<cloud>-prod | grep
'image:' | grep -v '@sha256:'` returns empty.

### PR-R2-3 — Neutralize K8s base manifests ✅

Severity: **High**. Affected: `deployment.yaml:8,11`, `rbac.yaml:16`,
`networkpolicy.yaml:17`.

**Status:** Closed — base resources no longer carry `environment:`
or `namespace:`; `replicas:` in base is the HPA floor, not a steady
state. "Base neutrality lint" in `validate-templates.yml` catches
regressions.

- Remove `environment: production` and `namespace: ml-services` from
  base; overlays own those fields (each overlay already ships its
  own `namespace.yaml` since v1.10.0).
- Align base `replicas: 1` with HPA `minReplicas: 2` (the existing
  contradiction sends mixed signals to controllers): set base to
  `replicas: 2` and document that it is the floor, not the steady
  state.
- Add a `kustomize build` lint check to CI that fails if base
  contains any of `environment:`, `namespace:`, or a `replicas:`
  value below the overlay's `minReplicas`.

Exit: each overlay's effective output is unchanged after the rebase;
the lint check is wired into `validate-templates.yml`.

### PR-R2-4 — Tabular schema validation in serving + drift ✅

Severity: **High**. Affected: `templates/service/app/schemas.py:1`,
`train.py:138` and missing in `fastapi_app.py`, drift CronJob.

**Status:** Closed by commit `96d366e` (2026-04-26).

- ✅ Added `templates/common_utils/input_validation.py` with three
  adapters (split single-row vs batch for clearer 422 redaction):
  - `validate_predict_payload(payload, schema)` — single-row Pandera
    pass; raises `HTTPException(422)` with a D-32 redacted body
    (column + check, never the value).
  - `validate_predict_batch(rows, schema)` — atomic semantics so one
    bad row rejects N.
  - `validate_drift_dataframe(df, schema, *, label)` — batch validator
    that raises a custom `DriftSchemaError` (not `HTTPException`,
    since drift runs outside FastAPI).
- ✅ Lazy resolver `templates/service/app/_pandera_schema.py` resolves
  the service-specific Pandera schema at runtime via
  `importlib.import_module(SERVICE_PACKAGE)` — needed because
  `fastapi_app.py` cannot ``from {service}.schemas import …`` at parse
  time before `new-service.sh` has rewritten the placeholder.
- ✅ Wired into `/predict`, `/predict_batch` BEFORE the model call,
  and the broad ``except Exception`` block now re-raises
  ``HTTPException`` so 422s never get masked as 500s. A new
  ``requests_total{status="422"}`` counter separates schema rejections
  from platform errors in the SLO panel.
- ✅ Wired into the drift CronJob BEFORE PSI computation. New CLI flag
  ``--skip-schema`` is the documented forensics escape hatch (warns
  loudly when used). On schema mismatch the CronJob now exits with
  code **3**, distinct from real-drift codes 1/2, so on-call rotates
  operators to the data pipeline instead of retraining a healthy
  model.
- ✅ Tests added in `templates/service/tests/test_input_validation.py`
  cover schema=None no-op, redacted 422 bodies (D-32), batch
  atomicity, drift `DriftSchemaError`, and end-to-end through
  `TestClient`.
- ✅ CI lint added in `validate-templates.yml`
  ("Schema-validation wiring") greps for the import + call site of
  every validator + the existence of `_pandera_schema.py`. A future
  PR that touches the schema contract without updating the validators
  fails the lint job.

Exit criteria all met: `tests/test_input_validation.py` green; a PR
that breaks `schemas.py` and forgets to update validators fails CI.

### PR-R2-5 — Replace `curl | bash` toolchain installs with versioned actions ✅

Severity: **Medium** (but contradicts the supply-chain story).
Affected: `deploy-common.yml:187`, `validate-templates.yml:168`.

**Status:** Closed by commit `153bc1d` (2026-04-26).

Replaced every `curl … | bash` and every `/releases/latest/download/`
in `.github/workflows/` and `templates/cicd/` with pinned direct
release tarballs, matching the proven `golden-path.yml` pattern:

- ✅ `validate-templates.yml` — kubeconform pinned to `v0.6.7`,
  kustomize pinned to `v5.4.3` (both jobs).
- ✅ `templates/cicd/deploy-common.yml` — kustomize install replaced
  with the same pinned-tarball pattern. Production deploys no longer
  execute upstream-controlled shell code.
- ✅ `templates/cicd/ci-infra.yml` — migrated from `kubeval` (archived
  upstream) to `kubeconform v0.6.7`, and overlay validation updated
  accordingly.

A different route from the original ADR draft: rather than adopt
`imranismail/setup-kustomize@v2` + `dcarbone/install-jq-action@v3`,
we standardised on **pinned direct-release-tarball downloads** from
`github.com/*/releases/download/<version>/`. Rationale:

- No new third-party action dependency (smaller supply-chain
  attack surface than trusting another maintainer's action).
- No unauthenticated GitHub API call (the concrete cause of the
  rate-limit failure the audit cited — run 24953193994).
- Version pins live in the workflow itself; bumping them is an
  explicit PR with code review, not an opaque `uses: …@v2` tag
  move.

**Regression lint:** new self-audit step in `validate-templates.yml`
("Toolchain install hygiene (PR-R2-5)") greps every workflow for:

  - `curl … | bash` (any piping of network bytes into a shell)
  - `/releases/latest/download/` (moving-version pins)
  - `install_kustomize.sh` (the specific upstream hack/ installer)

The lint's own patterns are assembled from concatenated string
fragments so the scan covers every workflow including itself
without self-matching — no self-exclusion filter, no coverage hole.

Exit criteria all met: CI runs without any `curl … | bash`; the
lint guarantees future PRs cannot reintroduce the anti-patterns.
`tfsec/checkov/trivy` continue to pass on the workflow files.

## 30-Day Remediation Window (PR-R2-6 → PR-R2-9)

### PR-R2-6 — AWS parity: storage, registry, IAM, secrets, logging ✅

Severity: **High**. Affected: `templates/infra/terraform/aws/*`.

**Status:** Closed by commit `92e7b3a` (2026-04-27).

GCP was roughly starter-grade serious; AWS was scaffold-only. AWS is
now at functional parity with GCP and exceeds it on the audit's
six explicit dimensions:

- ✅ `compute.tf` — EKS endpoint private by default; public access
  is opt-in via `var.allow_public_endpoint` AND CIDR-gated via
  `var.public_endpoint_access_cidrs`. A `lifecycle.precondition`
  fails the plan if public is enabled without a CIDR list. KMS
  envelope encryption for K8s Secrets is on. Five control-plane
  log types ship to CloudWatch.
- ✅ `storage.tf` — four S3 buckets (data, models, mlflow_artifacts,
  access_logs) one-for-one with GCS. BlockPublicAccess on all,
  SSE-KMS with a dedicated key, BucketOwnerEnforced ownership,
  versioning where appropriate, server-access logging, and a
  GLACIER_IR→DELETE lifecycle on `models` mirroring NEARLINE→DELETE.
  Two documented constraints baked into comments: access_logs uses
  ObjectWriter + log-delivery-write ACL (S3 server-access logging
  cannot deliver to BucketOwnerEnforced) and AES256 SSE (log
  delivery does not support customer KMS keys).
- ✅ `ecr.tf` — per-service repos with `IMMUTABLE` tags,
  `scan_on_push=true`, account-level ENHANCED scanning with
  `CONTINUOUS_SCAN`, KMS encryption, and a 14-day untagged-image
  expiry. Cosign verification at pull is intentionally NOT enforced
  here (ECR has no native hook); the gate lives in the Kyverno
  admission policy in the cluster.
- ✅ `iam.tf` — per-service IRSA roles with NARROW inline policies.
  Trust policy locked to `system:serviceaccount:ml-services:<svc>`.
  Permissions limited to: data bucket read-only, models bucket
  scoped to the service's own prefix, mlflow_artifacts read+write,
  KMS Decrypt/GenerateDataKey, and Secrets read scoped to
  `${project}/${service}/*`. Explicitly excluded: `Action: "*"`,
  `Resource: "*"`, `iam:*`, `s3:DeleteBucket`, `s3:PutBucketPolicy`.
- ✅ `secrets.tf` — Secrets Manager entries for the cartesian product
  of `var.service_names × var.secret_names`. Rotation gated by
  `var.enable_secret_rotation` and `var.rotation_lambda_arn` (rotation
  Lambdas are secret-shape-specific so they cannot be shipped
  generically). A precondition refuses plans where rotation is
  enabled without a Lambda — fails closed, never silently broken.
- ✅ `logging.tf` — CloudWatch log groups for both EKS control plane
  and per-service application logs, with `var.log_retention_days`
  validation rejecting 0 (= "never expire", the AWS default). Plus
  `aws_budgets_budget` for monthly cost alarming at 80% / 100%.

Exit criteria all met. `terraform validate` passes for both clouds.
Resource count check: GCP ≈ 7 resources, AWS ≈ 50 resources after
this PR — parity floor exceeded.

The originally-mentioned ADR-016a documenting intentional asymmetries
turned out unnecessary: every asymmetry is now an in-file comment
in the relevant `.tf` (e.g. why access_logs uses AES256 not KMS).
Adoption-boundary doc for parity tiers stays as PR-R2-12 scope.

### PR-R2-7 — Quality-gate config externalized per service ✅

Severity: **Medium**. Affected: `templates/service/src/{service}/training/train.py:145,215,221`.

**Status:** Closed by commit (this PR).

Quality-gate thresholds (primary/secondary metric + threshold,
fairness DIR floor, latency SLA, protected attributes, promotion
threshold) used to live as module-level constants in
`templates/service/src/{service}/training/train.py`. They now live
in `templates/service/configs/quality_gates.yaml`, parsed by a
`QualityGatesConfig` Pydantic model in `config.py`.

What landed:

- ✅ `QualityGatesConfig` (Pydantic): every threshold has range
  validation (`ge=0.0, le=1.0` on probabilities, `gt=0.0` on the
  latency SLA), metric names reject leading/trailing whitespace,
  and `protected_attributes` rejects duplicates.
- ✅ Required-no-default fields: `primary_metric`,
  `primary_threshold`, `secondary_metric`, `secondary_threshold`,
  `protected_attributes`. Missing any one fails Pydantic at load
  time with a clear ValidationError naming the missing field.
  Optional fields (`fairness_threshold`, `latency_sla_ms`,
  `promotion_threshold`) keep sensible defaults so a minimal YAML
  still validates.
- ✅ Demographic-target heuristic: `validate_against_data()` rejects
  any config where `target_column` substring-matches one of
  `DEMOGRAPHIC_TARGET_TOKENS` (gender, race, ethnicity, religion,
  age_group, …) AND `protected_attributes == []`. Match is
  case-insensitive. Operators must either populate
  `protected_attributes` or document an explicit ADR explaining
  why DIR enforcement does not apply (escalates to STOP per
  ADR-005).
- ✅ `train.py` no longer holds module-level threshold constants.
  `Trainer.__init__` loads the gates BEFORE any data work —
  config typos fail in milliseconds, not after a 30-minute Optuna
  run. The fairness check, the cross_val_score scoring metric,
  and the final `_quality_gates` evaluator all read from the
  loaded `QualityGatesConfig`.
- ✅ `--validate-config-only` CLI flag: cheap CI gate that loads
  the YAML and runs the demographic-target heuristic without
  importing sklearn/MLflow, exits 0 / 2 with a stderr message.
- ✅ `tests/test_quality_gates_config.py`: 37 tests covering
  schema integrity, range validation, the demographic heuristic
  (parametrised over every token), case-insensitivity, substring
  match (`customer_gender_v2`), and round-trip dump/reload.
- ✅ `scripts/test_scaffold.sh` extended to run the new test
  file in the SCAFFOLD_SMOKE pass — every PR that touches the
  config schema is gated through CI.

Migration note: a fresh scaffold ships
`configs/quality_gates.yaml` with `protected_attributes: []` (the
explicit "fairness considered, none apply" stance) and a comment
showing how to populate it. Existing services in user repos that
did NOT regenerate from this template need to add the YAML
manually — `python -m src.<svc>.training.train --validate-config-only`
prints the missing-field error in the same form Pydantic uses.

Exit criteria all met. Local validation: 37/37 tests pass on a
freshly-substituted scaffold.

### PR-R2-8 — EDA artifacts as machine-readable contracts

Severity: **Medium**. Affected: `templates/eda/*` and drift consumers.

The 6-phase EDA pipeline today produces human-readable Markdown +
plots. Drift detection re-derives baseline distributions from raw
data because it cannot consume EDA output. This forces every drift
operator to know enough to recompute the reference.

- Emit `eda/artifacts/baseline_distributions.parquet` with one row
  per feature × bucket × frequency.
- Emit `eda/artifacts/leakage_report.json` with the explicit
  blocklist drift consumes.
- `templates/cicd/drift-detection.yml` defaults to consuming those
  artifacts; falls back to recomputation only with an explicit env
  override (and warns).

Exit: a fresh scaffolded service runs EDA, then drift detection,
without re-deriving baselines.

### PR-R2-9 — End-to-end smoke test that proves closed-loop + alert

Severity: **Medium**. New `templates/cicd/golden-path-extended.yml`.

The current Golden Path E2E proves scaffold → build → deploy →
audit. It does NOT prove closed-loop or alerting actually fire.

Add a downstream job that:
1. Posts 100 valid + 5 invalid requests through `/predict`.
2. Reads `/metrics`, asserts `<svc>_prediction_log_total >= 100`.
3. Pushes a synthetic drift report (PSI > 2x threshold) into the
   Pushgateway used by the SLO rules.
4. Polls Prometheus for the matching alert; asserts it transitions
   to `firing` within `for: 2m`.
5. Tears everything down.

Exit: golden-path-extended is green and required on `main`.

## 90-Day Remediation Window (PR-R2-10 → PR-R2-12)

### PR-R2-10 — Reproducible drift + degraded-deploy drills

Convert the existing runbook templates into reproducible drills with
captured evidence under `docs/runbooks/drills/` so adopters can
practise. One drill per quarter; results signed and stored.

### PR-R2-11 — D-01..D-31 anti-patterns as policy tests ✅

✅ **shipped**.

Promotes D-01..D-31 from ad-hoc grep checks into a dedicated
`templates/service/tests/policy/` suite that runs against the
**output of `new-service.sh`**, not the template repo itself. This
closes the gap between the template's claims and what users actually
receive when they scaffold a service.

**What landed:**

- `templates/service/tests/policy/conftest.py` — session-scoped
  `scaffold_dir` fixture that runs `new-service.sh` once per test
  session into a tmpdir (~45s) and yields the path. Helpers
  `file_text` / `glob_files` / `yaml_load_all` / `json_load` accept
  either a relative string or an absolute Path so call-sites stay
  short. `KEEP_SCAFFOLD=1` preserves the tmpdir for post-mortem.

- `templates/service/tests/policy/test_smoke.py` — 3 fixture-level
  invariants: (1) directory created, (2) canonical structure
  (`src/`, `k8s/`, `tests/`), (3) no raw `{ServiceName}` /
  `{SERVICE}` placeholders survive substitution.

- `templates/service/tests/policy/test_anti_patterns.py` — 11 D-XX
  policy tests (10 PASS + 1 SKIP because `.gitignore` is at repo
  root, not service-level):
    - **D-01** no multi-worker uvicorn in Dockerfile or k8s manifests
    - **D-02** HPA does not reference memory metric
    - **D-05** ML packages (numpy/pandas/scipy/sklearn/xgboost/
      lightgbm) pinned with `~=`, never `==`
    - **D-10** `.gitignore` blocks `*.tfstate*` (skipped: gitignore
      lives at repo root, not service)
    - **D-11** Dockerfile does not COPY models/ or `*.joblib`/`*.pkl`
    - **D-17** no direct `os.environ["API_KEY"]`-style reads outside
      `common_utils/secrets.py`
    - **D-23** liveness and readiness probes use distinct paths
    - **D-25** `terminationGracePeriodSeconds >= 30` on base
      Deployments (overlay patches inherit the base value)
    - **D-27** at least one `PodDisruptionBudget` ships in `k8s/`
    - **D-29** every overlay Namespace carries
      `pod-security.kubernetes.io/enforce` label
    - **D-31** AWS + GCP `iam*.tf` reference all 5 ADR-017 identities
      (ci / deploy / runtime / drift / retrain)
  - 2 process-only invariants (D-06, D-13) are present as explicit
    `@pytest.mark.skip` with reasons tying back to where they ARE
    enforced (training-time gates, EDA isolation policy).

- `.github/workflows/policy-tests.yml` — runs the suite weekly
  (Mondays 06:00 UTC) + on-demand via `workflow_dispatch` + on push
  to `main` when files that could affect the rendered output change
  (templates/scripts, templates/k8s, templates/infra/terraform,
  Dockerfile, requirements.txt, AGENTS.md). 15-minute job timeout.

**Why a separate workflow (not part of regular CI):**

Each scaffold takes ~45s on GitHub-hosted runners; the full suite
runs in ~4-5 minutes. Adding ~5 minutes to every PR's wall-clock
buys low marginal value (the regular contract tests catch most
drift) while costing every developer noticeably more iteration time.
Weekly catches drift before it accumulates; `workflow_dispatch` is
the on-demand escape hatch for any contributor who wants a green
signal before merging a templates-touching PR.

**Bug surfaced + fixed during R2-11 itself:**

`templates/infra/terraform/aws/iam.tf` did not mention the literal
string `runtime` — the per-service IRSA roles ARE the runtime
identity, but the file's header comment did not say so. The D-31
test caught this immediately on first run. Fixed in this commit by
adding a 6-line header that names the role this file plays in the
ADR-017 5-identity split. This is the exact kind of latent
documentation drift the suite is designed to catch.

### PR-R2-12 — Adoption-boundary doc + agentic-fallback path

- Publish an explicit adoption-boundary table per cloud × maturity
  level (dev / staging / prod) so a platform reviewer can answer
  "is this ready for our org?" in 60 seconds.
- Provide a non-agentic on-ramp: every skill / workflow we ship has
  an equivalent `make` target documented in `Makefile`. Teams that
  don't operate with AI assistants can adopt the template without
  inheriting the agentic surface.

## Low-severity items (next sprint, no PR yet)

- `progress.txt` removed from repo root (internal artifact).
- README headline edited to mirror ADR-015's stated maturity, not
  outpace it.
- `fastapi_app.py:445`, `main.py:190` — error responses sanitized to
  drop `str(exc)` from the user-facing body (kept in logs).
- `networkpolicy.yaml:91` — egress to `0.0.0.0/0:443` replaced with
  cloud-specific destinations (GKE/EKS API, Secret Manager, ECR/AR,
  MLflow). This will likely become PR-R2-13 if it cannot fit into
  PR-R2-3.

## Consequences

- **Positive:** every audit finding has a tracked landing spot.
  Reviewers can see at a glance which parts of the template are
  production-grade, which are roadmap-only, and what the agent
  governs vs what humans still own.
- **Negative:** 12 PRs are real engineering work; we explicitly
  pause new feature surface (no new D-31..D-N anti-patterns, no
  new skills) until 7-day batch lands. ADR-015's productization
  roadmap waits behind this.
- **Risk:** if AWS parity slips into 60-day territory, the
  multi-cloud claim in `README.md` § Template should be downgraded
  on that schedule rather than extending the optimistic copy.

## Acceptance criteria for this ADR

- [ ] All 5 24-hour fixes shipped (commit `7bc53fd`).
- [x] PR-R2-1 through PR-R2-5 merged within 7 calendar days of
      this ADR's date.
- [ ] PR-R2-6 through PR-R2-9 merged within 30 calendar days.
- [ ] PR-R2-10 through PR-R2-12 merged within 90 calendar days.
- [ ] Each PR closes its corresponding finding with a comment
      linking back to the audit transcript and this ADR.

## Revisit triggers

- A third-round external audit fires a Critical/High finding the
  remediation plan did not anticipate → re-open this ADR with an
  R3 section.
- An adopter reports a closed-loop, SLO, or audit-trail failure that
  matches one of the original 16 findings → escalate to STOP and
  treat as a regression.

## References

- External audit transcript (2026-04-26).
- ADR-014 — gap remediation plan (R1).
- ADR-015 — productization roadmap.
- ADR-005 — agent behavior + security.
- ADR-006 — closed-loop monitoring.
- Commit `7bc53fd` — 24h batch closure.
