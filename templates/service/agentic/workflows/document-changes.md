---
description: Document every change in the current working set — CHANGELOG entry, rule-16 cascade, ADR linkage, audit-trail record — Agent-DocUpdater's operational entry point (ADR-043)
---

# /document-changes Workflow

Owner: `Agent-DocUpdater` (Layer 3 — "keeps documentation in sync with
code"). Run BEFORE requesting review on any non-trivial change, and as
the closing step of `/audit-quality`, `/release`, and any workflow that
mutates governed surfaces. Mode: AUTO (documents are reviewable in PRs).

Principle: a change is not done until a reader who was not present can
reconstruct **what** changed, **why**, and **under which authority**.

## 1. Collect the change surface

// turbo

```bash
git status --short && git diff --stat HEAD
```

Classify every touched path:

| Touched | Documentation obligation |
| --- | --- |
| Behavior/contract code (`app/`, `common_utils/`, `scripts/`) | CHANGELOG entry (Added/Changed/Fixed) |
| Anything under `agentic/`, adapters, manifests | CHANGELOG + surface-count cascade (step 3) + adapter sync |
| CI workflows, gates, `.gitleaks.toml`, branch protection | CHANGELOG + note the gate semantics change explicitly |
| Non-trivial decision embodied in the change | New ADR or amendment to the governing ADR — cite it in the CHANGELOG line |
| Vendored pairs (root ↔ `templates/service/`) | Confirm BOTH sides in the diff (Q-06) |

## 2. Write the CHANGELOG entry

Under `## [Unreleased]` (create the section if absent), Keep-a-Changelog
categories. Each line: what + why + authority, e.g.:

```markdown
### Added
- `supply-chain-evidence` job in `release-on-tag.yml`: source SBOM
  (CycloneDX+SPDX) + keyless Sigstore signature attached to every
  release (AUDIT R11 M-2, ADR-043).
```

Never rewrite a released (dated) heading — released history is immutable.

## 3. Propagate restated facts (rule 16 cascade)

If the change touched any fact restated across documents:

- New rule/skill/workflow → update counts in `llms.txt` §Agentic system
  and `CLAUDE.md`.
- New ADR → update the ADR count/range in `llms.txt` §Key files.
- New `D-`/`Q-` anti-pattern → update the counts where the range is
  restated (README, llms.txt, CLAUDE.md for `D-`; rule 18 header for `Q-`).
- Version bump → `VERSION` first, then CHANGELOG heading, then `llms.txt`.
- Agentic surface changed → regenerate adapters:

// turbo

```bash
python3 scripts/sync_agentic_adapters.py && python3 scripts/sync_agentic_adapters.py --check
```

## 4. Verify

// turbo

```bash
python3 scripts/check_doc_coherence.py
```

Exit 1 → fix per the cascade map in `/doc-coherence` (or load the
`doc-coherence` skill), then re-run. Do not proceed while red.

## 5. Record the audit-trail entry

// turbo

```bash
python3 scripts/audit_record.py \
  --agent Agent-DocUpdater \
  --operation document-changes \
  --environment repo \
  --base-mode AUTO --final-mode AUTO \
  --result success \
  --inputs "$(git diff --stat HEAD | tail -1)" \
  --outputs "CHANGELOG [Unreleased] + rule-16 cascade"
```

## 6. Hand back

Report to the caller (human or workflow): files documented, CHANGELOG
lines added, cascade updates applied, gate status. The calling workflow
owns commit/PR mechanics — this workflow never pushes.
