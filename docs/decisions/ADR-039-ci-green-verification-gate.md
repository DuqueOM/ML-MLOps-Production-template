# ADR-039 — CI-Green Verification as a Separated-Verb Agentic Gate

- **Status**: Accepted
- **Date**: 2026-07-02
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none. Executes item R9-05 of
  `docs/audit/ACTION_PLAN_R9_ENTERPRISE_BENCHMARK.md` (Anexo C).
- **Superseded by**: none
- **Related artifacts**:
  - `agentic/skills/ci-green-verify/SKILL.md` — the AUTO-mode verification
    skill.
  - `agentic/workflows/ci-green.md` — the `/ci-green` workflow.
  - `AGENTS.md` — anti-pattern D-36.
  - `agentic/workflows/release.md`, `agentic/skills/deploy-gke/SKILL.md`,
    `agentic/skills/deploy-aws/SKILL.md` — the callers this gate is wired
    into.

## 1. Context

The template did not have an agentic surface that actively verified GitHub
Actions CI status before a promote/release/deploy action. `agentic/workflows/release.md`
listed `gh run list --workflow=ci.yml --limit=1` as its first numbered step,
but nothing enforced that the output was actually green, checked more than
one workflow, or blocked the following steps if it wasn't. The R9 benchmark
(§4, Anexo C) asked directly: should an agent verifying CI status before a
risky action be CONSULT or STOP?

The answer required separating two different verbs that had been conflated
under one question:

1. **Verifying** CI status is a read-only observation — an agent should
   always be able to check it, the same way `git status` is always safe.
2. **Proceeding despite red CI** is a destructive-adjacent decision — it
   removes a safety signal on purpose, which is categorically different
   from "check and report."

Treating both under a single CONSULT or single STOP mode would either make
routine status checks annoyingly slow (CONSULT for a read) or make the gate
toothless (AUTO for an override). The precedent already in this repo —
GitHub branch protection and required status checks — makes exactly this
verb split at the platform level: anyone can view check status; only an
authorized override (admin bypass) can merge past a red required check, and
that bypass is itself logged.

## 2. Decision

Introduce a **verb-separated** agentic gate, not a single new mode:

| Verb | Mode | Rationale |
| --- | --- | --- |
| **Verify** CI status (`gh run list`/`gh api`, read-only) | **AUTO** | No side effects; an agent must always be able to look |
| **Re-run** a suspected-flaky job | **CONSULT** | Has real effects (consumes CI minutes, re-triggers a pipeline); a human confirms the "this looks flaky, not a regression" judgment |
| **Override** — proceed with promote/release/deploy while CI is RED or MISSING | **STOP**, unconditionally, no environment-based downgrade | Mirrors `rollback`'s `execute_rollback: STOP` regardless of dev/staging/prod — removing a safety signal is always a human decision with an audit trail, never a convenience |

### 2.1 New surfaces

1. **Skill `ci-green-verify`** (AUTO) — resolves a ref, lists every workflow
   run for the latest commit on that ref (not just `ci.yml`), classifies
   GREEN/RED/PENDING/MISSING per workflow, and reports. Never fixes,
   never overrides — see its own "What this skill is NOT" section.
2. **Workflow `/ci-green`** — the human-invokable entry point that wraps the
   skill and states the escalation path when red/missing.
3. **Anti-pattern D-36** in `AGENTS.md`: *"Promoting, tagging, or deploying
   without a verified-green CI check, or overriding a red/missing check
   without a STOP-class human approval + `scripts/audit_record.py`
   entry."*

### 2.2 Wiring into existing callers

- `agentic/workflows/release.md` step 1 ("Pre-Release Checks") is rewritten
  to actually invoke `ci-green-verify` and treat its verdict as a hard
  precondition for step 2 onward, instead of merely listing output.
- `agentic/skills/deploy-gke/SKILL.md` and `.../deploy-aws/SKILL.md` gain a
  precondition step before the `staging`/`prod` deploy path: verify CI
  green for the commit being deployed. `dev` is exempt (AUTO/sandbox,
  matches the skill's existing per-environment table).

### 2.3 Why this is not a new CI job

`ci-green-verify` reads the ALREADY-authoritative signal (GitHub Actions'
own run status via the API) — it does not re-run tests or add a check of
its own. Making it a CI job would be circular (a CI job cannot verify
"is CI green" about itself). It is agentic-surface-only, mirroring how
`rule-audit` and `doc-coherence` are also skills that read existing state
rather than new pipeline stages.

## 3. Invariants (contract-enforced)

- **I-039-1** — `override_red` (or any equivalently-named mode controlling
  proceeding past red/missing CI) MUST be `STOP` in every caller that wires
  in this gate, with no `escalation_override` de-escalating it — enforced
  by the same `validate_agentic_manifest.py --strict` rule that already
  forbids any mode de-escalation repo-wide.
- **I-039-2** — Verification itself (`verify_status`/equivalent) MUST be
  `AUTO` — an agent must never need permission to check status.
- **I-039-3** — A human override of D-36 MUST produce a
  `scripts/audit_record.py` entry before the gated action (release tag
  push, `kubectl apply` to staging/prod) proceeds.

## 4. Scope

**In scope**: the skill, the workflow, D-36, and wiring into `/release` +
`deploy-gke`/`deploy-aws`.

**Out of scope**:

- Autofixing red CI — that is ADR-019's (Agentic CI Self-Healing) surface,
  gated through its own shadow-mode timeline; this ADR's skill only
  observes and reports.
- A new blocking CI job — see §2.3.
- Extending the gate to non-release/deploy actions (e.g., merging a normal
  PR) — GitHub's own required-status-checks branch protection already
  covers that path; this ADR adds the gate specifically where the
  AGENT-DRIVEN workflows (`/release`, deploy skills) didn't have it.

## 5. Consequences

### Positive

- Closes a real gap: an agent-driven release or deploy could previously
  proceed on top of red CI with nothing stopping it except a human
  remembering to check.
- The verb separation (AUTO-verify / CONSULT-rerun / STOP-override) is
  reusable pattern language for any future "check an external signal
  before a risky action" gate — it doesn't need to be invented per-skill.
- Dogfoods the template's own AUTO/CONSULT/STOP protocol on itself, adding
  credibility to the claim that the protocol scales to new gates cheaply.

### Negative

- One more skill + workflow to maintain (small — read-only, `gh` CLI only,
  no new dependency).
- `/release` and the deploy skills gain one more step; mitigated by AUTO
  mode meaning it adds negligible latency for the common (green) case.

### Neutral

- Surface counts move: skills 20→21, workflows 16→17, anti-patterns
  D-01..D-35→D-01..D-36. Cascaded through `AGENTS.md`, `CLAUDE.md` (×2),
  `llms.txt`, and `templates/config/agentic_manifest.yaml` in the same PR
  (rule 16 / ADR-031 discipline).

## 6. Revisit triggers

- A real incident occurs where `ci-green-verify` itself gave a false
  GREEN (e.g., GitHub API returned stale data) → add a staleness check
  (compare `createdAt` against current time) as a follow-up hardening.
- Adopters report the AUTO-verify step adding meaningful latency to
  `/release` → consider caching within a single workflow run.
- CI self-healing (ADR-019) reaches a maturity where autofix-on-red is
  proven safe → this skill could gain an OPTIONAL "propose autofix" step,
  still gated CONSULT/STOP, never AUTO for the fix itself.

## 7. Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Single CONSULT mode for the whole gate (verify + override together) | Makes routine status checks unnecessarily interactive; erodes the value of AUTO-mode read operations that the rest of the repo relies on |
| Single STOP mode for the whole gate | Same problem in the other direction — a human would have to approve merely LOOKING at CI status, which trains people to click through STOP prompts, weakening the signal for when it actually matters |
| A new required CI job that blocks merge if a prior job failed | Circular (see §2.3); also duplicates what branch protection required-status-checks already does at the platform level |
| Do nothing; trust `gh run list` in `/release` step 1 as sufficient | This is the status quo the R9 benchmark flagged as a gap — it lists, it does not block |

## 8. Related

- `docs/audit/ACTION_PLAN_R9_ENTERPRISE_BENCHMARK.md` — the benchmark that
  identified this gap (Anexo C, item R9-05).
- `docs/decisions/ADR-005-agent-behavior-and-security.md` — the
  AUTO/CONSULT/STOP protocol this ADR extends with a new gate.
- `docs/decisions/ADR-019-agentic-ci-self-healing.md` — the explicitly
  out-of-scope autofix surface this ADR does not touch.
- `agentic/skills/rollback/SKILL.md` — the precedent for
  environment-independent STOP on a destructive-adjacent override.
