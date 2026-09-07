---
name: diagnose-bug
description: Systematic root-cause diagnosis for any non-ML-serving bug (CI, infra, agentic tooling, drift scripts) — reproduce, minimize, hypothesize, instrument, fix, regression-test
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(python3:*)
  - Bash(pytest:*)
when_to_use: >
  Use for any bug outside ML inference itself (which has its own
  debug-ml-inference skill, D-01..D-37 checklist first): CI failures,
  flaky tests, validator/gate bugs, deploy issues, agentic tooling bugs.
  Examples: 'the CI run is red and I don't know why', 'this script fails
  intermittently', 'diagnose why the gate is flaky', 'why did the
  force-push break the gitleaks scan'.
argument-hint: "<symptom-description> [--logs <path>]"
arguments:
  - symptom
authorization_mode:
  reproduce: AUTO
  instrument: AUTO
  apply_fix: AUTO                  # local, reversible code/config/test change
  add_regression_test: AUTO
  escalation_triggers:
    - fix_touches_prod_infra: CONSULT   # k8s/terraform/CI workflow changes
    - fix_touches_secrets_or_iam: STOP
    - root_cause_unclear_after_instrumentation: CONSULT  # never guess-and-check
---

# Diagnose-Bug Skill

Six stages, in order. The discipline is skipping none of them — the
common failure mode is jumping straight from "reproduce" to "fix" and
shipping a patch for the symptom instead of the cause.

## 1. Reproduce (AUTO)

Get the failure to happen on demand, locally, before touching anything.

```bash
git log -1 --format='%H %s'    # confirm exact commit/state
# re-run the exact failing command/suite/workflow step
```

If it won't reproduce locally, that gap (env difference, timing, scope)
**is itself the first clue** — note it explicitly, don't paper over it.

## 2. Minimize (AUTO)

Shrink the reproduction to the smallest input/state that still triggers
it. A single failing test, a single file, a single commit range — not
"the whole suite is red." Minimizing often reveals the bug is narrower
(or wider) than the initial symptom suggested.

## 3. Hypothesize (AUTO)

State a falsifiable hypothesis in one sentence before instrumenting:
*"X fails because Y, which should show up as Z if true."* If you can't
state one, you don't have enough information yet — go back to
minimizing, don't start guessing fixes.

## 4. Instrument (AUTO)

Add the smallest probe that confirms or kills the hypothesis: a print,
an assert, a `git bisect`, a diff between the two states being compared.
**Do not fix anything yet.** If instrumentation contradicts the
hypothesis, form a new one from what you just learned — do not keep the
old fix plan and bolt on a special case.

### Worked example (real incident, this repo)

Symptom: CI's gitleaks job went red on the first push *after* a
history-rewrite force-push, flagging a line that had been in the repo,
unchanged, for days.

- **Reproduce**: confirmed the flagged file's current content was clean
  via `gitleaks detect --no-git` (scans a plain file, not history).
- **Minimize**: the finding pointed at one specific historical commit,
  not the current tree.
- **Hypothesize**: "the force-push changed what GitHub's push-event
  diff range covers, so CI scanned a commit a normal push never would."
- **Instrument**: compared the pre-rewrite and post-rewrite commit SHAs
  GitHub had cached — confirmed the "before" SHA no longer existed in
  the new history, widening the comparison range.
- **Fix**: scoped allowlist entry for the finding's file class (not a
  blanket disable).
- **Regression test**: re-ran CI; watched it go green; documented the
  mechanism so the next history rewrite doesn't re-diagnose from zero
  (see `docs/audit/` R10 addendum and this repo's own module on audit
  methodology).

## 5. Fix (AUTO, scoped)

Fix the cause you instrumented, not the symptom. Prefer the smallest
change that removes the mechanism, not one that special-cases the
observed input. If the fix touches Kubernetes manifests, Terraform, or
a CI workflow's permissions/secrets → **CONSULT** before applying. If it
touches IAM/secrets directly → **STOP**.

## 6. Regression-test (AUTO)

Add a test that fails without the fix and passes with it — not just a
re-run of the original repro. If the bug class can't be unit-tested
(e.g. a CI-range artifact), document the mechanism where the next
person will look (a runbook, an ADR, or a code comment on the
non-obvious constraint) so it's diagnosed once, not every time.

## Success criteria

- A one-sentence hypothesis was stated before any instrumentation.
- The fix targets the confirmed cause, not the first plausible guess.
- A regression test (or, where untestable, a documented mechanism)
  exists so the same symptom is recognized faster next time.

## Related

- Skill: `debug-ml-inference` (ML serving bugs specifically — D-01..D-37 first)
- Skill: `pr-review` (Standards pass may find the bug before you diagnose it)
- Skill: `incident-postmortem` (when the bug caused a real incident, not just a red CI run)
- Skill: `ci-green-verify` (confirms the regression test actually landed green)
