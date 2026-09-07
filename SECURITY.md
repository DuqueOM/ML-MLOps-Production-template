# Security Policy

## Supported Versions

| Version | Supported |
| --------- | ----------- |
| Latest | :white_check_mark: |
| Previous | :x: |

## Reporting a Vulnerability

If you discover a security vulnerability in this template, please report it privately before disclosing it publicly.

### How to Report

**Preferred Method:**

- Send an email to: <DuqueOrtegaMutis@gmail.com>
- Use the subject line: `Security Vulnerability Report - ML-MLOps-Template`

**Alternative Methods:**

- GitHub's private vulnerability reporting: [Report Vulnerability](https://github.com/DuqueOM/ml-service-template/security/advisories/new)

### What to Include

1. **Vulnerability Type** (e.g., hardcoded secrets, insecure defaults, dependency issue)
2. **Affected Templates** (specific files or patterns)
3. **Impact Assessment** (what could go wrong if the template is used as-is)
4. **Reproduction Steps** (how to trigger the vulnerability)
5. **Suggested Mitigation** (optional but helpful)

### Response Timeline

| Severity | Response Time | Description |
| ---------- | --------------- | ------------- |
| Critical | 48 hours | Hardcoded credentials, RCE in templates |
| High | 7 days | Insecure defaults that expose data |
| Medium | 14 days | Missing security best practices |
| Low | 30 days | Minor improvements |

## Security Measures in This Template

### Built-In Protections

**Secret management (D-17, D-18)**

- `.gitleaks.toml` + pre-commit hook for secret detection
- CI `security-audit` job: `gitleaks-action` + credential pattern grep (AWS/GCP/GitHub tokens) + `os.environ`
  secret-name detection
- `templates/service/common_utils/secrets.py` — cloud-native loader that refuses to fall through to `os.environ` in staging/production
- Workload Identity (GCP) and IRSA (AWS) — no hardcoded credentials in pods

**Container & image security (D-11, D-19)**

- Multi-stage Docker builds, non-root USER, HEALTHCHECK
- Trivy vulnerability scan (blocks HIGH/CRITICAL) — CI gate
- **Syft SBOM** in CycloneDX + SPDX formats (90-day artifact retention)
- **Cosign keyless signing** via GitHub OIDC (no key management)
- **Cosign attest** of SBOM as CycloneDX attestation (SLSA L2 component)
- Init container pattern for model artifacts (no models baked into images)

**Admission control (D-19)**

- `templates/k8s/policies/kyverno-image-verification.yaml` — Kyverno ClusterPolicy
  - Rejects unsigned images in namespaces labeled `environment: production`
  - Verifies keyless Cosign identity + Rekor transparency log
  - Requires CycloneDX SBOM attestation (max 90 days old)
  - Companion policy `require-image-digest` — forbids tag-only refs in staging/prod

**Infrastructure (D-10)**

- Trivy config + Checkov for Terraform misconfigurations (ADR-046)
- Remote state (GCS / S3 + DynamoDB) enforced by rule `03-terraform.md`
- `.gitignore` blocks `terraform.tfstate`, `.tfvars` with secrets

**Code quality**

- bandit for Python security linting
- Type hints + mypy
- Pre-commit hooks (see `.pre-commit-config.yaml`)

**Automated updates**

- `dependabot.yml` for weekly dependency updates
- Renovate-compatible PR format

### Agent Behavior Protocol

The agentic system enforces **AUTO / CONSULT / STOP** modes per operation
(documented in `AGENTS.md`). Security-relevant operations are always STOP-class:

- `terraform apply prod` — STOP (requires PR + Platform Engineer approval)
- Secret rotation — STOP (chain to `/secret-breach` workflow, never silent)
- Model promotion to Production — STOP (governed by ADR-002)
- Any detection of a credential pattern — STOP (halt pipeline)

### Template Security Invariants

- **NEVER** commit secrets to tfvars or repository — use cloud Secrets Manager
- **NEVER** hardcode API keys, tokens, or passwords in any template file (D-17)
- **NEVER** use `os.environ["API_KEY"]` in production code paths (D-17) — use `common_utils.secrets.get_secret`
- **NEVER** use static AWS access keys or GCP JSON service-account keys in production (D-18)
- **ALWAYS** use IAM roles (IRSA / Workload Identity) instead of static credentials (D-18)
- **ALWAYS** sign production images with Cosign + attach SBOM (D-19)
- **ALWAYS** pin images by digest (`@sha256:...`) in staging/production (D-19)
- **ALWAYS** run Trivy + gitleaks + credential-pattern grep before pushing
- **ALWAYS** use `dependabot.yml` for automated dependency updates

### Incident Response

If a credential is leaked in the repo, logs, or an artifact:

1. **STOP** the pipeline immediately
2. Invoke the `/secret-breach` workflow (or the `secret-breach-response` skill)
3. Follow the 7-phase procedure: halt → classify → revoke → audit → rotate → clean history → notify → post-mortem
4. Never attempt silent rotation — audit trail is mandatory

The full procedure is codified in `agentic/skills/secret-breach-response/SKILL.md`.

### SLSA Compliance

This template targets **SLSA Level 2** out of the box:

- ✅ Source: GitHub (version-controlled, retention)
- ✅ Build: GitHub Actions hosted runners
- ✅ Provenance: Syft SBOM + Cosign attestation (keyless OIDC)
- ✅ Signed: `cosign sign` with GitHub OIDC identity
- ⚠️ Hermetic builds (SLSA L3): **deferred by ADR-001** — revisit when compliance regime requires it

### Documentation

- `docs/decisions/ADR-005-agent-behavior-and-security.md` — full rationale for security stack
- `agentic/rules/12-security-secrets.md` — always_on rule enforcing D-17/D-18/D-19
- `agentic/skills/security-audit/SKILL.md` — pre-build/pre-deploy audit procedure

## Historical security disclosures

> Defensive transparency for adopters who forked or copied template
> patterns from earlier releases. Each entry below was a real issue
> that has been remediated in the version listed; if you forked
> before that version, audit your downstream copy for the same
> pattern.

| ID | Disclosed | Versions affected | Issue | Remediation in template |
| ---- | ----------- | ------------------- | ------- | ------------------------- |
| HD-001 | 2026-04 | < v0.10 | `GCP_SA_KEY` JSON service account key was the documented auth pattern in deploy workflows | Replaced with Workload Identity Federation (no static keys). Earlier forks should rotate any leaked key via `/secret-breach` and migrate to WIF. (D-18) |
| HD-002 | 2026-05 | < v0.15.0 | Prometheus scraping over plain HTTP, no Bearer auth, no CA verification | `risk_context.py` now requires Bearer token + TLS verification; `INSECURE_SKIP_VERIFY` refused outside dev/local. Forks should add the same controls. (HIGH-9 in ADR-024) |
| HD-003 | 2026-05 | < v0.15.0 | `argo-rollout.yaml` shipped without PSS-restricted `securityContext` while the canonical `deployment.yaml` had it | Both manifests now have full security parity (CRIT-3 in ADR-024). Forks that enabled progressive delivery before v0.15.0 should re-render. |
| HD-004 | 2026-05 | < v0.15.0 | `tfsec` / `checkov` / `trivy` ran with `soft_fail: true`, silently passing CRITICAL findings | Hard-fail with explicit per-finding baselines + expiry annotations; `security-baseline-expiry` CI gate forces ADR-backed extensions. (HIGH-1 in ADR-024) |

If you find an issue NOT listed here, please follow the Reporting a
Vulnerability section above so it can be added.

## Security Contacts

- **Lead**: Duque Ortega Mutis
- **Email**: <DuqueOrtegaMutis@gmail.com>
- **GitHub**: [@DuqueOM](https://github.com/DuqueOM)

---

**Last Updated**: May 2026 — added Historical security disclosures
section (HD-001..HD-004) per external-feedback gap 4.2.
