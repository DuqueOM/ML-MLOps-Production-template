---
name: ci-green-verify
description: Verify GitHub Actions CI status before a promote/release/deploy action proceeds — read-only check, never an override
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(gh:*)
when_to_use: >
  Use before any promote, release, or deploy action, and any time a human
  asks "is CI green?" or "can we ship this?". Also used internally as a
  precondition by the /release workflow and the deploy-gke / deploy-aws
  skills (D-36) — never called by those to grant an override, only to
  confirm or to produce the evidence for a STOP.
  Examples: 'is CI green on main?', 'check before we tag', 'verify checks
  pass before deploying to prod'.
argument-hint: "[ref] (branch or commit SHA; defaults to main)"
authorization_mode:
  verify_status: AUTO       # read-only; gh api / gh run list, no writes
  rerun_flaky_job: CONSULT  # has effects (consumes CI minutes, re-triggers)
  override_red: STOP        # proceeding with promote/release/deploy despite red CI
---

# CI-Green Verify

Answers exactly one question — "is the CI state for `{ref}` currently
green?" — and never more. This skill does not fix red CI, does not decide
whether a failure is safe to ignore, and does not grant permission to
proceed. Those are CONSULT/STOP decisions made by the caller, not by this
skill (AUDIT R9-05, ADR-039).

## Why this exists

Both repos in this ecosystem (this template and `agent-local`) discovered
in AUDIT R8/R9 that "the tests pass locally" and "CI is green on GitHub"
can silently diverge (a lane nobody wired, a scope mismatch between root
and service pyproject). A release or deploy that only checks local state
can ship on top of a red remote pipeline. This skill makes "check the
remote, authoritative state" a first-class, reusable, AUTO-mode step
instead of an ad-hoc `gh run list` a human has to remember to run.

## Step 1 — Resolve the ref (AUTO)

```bash
REF="${1:-main}"
git rev-parse "$REF"  # fail loud if the ref doesn't exist locally
```

## Step 2 — List every workflow run for that ref (AUTO, read-only)

```bash
gh run list --branch "$REF" --limit 20 \
  --json name,status,conclusion,headSha,workflowName,createdAt
```

Collect **every** workflow that has run for the most recent commit on
`$REF` — not just `ci.yml`. A repo typically has several required lanes
(see this template's own `.github/workflows/*.yml`); the skill must check
all of them, not the first one that returns.

## Step 3 — Classify (AUTO)

For the most recent run of each distinct `workflowName` at the target SHA:

| `status` | `conclusion` | Classification |
| --- | --- | --- |
| `completed` | `success` | GREEN |
| `completed` | `failure` / `cancelled` / `timed_out` | RED |
| `in_progress` / `queued` | — | PENDING |
| (no run found for this SHA) | — | MISSING — treat as RED; a lane that never ran is not evidence of passing |

Overall verdict:

- **ALL GREEN** → proceed.
- **ANY RED or MISSING** → STOP; do not proceed with the caller's
  promote/release/deploy action. Report exactly which workflow(s) failed,
  with a link (`gh run view <id> --web` or the run URL from the JSON) and
  the failing job/step names (`gh run view <id> --log-failed`).
- **ANY PENDING, none RED** → report status; the caller decides whether to
  wait (this skill does not poll/block on its own — polling belongs to
  the caller's own retry logic, e.g. `Monitor`/background wait, never a
  busy loop inside this skill).

## Step 4 — Optional: re-run a flaky job (CONSULT)

If a failure looks like a known-flaky infra issue (timeout, runner
capacity, a transient network fetch) — NOT a real test/lint failure — the
skill may PROPOSE a re-run:

```text
[AGENT MODE: CONSULT]
Operation: gh run rerun <run-id> --failed
Reason: <job> failed with <transient signature>; re-running rather than
        treating as a real regression
Waiting for: operator confirmation
```

Never auto-rerun. A flaky-looking failure that is actually a real
regression re-run into green is a false signal — the human call is not
optional here.

## Step 5 — Never grant an override (STOP)

If the caller (a human, or another skill/workflow acting on a human's
instruction) wants to proceed DESPITE red/missing CI, this skill's answer
is always:

```text
[AGENT MODE: STOP]
Operation: Proceed with {caller-action} while CI is RED/MISSING for {ref}
Reason: Anti-pattern D-36 — promoting, tagging, or deploying without
        verified-green CI (or overriding red) requires explicit human
        sign-off and an audit record, every time, no exceptions for
        urgency.
Waiting for: operator confirmation AND scripts/audit_record.py entry
             documenting the override reason before the action proceeds.
```

The override itself is never performed by this skill — it only refuses
and defers to the human + the audit trail. The caller (`/release`,
`deploy-gke`, `deploy-aws`) is the one that actually gates its own next
step on this refusal.

## What this skill is NOT

- **Not a CI dashboard replacement.** For routine "how's CI doing"
  browsing, just use `gh run list`/`gh run watch` directly — this skill
  exists for the specific moment before a promote/release/deploy decision.
- **Not a fixer.** If CI is red, this skill reports why; it does not
  attempt `ci-self-healing`-style autofixes (that is ADR-019's Phase 1/2
  surface, gated separately, shadow-mode-first).
- **Not authorized to relax D-36.** No `escalation_override` may
  de-escalate `override_red` below STOP (enforced by
  `validate_agentic_manifest.py --strict`, same rule as every other mode
  in this repo).

## Invariants

- Verification is always AUTO and read-only — an agent must always be
  able to check CI status without asking permission first.
- An override of red/missing CI is always STOP, with no environment- or
  urgency-based downgrade (mirrors `rollback`'s `execute_rollback: STOP`
  regardless of dev/staging/prod).
- Every STOP triggered by this skill that a human overrides MUST produce
  a `scripts/audit_record.py` entry (D-36) before the caller's action
  proceeds.
