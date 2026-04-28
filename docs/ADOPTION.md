# Adoption Boundary & Non-Agentic On-Ramp

This document is the canonical answer to two questions a platform reviewer
asks when evaluating this template:

1. **"Is this ready for our org?"** — answered by the maturity matrix below.
2. **"Can my team adopt it without using AI agents?"** — answered by the
   make-target equivalents.

Authority: ADR-016 PR-R2-12.

---

## 1. Maturity matrix

Each capability is rated **per environment**. Definitions:

- **ready** — works out of the box after standard configuration; covered by
  contract tests; documented in a runbook
- **partial** — works but requires team-specific decisions or a follow-on PR
  before going live (see Notes column)
- **roadmap** — the template documents the intent and may include
  scaffolding, but you would build the production surface yourself

### Compute & networking

| Capability | dev | staging | prod | Notes |
|---|---|---|---|---|
| GKE cluster + node pool split (system / workload) | ready | ready | ready | PR-A3 cluster defaults; workload taint enforced |
| EKS cluster + node group split (system / workload) | ready | ready | ready | Mirrors GCP; same taint contract |
| VPC networking (custom-mode + private subnets) | ready | ready | ready | `network_mode = "managed" \| "existing"` |
| Private GKE/EKS API endpoint | ready | ready | ready | `enable_private_endpoint` defaults to false in dev for ergonomics; flip to true in staging/prod |
| Workload Identity (GCP) / IRSA (AWS) | ready | ready | ready | D-18 enforced by contract tests; 5-identity split per ADR-017 |
| Deny-default NetworkPolicy | ready | ready | ready | `k8s/base/networkpolicy-deny-default.yaml` selects all pods |
| Cilium / advanced eBPF policies | roadmap | roadmap | roadmap | Out of scope; bring your own CNI overlay |

### Container & supply chain

| Capability | dev | staging | prod | Notes |
|---|---|---|---|---|
| Multi-stage Dockerfile (slim runtime) | ready | ready | ready | Base image pinned by digest in staging/prod overlays |
| Init-container model fetch (D-11) | ready | ready | ready | Models never in the image |
| Cosign keyless signing | ready | ready | ready | OIDC via GitHub Actions |
| SBOM (Syft / CycloneDX) attestation | ready | ready | ready | D-30 enforced; cosign attest in deploy workflow |
| Kyverno admission policies (verify-images) | ready | ready | ready | `verifyImages` rule on prod namespace |
| SLSA L3 hermetic builds | roadmap | roadmap | roadmap | Out of scope; would require BuildKit Frontend changes |
| Image vulnerability scanning gate | partial | partial | partial | Trivy runs in CI; threshold (block on HIGH+) is team decision |

### Secrets & IAM

| Capability | dev | staging | prod | Notes |
|---|---|---|---|---|
| Secrets via cloud manager (GSM/ASM) | ready | ready | ready | Per-service IAM binding only |
| `common_utils.secrets.get_secret()` loader | ready | ready | ready | D-17 enforced by policy test |
| Secret rotation procedure | ready | ready | ready | `/secret-breach` workflow + skill |
| HashiCorp Vault integration | roadmap | roadmap | roadmap | Deferred by ADR-001 (revisit if IRSA/WI insufficient) |
| 5-identity IAM split (ci/deploy/runtime/drift/retrain) | ready | ready | ready | D-31 enforced by policy test on scaffolded output |

### ML quality & observability

| Capability | dev | staging | prod | Notes |
|---|---|---|---|---|
| Pandera schema validation in serving + drift | ready | ready | ready | PR-R2-4; second validation wall |
| MLflow tracking + model registry | ready | ready | ready | Self-hosted on K8s; CMEK-backed |
| Quality gates on promotion (DIR ≥ 0.80, primary metric, latency) | ready | ready | ready | PR-B1; per-service `quality_gates.yaml` |
| Drift detection (PSI quantile-based) | ready | ready | ready | D-08 enforced; CronJob with heartbeat alert |
| Sliced performance monitoring (concept drift) | ready | ready | ready | PR-C2; ground-truth join via `entity_id` |
| Prediction logging | ready | ready | ready | D-20/D-21/D-22 enforced; non-blocking + buffered |
| Multi-window burn-rate alerts | ready | ready | ready | PR-C2; mandatory `runbook_url` |
| SLO error-budget tracking | ready | ready | ready | Recording rules + alert routes |
| Champion/challenger online experiments | partial | partial | partial | Argo Rollouts pattern documented; AnalysisTemplates require per-service tuning |
| Feature store integration | roadmap | roadmap | roadmap | PSI baseline + DVC suffices for 2-3 model scale (ADR-001) |

### Delivery

| Capability | dev | staging | prod | Notes |
|---|---|---|---|---|
| 4-job deploy chain (build → dev → staging → prod) | ready | ready | ready | D-26 enforced; GitHub Environment Protection |
| `terraform plan` nightly drift detection | ready | ready | ready | PR-A4; opens dedup'd `infra-drift` issue |
| Argo Rollouts canary template | partial | partial | partial | AnalysisTemplate scaffolded; metric thresholds per service |
| Rollback runbook + automation | ready | ready | ready | `/rollback` workflow + `make rollback` |
| Reproducible drills (drift, deploy-degraded) | ready | ready | ready | PR-C3; evidence under `docs/runbooks/drills/` |

### Governance

| Capability | dev | staging | prod | Notes |
|---|---|---|---|---|
| ADRs for non-trivial decisions | ready | ready | ready | 17 ADRs cover all design choices |
| Audit trail (append-only `ops/audit.jsonl`) | ready | ready | ready | ADR-014; CLI `scripts/audit_record.py` |
| Anti-pattern policy tests on scaffolded output | ready | ready | ready | PR-R2-11; D-01..D-31 enforced |
| Agent risk-context dynamic mode (AUTO→CONSULT→STOP) | ready | ready | ready | ADR-014; risk signals from Prometheus |
| SOC2 / HIPAA controls | roadmap | roadmap | roadmap | Organizational, not template (ADR-001) |

---

## 2. Non-agentic on-ramp

Every workflow we ship has either:

- a `make` target that runs the equivalent procedure end-to-end, or
- an explicit doc/runbook reference for the team to follow manually.

Teams that don't operate with AI assistants can adopt the template without
inheriting the agentic surface.

### Workflow → make-target / runbook map

| Slash workflow | Make equivalent | Runbook reference |
|---|---|---|
| `/new-service` | `make new-service NAME=<PascalCase> SLUG=<snake_case>` | `templates/scripts/new-service.sh --help` |
| `/eda` | `make eda` (runs the 6-phase pipeline) | `eda/README.md` |
| `/drift-check` | `make drift-check` (runs `scripts/drills/run_drift_drill.py`) | `docs/runbooks/drift-detection.md` |
| `/retrain` | `make retrain` (invokes training pipeline + quality gates) | `docs/runbooks/model-retrain.md` |
| `/load-test` | `make load-test` (Locust headless 60s) | `tests/load_test.py` docstring |
| `/release` | `make release-checklist` (prints the canonical checklist) | `docs/runbooks/release-checklist.md` |
| `/rollback` | `make rollback REV=<n>` (Argo Rollouts abort + kubectl undo) | `docs/runbooks/rollback.md` |
| `/incident` | `make incident-runbook` (prints incident response steps) | `docs/runbooks/incident-response.md` |
| `/performance-review` | `make performance-review` (sliced metrics + ground truth) | `docs/runbooks/performance-review.md` |
| `/cost-review` | `make cost-review` (cloud billing pull + budget compare) | `docs/runbooks/cost-review.md` |
| `/new-adr` | `make new-adr TITLE='<title>'` | `docs/decisions/template.md` |
| `/secret-breach` | `make secret-breach-check` (gitleaks scan) + escalation runbook | `docs/runbooks/secret-breach.md` |

### Skill → CLI / runbook map

Skills are agent reasoning bundles, so their non-agentic equivalent is the
underlying CLI tool plus the corresponding human runbook:

| Skill | CLI / runbook |
|---|---|
| `new-service` | `templates/scripts/new-service.sh` |
| `deploy-gke` / `deploy-aws` | `templates/scripts/deploy.sh` + `docs/runbooks/deploy-{gke,aws}.md` |
| `rollback` | `make rollback` + `docs/runbooks/rollback.md` |
| `drift-detection` | `scripts/drills/run_drift_drill.py` + `docs/runbooks/drift-detection.md` |
| `model-retrain` | `make retrain` + `docs/runbooks/model-retrain.md` |
| `eda-analysis` | `eda/run_eda.py` + `eda/README.md` |
| `cost-audit` | `make cost-review` + `docs/runbooks/cost-review.md` |
| `security-audit` | `make security-audit` (gitleaks + bandit + trivy) |
| `secret-breach-response` | `make secret-breach-check` + `docs/runbooks/secret-breach.md` |
| `rule-audit` | `make audit-rules` (validates AGENTS.md invariants D-01..D-31 are documented) |
| `debug-ml-inference` | `docs/runbooks/debug-ml-inference.md` (manual procedure; no CLI equivalent — pure RCA reasoning) |
| `performance-degradation-rca` | `docs/runbooks/performance-degradation-rca.md` (manual RCA procedure) |
| `concept-drift-analysis` | `make performance-review` + `docs/runbooks/concept-drift-analysis.md` |
| `release-checklist` | `make release-checklist` |
| `batch-inference` | `templates/scripts/batch_inference.sh` (or `make batch-inference DATA=<path>`) |

### Operational reality check

If your team adopts the template **without agents**, you lose:

- automatic mode escalation on incidents (`AUTO→CONSULT→STOP` — you decide
  manually based on the same signals from Prometheus)
- audit trail entry generation (you invoke `scripts/audit_record.py` from
  your runbooks instead of the agent doing it transparently)
- proactive risk-context queries before destructive operations

You **do not** lose:

- any of the production invariants (D-01..D-31 are codified in tests, not
  agent behavior)
- contract tests (run on every PR via the same CI workflows)
- supply-chain security (Cosign + SBOM + Kyverno are pipeline, not agent)
- monitoring / alerting / drift detection (CronJobs + Prometheus, not
  agents)
- 4-job deploy chain (GitHub Environments + reviewer approval, not agents)

The agentic surface is a **productivity multiplier** for teams that want
it; it is not a load-bearing component of the template's safety guarantees.

---

## 3. What this template does NOT claim

To prevent over-promising:

- **Multi-region active-active**: out of scope. The template assumes one
  active region per service per cloud. Cross-region failover is your
  organization's choice.
- **Compliance certifications**: SOC2, HIPAA, FedRAMP — these are
  organizational programs that consume the template's evidence (audit
  trail, signed images, RBAC) but aren't the template itself.
- **Zero-downtime database migrations**: out of scope. The template's
  4-job deploy chain handles stateless service rollouts; database schema
  evolution is your team's discipline.
- **Built-in feature store**: ADR-001 deferred this until 5+ services
  share features. PSI baselines + DVC remotes serve 2-3 services well.
- **Prompt engineering for LLM services**: this template targets
  classical ML serving (sklearn/XGBoost/LightGBM). LLM serving has
  different invariants (cold-start latency, token streaming, GPU pinning)
  not covered here.
- **Mobile / edge inference**: out of scope. The template assumes
  Kubernetes serving with HPA-driven horizontal scale.

If your use case lives in any of these gaps, the template is still useful
as a starting point, but expect to do additive work rather than just
configuration.
