# ADR-024 — May 2026 Audit Remediation & Posture Correction

- **Status**: Accepted
- **Date**: 2026-05-04
- **Supersedes / amends**: ADR-020 (R4), ADR-016 (R2). Does NOT supersede
  ADR-001 — the template scope boundaries remain unchanged.
- **Authors**: Template maintainer + Staff MLOps Engineer (audit persona).

## Context

A Staff-level audit was performed against the repository under these
evaluation dimensions: architecture & agentic design, ML serving,
Kubernetes, infrastructure (Terraform), CI/CD, data validation,
observability, security, tests, documentation, product quality, and
agent protocols (AUTO / CONSULT / STOP).

The audit identified **23 findings**:

| Severity | Count | Focus areas |
| ---------- | ------- | ------------- |
| Critical | 4 | K8s serving chain, drift pipeline, admission security |
| High | 9 | Supply chain, auth, audit trail, posture honesty |
| Medium | 8 | Threadpool sizing, NetworkPolicy, tests, observability |
| Low | 2 | Runbooks, missing action-plan stub |

The most important structural finding was **posture dishonesty**: the
README claimed "Production-ready by design" and shipped a numeric
self-rating table while the underlying capabilities had never been
validated against a real cloud cluster under load (L4 evidence absent).

## Decision

1. **Posture correction** — the template is "Designed-ready
   (L1+L2+L3)" until real GKE + EKS L4 evidence is captured.
   Numeric self-rating removed from the README. Phase 1 contracts
   (Memory Plane, CI self-healing) explicitly demoted from hero
   capabilities to "shipped as contract, not validated in production".

2. **Remediate all 23 findings in a single release** (v0.15.0)
   rather than staging over multiple minor versions. The findings
   interact: fixing the drift CronJob (CRIT-2, CRIT-3) without
   fixing the NetworkPolicy default-deny (MED-11) leaves the
   init container failing to fetch reference data; fixing
   `/model/info` auth (MED-3) without fixing `/metrics` access
   control (MED-4) leaves model fingerprinting open through a
   different path.

3. **Hard-fail supply-chain scans with explicit baselines**.
   `soft_fail: true` on tfsec/checkov/trivy is removed. The
   `.security-baselines/` directory documents accepted findings
   with a rationale and an expiry — every exception is reviewable
   in a PR and the path to a zero-baseline state is explicit.

4. **Bus-factor=1 disclosed, not concealed**. The single-maintainer
   reality is documented in `.github/CODEOWNERS` and both deploy
   workflows (`deploy-gcp.yml`, `deploy-aws.yml`). The "2 reviewers"
   production gate is labelled aspirational; adopters are told
   exactly what to configure on their fork.

5. **Dynamic-risk protocol must query the signal source over
   authenticated TLS**. The `risk_context` fallback was already
   safe (escalates on error, never relaxes); this ADR adds the
   positive contract: only `http(s)://` schemes, optional Bearer
   auth, optional custom CA bundle, and refusal to skip TLS
   verification outside `dev`/`local`.

6. **Model artifacts are cryptographically signed at retrain time**.
   `retrain-service.yml` now produces a cosign blob signature
   (`model.joblib.sig` + `.pem`) published alongside the model in
   the cloud bucket; the deploy-side verification command lives in
   `docs/runbooks/deploy-gke.md`.

## Consequences

### Positive

- **Closed-loop story survives first-contact with PSS-restricted
  clusters**. The drift CronJob now passes Pod Security Admission
  without adopter modifications; previously the chain was "shipped
  broken, alert silenced by adopters".
- **Supply chain is provably verifiable end to end**. Image digest +
  SBOM attestation + model blob signature are all rooted in Rekor
  via Sigstore keyless signing. An attacker who compromises the
  model bucket cannot silently substitute a model.
- **Runbooks are usable under incident pressure**. Previously each
  critical runbook was ~10 lines of prose; now every one has
  trigger criteria, pre-flight, procedure, verification table,
  audit + comms, exit criteria, failure paths, and anti-patterns.
- **Posture claims are defensible**. An adopter reviewing the
  README can no longer misread the template as a drop-in GA
  product; the L1/L2/L3/L4 layer disclosure makes the gap
  explicit.

### Negative

- **Adopter friction on first scaffold**. The `new-service.sh`
  scaffolder now substitutes `{ORG}/{REPO}` — adopters who scaffold
  from a freshly-cloned fork without a configured remote will get
  the `YOUR_ORG/YOUR_REPO` fallback with a loud warning. This is
  intentional: a silent fallback would let a Kyverno policy ship
  that never accepts any signature.
- **Baselines now required for every scan exception**. Adding an
  accepted CVE or a skipped Checkov check now requires a PR that
  touches `.security-baselines/` with a rationale comment. This is
  more overhead for adopters who previously added a CI `continue-on-error`.
- **Audit entries are mandatory on every retrain run**. A retrain
  that fails before the audit step can still fail silently, but
  the `if: always()` guard is in place and the workflow summary
  shows the missing entry.

### Neutral

- The v0.x line continues to reserve v1.0.0 for the first real-cluster
  L4 validation. This ADR does not bring v1.0.0 forward.

## Alternatives considered

1. **Stage the remediation over v0.15 → v0.17**. Rejected because
   the findings interact (see Decision §2) and partial remediation
   would ship an inconsistent template state to adopters who
   scaffold at a mid-point tag.
2. **Keep `soft_fail: true` on supply-chain scans and instead add
   a monthly compliance audit**. Rejected because it keeps the
   signal-to-noise problem: scan output is ignored at PR review
   time, and the monthly audit becomes a ritualistic checkbox.
   Hard-fail + explicit baseline is the only contract that makes
   the exception list visible at PR time.
3. **Move `argo-rollout.yaml` into `base/` kustomization**. Rejected
   because it would collide with `deployment.yaml` (same pod
   template, same service selector) — dual-shipping requires an
   explicit operator opt-in, so the file stays OPT-IN with a
   header comment explaining the enablement patch.

## Compliance & evidence

| Finding | Evidence |
| --------- | ---------- |
| CRIT-1 | `templates/k8s/base/kustomization.yaml` `resources:` |
| CRIT-2 | `templates/k8s/base/cronjob-drift.yaml` `securityContext:` (pod + container) |
| CRIT-3 | `templates/k8s/base/cronjob-drift.yaml` `initContainers:` + `volumes:` |
| CRIT-4 | `templates/k8s/base/argo-rollout.yaml` full rewrite |
| HIGH-1 | `.github/workflows/validate-templates.yml` + `.security-baselines/` |
| HIGH-2 | `.github/CODEOWNERS` + `templates/cicd/deploy-*.yml` |
| HIGH-3–5 | `README.md` §"Production-ready scope" + §"Recent hardening" |
| HIGH-6 | `templates/service/app/fastapi_app.py` `ENVIRONMENT` refusal |
| HIGH-7 | `templates/cicd/retrain-service.yml` `Emit audit entry` step |
| HIGH-8 | `templates/cicd/retrain-service.yml` `Sign model with cosign` step |
| HIGH-9 | `templates/common_utils/risk_context.py` auth + TLS |
| MED-1 | `templates/service/tests/integration/test_train_serve_drift_e2e.py` |
| MED-2 | `templates/service/app/fastapi_app.py` threadpool sizing |
| MED-3 | `templates/service/app/main.py` `/model/info` auth |
| MED-4 | `templates/service/app/fastapi_app.py` `/metrics` docstring |
| MED-5 | `templates/service/constraints.txt` |
| MED-6 | `templates/common_utils/tracing.py` + `app/main.py` wiring |
| MED-8 | `templates/service/pyproject.toml` version → 0.1.0 |
| MED-9 | `examples/minimal/serve.py` warm-up + `/ready` |
| MED-10 | `templates/scripts/new-service.sh` `{ORG}/{REPO}` resolution |
| MED-11 | `templates/k8s/base/networkpolicy.yaml` + all overlay patches |
| LOW-4 | `docs/audit/ACTION_PLAN_R4.md` (pre-existing) |
| LOW-5 | `docs/runbooks/{rollback,deploy-gke,deploy-aws,secret-breach}.md` |

## Review

Revisit when:

- First real-cluster L4 evidence is captured (promotes template to v1.0.0).
- A second maintainer is added to CODEOWNERS (unblocks the "2 reviewers" claim).
- Any baseline entry hits its expiry without being closed.
