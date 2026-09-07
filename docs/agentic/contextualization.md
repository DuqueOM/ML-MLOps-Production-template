# Contextualization — company & project context layer

**Authority**: `docs/decisions/ADR-023-agentic-portability-and-context.md`
**Files**: `templates/config/{company,project}_context.example.yaml`
**Schema**: `templates/config/context.schema.json`
**Validator**: `scripts/validate_agentic_manifest.py --strict`

---

## 1. Why this layer exists

The template used to assume every adopter had the same risk appetite,
budget, regulatory profile, and KPIs. An adopter in `financial_services`
with SOC2 + GDPR and a USD 500 monthly budget needs different escalation
thresholds than a research lab. Before ADR-023, the only way to specialize
was to fork `AGENTS.md` or the policy YAMLs — which defeated the template.

This layer lets adopters specialize declaratively: copy two example
files, fill placeholders, commit your `.local.yaml` variants **nowhere**
(they are `.gitignore`d and CI blocks them if they appear).

## 2. The two files

### `company_context.example.yaml`

Answers **WHO the adopter is**: legal entity, industry, regulatory
regime, risk appetite, budget ceiling, approval model, on-hours window.

It feeds directly into `templates/service/common_utils/risk_context.py`:

- `risk_appetite: high` downgrades AUTO→CONSULT for any prod operation.
- `monthly_budget_usd` gates the cost-overrun escalation (`cost_estimate > 1.2× budget` → STOP).
- `on_hours_utc` overrides the `MLOPS_ON_HOURS_UTC` default (validated by `_parse_on_hours_window` — full-day and
  reversed spans are rejected).
- `approval_model` names the role that must sign off per promotion lane.

### `project_context.example.yaml`

Answers **WHAT this service does and which KPIs matter**: business goal,
primary users, criticality, environments, and three KPI buckets
(business / ml / platform). Plus `agentic_policy.escalation_overrides`
which can only make modes stricter, never more permissive.

## 3. Adopter workflow

```bash
# From your fork's root:
cp templates/config/company_context.example.yaml \
   templates/config/company_context.local.yaml
cp templates/config/project_context.example.yaml \
   templates/config/project_context.local.yaml

# Edit the .local.yaml files, replacing every {placeholder}.
# Then validate:
python3 scripts/validate_agentic_manifest.py --strict
```

The validator refuses to proceed if:

- Any placeholder (`{CompanyName}`, `{ServiceName}`, `{team_or_role_1}`) remains.
- A schema constraint is violated (wrong enum, missing required field).
- `escalation_overrides` would DE-escalate a mode (e.g. `STOP → AUTO`).
- The `on_hours_utc` window is full-day / reversed / degenerate.

## 4. What does NOT belong in these files

The context layer is **configuration**, not **secret storage**. Per
rule `12-security-secrets.md` (D-18):

| Item | Belongs in context YAML? | Belongs where? |
| ------ | -------------------------- | ---------------- |
| Company legal name | Yes | — |
| Industry / regulatory regime | Yes | — |
| Monthly budget ceiling | Yes | — |
| Role-based approval model | Yes | — |
| KPI thresholds | Yes | — |
| IAM role ARNs (AWS) | **No** | AWS Secrets Manager + IRSA |
| Service-account JSON (GCP) | **No** | GCP Secret Manager + Workload Identity |
| PagerDuty webhook URL | **No** | Secret Manager, mounted via CSI |
| Slack webhook URL | **No** | Secret Manager |
| Live production endpoints | **No** | Kustomize overlay (`overlays/gcp-prod/`) |
| PII / customer identifiers | **No** | Never in repo, ever |
| Per-adopter licence keys | **No** | Secret Manager |

If you find yourself needing a secret in the context YAML, stop: the
correct primitive is Workload Identity / IRSA + a Secret Manager mount,
documented in `docs/runbooks/secrets-integration-e2e.md`.

## 5. How this connects to the other layers

```text
           ┌─────────────────────────────┐
           │  AGENT_CONTEXT.md (entry)   │   "where to read first"
           └─────────────┬───────────────┘
                         │
           ┌─────────────▼───────────────┐
           │  agentic_manifest.yaml      │   "index of rules / skills / workflows"
           └─────────────┬───────────────┘
                         │
           ┌─────────────▼───────────────┐
           │  AGENTS.md                  │   "invariants + modes + permissions"
           └─────────────┬───────────────┘
                         │
           ┌─────────────▼───────────────┐
           │  company + project context  │   "what matters for THIS adopter"
           └─────────────┬───────────────┘
                         │
           ┌─────────────▼───────────────┐
           │  risk_context.py (runtime)  │   "escalates AUTO → CONSULT → STOP"
           └─────────────┬───────────────┘
                         │
           ┌─────────────▼───────────────┐
           │  ops/audit.jsonl            │   "what has happened"
           └─────────────────────────────┘
```

The layers answer different questions. The context YAMLs answer only
one of them; they never reach into invariants (`AGENTS.md`) or memory
(`ops/audit.jsonl`).

## 6. Example contexts by adopter archetype

### Archetype A — Financial services enterprise (default in `*.example.yaml`)

```yaml
company:
  profile: "enterprise"
  industry: "financial_services"
  regulatory_profile: ["soc2", "gdpr"]
  risk_appetite: "medium"
  monthly_budget_usd: 500
  approval_model:
    production: "platform_owner + business_owner"
```

### Archetype B — Research lab on synthetic data

```yaml
company:
  profile: "research_lab"
  industry: "research"
  regulatory_profile: ["none"]
  risk_appetite: "high"       # more AUTO, faster iteration
  monthly_budget_usd: 50
  approval_model:
    production: "ml_owner"    # smaller org, single approver
```

### Archetype C — Healthcare SaaS

```yaml
company:
  profile: "sme"
  industry: "healthcare"
  regulatory_profile: ["hipaa", "soc2"]
  risk_appetite: "low"        # every prod op is CONSULT minimum
  monthly_budget_usd: 2000
  approval_model:
    production: "platform_owner + security_owner"
    secret_rotation: "security_owner"   # HIPAA-driven
```

## 7. Validating CI hygiene

The test `templates/service/tests/test_context_files_hygiene.py`
enforces at every PR:

- No `*_context.local*.yaml` tracked by git.
- `*.example.yaml` files parse against `context.schema.json`.
- `*.example.yaml` files contain no real-looking secret patterns
  (AKIA-prefix AWS keys, AIza-prefix GCP keys, PEM blocks, bearer
  tokens, credential-laden URLs).
- Placeholders in `*.example.yaml` use the `{PlaceholderName}` format
  so the validator can detect unreplaced values.

## 8. Related

- `docs/decisions/ADR-023-agentic-portability-and-context.md`
- `docs/decisions/ADR-010-dynamic-behavior-protocol.md` (consumer)
- `agentic/rules/12-security-secrets.md` (what lives where)
- `templates/service/common_utils/risk_context.py` (runtime consumer)
