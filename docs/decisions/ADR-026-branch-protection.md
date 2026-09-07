# ADR-026 — Branch Protection & Tag Immutability via GitHub Rulesets

- **Status**: Accepted
- **Date**: 2026-05-15
- **Supersedes / amends**: none. Complements ADR-002 (model promotion governance),
  ADR-005 (agent behavior + supply chain), ADR-024 (May 2026 audit posture).
- **Authors**: Template maintainer (`@DuqueOM`).
- **Related artifacts**:
  - `docs/governance/branch-protection.md` — canonical config table (single source of truth).
  - `scripts/setup_branch_protection.sh` — idempotent applier via `gh api`.

## Context

The template ships an enterprise governance surface (15 rules, 16 skills,
12 workflows, 32 anti-patterns, 24 ADRs) and **claims** that `main` is the
audited baseline. Until this ADR, that claim was unenforced at the SCM
layer: a force-push could rewrite history, a deletion could vaporise the
release tag chain, and a bypassed PR could land in `main` without ever
triggering CI. Adopters who clone the template inherit our governance
**story**, not our **enforcement**.

Three concrete realities shape this decision:

1. **Bus factor = 1.** `@/home/duque_om/projects/template_MLOps/.github/CODEOWNERS:8-12`
   declares the single-maintainer reality. Any policy that requires a
   second human (`required_approving_review_count >= 1` with the only
   CODEOWNER being the author) creates a self-block that can only be
   resolved via bypass — making bypass a daily tool instead of break-glass.

2. **DCO already in place, GPG/SSH commit signing is not.** The repo
   enforces `Signed-off-by` via `@/home/duque_om/projects/template_MLOps/.github/pull_request_template.md`
   and `DCO.md`. Layering required commit signing on top adds verification
   surface (key management, contributor friction, lost-key recovery) that
   is not proportional to the marginal protection — DCO + verified commit
   email + IP-attribution are already in the audit trail.

3. **CI workflow inventory is split between always-on and conditional.**
   - Always on every PR: `validate-templates`, `ci-examples`, `pr-smoke-lane`,
     `pr-evidence-check`.
   - Path-filtered (only run when relevant files change): `docs-quality`,
     `kyverno-smoke`.
   - Schedule-only: `golden-path`, `golden-path-extended`, `policy-tests`.

   GitHub Rulesets fail closed on missing required checks: a check that
   does not report on a given PR blocks merge forever. Required-checks
   list MUST be drawn only from the always-on set.

4. **Tag immutability is a separate concern from branch protection.**
   `release-on-tag.yml` triggers on `push: tags: v*`. A write-credentialed
   actor who can delete and recreate `v0.15.3` can re-execute the release
   pipeline against arbitrary content. Branch protection on `main` does
   not cover this; tags need their own ruleset.

## Decision

Adopt **two GitHub Rulesets** on the repository:

### Ruleset 1 — `main` branch baseline (Active)

| Knob | Value | Rationale |
| ------ | ------- | ----------- |
| Target | branch `main` only | `dependabot/*`, `codex/*`, `feature/*` need to be force-pushable and deletable; protecting only `main` keeps the contract surgical. |
| Enforcement | Active | "Evaluate" mode reports without blocking — useful for staging the rule, useless as protection. |
| Restrict deletions | ON | `main` is the audit baseline; deletion is never legitimate. |
| Block force pushes | ON | Force push can rewrite history past CI; never legitimate to `main`. |
| Require pull request | ON | Codifies the existing flow. |
| Required approvals | **0** | Bus-factor=1; revisit when a co-maintainer lands. See §Revisit triggers. |
| Dismiss stale reviews on push | ON | Cheap correctness; aligns with the 0-approvals choice for forward compat. |
| Require review from CODEOWNERS | OFF | Same reason as 0 approvals. Turning ON with one CODEOWNER who is also the only contributor creates a permanent self-block. |
| Require last pusher to be different from approver | OFF | Implied by the 0-approval choice; cannot meaningfully apply with bus-factor=1. |
| Require status checks to pass | ON | The teeth of this ruleset. |
| Required checks | (see §Required Status Checks below) | Drawn only from always-on PR jobs to avoid the missing-check deadlock. |
| Require branches up-to-date before merging | OFF | Forces serial rebase on every prior merge; for a low-PR-volume repo the churn outweighs the marginal staleness risk. Activate when concurrent PR rate justifies it. |
| Require conversation resolution before merging | ON | Cheap, prevents review TODOs from being implicitly closed at merge. |
| Require signed commits | OFF | Redundant with DCO under current setup; see Context §2. |
| Require linear history | ON | Squash or rebase merge only. The CHANGELOG and `git log --oneline` reading workflows already assume linear history. |
| Require deployments to succeed | OFF | The repo has no environments configured directly; deploy environments are in the **scaffolded** services, not the template repo. |
| Block creations | OFF | `main` already exists; turning this ON could reject legitimate restoration. |
| Block updates (read-only mode) | OFF | Repository is actively maintained. |
| Bypass actors | `Repository admin` (role) | Break-glass only. Roles age better than user lists; audit log captures every bypass with reason. |

#### Required Status Checks (final list — exactly 6)

| Check (display name reported by GitHub) | Workflow file | Why it gates |
| ---- | ---- | ---- |
| `Tests & Coverage / Python 3.11` | `ci-examples.yml` | Coverage + behavior |
| `Tests & Coverage / Python 3.12` | `ci-examples.yml` | Forward Python compat |
| `Self-audit (secrets + IaC + supply chain)` | `validate-templates.yml` | Security scans + secret detection |
| `Python Lint + Type Check` | `validate-templates.yml` | black / isort / flake8 / mypy / bandit |
| `Agentic System Validation` | `validate-templates.yml` | Governance contract: rules, skills, workflows, AGENTS.md |
| `Scaffolder End-to-End Test` | `validate-templates.yml` | The scaffolder still produces a working service (catches D-32-class regressions) |

**Deliberately NOT required** (path-filtered or schedule-only — would create
phantom-required-check deadlock):

- `docs-quality` (path-filtered to `**/*.md`)
- `Kyverno Admission Smoke` (path-filtered to policies/scripts)
- `Golden Path E2E` and `…(extended)` (schedule + workflow_dispatch)
- `Policy Tests (D-XX anti-patterns)` (schedule + push-only, no PR trigger)

The **other 8 jobs** of `validate-templates.yml` (Kubernetes validate, Terraform
validate, Docker lint, Security Baseline Expiry, Test Clock Isolation, Agentic
Adapter Drift, Dashboard Inventory, common_utils Drift) are not on the required
list because they would be added or removed as the audit gates evolve; they
must still be GREEN for a clean PR (they fail the workflow), they just don't
gate at the SCM layer. Adding them later as required is a one-line script change.

### Ruleset 2 — Tag immutability `v*` (Active)

| Knob | Value | Rationale |
| ------ | ------- | ----------- |
| Target | tag pattern `v*` | All semantic-version tags. |
| Enforcement | Active | Same logic as Ruleset 1. |
| Restrict deletions | ON | Tags drive `release-on-tag.yml`; deletion + recreation = release hijack. |
| Block force pushes | ON | A tag pointing at a different commit re-executes the release pipeline against arbitrary content. |
| Required checks | none | Tags are post-merge; they reference a commit that already passed Ruleset 1. |
| Bypass actors | `Repository admin` | Identical posture to Ruleset 1. |

## Options considered and rejected

### A. Require 1 approving review now

Rejected. With one CODEOWNER (`@DuqueOM`) who is also the author of every
PR, this would block every merge without bypass. Bypass-as-a-tool defeats
the audit trail. Re-evaluate when a co-maintainer is onboarded
(see §Revisit triggers).

### B. Require signed commits (GPG / SSH / S/MIME)

Rejected for now. DCO + verified commit email already cover author
attribution. Adding required signing forces every contributor (including
Dependabot via `commit.gpgsign`) to manage keys; the marginal protection
against impersonation is small for a public template repo. Revisit if
the repo ever moves to a regulated / SBOM-attested distribution model.

### C. Require branches to be up-to-date before merging

Rejected for current PR volume (single-digit per week). Forces serial
rebase on every merge; for a low-volume repo the developer-time cost
exceeds the probability of merge-skew bugs that the always-required
`Scaffolder End-to-End Test` would not catch. Re-evaluate at >5 concurrent
PRs/day.

### D. Add `golden-path` to required checks

Rejected. `golden-path.yml` triggers on schedule and `workflow_dispatch`,
not on `pull_request`. A required check that never reports = permanent
merge block. The existing weekly schedule + branch protection on `main`
gives the same evidence without coupling PR latency to a 30-minute E2E run.

### E. No bypass at all

Considered. Rejected because legitimate break-glass exists (revert a
malicious commit pushed by a compromised CI token, hotfix a security CVE
mid-incident). `Repository admin` role bypass with audit log is the
minimum defensible posture.

### F. Per-environment ruleset duplication on the template repo

Rejected. Environment-protected deploys live in the **scaffolded** services
(`templates/cicd/deploy-*.yml` reference `environment: staging|production`),
not the template repo itself. Adopters configure their own per-environment
rules. This ADR governs the source-of-truth repo only.

## Consequences

### Positive

- **Audit teeth.** "Production-style governance" stops being a README claim
  and becomes an enforced contract at the SCM layer.
- **Tag chain integrity.** Releases (v0.13.0 onward) become immutable in
  practice, not just by convention.
- **Reproducibility.** `scripts/setup_branch_protection.sh` makes the
  ruleset declarative; an adopter forking the template can run one
  command to inherit the same posture.
- **No CI deadlock.** Required-checks list is drawn from the always-on
  set; PRs cannot be eternally blocked by a missing path-filtered check.

### Negative / costs

- **One more script to maintain** (`scripts/setup_branch_protection.sh`).
  Contained: it has no runtime path, runs only when manually invoked or
  in a future bootstrap workflow.
- **Required-checks list drifts if workflow names change.** Mitigation:
  the script reads names from the doc table; the contract is human-
  reviewable in `docs/governance/branch-protection.md`.

### Neutral

- **Bypass remains possible** for `Repository admin`. This is not a
  weakness; an enforced policy with no break-glass is operationally
  brittle. The audit log makes every bypass attributable.

## Validation

- `scripts/setup_branch_protection.sh --dry-run` prints the JSON payload
  that would be sent to `POST /repos/{owner}/{repo}/rulesets`.
- After application, `gh api repos/:owner/:repo/rulesets` returns 2
  rulesets with `enforcement: active`.
- Live verification: open a draft PR with one of the required checks
  failing → merge button must be disabled with the failing-check reason.
- Tag verification: `git push --force origin v0.15.3` from a non-admin
  account must be rejected with the ruleset reason.

## Revisit triggers

Re-open this ADR when ANY of the following becomes true:

| Trigger | Likely change |
| --------- | --------------- |
| Second CODEOWNER onboarded | Set `required_approving_review_count: 1` and `require_code_owner_review: true`. |
| PR volume sustained >5 concurrent/day | Turn on "Require branches up to date" and reassess required-checks set. |
| External adopter requests SOC 2 / HIPAA posture | Add required commit signing and consider `block deletions` on additional protected branches. |
| New always-on PR workflow added | Add it to the required-checks list in `docs/governance/branch-protection.md`, run the apply script. |
| Workflow renamed | Update both the doc table and the script in the same PR (the workflow rename PR itself MUST update them, enforced by review). |

## Notes on adopter use

This ADR governs the **template source repo**, not the scaffolded service.
Adopters of the template who fork or clone may apply
`scripts/setup_branch_protection.sh` to their fork; they are expected to
adapt the required-checks list to whatever workflows their fork actually
ships. The doc + script structure makes that adaptation a one-file change.
