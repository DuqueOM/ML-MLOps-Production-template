# Runtime Monitoring Companion (ADR-023 F7)

**Authority**: `docs/decisions/ADR-023-agentic-portability-and-context.md` §F7
**Mode**: advisory, read-only, MCP-only
**Status**: shipped (Sprint-4 F7)

---

## Scope

The Runtime Monitoring Companion is **not** a new surface. It is a
**read-only consumption pattern** that lets any of the four surfaces
(`windsurf`, `cursor`, `claude`, `codex`) pull live runtime state —
alerts, metrics, audit events, recent reports — into the agent's
context during incident response, rollback, or drift investigation.

The companion is deliberately thin:

- **No new files checked into the service.** The companion is a
  configuration pattern plus a documented MCP wiring.
- **No writes.** Every integration is scoped to the read verbs of
  the underlying MCP (`prometheus.query`, `github.get_issue`, file
  reads under `ops/reports/` + `ops/audit.jsonl`).
- **No new skills or workflows.** Existing skills (`debug-ml-inference`,
  `incident`, `performance-degradation-rca`) already know how to
  consume these signals; F7 documents the invariants they rely on.

## Why this is a docs-only companion

Earlier ADR drafts considered a standalone "runtime agent" that
would subscribe to Alertmanager webhooks and proactively trigger
workflows. That path was rejected in ADR-023 §4 on the grounds
that:

1. Proactive workflow triggers against production would be **STOP**
   per the permissions matrix — automating them via a runtime agent
   would be the exact escape hatch the matrix forbids.
2. Alertmanager already routes to `#mlops-alerts` and paging. Adding
   an agent in the middle multiplies the noise surface without
   improving MTTR.
3. The read-only "pull when asked" pattern gets 90% of the value
   with 10% of the risk.

## Required MCPs

The companion is the first concrete caller of the MCPs declared in
`templates/config/mcp_registry.yaml`. When an adopter wires these
servers into a surface's MCP config, the companion activates
automatically — skills and workflows start consulting the live
signals without code changes.

| MCP | Purpose | Required scope |
| ----- | --------- | ---------------- |
| `prometheus` | Sliced latency / error / drift metrics | query only |
| `github` | Open incidents, recent PRs, deploy status | `issues:read`, `pulls:read` |
| `kubectl` | Pod / HPA / event snapshots during incidents | `--read-only` |

Reading `ops/reports/` and `ops/audit.jsonl` does **not** require an
MCP — these are plain files on the local checkout.

## Invariants F7 asserts

1. **Read-only MCPs only.** No skill may invoke a write verb
   (`create_issue`, `apply`, `patch`) as part of its companion path.
   Write operations remain gated by the AGENTS.md permissions matrix.
2. **Graceful degradation.** If an MCP is absent, the companion path
   returns a structured "signal unavailable" result; skills must
   fall back to the static authority (AGENTS.md anchors, latest
   report file) rather than synthesize values.
3. **No proactive triggering.** The companion never opens a PR,
   creates an issue, or kicks a workflow on its own. The agent
   consults signals; the **human** decides what to do.
4. **Audit trail.** Each consult produces an `AuditEntry` via the
   existing `scripts/audit_record.py` wrapper, with
   `operation="companion-consult"` and `inputs` listing the queries
   made. This is the ONLY side effect.

## How existing skills consume the companion

### `debug-ml-inference` (ADR-023 F5 adapter-ready)

```text
1. Read recent alerts from prometheus MCP (last 30m, service label)
2. Read pod status + recent events from kubectl MCP (read-only)
3. Read the latest drift report from ops/reports/drift/<service>/
4. Cross-reference against D-01 / D-03 / D-23 / D-25 invariants
5. Emit a diagnosis; ALL recommendations are advisory
```

### `incident`

```text
1. Read ops/audit.jsonl for recent STOP/CONSULT escalations
2. Read the latest 3 reports under ops/reports/ (any type)
3. Read current alerts from prometheus MCP
4. Compose a timeline proposal; HUMAN approves every timeline entry
5. If an incident report is warranted, it is WRITTEN by the /incident
   workflow (not by the companion) using the F6 contract.
```

### `performance-degradation-rca`

```text
1. Read prometheus MCP for sliced metrics over the alert window
2. Read the latest drift report + training report for the service
3. Correlate drift features with performance sliced metrics
4. Emit a root-cause hypothesis; human validates before acting
```

## Integration checklist (for adopters)

When wiring a new environment:

1. Configure `prometheus` MCP in the surface's MCP config (Codex:
   `.codex/mcp.json`; Cursor/Claude: per-IDE conventions; Devin:
   per-IDE conventions).
2. Configure `github` MCP with an `issues:read + pulls:read` scoped
   PAT. The companion never needs write scope.
3. Configure `kubectl` MCP with `--read-only`. Writes are out of
   scope for the companion.
4. Confirm `ops/reports/` and `ops/audit.jsonl` are readable by the
   agent's process.
5. Run a dry-run query:

   ```bash
   python3 -c "
   from common_utils.reports import load_report
   import pathlib
   for p in sorted(pathlib.Path('ops/reports').rglob('*.json'))[-3:]:
       print(p, load_report(p)['report_type'])
   "
   ```

   If this prints something sensible, the file-plane half of the
   companion is wired.

6. Verify MCP connectivity via the surface's native command
   (Codex: `/mcp list`, Cursor/Claude/Devin: the IDE's native MCP
   status view). This is a one-time smoke test, not an ongoing
   requirement.

## Anti-list

- **No companion-specific skill file.** Skills already own their
  behaviour; the companion is wiring + invariants, not logic.
- **No webhook subscriber service.** Alertmanager → human → agent,
  not Alertmanager → agent → human.
- **No long-lived daemon.** Every companion consult is a single
  read executed on demand during a skill/workflow run.
- **No cross-cluster aggregation.** Out of scope for v1; adopters
  with multiple clusters consult each one explicitly.

## Authority chain

```text
ADR-023 §F7
  └─ docs/agentic/runtime-monitoring-companion.md  (this file)
       └─ templates/config/mcp_registry.yaml       (declares the 3 MCPs)
            └─ existing skills                      (debug-ml-inference, incident, performance-degradation-rca)
                 └─ AGENTS.md permissions matrix    (gates write paths)
```

A change to the companion contract requires:

1. A new ADR amending F7 scope.
2. Update to this document.
3. Update to the consuming skills' SKILL.md files.
4. A contract-test case (add to `test_runtime_companion_contract.py`).
