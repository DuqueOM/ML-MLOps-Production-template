---
name: incident-postmortem
description: Structured, blameless post-incident review after /incident, /rollback, or /secret-breach closes — timeline reconstruction from primary sources, 5-whys root cause, action items with owner and date, written to docs/incidents/
allowed-tools:
  - Read
  - Write
  - Grep
  - Bash(git:*)
when_to_use: >
  Use AFTER an incident is resolved (post `/incident`, `/rollback`, or
  `/secret-breach`). Examples: 'write the postmortem', 'do a 5-whys on
  this incident', 'what are the action items from this outage'. Do not
  use mid-incident — this is a review skill, not a response playbook.
argument-hint: "<incident-ref>"
arguments:
  - incident_ref
authorization_mode:
  reconstruct_timeline: AUTO      # read-only: git log, ops/audit.jsonl, alert history
  draft_postmortem: AUTO          # local markdown file
  assign_action_items: CONSULT    # assigning an owner + date is a commitment, not a fact
  escalation_triggers:
    - blameless_violation_detected: STOP   # never let a draft name-blame an individual
---

# Incident Postmortem Skill

Runs once an incident is closed. Produces one artifact:
`docs/incidents/<incident_ref>-postmortem.md`. The discipline that makes
a postmortem useful instead of ceremonial is the same one the rest of
this repo already applies to audits (see the audit-methodology chapter
this template's Guía cross-references): **every claim traces to a
primary source**, not memory of what happened.

## 1. Reconstruct the timeline (AUTO, primary sources only)

```bash
git log --since="<incident-start>" --until="<incident-end>" --oneline
```

Pull from, in order of reliability: `ops/audit.jsonl` (structured
records), Alertmanager firing/resolved timestamps, `git log` (deploys,
reverts), CI run history (`gh run list`). **Never reconstruct from
memory of the conversation** — if a step isn't in a log, mark it
"unconfirmed timing" rather than guess a time.

## 2. Five-whys (AUTO)

Start from the customer-visible symptom, ask "why" until you reach a
cause that, if fixed, would have prevented this **class** of incident —
not just this instance of it. Stop when the answer becomes a process or
system gap (missing gate, missing test, missing runbook step), not when
it becomes a person. A 5-whys that terminates on "someone should have
been more careful" hasn't finished — that's a symptom of a missing gate,
not a root cause.

## 3. Blameless check (AUTO — hard gate)

Before writing anything to the file, scan the draft for individual
names attached to fault ("X forgot to...", "Y's change broke..."). If
found → **STOP**, rewrite in terms of the system gap ("the deploy step
had no gate that would have caught..."). This is not a style
preference — a postmortem that assigns blame stops people from
reporting the next incident honestly, which is a worse long-term outcome
than any single bug.

## 4. Draft the postmortem (AUTO)

```markdown
# Postmortem: <incident_ref>

- **Date**: <date> · **Severity**: <P1-P4, from the /incident classification>
- **Duration**: <first symptom> → <resolution>, from primary sources only

## Timeline
<reconstructed from step 1, each entry cites its source>

## Impact
<what broke, for whom, for how long — measured, not estimated>

## Five whys
<chain from symptom to system-level root cause>

## What went well
<what limited the blast radius or sped up detection — worth keeping>

## Action items
| # | Action | Owner | Date | Verifies |
|---|--------|-------|------|----------|
| 1 | | | | |
```

## 5. Action items (CONSULT)

Every action item needs an owner and a date — an item with neither is a
wish, not a commitment. **Assigning** the owner is CONSULT: propose it,
let the human confirm, don't commit someone else's time unilaterally.
Prefer action items that become a **gate** (a test, a check, a rule)
over ones that rely on someone remembering — the same principle this
repo already applies everywhere else (see `doc-coherence`, `ci-green-verify`).

## Success criteria

- Every timeline entry cites a primary source (log, commit, alert), not memory.
- The 5-whys terminates on a system/process gap, never an individual.
- Every action item has an owner, a date, and — where feasible — is a
  gate rather than a reminder.
- The blameless check ran and found nothing before the file was written.

## Related

- Workflow: `/incident` (the response this skill reviews after the fact)
- Skill: `diagnose-bug` (root-cause technique this skill's five-whys draws on)
- Skill: `rollback` / `secret-breach-response` (the two other closers this skill can follow)
- Precedent: `docs/audit/AUDIT_R8_STAFF_LEAD.md` addendum (same-day remediation table format, reused here for action items)
