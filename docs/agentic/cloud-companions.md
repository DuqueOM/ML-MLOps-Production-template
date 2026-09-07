# Cloud Companions — GCP Gemini Enterprise (F8) and AWS AgentCore (F9)

**Authority**: `docs/decisions/ADR-023-agentic-portability-and-context.md` §F8, §F9
**Mode**: docs-only, advisory
**Status**: shipped (Sprint-4 F8, F9)

---

## What this document is

A *companion* is a documented integration pattern that lets an adopter
run our agent stack (skills + workflows + MCP registry) on a managed
agent platform without forking the template. We ship companions for:

- **GCP Gemini Enterprise / Vertex AI Agent Builder** (F8)
- **AWS Bedrock AgentCore** (F9)

Both companions are **docs-only** in v1. The template does not vendor
provider SDK code, does not generate platform-specific manifests, and
does not register agents on the adopter's behalf. We document the
mapping so an adopter can wire the integration in a few hours rather
than reverse-engineering the template's contracts.

## Why docs-only

The same reasoning as F7 (runtime monitoring companion):

1. **Provider APIs change quarterly.** A code-vendored adapter rots
   between releases. Documentation aging is visible; vendored code
   silently breaks production registrations.
2. **Each adopter's IAM, project, and account topology is unique.**
   Any opinionated wiring would block 80% of adopters.
3. **Production registration is STOP per the permissions matrix.**
   Auto-wiring would be the exact bypass forbidden by AGENTS.md.

When (not if) a second large adopter requests a code companion for
the same provider, ADR-023 §6 revisit triggers fire and we reopen.

---

## F8 — GCP Gemini Enterprise / Vertex AI Agent Builder

### Mapping

| Template concept | GCP equivalent | Notes |
| ------------------ | ---------------- | ------- |
| `AGENTS.md` permissions matrix | Vertex AI Agent IAM policy | Map AUTO → `roles/aiplatform.user`, CONSULT → custom role with reviewer step, STOP → blocked at IAM |
| Skill (`agentic/skills/<id>/SKILL.md`) | Agent Builder *Tool* with explicit instruction text | Copy SKILL body into the tool description; do NOT auto-translate |
| Workflow (`agentic/workflows/<id>.md`) | Agent Builder *Playbook* | Slash-command name maps 1:1 to playbook trigger |
| MCP server (e.g. `prometheus`) | Vertex AI *Extension* or HTTP function tool | Use the same auth as our MCP registry — do not add a second credential |
| `ops/audit.jsonl` | Cloud Logging sink with structured payload | Schema is identical; ship via Logging API rather than file write |
| Reports v1 JSON | GCS bucket + Pub/Sub notification | Bucket name from `project_context.local.yaml` |

### Required reading before wiring

1. `AGENTS.md` (full).
2. `docs/decisions/ADR-023-agentic-portability-and-context.md`.
3. `templates/config/agentic_manifest.yaml` (the inventory).
4. `templates/config/mcp_registry.yaml` (the MCPs to expose as
   Vertex AI Extensions or HTTP tools).

### Wiring checklist (manual, AUTO → CONSULT)

1. Provision a Vertex AI Agent in the adopter's GCP project. **AUTO**
2. Create one *Tool* per skill listed in the manifest with
   `surfaces: [..., "vertex"]` (no skill currently has that — F8 is
   the FIRST consumer, so adopters will edit the manifest to claim
   the surface they want). **AUTO**
3. Map MCP servers to Vertex Extensions. **CONSULT** — the agent
   reviews the tool spec; the human approves the IAM. **CONSULT**
4. Wire Cloud Logging sink for `ops/audit.jsonl` ingestion. **AUTO**
5. Test in dev project. Production registration is **STOP** —
   handled exactly like our existing prod deploy gates.

### Anti-list (do NOT do)

- Do not vendor `google-cloud-aiplatform` SDK calls into template code.
- Do not auto-create IAM policies. The adopter's IAM team owns those.
- Do not export skill bodies as Tool descriptions during render time.
  Skill text is human-edited; copy it once, then maintain in place.
- Do not enable `roles/aiplatform.admin` for the agent SA — read +
  invoke is sufficient for every documented use case.

### Authority and revisit

- Authority: ADR-023 §F8.
- Revisit when GCP publishes a stable agent registration API that
  supports our handoff schema natively (currently they don't).

---

## F9 — AWS Bedrock AgentCore

### Mapping

| Template concept | AWS equivalent | Notes |
| ------------------ | ---------------- | ------- |
| `AGENTS.md` permissions matrix | AgentCore policy + IAM permission boundary | AUTO → invoke, CONSULT → invoke + reviewer Lambda, STOP → blocked at SCP |
| Skill | AgentCore *Action Group* schema | Schema lives in repo as the SKILL frontmatter, copied to AgentCore |
| Workflow | AgentCore *Flow* | Slash-command maps to flow trigger |
| MCP server | Lambda action group with the MCP's HTTP transport | Adopters with private MCP servers expose them through API Gateway with IAM auth |
| `ops/audit.jsonl` | CloudWatch Logs structured stream | Same schema; tail via `aws logs tail` for parity with file reads |
| Reports v1 JSON | S3 prefix + EventBridge notifications | Bucket name from `project_context.local.yaml` |

### Required reading before wiring

Same as F8: AGENTS.md, ADR-023, `agentic_manifest.yaml`,
`mcp_registry.yaml`. The two cloud companions are intentionally
symmetric — once an adopter has wired one, the other is a 4-hour
job, not a re-architecture.

### Wiring checklist (manual)

1. Create an AgentCore Agent in the adopter's AWS account. **AUTO**
2. Create one Action Group per claimed skill. **AUTO**
3. Map MCP servers to Lambda action groups (or API Gateway-fronted
   HTTP). **CONSULT**
4. Wire CloudWatch Logs subscription for `ops/audit.jsonl`. **AUTO**
5. Test in dev account. Production wiring is **STOP**.

### Anti-list

- No vendored `boto3` AgentCore code in template Python paths. The
  template stays cloud-agnostic; AgentCore wiring lives in the
  adopter's IaC.
- No automatic IAM policy creation for action groups. IAM stays
  with the adopter's security team.
- No silent re-registration on PR merge. Re-registration is a
  CONSULT operation that opens a PR with a diff in the AgentCore
  schema.

### Authority and revisit

- Authority: ADR-023 §F9.
- Revisit when AWS publishes parity for the structured handoff
  schema in `templates/service/common_utils/agent_context.py` (today it is
  closer than Vertex AI but still not 1:1).

---

## Cross-cutting invariants (F7 + F8 + F9)

1. **Read-only by default.** Every companion's first integration is
   read-only. Write paths are unlocked one at a time per CONSULT.
2. **Single source of truth for skills.** A skill body is edited in
   `agentic/skills/<id>/SKILL.md` and copied to the platform once.
   Subsequent edits are propagated by the adopter's runbook, not by
   automatic sync.
3. **Audit parity.** Whatever the cloud platform's native audit
   produces, the adopter MUST also write an entry to
   `ops/audit.jsonl` (or its CloudWatch / Cloud Logging mirror) so
   the template's existing CI checks keep working.
4. **No vendor lock-in in template code.** `templates/**` stays
   provider-agnostic. Provider integration code lives in the
   adopter's repo, behind their `infra/` boundary.

## Authority chain

```text
ADR-023 §F8, §F9
  └─ docs/agentic/cloud-companions.md   (this file)
       ├─ templates/config/agentic_manifest.yaml   (skills / workflows / surfaces)
       └─ templates/config/mcp_registry.yaml       (MCPs to expose)
            └─ AGENTS.md                            (permissions, modes, audit)
```

A change to either companion contract requires:

1. ADR-023 amendment (new revision section).
2. Update to this document.
3. If a new surface is claimed by skills → manifest edit + validator
   re-run.
4. Contract-test update in `test_cloud_companions_contract.py`.
