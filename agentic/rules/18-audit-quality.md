---
trigger: glob
globs:
  - ".github/workflows/**"
  - "templates/**"
  - "LICENSE"
  - "NOTICE"
  - "llms.txt"
  - "README.md"
  - "pyproject.toml"
  - "**/requirements*.txt"
  - "**/Makefile"
  - ".gitleaks.toml"
  - "scripts/**/*.py"
  - "templates/service/scripts/**/*.py"
  - "templates/service/common_utils/**/*.py"
description: Audit-grade quality standards — anti-patterns Q-01…Q-08 that preserve the enterprise-audit bar between audits (ADR-043)
---

# Rule 18 — Audit-Grade Quality Standards

Rules 01–17 encode *runtime and platform* correctness. This rule encodes
the standards an **external enterprise/ISO auditor** holds the repository
to — the ones that erode silently because no test fails when they slip.
Owner: `Agent-QualityGuardian` (Layer 3). Recurring verification:
`/audit-quality` workflow + `enterprise-audit` skill. Authority: ADR-043.

Namespace note: `Q-NN` patterns govern audit-standard erosion. They are
deliberately separate from the runtime `D-NN` namespace in AGENTS.md
(see ADR-043 §2 for why).

## Anti-patterns — Q-01 … Q-08

| ID | Anti-pattern | Detection | Mode on violation |
| ---- | -------------- | ----------- | ------------------- |
| Q-01 | **Unpinned GitHub Action** — `uses:` referencing a tag or branch instead of a full 40-char SHA | `grep -E "uses: [^@]+@(v[0-9]\|main\|master)"` over workflow files | Block the edit; pin to SHA with a trailing `# vX.Y.Z` comment |
| Q-02 | **License statement drift** — README badge, `llms.txt`, `pyproject.toml`, or scaffolded outputs claiming a license other than the `LICENSE` file (Apache-2.0) | compare license strings across the four surfaces | Fix mirrors to match `LICENSE`; never "fix" `LICENSE` to match a mirror |
| Q-03 | **Evidence-free release** — a `v*` tag published without SBOM + signed checksum assets on its GitHub Release | `release-on-tag.yml` `supply-chain-evidence` job missing, skipped, or failing | CONSULT before tagging; a tag already pushed without evidence gets the job re-run, never a tag rewrite |
| Q-04 | **Complexity hotspot introduced** — new/modified production function with cyclomatic complexity > 15 or > 100 lines (excludes tests and generated code) | advisory AST scan in `enterprise-audit` skill §3 | Refactor before merge, or record the exemption + reason in the PR body |
| Q-05 | **Weakened quality gate** — lowering `--cov-fail-under`, deleting/skipping tests without replacement, loosening a lint/type config, removing a required status check | diff review over gate configs | **STOP** — same class as "override a failing quality gate" (AGENTS.md) |
| Q-06 | **One-sided vendored edit** — changing a file that exists in both the repo root and `templates/service/` (scripts, agentic surface, AGENTS.md) on only one side | `scripts/check_cicd_template_drift.py`, `sync_agentic_adapters.py --check`, vendored-runtime drift gates | Apply to both sides in the same commit |
| Q-07 | **Undocumented change** — a merged change that touches behavior, contracts, or counts without its CHANGELOG entry / ADR / rule-16 cascade | `scripts/check_doc_coherence.py` + `/document-changes` | Run `/document-changes` before requesting review |
| Q-08 | **Working-tree pollution shipped** — binaries, archives, coverage artifacts, or extracted tarballs committed to the repo root | `git ls-files` scan for archives/binaries > 1 MB outside declared asset paths | Remove; add the pattern to `.gitignore` in the same commit |

## Standing obligations (not tied to a single edit)

- **Reproducibility**: every scaffolded service release SHOULD commit a
  hash-pinned lockfile (`make lock` → `requirements.lock.txt`).
  `requirements.txt` with `~=` states intent; the lockfile is what an
  auditor accepts as "rebuildable in a year."
- **Secret-scan parity**: `.gitleaks.toml` uses the plural
  `[[allowlists]]` tables ONLY. The legacy singular `[allowlist]` mirror
  that R11 L-2 introduced was removed in v0.22.0: gitleaks >= 8.25 refuses
  to load a config containing both dialects, so the compatibility shim had
  become the blocker for upgrading. Parity is now held by pinning one
  version across all three declaration sites — enforced by
  `scripts/check_gitleaks_pin.py`.
- **Signed history forward**: commits and release tags are signed from
  v0.21.0 onward. Never rewrite history to retro-sign, and never move a
  tag to a different commit (tags are immutable per AGENTS.md).
  **Scope clarified by ADR-045**: immutability attaches to the commit and
  its content, not to the reference name used to reach it. Renaming a tag
  while preserving its commit, tree and signature — as done for the
  `archive/v1.x` audit snapshots — is a tooling-namespace change, not a
  historical claim. Deleting an archived snapshot outright remains
  forbidden: archiving preserves provenance, deletion destroys it.
- **Evidence discipline**: audit claims cite `file:line` or a command
  with its output. "We have tests" is not evidence; a coverage report is.

## When editing this rule

Adding a Q-pattern: append to the table, update the range in the header
of `agentic/skills/enterprise-audit/SKILL.md`, and record the addition in
CHANGELOG. Removing or loosening a Q-pattern is **STOP** — it requires an
ADR amendment to ADR-043, exactly like a D-pattern removal.
