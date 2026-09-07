# Documentation Path Reference Gate

**Status**: Active enforcement (2026-09-04+)
**Enforcement**: `scripts/check_doc_path_refs.py` + `doc-path-refs` job in `.github/workflows/validate-templates.yml` +
pre-commit hook `doc-path-refs`
**Baseline**: `.doc-path-baseline.yml`
**Related**: ADR-030 (Copier scaffolding migration), ADR-031 (rule 16 doc coherence), `docs/governance/cicd-templates-drift.md`

## What this gate enforces

Every repo-relative path named inside backticks in living documentation —
or inside a comment in a tracked `.py`, `.yml`, `.yaml`, `.sh` or `Makefile`
— must resolve to a file or directory that exists.

The code-comment half was added on 2026-09-04. The gate shipped scanning
`.md`/`.txt` only, which left the then-current .security-baselines/tfsec.yml
justifying three suppressed HIGH findings against a directory ADR-030 had
deleted, and
a set of test comments describing a layout that had not existed since June.
Measured before widening: **15 unresolved paths across 309 code files** —
small enough for a hard gate.

## Why this gate exists

The Copier migration (ADR-030, commit `fe89e92`, 2026-06-30) relocated
the entire scaffolder payload from `templates/{cicd,k8s,monitoring,docs,
eda,infra,common_utils,scripts}` to `templates/service/*`.

It updated every reference that **executes**: the runtime workflows,
`Makefile`, `.github/CODEOWNERS`, the Kustomize overlays, two contract
tests, `scripts/verify_enterprise_adoption.py`, and
`scripts/check_cicd_template_drift.py` itself — 14 files. Those break
loudly when a path is wrong, so they got fixed.

It updated **none of the prose**. Thirty documents kept pointing at
directories that no longer existed:

| Surface | Examples |
| --- | --- |
| Root docs | `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `MIGRATION.md`, `CLAUDE.md` |
| Runbooks | `gcp-wif-setup.md`, `aws-irsa-setup.md`, `terraform-state-bootstrap.md`, `closed-loop-sla.md`, `digest-pin-init-image.md` |
| Governance | `docs/security/compliance-mapping.md`, `docs/PROGRESSION.md` |
| Machine-readable | `llms.txt` |

Nothing noticed, because until this gate no check in the repository
verified that a path named in a document exists.

The failure then compounded. Two audit rounds later, commit `f219895`
("feat: add Agent-QualityGuardian + R11 audit remediation", 2026-07-08)
copied the dead templates/cicd/ path **into the audit tooling itself**:

- `agentic/rules/18-audit-quality.md` scoped its glob list to
  `templates/cicd/**`, a directory that had not existed for eight days
  shy of two months;
- `agentic/workflows/audit-quality.md` ran its Q-01 unpinned-action sweep
  over templates/cicd with `2>/dev/null`, so the missing directory was
  silent.

Both propagated across three adapter surfaces (`agentic/`, `.devin/`,
`templates/service/agentic/`) via the normal sync. The rule that defines
the repository's quality anti-patterns was itself pointing at nothing,
and reported green the entire time.

## The lesson this gate encodes

**Documentation that names a path is making a checkable claim.** The
migration was validated by execution, so everything executable survived
and everything declarative rotted. A repository that enforces byte-level
drift gates on vendored scripts, digest pinning on container images and
SHA pinning on actions had no equivalent check on the claims its own
documents make about its own layout.

## The dual-perspective model

A reference is valid if it resolves from **either** root:

1. the repository root — the perspective of the template repo's docs;
2. `templates/service/` — the perspective of a *generated service*.

The second root is not a convenience. `agentic/**` is mirrored
byte-for-byte into `templates/service/agentic/` (enforced by
`check_vendored_runtime_drift.py`), and `AGENTS.md` / `AGENT_CONTEXT.md`
are vendored verbatim. One text has to serve both readers: the bare form
scripts/refresh_contract.py is correct prose in a rule that executes
inside a scaffolded service, even though this repo only has that file at
`templates/service/scripts/refresh_contract.py`.

Documents that ship into a service resolve against both roots. Documents
that never leave the template repo resolve against the repo root only.

## What this gate does NOT enforce

- **Frozen records.** `docs/decisions/`, `docs/audit/`, `releases/`,
  `CHANGELOG.md` and `VALIDATION_LOG.md` are excluded. An ADR describing
  the tree as it stood in May 2026 is *supposed* to name paths that have
  since moved; rewriting them would falsify the record. This is the same
  reasoning that keeps historical audit snapshots immutable (ADR-045).
- **Non-literal tokens.** Placeholders (`<id>`, `{service_slug}`), globs,
  brace sets, shell arguments, `file:line` suffixes, URL fragments and
  ellipses are illustrative, not claims about the tree.
- **Paths outside this repo's top-level directories.** A runbook naming
  `src/main.py` is describing the adopter's tree, not ours.
- **External URLs and site-root links.** `http(s)://`, `mailto:` and
  targets beginning with `/` stay with the `Link Check` job, where network
  latency and third-party flakiness are tolerable because that job does not
  gate a merge. Internal relative links *are* checked here — see below.
- **String literals in code.** Only comments are scanned. A path built at
  runtime is program logic, not a claim, and matching it would report
  every `Path(...) / "templates"` expression.
- **Glob and brace shapes.** `deploy-*.yml` and `deploy-{gcp,aws}.yml` are
  legitimate shorthand. A negative lookahead drops them rather than
  reporting the truncated prefix `.../deploy-` as dead — the false
  positive that this widening produced on its first run.
- **Stand-ins and files that must not exist.** Uppercase placeholders
  (`ADR-XXX.md`) and any `*.local.*` path are excluded; the latter is
  gitignored by contract, so a comment naming one is describing something
  that is *supposed* to be absent.
- **Paths written as plain prose.** In Markdown this is a deliberate
  convention, not a hole: a code span asserts *this resolves today, from this document's
  perspective*. A document discussing a path that has been removed, or
  illustrating a form that is only valid from the other root — this one
  does both — names it without code formatting. That is how you write a
  path you are talking *about* rather than pointing *at*. Do not reach
  for the baseline instead: the baseline is for references that are
  still making a live claim.

  **This escape hatch does not exist in a code comment**, where there is no
  formatting to distinguish naming a path from pointing at one. Discussing a
  removed path in a comment therefore means describing it rather than
  spelling it — "the pre-ADR-030 layout, one level higher" instead of the
  path itself. That is a real limitation of the code-comment half of this
  gate, and the cost of not having a per-line opt-out marker, which would be
  a bigger hole than the one it closes.

## Markdown link targets, and why they are checked here

A link target resolves **relative to the file that contains it**, not to the
repo root. That distinction produced the only broken link this repo had:
`templates/service/README.md` pointing at
`templates/service/docs/CCDS_MAPPING.md`, which from inside that directory
means the doubled templates/service/templates/service/docs/… path. I
introduced it in #84
by rewriting path text without accounting for link relativity, and CI caught
it — which is the argument for checking it locally instead.

The `Link Check` job in `docs-quality.yml` also validates these, and it is a
real gate. But its coverage has a shape worth stating:

- it triggers only on `pull_request` with `paths: **/*.md`, so a PR that
  moves or deletes a file without touching a `.md` never runs it;
- on a PR it passes `check-modified-files-only: yes`, so it sees only
  changed files.

**A link breaks when its target moves, not when the linking file changes.**
That case is invisible at PR time and surfaces up to seven days later in the
Monday 06:00 UTC scan, on `main`, as a red scheduled run that blocks nobody.
That is long enough for someone to suppress it instead of fixing it — which
is exactly what happened to `../SECURITY.md`, silenced by a dedicated
`ignorePatterns` entry until #86.

So the split is by *what the check needs*, not by syntax: internal links are
deterministic, need no network, and run in pre-commit; external URLs need the
network and stay off the critical path.

Code spans are stripped before link matching, because a code span containing
link-shaped text (`[text](path)`) is documentation *about* links.

## Baseline contract

`.doc-path-baseline.yml` carries the references that do not resolve but are
not defects. Every entry declares a `kind:`, and **the two kinds are verified
differently because they are not the same claim.**

| Kind | The claim | How it is checked |
| --- | --- | --- |
| `unimplemented` | "we intend to build this" | `expiry:` — a deadline is the only honest check on an intention |
| `runtime-artifact` | "this resolves at runtime, and X creates it" | `created-by:` — the gate asserts that file exists and still names the path |

The second is a deliberate correction. These entries originally carried a
one-year expiry, and that was ceremony: the condition never changes, so the
date could only ever be bumped. A date that can only be postponed trains
reviewers to postpone dates, which degrades the mechanism for the entries
where the deadline *is* the point. Replacing it with `created-by:` turns a
dated assertion into one that is falsified automatically the moment it stops
being true — if the skill that writes `docs/concept_drift_log.md` is deleted
or stops mentioning it, the entry fails on the next run.

A `runtime-artifact` carrying an `expiry:` is rejected outright, so the two
mechanisms cannot be quietly mixed.

Four failure modes are enforced:

| Condition | Result |
| --- | --- |
| A path is unresolved and not baselined | fail — the new-defect case |
| An `unimplemented` entry is past its `expiry` | fail — forces a fix or a fresh justification |
| A `runtime-artifact`'s creator is gone, or no longer names the path | fail — the claim is no longer true |
| A baselined entry now resolves | fail — the baseline may not outlive its reason |

New dead paths are **never** baselined. They fail on the PR that
introduces them, which is precisely the failure mode that would have
stopped `f219895`.

## Operational cost

595 documents plus 330 code files, one regex pass each, and a filesystem
`exists()` per candidate token. Tens of milliseconds on a CI runner,
dominated by Python startup. The pre-commit hook fires on `*.md`, `*.txt`,
`*.py`, `*.yml`, `*.yaml`, `*.sh`, any `Makefile`, and the baseline.

## Revisit triggers

- If Markdown link targets are added to the scan, this document and the
  script docstring change together.
- If the repository ever drops the byte-identical vendoring of `agentic/`
  into `templates/service/agentic/`, the dual-perspective model collapses
  to a single root and the `DUAL_PREFIXES` list should be deleted rather
  than maintained.
- When `.doc-path-baseline.yml` reaches zero entries, the baseline file
  and its parsing code can be removed and the gate becomes unconditional.
