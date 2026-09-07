# Compliance Mapping — NIST AI RMF · ISO/IEC 42001 · EU AI Act

> **What this is**: a map from artifacts this template ALREADY produces to
> the evidence three major governance frameworks ask for.
> **What this is NOT**: a certification, an attestation, or legal advice.
> No framework certifies a *template* — only a specific deployed *system*,
> operated by a specific organization, can be assessed or certified. This
> document exists so an adopter's compliance/risk team can do a
> gap-assessment in minutes instead of days, by showing exactly which
> control questions this template already answers with a running artifact,
> and which remain the adopter's responsibility (organizational policy,
> human roles, deployment-specific risk classification).

Authority: this mapping is descriptive, not normative — `AGENTS.md` and the
ADRs remain the source of truth for what the template actually does. If this
document and the code ever disagree, the code (and its tests) win; open an
issue.

---

## 1. NIST AI Risk Management Framework (AI RMF 1.0)

The RMF has four functions: GOVERN, MAP, MEASURE, MANAGE. Each row below
is a control question a MEASURE/MANAGE assessor would ask, and the file
that answers it.

| Function | Control question | Template artifact | Evidence produced |
| --- | --- | --- | --- |
| **GOVERN** | Is there a documented, versioned decision record for architecture/risk trade-offs? | `docs/decisions/*.md` (37 ADRs) | Context → Decision → Consequences → Revisit triggers, per decision |
| **GOVERN** | Are AI system actions constrained by an explicit authority/escalation policy? | `AGENTS.md` §Agent Behavior Protocol | AUTO/CONSULT/STOP modes; ADR-010 (escalation-only, never de-escalates) |
| **GOVERN** | Are roles and responsibilities for the system defined? | `templates/governance/ROLES.md` | Named roles + approval paths for promotion/deploy |
| **GOVERN** | Is there a documented process to review and modify the risk posture over time? | ADR "Revisit triggers" sections (all 37) | Explicit conditions under which each decision is reopened |
| **MAP** | Is the model's operating context (schema, data sources, intended use) documented? | `templates/service/docs/model-card-template.md`, `eda/CONTRACT.md` | Model card fields: intended use, out-of-scope use, training data description |
| **MAP** | Is there a structured process to understand data before training? | `eda/eda_pipeline.py` (6-phase EDA) | Univariate, correlation, leakage-gate report per run |
| **MAP** | Are dynamic risk factors (load, error rate) fed back into system behavior? | `common_utils/risk_context.py` | ADR-010: Prometheus signals escalate CONSULT→STOP |
| **MEASURE** | Is model quality measured against a documented threshold before promotion? | `templates/service/configs/quality_gates.yaml` | Metric threshold + fairness DIR ≥ 0.80 + leakage check, enforced pre-promotion |
| **MEASURE** | Is fairness/disparate impact measured, not just assumed? | `common_utils/evidence_bundle.py`, ADR-021 | Disparate Impact Ratio computed per protected attribute, gated |
| **MEASURE** | Is data drift measured post-deployment, continuously? | `drift-detection` skill, ADR-022 | PSI with quantile bins; warn/alert thresholds |
| **MEASURE** | Is concept drift (silent accuracy decay) measured, not just data drift? | `concept-drift-analysis` skill, ADR-006 (portfolio) | Sliced performance analysis vs. ground truth |
| **MEASURE** | Are explanations available for individual predictions? | `explainability.py` (KernelExplainer/SHAP) | Feature attributions in ORIGINAL feature space (never transformed) |
| **MANAGE** | Is there a governed, non-automatic path to promote a challenger model? | `evaluation/champion_challenger.py`, ADR-008 (template) | Statistical significance gate (McNemar + bootstrap), not a raw metric bump |
| **MANAGE** | Is there a documented, rehearsed incident response for a bad deployment? | `rollback` skill/workflow | STOP-class: human approves every destructive step; audit issue mandatory |
| **MANAGE** | Are retraining triggers documented and bounded (not silently automatic)? | ADR-009 (template), `retrain` workflow | GitHub Actions triggers, CONSULT-gated promotion |
| **MANAGE** | Is prediction-time logging sufficient to reconstruct what happened? | `common_utils/prediction_logger.py` | Fire-and-forget, non-blocking, closed-loop with ground truth (ADR-006 template) |

---

## 2. ISO/IEC 42001:2023 (AI Management System) — Annex A controls

| Annex A control area | Template artifact | Evidence |
| --- | --- | --- |
| **A.4 Resources** (data, tooling, compute) | `pyproject.toml`/`requirements.txt` (`~=` pinning), `docs/decisions/ADR-025-*.md` | Compatible-release pinning prevents silent breakage (e.g. numpy 2.x corrupting joblib) |
| **A.5 AI system impact assessment** | `templates/service/docs/model-card-template.md`, fairness gate (ADR-021) | DIR ≥ 0.80 floor documented with rationale (Siddiqi-style thresholds, ADR-022 for PSI) |
| **A.6 AI system life cycle** | `Makefile` targets (`train`, `serve`, `drift-check`), `dvc.yaml` | Reproducible pipeline stages, versioned via DVC |
| **A.7 Data for AI systems** | `common_utils/input_validation.py`, Pandera `DataFrameModel` | Schema validation at training AND serving (second-wall validation, PR-R2-4) |
| **A.8 Information for interested parties** | `templates/service/docs/model-card-template.md`, `RUNBOOK.md`, `docs/runbooks/*.md` | Model card + operational runbooks for on-call/audit readers |
| **A.9 Use of AI systems** | K8s `readinessProbe`/`livenessProbe` (D-23), warmup gate (D-24) | System does not serve traffic before it is verifiably ready |
| **A.10 Third-party and supplier relationships** | `SBOM` attestation (Cosign), `NOTICE`, dependabot | Every image ships a signed SBOM; dependency provenance is attested, not assumed |

---

## 3. EU AI Act — Articles 9–15 (high-risk system obligations)

**Timeline note (verified 2026-07)**: the Digital Omnibus agreement
(2026-05-07) postpones Annex III (use-based) high-risk obligations from
2026-08-02 to **2027-12-02**; Annex I (product-regulated) obligations move
from 2027-08-02 to 2028-08-02. These changes take legal effect on formal
adoption/publication of the Omnibus. This mapping targets the *substance* of
Arts. 9–15 regardless of the exact enforcement date — the underlying
practices (risk management, data governance, logging, human oversight) are
good engineering independent of the regulatory calendar.

| Article | Requirement (paraphrased) | Template artifact | Evidence |
| --- | --- | --- | --- |
| **Art. 9** — Risk management system | Continuous risk identification/mitigation across the lifecycle | Quality gates + fairness gate + drift monitoring + dynamic risk escalation (ADR-010) | A closed loop: measure → gate → escalate, not a one-time check |
| **Art. 10** — Data governance | Training/validation/test data subject to quality criteria; bias examination | 6-phase EDA with leakage gate; Pandera schema validation; fairness DIR gate | `eda_pipeline.py` phase 4 (leakage) blocks training on a leaking feature |
| **Art. 11** — Technical documentation | Documentation sufficient to assess compliance | The [ADR index](decisions/README.md) (generated from the files, verified in CI) + model card + `RUNBOOK.md` | Documentation is versioned alongside code, not a separate artifact that drifts (rule 16 / ADR-031 doc-coherence gate). The count is deliberately not restated here: it was wrong (37 against 45 on disk) for as long as the index it cited did not exist. |
| **Art. 12** — Record-keeping (logging) | Automatic logging of events over the system's lifetime | `ops/audit.jsonl` (append-only), `prediction_logger.py`, MLflow tracking | Every prediction + every agent action is logged with a trace id |
| **Art. 13** — Transparency | Sufficient information for deployers to interpret output | SHAP explainability (`?explain=true`), model card "intended use" section | Per-prediction feature attribution, in the original feature space |
| **Art. 14** — Human oversight | Natural persons can oversee, and if needed intervene/stop | AUTO/CONSULT/STOP protocol; STOP-class rollback (human approves every step) | The agent cannot promote, deploy to prod, or rollback without a human in the loop |
| **Art. 15** — Accuracy, robustness, cybersecurity | Appropriate accuracy metrics; resilience to errors; cybersecurity measures | Quality gates (accuracy floor); IRSA/WI (no static creds); Cosign+SBOM+Kyverno (signed, verified-by-digest images); gitleaks/bandit in CI | Supply-chain integrity is enforced end-to-end, not just "we use HTTPS" |

**Annex IV** (technical documentation content) maps almost 1:1 to the
combination of `templates/service/docs/model-card-template.md` + the relevant ADRs +
`RUNBOOK.md` — an adopter completing Annex IV should start from those three
files, not from a blank page.

---

## 4. What remains the adopter's responsibility

This template cannot and does not provide:

- **Risk classification of your specific use case** (Annex III of the AI
  Act, or your organization's internal risk taxonomy) — that depends on
  what the model decides and who it affects, which only the adopter knows.
- **Organizational governance roles beyond the template's default**
  (`ROLES.md` gives a starting structure; a real DPO/AI governance
  committee sign-off is an organizational act, not a file).
- **A conformity assessment or certification** — only an accredited body
  (for AI Act Annex III high-risk systems) or a certification body (for
  ISO/IEC 42001) can issue one, against a *specific deployed system*.
- **Legal review** — this document is engineering documentation, not legal
  advice. Consult qualified counsel before relying on it for a compliance
  filing.

## 5. Revisit triggers

- The Digital Omnibus is formally adopted/published → re-verify the
  Art. 9–15 timeline note above.
- A new NIST AI RMF profile or ISO/IEC 42001 amendment ships → re-audit
  this mapping's control coverage.
- A template artifact referenced here is renamed/removed → update this file
  in the same PR (same discipline as `docs/decisions/ADR-034-ccds-aligned-generated-layout.md` CCDS mapping).

## Related

- `docs/decisions/ADR-038-compliance-mapping.md` — the ADR recording this
  decision and its scope boundary.
- `templates/service/docs/model-card-template.md`, `RUNBOOK.md`, `docs/decisions/` — the
  primary artifacts this document indexes.
