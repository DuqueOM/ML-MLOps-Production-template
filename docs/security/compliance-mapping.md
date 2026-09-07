# Informal compliance crosswalk

> **Status: INFORMAL.** This document is **NOT a compliance program,
> a SOC 2 control matrix, a GDPR DPA, or a HIPAA risk assessment**.
> It is a starting-point mapping between the controls this template
> ships and the categories adopters are commonly asked about.
>
> **Closes external-feedback gap 4.1 (May 2026 triage).**

## What this document IS

A pointer document. Each row links a feature shipped in this template
to the high-level compliance category it materially HELPS with — so
adopters who must comply can jump-start their own evidence
collection rather than re-discovering what the template covers.

## What this document is NOT

Per [`ADR-001`](../decisions/ADR-001-template-scope-boundaries.md):

> Compliance requires legal review, organizational policies, and
> audit infrastructure. Code templates can't substitute for
> compliance programs.

This file does NOT:

- Constitute legal or compliance advice.
- Map every shipped control to every applicable regulation.
- Replace a SOC 2 Type II audit, a HIPAA gap assessment, or a GDPR
  Article 30 record of processing.
- Imply that an adopter using this template is automatically compliant
  with anything.

If you need certifiable evidence, your auditor — not this README —
defines the bar.

---

## Crosswalk table

The mappings below cite SOC 2 Trust Service Criteria (CC = Common
Criteria; A = Availability), GDPR articles, and HIPAA Security Rule
sections. Coverage is **partial** by design (single-team scope per
ADR-001).

### Identity & access

| Control category | Shipped artifact | SOC 2 | GDPR | HIPAA |
| ------------------ | ------------------ | ------- | ------ | ------- |
| Workload identity (no static keys) | `templates/service/k8s/base/serviceaccount.yaml` + IRSA / Workload Identity (D-18) | CC6.1, CC6.6 | Art 32 | §164.312(a)(1) |
| RBAC least-privilege per service | `templates/service/k8s/base/rbac.yaml` | CC6.3 | Art 32 | §164.312(a)(1) |
| Network segmentation | `networkpolicy-deny-default.yaml` + per-overlay allowances | CC6.6 | Art 32 | §164.312(e)(1) |
| Service account scoping | One SA per scaffolded service, namespace-scoped | CC6.3 | — | §164.308(a)(4) |

### Secrets handling

| Control category | Shipped artifact | SOC 2 | GDPR | HIPAA |
| ------------------ | ------------------ | ------- | ------ | ------- |
| No hardcoded credentials | `common_utils/secrets.py` (D-17) + gitleaks pre-commit | CC6.1 | Art 32 | §164.312(c)(1) |
| Cloud-native secret store | AWS Secrets Manager / GCP Secret Manager via IRSA / WI | CC6.1, CC7.1 | Art 32 | §164.312(a)(2)(iv) |
| Secret rotation runbook | `agentic/skills/secret-breach-response/` + `/secret-breach` workflow | CC7.4, CC9.2 | Art 33 | §164.308(a)(6) |
| Static credential refusal | `secrets.py` refuses os.environ fallback in staging/production (D-18) | CC6.1 | Art 32 | §164.312(a)(2)(i) |

### Supply chain

| Control category | Shipped artifact | SOC 2 | GDPR | HIPAA |
| ------------------ | ------------------ | ------- | ------ | ------- |
| Image signing (Cosign keyless) | `deploy-{gcp,aws}.yml` cosign sign step | CC8.1 | — | §164.308(a)(5)(ii)(B) |
| Image digest pinning enforced | `kyverno-image-verification.yaml` `require-image-digest` policy + `kyverno-smoke.yml` CI gate | CC8.1 | — | §164.312(c)(1) |
| SBOM per image | Cosign attest CycloneDX in deploy workflows | CC8.1, CC9.2 | — | §164.308(a)(8) |
| Model blob signing | `retrain-service.yml` cosign sign-blob + `model-verifier` init container | CC8.1 | — | §164.312(c)(1) |

### Audit & accountability

| Control category | Shipped artifact | SOC 2 | GDPR | HIPAA |
| ------------------ | ------------------ | ------- | ------ | ------- |
| Append-only audit trail | `ops/audit.jsonl` + `scripts/audit_record.py` | CC4.1, CC7.3 | Art 30 | §164.312(b) |
| Per-deploy audit entry | `templates/service/.github/workflows/deploy-common.yml` records `if: always()` | CC7.3 | Art 30 | §164.308(a)(1)(ii)(D) |
| Risk-mode escalation logged | `risk_context.RiskContext` recorded per audit entry | CC4.1 | — | §164.312(b) |
| MLflow experiment lineage | git_commit, params, metrics, artifacts | CC4.1, CC8.1 | Art 22 | §164.312(b) |

### Availability & continuity

| Control category | Shipped artifact | SOC 2 | GDPR | HIPAA |
| ------------------ | ------------------ | ------- | ------ | ------- |
| SLO + multi-window burn-rate alerts | `slo-prometheusrule.yaml` (CRIT-1) | A1.1 | — | §164.308(a)(7)(ii)(B) |
| HPA per service | `hpa.yaml` | A1.1 | — | §164.308(a)(7)(ii)(B) |
| Pod disruption budget | `pdb.yaml` | A1.1 | — | §164.308(a)(7)(ii)(B) |
| Rollback procedure (codified) | `agentic/skills/rollback/` + `/rollback` workflow | A1.3, CC7.4 | — | §164.308(a)(7)(ii)(B) |
| Drift heartbeat alert | `drift_cronjob_last_success_timestamp_seconds` | A1.1, CC7.2 | Art 22 | §164.312(b) |

### Data protection

| Control category | Shipped artifact | SOC 2 | GDPR | HIPAA |
| ------------------ | ------------------ | ------- | ------ | ------- |
| Schema validation at ingest | Pandera `DataFrameModel` + 3 validation points | CC8.1 | Art 5(1)(d) | §164.312(c)(1) |
| Prediction logger as transport (no redaction) | `prediction_logger.py` — adopter MUST drop PII upstream | CC8.1 | Art 5(1)(c) | §164.312(a)(2)(iii) |
| TLS/Auth on Prometheus | `risk_context.py` Bearer + CA bundle (HIGH-9) | CC6.7 | Art 32 | §164.312(e)(1) |
| Default-deny egress | `networkpolicy-deny-default.yaml` (MED-11) | CC6.6 | Art 32 | §164.312(e)(1) |

---

## What is NOT covered

Areas where adopters MUST bring their own controls:

- **PII detection/redaction**: per ADR-018 §"Phase 2", redaction is
  Phase 2 work. Today the contract is "drop PII upstream of
  `log_prediction()`" — see `tests/unit/test_prediction_logger_contract.py`.
- **Encryption at rest**: cluster-level (etcd, EBS / PD encryption)
  is the cloud platform's job. Template assumes the cluster is
  configured per the cloud's hardening guide.
- **Disaster recovery**: cross-region replication, RTO/RPO targets,
  backup retention. Out of scope (single-cluster template).
- **Vendor management / sub-processor list**: GDPR-specific, fully
  organizational.
- **Risk assessment / threat model**: each adopter's risk surface
  differs. The closest artifact this template ships is the
  `red-team-log.md` for the agentic surface.
- **Continuous compliance scanning**: third-party tools (Wiz, Prowler,
  Drata) sit on top of this template, not in it.

---

## How to use this document

1. **Map your obligations** to your auditor's required evidence list
   (SOC 2 Type II controls, GDPR Article 30 record, HIPAA risk
   analysis worksheet).
2. **Cross-reference with the table above**. For each row you can
   claim, link directly to the shipped artifact in your evidence
   inventory — the template's git history is the authoritative
   source.
3. **Document the gaps** explicitly. The "What is NOT covered"
   section above is your starting list of compensating controls
   you must implement separately.
4. **Re-run periodically.** The template ships ~12 minor releases
   per year; new releases may close gaps OR raise new ones. Re-walk
   the table on every release that bumps `MAJOR` or any `MINOR`
   labeled `security` in CHANGELOG.md.

If you find this mapping wrong or stale, open a PR. The mapping is a
contract with adopters, not the author's private notes.
