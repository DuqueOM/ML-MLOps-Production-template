---
name: pr-review
description: Dual-axis change review — Standards (repo conventions, anti-patterns) and Spec (does the diff implement what the linked ADR/issue asked for) — evaluated in isolation so neither pass contaminates the other's verdict
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(python3:*)
when_to_use: >
  Use before merging any non-trivial change, or when asked to 'review
  this PR', 'check this diff', 'does this satisfy the ADR/issue',
  'review my change'. Complements `rule-audit` (fixed D-01..D-37
  rubric, whole-repo) and `security-audit` (security-only, pre-build):
  this skill is general-purpose, always runs two independent passes,
  and is the one to reach for on an ordinary feature/fix PR.
argument-hint: "<diff-ref-or-PR> [--spec <adr-or-issue-path>]"
arguments:
  - diff_ref
  - spec_ref
authorization_mode:
  review_standards: AUTO           # read-only: conventions + anti-patterns against the diff
  review_spec: AUTO                # read-only: diff vs. the linked ADR/issue intent
  post_review_comment: CONSULT     # writing to a real PR is a visible, external action
  escalation_triggers:
    - recommend_blocking_merge: CONSULT  # a human decides whether to actually block
    - finds_security_or_D17_18_19: STOP  # never self-approve; chain to security-audit/secret-breach
---

# PR Review Skill

Runs two reviews of the same diff **in isolation** — neither one sees the
other's notes before forming its own verdict — then reconciles them into
a single report. The isolation is the point: a reviewer who already knows
"this satisfies the ticket" tends to go easy on style; a reviewer who
already knows "the code is clean" tends to skip checking intent. Keeping
them apart is cheaper than a habit of catching it in your head.

## Why two axes, not one checklist

- **Standards** answers: *does this diff violate a convention or a known
  anti-pattern (D-01..D-37), independent of what it's trying to do?*
- **Spec** answers: *does this diff actually do what the linked
  ADR/issue asked for, independent of how clean the code is?*

A diff can pass one and fail the other: a beautifully-typed function that
solves the wrong problem, or a correct fix that reintroduces D-24. Both
are real defects and neither axis alone catches both.

## 1. Resolve inputs (AUTO)

```bash
git diff <diff_ref>          # or: gh pr diff <PR-number>
```

If `--spec` was given, read that ADR/issue in full. If not, look for one
linked in the PR description or the branch name (`ADR-\d+`, issue `#\d+`);
if none exists, say so explicitly in the report — "no spec found" is a
finding, not a silent skip.

## 2. Pass A — Standards (AUTO, independent)

Check the diff against, in order:

1. `AGENTS.md` anti-patterns D-01..D-37 (the same rubric `rule-audit`
   uses, scoped to just the changed lines/files).
2. The relevant `agentic/rules/*.md` for any touched path (e.g. a
   changed `app/*.py` file triggers `04a-python-serving.md`).
3. Repo-wide conventions: type hints, docstring style, `~=` pinning,
   lint/format (`black`, `isort`, `flake8`, `mypy` — run them if the
   language toolchain is present).

Produce a list: `file:line — violation — which rule/anti-pattern`. Do
**not** yet read Pass B's notes.

## 3. Pass B — Spec (AUTO, independent)

Re-read the spec artifact (ADR/issue) and check, ignoring code style
entirely:

1. Does the diff implement every acceptance criterion the spec states?
2. Does it implement *only* those — flag scope creep (new abstractions,
   unrelated refactors) the same way as a missing criterion.
3. If the spec documented rejected alternatives, confirm the diff didn't
   silently reintroduce one.

Produce a list: `criterion — met / not met / partially met — evidence`.

## 4. Reconcile (AUTO)

Only now combine both passes into one report:

```text
## PR Review: <diff_ref>

### Standards
<Pass A findings, or "clean">

### Spec (vs. <spec_ref>)
<Pass B findings, or "no spec found">

### Verdict
<merge-ready | needs-changes | blocked>
```

A finding in *either* pass is enough to mark `needs-changes`. Only a
security/D-17/D-18/D-19 finding, or an explicit ask to enforce it,
escalates to recommending `blocked` — and that recommendation is
CONSULT, not a unilateral block.

## 5. Escalate (if triggered)

- Any secret, static credential, or unsigned-image-in-prod finding →
  **STOP**, chain to `security-audit` / `secret-breach-response`. Do not
  include it as "just another Standards note."
- A recommendation to block the merge → **CONSULT**: state the reason
  and wait for a human decision, never block unilaterally.

## Success criteria

- Both passes ran and are reported before any combined verdict appears.
- Every Standards finding cites `file:line` and the specific rule/D-NN.
- Every Spec finding cites the specific criterion from the spec artifact.
- No security-class finding was downgraded into a generic style note.

## Related

- Skill: `rule-audit` (fixed D-01..D-37 rubric, whole-repo, not diff-scoped)
- Skill: `security-audit` (security-only, pre-build/pre-deploy)
- Skill: `diagnose-bug` (when Standards review finds a bug, not just a style issue)
- Workflow: `/new-adr` (when Spec review finds an undocumented decision)
