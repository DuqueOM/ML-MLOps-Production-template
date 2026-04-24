# Incidents directory

Blameless post-mortems for production / local incidents that affected a
service or the development environment.

## What goes here

| Committed? | What |
|-----------|------|
| ✅ Yes | `README.md` (this file) |
| ✅ Yes | `EXAMPLE.md` — canonical format / template |
| ✅ Yes | Generalized learnings that apply to any adopter of the template |
| ❌ No (gitignored) | `YYYY-MM-DD-*.md` — dated incident files (personal to your environment) |

The `.gitignore` pattern `docs/incidents/20*.md` excludes dated incident
reports from being committed to the template. They live locally for your
audit trail; if a learning from a specific incident is broadly useful,
extract it into `docs/runbooks/` as a reusable playbook.

## When to open an incident doc

Open a new `docs/incidents/YYYY-MM-DD-<slug>.md` when any of:

- A service alert fired (P1 or P2) and required intervention
- A rollback was executed in production
- A secret was exposed (use `/secret-breach` workflow — STOP-class)
- An agent proposed or executed an action that broke an invariant
- A quality gate was bypassed with explicit justification
- A deployment was manually promoted outside the normal chain

## Format

Use `EXAMPLE.md` as the template. Required sections:

1. **Severity + status** (P1/P2/P3, Open/Resolved)
2. **Owner** + agent that detected/resolved
3. **Detection** — how was it found, first symptom
4. **Blast radius** — scope, exposure, evidence
5. **Classification** — which D-XX invariant(s)
6. **Remediation** — checkboxes, audit trail
7. **Root cause** — why, not who
8. **Corrective actions** — prevention for next time
9. **Related** — ADRs, skills, workflows

## Related

- `.windsurf/skills/rollback/SKILL.md` — STOP-class emergency revert
- `.windsurf/skills/secret-breach-response/SKILL.md`
- `.windsurf/workflows/incident.md`
- `ops/audit.jsonl` — append-only structured audit trail
