# ADR-023 — Agentic Portability Layer and Contextualization

**Status**: Accepted
**Date**: 2026-05-03
**Deciders**: Platform owner
**Supersedes**: none
**Superseded by**: none

## 1. Context

The template currently exposes three agent surfaces:

- `.windsurf/` (authoritative — 15 rules, 16 skills, 12 workflows)
- `.cursor/` (rules + commands + `skills/INDEX.md` adapter)
- `.claude/` (rules + commands + `skills/INDEX.md` adapter)

The adapters paraphrase the Windsurf source and drift silently. A rule
edit in `.windsurf/rules/12-security-secrets.md` can diverge from
`.cursor/rules/07-security-secrets.md` without CI catching it. Adding a
fourth surface (Codex, evaluated in Sprint 4) or a fifth (Antigravity,
roadmap) would multiply the duplication.

Second problem: the template assumes every adopter has the same risk
appetite, budget, regulatory profile, and KPIs. In practice an adopter
in `financial_services` with `soc2 + gdpr` and a USD 500 monthly budget
needs different escalation thresholds than a research lab running
XGBoost on synthetic data. Today the only override channel is editing
`AGENTS.md` or the policy YAMLs in place, which forks the template.

Third problem: new agent surfaces arrive regularly (Codex, Vertex AI
Agent Platform, AWS AgentCore, Antigravity). Each ships its own
conventions (AGENTS.md, skills, plugins, automations, agent registries).
Without a canonical layer, each addition means another 15-rule
paraphrase and another divergence risk.

## 2. Decision

We introduce three perpendicular layers, each solving one failure mode:

1. **Context layer** (`templates/config/{company,project}_context.example.yaml`)
   — declarative contextualization of company profile, project scope,
   KPIs, and agentic-policy overrides. Adopters copy to
   `*_context.local.yaml` (gitignored) to specialize without forking.

2. **Agentic manifest** (`templates/config/agentic_manifest.yaml`)
   — the machine-readable index that enumerates canonical agents,
   skills, workflows, rules, and the surfaces that consume them. The
   manifest validates coherence and drives thin adapter rendering.

3. **MCP portability registry** (`templates/config/mcp_registry.yaml`,
   deferred to F4) — capability-centric registry of MCP servers used
   by skills + workflows, with install-mode per surface.

The `AGENTS.md` file remains the sole authority for invariants, modes,
permissions matrix, and handoffs. The manifest points at `AGENTS.md`;
it never paraphrases it.

## 3. Invariants (contract-enforced)

### I-1 — Manifest never contradicts `AGENTS.md`

Every policy claim in `agentic_manifest.yaml` must be anchored to a
section of `AGENTS.md` or an ADR. The validator
(`scripts/validate_agentic_manifest.py --strict`) rejects claims
without an `authority:` field referencing one of:

- `AGENTS.md#<section>` (must resolve to a real heading)
- `docs/decisions/ADR-<NNN>-*.md` (must exist)

Surfaces consuming the manifest inherit the authority chain.
**Consequence**: the moment someone edits a rule to contradict
`AGENTS.md`, CI fails with the specific anchor that was violated.

### I-2 — `*_context.local.yaml` is NEVER committed

`.gitignore` blocks `*_context.local.yaml` and `*_context.*.local.yaml`.
A contract test (`test_context_files_hygiene.py`) fails CI if:

- Any file matching `*_context.local*` is tracked by git.
- Any `*.example.yaml` contains a literal that looks like a real secret
  (regex: PEM blocks, AKIA prefix, AIza prefix, bearer tokens, URLs
  with embedded credentials).
- Any `*.example.yaml` contains a company/project name that is not a
  placeholder (`{CompanyName}`, `{@ service_name @}`, or a deliberately
  fictional example from `docs/agentic/contextualization.md`).

The `example.yaml` contents are syntactically valid YAML that also
parses against `context.schema.json` — an adopter can copy the file
verbatim to `.local.yaml` and have a working config.

### I-3 — MCP install is never automatic

(Active when F4 lands, stated here as the governing invariant.)

No template code path installs, configures, or enables an MCP server
without explicit human approval. The matrix:

| Scope | Mode |
| ------- | ------ |
| Validate MCP config exists | AUTO |
| Render setup docs | AUTO |
| Install local MCP without credentials | CONSULT |
| Install MCP requiring tokens / cluster access | CONSULT or STOP by risk |
| Configure access to production | STOP |

### I-4 — Adapters are generated pointers, never forks

`.windsurf/` remains the canonical body store for rules, skills, and
workflows. Adapter surfaces (`.cursor/`, `.claude/`, `.codex/`) contain
only discoverability files that point back to the canonical source and
`AGENTS.md`. The sync command:

```bash
python3 scripts/sync_agentic_adapters.py
```

is allowed to write adapter files, but it is forbidden from copying
full canonical bodies. The strict validator rejects adapter pointers
that omit the canonical source or the `AGENTS.md` authority chain.

## 4. Scope of this ADR (current deliverables)

**In scope** (F1–F3, single PR):

- ADR-023 (this file).
- `templates/config/company_context.example.yaml`
- `templates/config/project_context.example.yaml`
- `templates/config/context.schema.json`
- `docs/agentic/contextualization.md`
- `.gitignore` entries for `*_context.local*`
- `templates/config/agentic_manifest.yaml` (cross-surface source of truth)
- `scripts/sync_agentic_adapters.py` (manifest → thin adapter pointers)
- `scripts/validate_agentic_manifest.py --strict`
- `AGENT_CONTEXT.md` (canonical entry point)
- `.windsurf_context.md`, `.cursor_context.md`, `.claude_context.md`,
  `.codex_context.md`
  (compact pointers to `AGENT_CONTEXT.md`)
- Contract tests that enforce I-1, I-2, and the format validator
  (max 150 lines per context pointer, no date-led lines, no tables
  with > 10 rows).

**Explicitly OUT of scope**:

- A generator that translates canonical bodies into surface-specific
  syntax. The current renderer emits pointers only.
- Automatic MCP installation or credential wiring.
- Antigravity adapter — parked until the platform publishes a stable
  configuration format (revisit trigger below).

## 5. Consequences

### Positive

- A single source of truth for agent orchestration coherence
  (`AGENTS.md` + manifest) that CI enforces.
- Adopters specialize the template by editing 2 YAML files, not by
  forking rules and skills.
- Adding a new surface (Codex, Vertex, AgentCore) becomes an additive
  change to `agentic_manifest.yaml` + one `*_context.md` pointer + one
  adapter-root entry, then `scripts/sync_agentic_adapters.py`.
- Drift between `.windsurf/`, `.cursor/`, `.claude/` becomes a CI
  failure with a specific anchor, not a silent review-time catch.

### Negative

- One more YAML to maintain (`agentic_manifest.yaml`). Mitigated by
  making it the single manifest that both validators and adapter sync
  consume.
- Validator has to resolve anchors into `AGENTS.md` and ADR headings;
  brittle if someone renames a heading. Mitigated by the validator
  emitting line-accurate error messages and by the headings already
  being stable (the last rename was 8 months ago).
- Adopters may mis-read `company_context.local.yaml` as a general
  secret store. Mitigated by `contextualization.md` explicitly
  listing "what does NOT belong here" (IRSA ARNs, service-account
  JSON, API tokens — those live in Secret Manager per D-18).

### Neutral

- The template now has an entry point (`AGENT_CONTEXT.md`) which
  is itself subject to a format validator. Net neutral — cheaper than
  the agent reading 200k lines of repo to bootstrap.

## 6. Revisit triggers

- **Second surface requires non-pointer native syntax** → extend the
  renderer with a surface-specific adapter backend. Do not fork
  canonical bodies.
- **Antigravity publishes stable config spec** → add
  `companions/antigravity/` and `surfaces.antigravity` to the manifest.
- **An adopter's `company_context.local.yaml` needs a field not in
  the schema** → schema update + schema version bump + migration note.
- **A rule in `AGENTS.md` changes such that existing anchors break**
  → I-1 validator fails loud; authors decide whether to update
  anchors (preferred) or carve out a new ADR row.
- **A context file crosses 150 lines** → format validator fails; the
  author must either split the file or lobby to raise the limit in
  this ADR.

## 7. Alternatives considered

| Alternative | Why rejected |
| ------------- | -------------- |
| Keep paraphrasing per-surface, add Codex the same way | Drift compounds linearly in #surfaces × #rules; already 3 surfaces × 15 rules = 45 paraphrases today |
| Copy canonical content into every IDE surface | Rejected after Codex parity work; duplication drift is the exact failure ADR-023 exists to remove |
| Put company context in environment variables instead of YAML | Env variables are flat; nested structures (KPIs with owner + threshold + direction) need a typed schema |
| Store company context in a cloud Secret Manager | Correct for secrets, wrong for config: schema changes cadence is weeks, not hours |
| Skip the ADR and do this as "a refactor" | Violates the template's own governance (every non-trivial decision → ADR) |

## 8. Related

- `AGENTS.md` — the authority referenced by the manifest.
- `docs/decisions/ADR-001-template-scope-boundaries.md` — keeps this
  ADR from drifting into "platform of agents" territory.
- `docs/decisions/ADR-005-agent-behavior-protocol.md` — AUTO/CONSULT/STOP
  that the manifest points at.
- `docs/decisions/ADR-010-dynamic-behavior-protocol.md` — risk signals
  that `company_context.agentic_policy.escalation_overrides` feeds into.
- `docs/decisions/ADR-018-operational-memory-plane.md` — what happened
  vs. what the context layer covers (what matters for this project).
- Sprint 4 issues: F4 (MCP registry), F5 (Codex), F6 (Reporting), F7
  (Runtime Monitoring), F8–F9 (cloud companions).

## 9. Sprint 4 closure log

### F4 — MCP portability registry (shipped)

- `templates/config/mcp_registry.yaml`, `surface_capabilities.yaml`
- `scripts/mcp_doctor.py` — read-only diagnostics + docs renderer
- `docs/agentic/mcp-portability.md`
- Contract: `templates/tests/governance/test_mcp_registry_contract.py`

### F5 — Codex adapter (shipped)

- `.codex/{README.md, rules/, skills/, workflows/, automations/, mcp.example.json}`,
  `.codex_context.md`
- Full parity with 15 canonical rule files, 16 skills, and 12 workflows
  through generated pointer files.
- Skills are pointer-files referencing canonical Windsurf SKILL.md
- Contract: `templates/tests/governance/test_codex_adapter_contract.py`

### F6 — Reports v1 typed contract (shipped)

- `templates/config/report_schema.json`,
  `templates/common_utils/reports.py`, `scripts/generate_report.py`
- `docs/agentic/reports.md`
- Contract: `templates/tests/governance/test_reports_contract.py`

### F7 — Runtime monitoring companion (shipped, docs-only)

- `docs/agentic/runtime-monitoring-companion.md`
- Pattern: read-only consumption of `prometheus`, `github`, `kubectl`
  MCPs by existing skills (`debug-ml-inference`, `incident`,
  `performance-degradation-rca`). No new skill or workflow introduced.
- Manifest entry: `companions[].id == runtime-monitoring`.
- Contract: `templates/tests/governance/test_companions_contract.py`.

### F8 — GCP Gemini Enterprise / Vertex AI Agent Builder companion (shipped, docs-only)

- `docs/agentic/cloud-companions.md` §F8
- Mapping table: AGENTS.md → IAM, Skill → Vertex Tool, Workflow →
  Playbook, MCP → Extension/HTTP tool, audit → Cloud Logging,
  reports → GCS+PubSub.
- No vendored `google-cloud-aiplatform` SDK calls in `templates/`
  (enforced by contract test).
- Manifest entry: `companions[].id == gcp-gemini-enterprise`.

### F9 — AWS Bedrock AgentCore companion (shipped, docs-only)

- `docs/agentic/cloud-companions.md` §F9
- Mapping table: AGENTS.md → IAM permission boundary, Skill → Action
  Group, Workflow → Flow, MCP → Lambda action group, audit →
  CloudWatch Logs, reports → S3+EventBridge.
- No vendored `boto3.client('bedrock-agent*')` calls in `templates/`.
- Manifest entry: `companions[].id == aws-bedrock-agentcore`.

ADR-023 scope is fully delivered. Subsequent work proceeds under
ADR-024 (single-source-of-truth + pointer generator) and ADR-025
(versioning reset).
