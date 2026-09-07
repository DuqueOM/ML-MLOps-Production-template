# ADR-045 — Separate the release-channel tag namespace from frozen audit snapshots

- **Status**: Accepted
- **Date**: 2026-08-08
- **Deciders**: template maintainer
- **Amends**: ADR-014 §"immutable historical tags" and
  `agentic/rules/18-audit-quality.md` §"Signed history forward"
- **Related**: ADR-030 (Copier scaffolding), `docs/RELEASING.md` §2

---

## Context

This repository carries two sets of git tags with **incompatible
requirements**, in one namespace:

| Purpose | Requirement |
| --- | --- |
| Release-channel markers (`v0.x`) | machine-sortable; must contain **only live releases** |
| Frozen audit snapshots (`v1.0.0`–`v1.12.0`) | permanent; must **never be resolved** |

Version-resolving tooling picks the highest-sorting tag. `v1.12.0` sorts
above every `v0.x` tag, so the April 2026 audit snapshot won every
automatic resolution.

### This produced four defects in four releases

1. **`v0.22.0` reached nobody.** The documented `copier copy` was
   unpinned, so adopters received the `v1.12.0` snapshot — 435 files and
   no `.copier-answers.yml` instead of 626 with one.
2. **The `copier copy` docs fix did not cover `copier update`.**
3. **A bare `copier update` was destructive**: 627 files → 435, 582
   deleted, and `.copier-answers.yml` itself removed — deleting the record
   the operation needs, so the service could not recover on its own.
4. **`v0.24.0` pinned three of four surfaces**, missing the
   `/scaffold-update` workflow vendored into every generated service.

Every fix was a `--vcs-ref` pin. Pinning is correct, and the guard now
scans the tree rather than enumerating files — but **pinning treats the
symptom**. Each new surface documenting a Copier command is another
opportunity for the same defect.

The R11 audit noted the adjacent symptom ("confuses `sort -V` and any
tooling that assumes monotonicity") without connecting it to tag
resolution.

## Decision

**Move the frozen audit snapshots out of the version namespace.**

`v1.0.0` … `v1.12.0` → `archive/v1.0.0` … `archive/v1.12.0`, pointing at
the **same commits**.

### Why this works, mechanically

Copier's `get_latest_tag` (verified in `copier/_vcs.py`):

```python
all_tags = (tag for tag in all_tags if valid_version(tag))   # PEP 440 filter
sorted_tags = sorted(all_tags, key=version.parse, reverse=True)
return sorted_tags[0]
```

`archive/v1.12.0` is not a valid PEP 440 version, so it is **filtered out
before sorting**. Verified:

| Tag | PEP 440 valid | Copier behaviour |
| --- | --- | --- |
| `v1.12.0` | yes → `1.12.0` | resolved, wins |
| `v0.25.0` | yes → `0.25.0` | resolved |
| `archive/v1.12.0` | **no** | **filtered out** |

The same filter protects every other version-resolving tool, not just
Copier: `sort -V`, `git describe --tags` heuristics, "latest release"
queries, dependency bots.

## The immutability question

ADR-014 and `agentic/rules/18` state that the `v1.x` tags are immutable and
that history must never be rewritten to retro-sign. Renaming them looks, on
the letter, like a violation. It is not, and the distinction is the point of
this ADR.

**What the rule protects**: that the past cannot be made to look better than
it was. Specifically — a tag must not be moved to a different commit, and a
historical claim must not be re-signed after the fact to imply it was
verified when it was not.

**What this change does**: keeps every commit, every tree, every release
note, and every signature exactly as they are. Only the *reference name*
changes. `git show archive/v1.12.0` returns byte-identical content to what
`git show v1.12.0` returned. `releases/v1.*.md` is untouched.

**Therefore**: the reference namespace is a **tooling concern**, not a
historical claim. The immutability guarantee attaches to the commit and its
content, not to the string used to reach it.

This ADR amends both documents to say so explicitly, rather than leaving a
letter-versus-intent gap for a future reader to resolve on their own.

### What remains forbidden

- Moving any tag — archived or active — to a different commit.
- Re-signing a historical tag to imply verification that did not happen.
- Deleting an archived snapshot outright. Archiving preserves provenance;
  deletion destroys it, and the two must not be confused.

## Consequences

### The version numbers do not change

The alternative was renumbering the active line past `v1.12.0` (jumping to
`v2.x`). Rejected: `docs/RELEASING.md` §2 reserves `v1.0.0` for the first
cloud E2E validation, and the whole `v0.x` line exists to signal *not GA
yet*. Inflating the version to outrank a dead tag would make the version
number **misstate the project's maturity in order to satisfy a sorting
algorithm** — the tail wagging the dog, and a worse lie than the bug.

### GitHub Releases

The 15 `v1.x` releases carry **0 assets** and their bodies are duplicated
in `releases/v1.*.md`, so no content is at risk. They are recreated against
the `archive/` tags so the human-facing record survives.

### Pins and guards stay

`--vcs-ref` pinning and `scripts/check_adopter_scaffold_ref.py` are **not**
removed. Pinning an explicit ref is correct practice for any Copier
template regardless of this repo's tag history, because Copier's default —
silently resolving to the highest tag — is surprising in general. This
change removes the trap; the pin remains good hygiene.

### Recoverability

The `archive/` tags point at the same commits, so the operation is
reversible: recreating `v1.x` from `archive/v1.x` restores the prior state
exactly. A tag→commit mapping was recorded before execution.

## Alternatives considered

| Option | Verdict |
| --- | --- |
| Renumber the active line to `v2.x` | Rejected — makes the version number lie about maturity to satisfy a sort order |
| Delete the `v1.x` tags outright | Rejected — loses provenance for no gain over archiving |
| Keep pinning, change nothing | Rejected — four defects in four releases; the next surface is a matter of time |
| Archive out of the version namespace | **Accepted** |
