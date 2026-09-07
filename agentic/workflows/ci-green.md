---
description: Verify GitHub Actions CI status for a ref before a promote/release/deploy action — read-only check, never a bypass
---

# /ci-green

Invoke before `/release`, before `deploy-gke`/`deploy-aws` target
`staging`/`prod`, or any time a human asks "is CI green?". `/release` and
the deploy skills already call this internally as a precondition
(ADR-039) — invoke it directly when you just want the answer without
starting the larger workflow.

Authorization: **AUTO** to check; **STOP** to proceed past red/missing
(D-36). See `agentic/skills/ci-green-verify/SKILL.md` for the full
verb-by-verb breakdown.

## 1. Verify (AUTO)

Load `agentic/skills/ci-green-verify/SKILL.md` and follow its steps:

1. Resolve `{ref}` (defaults to `main`).
2. List every workflow run for the latest commit on `{ref}`.
3. Classify each: GREEN / RED / PENDING / MISSING.

## 2. Report

```text
CI status for {ref} @ {sha}:
  ✅ CI — Examples, Unit Tests & Coverage    success
  ✅ Validate Templates                       success
  ✅ Template-Context Tests                   success
  ✅ pr-smoke-lane                            success

Verdict: ALL GREEN — safe to proceed.
```

or, if not all green:

```text
CI status for {ref} @ {sha}:
  ✅ CI — Examples, Unit Tests & Coverage    success
  ❌ Template-Context Tests                   failure  (run 28552562658)
     → templates/service/monitoring/tests/test_alertmanager_routing.py
       ModuleNotFoundError: No module named 'tests.test_alertmanager_routing'

Verdict: RED — do NOT proceed with {caller-action}.
```

## 3. If not all green

- **Looks like a real failure** → stop here. Report to the human; do not
  attempt to fix inside this workflow (that's a separate debugging task,
  or `/incident` if it's a live production concern). The caller
  (`/release`, deploy skill) halts.
- **Looks flaky** (timeout, transient infra) → propose a re-run
  (CONSULT), per the skill's Step 4. Never re-run silently.
- **Human wants to proceed anyway** → this is D-36. Emit `[AGENT MODE:
  STOP]`, require an explicit `scripts/audit_record.py` entry documenting
  the override reason before the caller's action continues. There is no
  environment where this becomes AUTO or CONSULT — mirrors `/rollback`'s
  unconditional STOP on `execute_rollback`.

## What this workflow is NOT

- Not a CI-fixing workflow — see `agentic/rules/16-doc-coherence.md`/rule
  16 for doc drift, or ADR-019's shadow-mode self-healing surface for
  autofix; this workflow only observes and reports.
- Not a substitute for GitHub's own required-status-checks branch
  protection — that still gates normal PR merges; this workflow exists for
  the AGENT-DRIVEN release/deploy path specifically.

## Related

- Skill: `ci-green-verify/SKILL.md`
- Workflow: `/release` (calls this internally as step 1)
- Skills: `deploy-gke`, `deploy-aws` (call this internally before
  `staging`/`prod`)
- ADR-039 (CI-green verification gate) — the decision record
- Anti-pattern D-36 (`AGENTS.md`)
