# Incident YYYY-MM-DD — <one-line title>

> **This is the canonical template.** Copy this file to `YYYY-MM-DD-<slug>.md`
> (which will be gitignored) when you need to document a real incident.
> Keep sections below; replace the placeholder content.

**Severity**: P1 | P2 | P3
**Status**: Open | Mitigated | Resolved — YYYY-MM-DD
**Owner**: @username
**Agent**: windsurf-cascade | claude-code | cursor
**Workflow**: `/incident` | `/rollback` | `/secret-breach`

## Detection

How was this found? First symptom. Time from symptom to detection.
What alert fired, what dashboard spiked, what user reported it.

## Blast radius

What was exposed or affected. Concrete numbers:

- Users / requests affected: N over T minutes
- Services degraded: list
- Data exposure: yes/no (with evidence)
- Upstream / downstream: list

## Classification

Which invariant(s) broke: `D-XX`, `D-YY`. Link to the anti-pattern row
in AGENTS.md or the rule file that was violated.

## Remediation

Checkboxes, in chronological order. Each action gets a box.

- [x] 14:03 — Alert fired on `service-name-5xx-rate`
- [x] 14:05 — Paged on-call; opened this doc
- [x] 14:08 — Confirmed not a dashboard blip (error rate >1%)
- [x] 14:10 — Identified bad deploy `v1.8.3` as cause
- [x] 14:12 — Executed `/rollback` to `v1.8.2` (STOP-class)
- [x] 14:15 — Error rate returned to baseline
- [x] 14:20 — Silenced `service-name-5xx-rate` for 30 min
- [ ] Follow-up: regression test for the trigger condition
- [ ] Follow-up: ADR if a non-obvious decision was made

## Root cause

WHY this happened — the technical cause, not "someone made a mistake".
A blameless post-mortem focuses on the system that let the mistake pass:
missing test, unclear contract, gap in CI, etc.

## Corrective actions

Prevention for next time. Usually 1-3 items, with owners and due dates.

1. **Add test**: `tests/regression/test_<case>.py` — due YYYY-MM-DD — @owner
2. **Update rule**: `.windsurf/rules/0X-foo.md` — add new invariant D-XX
3. **Runbook**: extract general learning to `docs/runbooks/<topic>.md`

## Timeline (optional, for P1)

Condensed timeline of events for exec summary.

| Time (UTC) | Event |
|------------|-------|
| 14:03 | Alert fired |
| 14:05 | Paged |
| 14:12 | Rollback executed |
| 14:15 | Recovery |

## Related

- ADR-XXX — relevant decision
- `docs/runbooks/<topic>.md` — runbook this incident triggered
- `.windsurf/skills/<skill>/SKILL.md`
- Invariants: D-XX, D-YY

---

**After committing**: append a structured entry to `ops/audit.jsonl` with
operation=`incident_response`, result=`resolved`/`mitigated`, and link
back to this file.
