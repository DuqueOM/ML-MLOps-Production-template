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

### PR-R2-1 — API authentication + admin endpoint protection

Severity: **High**. Affected: `templates/service/app/main.py:95,169`.

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

### PR-R2-2 — Pin init container + CronJob images by digest

Severity: **High**. Affected: `templates/k8s/base/deployment.yaml:46`,
`cronjob-drift.yaml:25`, `cronjob-performance.yaml:36`.

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

### PR-R2-3 — Neutralize K8s base manifests

Severity: **High**. Affected: `deployment.yaml:8,11`, `rbac.yaml:16`,
`networkpolicy.yaml:17`.

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

### PR-R2-5 — Replace `curl | bash` toolchain installs with versioned actions

Severity: **Medium** (but contradicts the supply-chain story).
Affected: `deploy-common.yml:187`, `validate-templates.yml:168`.

- Replace `curl -L ... | bash` for kustomize, jq, etc., with:
  - `imranismail/setup-kustomize@v2` (pin to commit SHA)
  - `dcarbone/install-jq-action@v3`
  - `aquasecurity/setup-trivy@v0.x` (already done in audit-r2 §1)
- Anything that absolutely requires raw download installs to a
  per-job temp dir AND verifies a known SHA-256 of the binary.

Exit: `grep -rE 'curl[^|]*\| *bash' .github/workflows
templates/cicd/` returns nothing.

## 30-Day Remediation Window (PR-R2-6 → PR-R2-9)

### PR-R2-6 — AWS parity: storage, registry, IAM, secrets, logging

Severity: **High**. Affected: `templates/infra/terraform/aws/*`.

GCP is roughly starter-grade serious; AWS is currently scaffold-only
(audit observation, file:line). Bring AWS to functional parity with
GCP across:

- `compute.tf` — EKS endpoint private by default; public-only
  override behind a `var.allow_public_endpoint` with a comment
  pointing to ADR-018 (parity tier).
- `storage.tf` — S3 buckets matching GCS layout (raw / processed /
  reference / models), block public access, SSE-KMS by default.
- `iam.tf` — narrow per-service IRSA policies (read-only on data
  buckets, write-only on model bucket, no `*:*` actions).
- `ecr.tf` — registry per service with immutable tags and signed-only
  pull policy.
- `secrets.tf` — AWS Secrets Manager rotation policy enforced.
- `logging.tf` — CloudWatch logs with retention parity to GCP
  (default 30 days dev, 90 days staging, 365 days prod).

Exit: `terraform plan` for each AWS env emits resource counts ≥ GCP's
on the matching env; ADR-016a documents intentional asymmetries.

### PR-R2-7 — Quality-gate config externalized per service

Severity: **Medium**. Affected: `templates/service/src/{service}/training/train.py:145,215,221`.

- Move quality-gate thresholds (split strategy, protected attributes,
  promotion threshold, fairness DIR floor) from defaults inside
  `train.py` to `configs/quality_gates.yaml` per service.
- The schema is enforced by Pydantic; missing required keys (e.g.
  `protected_attributes`) refuse to load.
- `train.py` rejects models that pass with `protected_attributes:
  []` AND `target` looks demographic — heuristic warning escalates
  to STOP per ADR-005.
- Document the migration: existing services keep their current
  thresholds via a generated `configs/quality_gates.yaml` from
  per-service ADRs.

Exit: `python -m src.<svc>.training.train --validate-config-only`
fails on any service whose config is incomplete.

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

### PR-R2-11 — D-01..D-30 anti-patterns as policy tests

Today D-01..D-30 are documented + enforced by ad-hoc grep checks.
Promote them to policy tests over **scaffolded repos** (not just the
template repo) — a dedicated `tests/policy/` suite that runs against
the output of `new-service.sh`. This catches drift between the
template's claims and what users actually receive.

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
- [ ] PR-R2-1 through PR-R2-5 merged within 7 calendar days of
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
