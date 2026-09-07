# ADR-025: `common_utils/` distribution model

- **Status**: Proposed (DRAFT)
- **Date**: 2026-05-04
- **Authors**: Duque Ortega Mutis
- **Triggered by**: External feedback gap 6.1 (May 2026 triage),
  identified as recurring technical debt in past audits.

## Context

`common_utils/` is the shared Python library that ships:

- `secrets.py` (D-17/D-18 secret resolver)
- `risk_context.py` (ADR-010 dynamic risk evaluation)
- `prediction_logger.py` (D-21/D-22 prediction logging)
- `agent_context.py` (typed agent handoffs)
- `auth.py`, `audit.py`, `model_loader.py`, and ~10 more modules

It exists in **two locations** in the repository:

1. `templates/common_utils/` — the **template source of truth**.
   Modified by every PR, runs in `templates/tests/unit/`.
2. Inside each scaffolded service, copied verbatim by
   `templates/scripts/new-service.sh`. Lives at
   `<service>/common_utils/` after scaffolding.

This is **dual-source by design but dual-truth by accident**. There
is no automated mechanism that prevents an adopter from editing the
copied version and accidentally drifting from the template's
version. Past audits have repeatedly flagged this as latent debt.

## The actual problem (precise)

The dual-source pattern manifests as three concrete pain points:

1. **Bug-fix delivery latency.** When a security fix lands in
   `templates/common_utils/secrets.py` (e.g. HIGH-9 in v0.15.0), every
   already-scaffolded service holds a stale copy. There is no
   mechanism telling those adopters to re-pull.

2. **Schema drift in tests.** Tests under `tests/unit/` import from
   `common_utils.X` — the import works in the template AND in the
   scaffolded service, but the two physical files diverge silently.

3. **Cognitive load on contributors.** A new contributor sees
   `common_utils/` referenced from many places and reasonably asks
   "which one is canonical?". The answer ("the one in
   `templates/`") is not discoverable from the directory layout.

## Why this is being formalized NOW

External feedback flagged it; past audits also flagged it. Until
now there has been no ADR forcing a decision. This ADR's purpose is
NOT to pick a winner today — it is to **enumerate the options with
honest cost / benefit** so the next audit closes the debate.

## Options

### Option A — Keep dual-source + add a CI drift check

**What it is.** Continue copying `common_utils/` into scaffolded
services. Add a CI job that scaffolds a fresh service AND `diff`s
its `common_utils/` against `templates/common_utils/`; failure on
any divergence except known-templated substitutions (e.g. service
name).

**Cost**: ~1 day to write the diff job + maintain the
"intentionally-templated" allowlist over time.

**Pros**:

- Zero external dependency. Adopters keep getting a self-contained
  service after `new-service.sh`.
- Trivially debuggable: the file IS in the service, no PYTHONPATH
  magic.
- Compatible with air-gapped clusters / private registries.

**Cons**:

- Bug-fix delivery latency unchanged. Scaffolded services still
  hold stale copies.
- The CI gate guards the SCAFFOLD step, not the post-scaffold
  evolution of `common_utils/` inside an adopter's repo.
- Repository size grows with every release of the template.

### Option B — Publish `mlops-common-utils` as a versioned PyPI package

**What it is.** Extract `common_utils/` to a separate published
package. Scaffolded services pin a version range
(`mlops-common-utils ~= 1.2`).

**Cost**: ~2–4 weeks to extract, set up CI publishing,
documentation, semantic versioning policy + ~ongoing maintenance
burden of a distinct release line.

**Pros**:

- Clean dependency story; security fixes propagate via `pip install
  -U`.
- Forces an explicit public API surface (no more "secretly
  internal" symbols).
- Tests live with the package, not duplicated in every service.

**Cons**:

- Adopters running air-gapped MUST mirror the package internally.
- Two release cadences to manage (template AND package).
- The "package" surface is small (~15 modules); PyPI overhead may
  exceed the value for some adopters.
- Backward-compatible API changes become a rigid contract — every
  rename / signature change requires a major version bump and a
  migration note.

### Option C — Git submodule

**What it is.** `common_utils/` lives in its own repo. Scaffolded
services include it as a submodule, pinned to a SHA.

**Cost**: ~1 week to set up + ongoing UX cost (submodules are
disliked by many contributors).

**Pros**:

- Versioning is content-addressable (SHA), no separate package.
- Air-gap-friendly: adopters can mirror the submodule repo.

**Cons**:

- Submodule UX is notoriously confusing (forgotten `--recursive`
  clones, dangling refs after rebases).
- Doesn't solve the bug-fix delivery latency problem any better
  than Option A — adopters still need to bump the SHA.
- Most modern teams have moved AWAY from submodules toward
  packages.

## Recommendation (DRAFT)

**Option A** for v0.x → `v1.0.0`. The CI drift check closes the
**immediate audit gap** (silent template drift) at low cost without
committing the project to a long-running package release line
before adoption signals justify it.

Revisit Option B at the FIRST of:

- More than 5 distinct adopters request "how do I get the latest
  `common_utils` without re-scaffolding".
- A security fix in `common_utils/` requires a coordinated upgrade
  across `>= 3` adopter forks.
- The `common_utils/` public surface stabilizes (no breaking changes
  for 2 consecutive minor releases).

Submodules (Option C) explicitly REJECTED — submodule UX cost
exceeds the benefit for the project's audience.

## Validation strategy

Two implementations were considered:

1. **End-to-end scaffold + diff.** Run `new-service.sh` into a
   tmpdir and byte-diff the scaffolded `common_utils/` against the
   template (with substitutions applied). Rejected for CI: the
   scaffolder transitively copies `templates/infra/terraform/` which
   currently carries ~1.6 GB of untracked `.terraform/` provider
   caches, pushing the job past 5 min. End-to-end scaffolding is
   already covered by the slower `scripts/test_scaffold.sh`.

2. **Static placeholder scan (SHIPPED).** `new-service.sh` rewrites
   `common_utils/` via a single global `sed` pass over a known
   placeholder set (`{ServiceName}`, `{service-name}`, `{service}`,
   `{SERVICE}`, `{ORG}`, `{REPO}`). The scaffolded copy can therefore
   diverge from the template **iff** one of those placeholders
   appears inside `common_utils/`. Scanning for the placeholder set
   catches the entire drift class deterministically in ~100 ms,
   without running the scaffolder.

Implementation: `scripts/check_common_utils_drift.py`, wired into
`.github/workflows/validate-templates.yml` as the
`common-utils-drift` job (parallel to the existing
`agentic-adapter-drift` job introduced in PR-5 of the May 2026
triage).

First-run result (captured the exact bug class this ADR predicted):
the gate caught `reports.py::_default_report_id` whose f-string
parameter was named `service`, producing a literal `{service}`
token that `sed` would rewrite at scaffold time — corrupting the
scaffolded f-string. Fixed by renaming the internal parameter; the
public `build_*_report(service=...)` API is unchanged. A
documentation-only hit in `input_validation.py` (docstring
references to `src/{service}/...`) was rewritten to the generic
`src/<slug>/...` notation.

## Consequences (if Option A is ratified)

- **Maintenance**: +~1 day to add the drift gate; recurring overhead
  ≈ low (the gate fires at most once per `templates/common_utils/`
  edit).
- **Adopter experience**: unchanged for new adopters; existing
  adopters MUST manually re-pull after security fixes — documented
  in `MIGRATION.md`.
- **Supply chain**: simpler than Option B (no separate package
  attestation chain).

## Status of this ADR

DRAFT. Decision MUST be ratified by an audit cycle (or rejected with
counter-proposal) before v1.0.0. Until ratification, the dual-source
pattern remains the de-facto state — same as today, just no longer
silent debt.
