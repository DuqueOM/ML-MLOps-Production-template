# ADR-010: Dynamic Behavior Protocol via MCP-Prometheus

## Status

Accepted

## Date

2026-04-24

## Context

The Agent Behavior Protocol (AGENTS.md, ADR-005) maps every agentic
operation to one of **AUTO / CONSULT / STOP** based on its risk class.
That mapping is STATIC: "Transition MLflow to Staging" is always CONSULT;
"Apply Terraform in prod" is always STOP.

Static mapping is correct but **incomplete**. A deploy to staging that
is CONSULT at 10am on a healthy Tuesday should NOT be CONSULT when:

- a P1 incident is active on a dependent service,
- PSI drift on a critical feature exceeds 2× the alert threshold,
- the SLO error budget for this quarter is exhausted,
- it is 17:45 on a Friday before a long weekend.

In each case, the agent should ESCALATE to STOP without waiting for the
human to remember the current system state.

Without access to live system signals, any attempt to codify this as
rules becomes aspirational — a table the agent cannot actually check.

## Decision

**Adopt a dynamic risk-scoring layer that runs alongside the static
mapping. Make its inputs real, not stubs, by installing `mcp-prometheus`
as a core MCP in the template's recommended setup.**

### Architecture

```text
    Static baseline (AGENTS.md) : op_type → base_mode
                        │
                        ▼
    Risk signals (mcp-prometheus queries, local files):
      - incident_active ............. ALERTS{severity="P1", alertstate="firing"}
      - drift_severe ................ PSI > 2× per-feature alert threshold
      - error_budget_exhausted ...... (1 - SLO) * 30d consumed
      - off_hours ................... UTC weekday 18–08 or weekend
      - recent_rollback ............. rollback issue opened < 6h
                        │
                        ▼
    Dynamic escalation table (documented in rule 01):
      AUTO → CONSULT if any 1 signal
      CONSULT → STOP  if any 1 signal
      STOP → STOP    (no relaxation; STOP is sticky)
                        │
                        ▼
    Final mode emitted in the agent's [AGENT MODE: X] signal.
```

### Why MCP-Prometheus as core, not stub

The original drafting considered a file-based stub (`ops/incident_state.json`,
last drift report snapshot). We rejected this because:

1. Stub would drift out of sync with reality (who updates the file?)
2. Stub creates a false sense of security in reviewers
3. Prometheus is already required for monitoring; no new dependency
4. MCP server for Prometheus is mature and maintained

Installing mcp-prometheus alongside the existing `github`, `kubectl`, and
`terraform` MCPs makes the table **real** with no extra infra.

### Fallback when MCP is unavailable

If `mcp-prometheus` is not configured OR Prometheus is unreachable, the
agent MUST fall back to the **static** baseline (AGENTS.md table) and
emit a warning in the audit entry:

```text
[AGENT MODE: CONSULT]
risk_signals: UNAVAILABLE (mcp-prometheus not configured)
fallback: static
```

This ensures the protocol degrades safely: in the absence of dynamic
data, the agent behaves EXACTLY as it does today.

## Rationale

**Why not let a human just remember?**  
Fridays are exactly when humans forget. Mapping obvious escalation
signals into the protocol removes cognitive load from the reviewer
without adding governance surface.

**Why escalate (never de-escalate)?**  
Dynamic scoring is one-directional — it can only make the protocol
STRICTER, never looser. A STOP operation stays STOP even if all signals
are green. This is deliberate: the conservative floor is set by the
static mapping.

**Why not just alert the human separately?**  
Alert fatigue. The agent already sees the mode before any operation;
attaching risk context to that existing checkpoint costs less cognitive
load than a separate Slack ping.

## Consequences

### Positive

- The protocol reflects the current SYSTEM state, not just the
  operation's intrinsic class.
- Agents cannot accidentally approve a deploy during an incident.
- Dynamic data forces the operator to see the evidence before overriding.
- Fallback semantics keep the template usable WITHOUT mcp-prometheus
  (adoption path).

### Negative

- One more MCP to install and keep healthy.
- Prometheus query latency adds 100–500 ms to each agentic operation.
- Escalation table must be calibrated per deployment (PSI thresholds
  differ per feature).

### Mitigations

- mcp-prometheus install documented alongside the other 3 in AGENTS.md
  (§MCP Integrations) — same setup footprint.
- Risk query caching (60 s) eliminates per-operation latency except on
  the first check.
- Escalation table uses symbolic thresholds referring to rule 09 and
  slices.yaml; no duplication.

## Revisit When

- The agent begins making decisions WITHOUT consulting risk signals
  (signal logic regresses to code paths)
- A third risk class (beyond AUTO/CONSULT/STOP) becomes necessary — e.g.,
  "FREEZE" for regulatory holds
- Cross-service risk propagation (service A incident escalates service
  B operations) — opens the door to a distributed policy engine

## Related

- ADR-005 — Agent Behavior Protocol (the static baseline)
- AGENTS.md §MCP Integrations (mcp-prometheus installation)
- `.windsurf/rules/01-mlops-conventions.md` (the escalation table)
- Skills that currently declare `authorization_mode:` frontmatter
  (deploy-gke, deploy-aws, model-retrain) — still authoritative,
  dynamic layer escalates but never relaxes them
