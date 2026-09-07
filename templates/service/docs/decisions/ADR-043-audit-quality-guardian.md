# ADR-043 — Audit-Grade Quality Guardian: a Maintenance Agent for Enterprise Audit Standards

- **Status**: Accepted
- **Date**: 2026-07-07
- **Deciders**: Template maintainer (`@DuqueOM`)
- **Supersedes / amends**: none. Executes the remediation and
  preservation plan derived from the R11 enterprise/ISO audit
  (`docs/audit/AUDIT_R11_ISO_ENTERPRISE.md`).
- **Superseded by**: none
- **Related artifacts**:
  - `agentic/rules/18-audit-quality.md` — the always-on quality rule with
    anti-patterns Q-01…Q-08.
  - `agentic/skills/enterprise-audit/SKILL.md` — the 23-domain audit
    procedure.
  - `agentic/workflows/audit-quality.md` — the `/audit-quality` workflow.
  - `agentic/workflows/document-changes.md` — the `/document-changes`
    workflow (Agent-DocUpdater's operational entry point).
  - `AGENTS.md` §Agent Architecture — the `Agent-QualityGuardian` entry.

## 1. Context

The R11 audit evaluated this repository against 23 enterprise audit
domains (19 classical — governance, traceability, code quality, security,
dependencies, licensing, CI/CD, reproducibility, secrets, configuration,
testing, documentation, versioning, incidents, change management, commit
hygiene, supply chain, MLOps, evidence — plus 4 architect-level domains:
observability, architecture, technical debt, developer experience). The
verdict was "enterprise-ready with caveats": zero critical findings, but
several medium findings that share one property — **they are all standards
that erode silently**. Nothing in CI failed when `llms.txt` claimed MIT
while `LICENSE` was Apache-2.0; nothing complained when the template's own
release carried no SBOM while its scaffolded services signed theirs;
nothing tracked cyclomatic-complexity hotspots growing past review
thresholds.

The repository already has the machinery for making standards
self-preserving: path-scoped rules, skills with mode boundaries, slash
workflows, and deterministic gates (rule 16 / ADR-031 proved the pattern
for documentation coherence). What was missing is an owner: no Layer 3
agent's charter says "keep the repository at the bar an external auditor
would hold it to."

A second, related gap: `Agent-DocUpdater` exists in the agent architecture
("keeps documentation in sync with code") but had no operational entry
point — no workflow an operator or another agent could invoke to say
"document everything this change touched." Documentation updates happened
inside other workflows (release, doc-coherence) or not at all.

## 2. Decision

1. **Charter `Agent-QualityGuardian`** as a Layer 3 maintenance agent.
   Its scope is the audit surface itself: it runs the recurring
   enterprise audit, watches the quality anti-patterns, and chains to
   `Agent-DocUpdater` so findings and fixes are always documented.

2. **Encode the erosion-prone standards as anti-patterns Q-01…Q-08** in
   `agentic/rules/18-audit-quality.md` (always-on for CI/release/docs
   surfaces). They get a `Q-` namespace, NOT new `D-` numbers, because:
   - `D-NN` identifies *runtime/ML/infra* failure modes with measured
     production consequences; `Q-NN` identifies *audit-standard erosion*
     — different review audience, different trigger surface;
   - the `D-01→D-38` count is restated in README, llms.txt, CLAUDE.md and
     enforced by the C3 coherence check — extending that namespace for a
     different concern would couple every future quality pattern to a
     4-document renumber cascade.

3. **Ship the audit procedure as a skill** (`enterprise-audit`): scanning
   is AUTO (read-only), fixing findings is CONSULT, and downgrading any
   existing quality gate is STOP — the same verb separation ADR-039
   established for CI status.

4. **Give `Agent-DocUpdater` its operational entry point**:
   `/document-changes` collects the change surface (diff), writes the
   CHANGELOG entry, propagates restated facts (rule 16 cascade map), and
   records an audit-trail entry. `/audit-quality` ends by chaining into
   it, so every audit that changes anything leaves documentation in a
   coherent state by construction.

## 3. Consequences

**Positive**

- The 23-domain bar becomes recurring and owned instead of a one-off
  report; drift between audits gets caught by the always-on rule.
- Documentation of changes becomes an invocable verb. Other workflows can
  (and `/audit-quality` does) end with "chain `/document-changes`".
- The Q-namespace can grow without triggering the D-count cascade.

**Negative / accepted costs**

- Two anti-pattern namespaces to learn (`D-` runtime, `Q-` audit). The
  rule header states the boundary; the alternative (one namespace) costs
  a 4-document renumber per addition.
- The guardian's checks partially overlap `rule-audit` (D-invariants) and
  `doc-coherence` (C-checks). This is deliberate layering, not
  duplication: `enterprise-audit` *composes* those gates and adds the
  domains they don't cover (complexity, licensing, supply-chain evidence,
  reproducibility).

**Revisit triggers**

- A second maintainer joins → move M-1 (0-reviewer merges, unsigned
  commits requirement) from "disclosed limitation" to enforced ruleset,
  and update `docs/governance/branch-protection.md` + ADR-026 together.
- Q-patterns exceed ~15 → consider promoting the Q-table into AGENTS.md
  with its own coherence check.
- A deterministic complexity gate (e.g. radon/xenon in CI) replaces the
  advisory scan → rule 18 thresholds become the gate config's source of
  truth.
