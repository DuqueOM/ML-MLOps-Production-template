---
name: doc-coherence
description: Keep enterprise documentation coherent across the repo — version, CHANGELOG, ADRs, READMEs, schemas, llms.txt, and agentic surface counts — driven by check_doc_coherence.py (rule 16, ADR-031)
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash(python3:*)
  - Bash(git:*)
when_to_use: >
  Use after any change that touches a fact restated across documents:
  a new/withdrawn ADR, a new rule/skill/workflow, an anti-pattern added,
  a version bump or release, a schema change. Examples: 'sync the docs',
  'fix doc drift', 'prepare the changelog', 'update llms.txt', 'the
  coherence gate is failing', 'I added an ADR — propagate it'.
argument-hint: "[--check | --fix | --release <vX.Y.Z>]"
arguments:
  - mode
authorization_mode:
  run_gate: AUTO                 # read-only; runs check_doc_coherence.py
  apply_doc_fixes: AUTO          # local, reversible Markdown/YAML edits; gate re-verifies
  bump_version: CONSULT          # cutting a release is a human decision
  edit_public_api_docs: CONSULT  # API contract docs change semver surface (rule 14)
  escalation_triggers:
    - delete_or_renumber_adr: STOP   # ADR numbering is immutable (use a tombstone)
    - gate_still_red_after_fix: CONSULT
    - changelog_rewrite_history: STOP # never rewrite a released, dated heading
---

# Doc-Coherence Skill

Drives `scripts/check_doc_coherence.py` and applies the rule-16 cascade map so
documentation never loses the thread. Default action is **read + local fix**;
release/version decisions escalate to CONSULT.

## 1. Run the gate (always first)

```bash
python3 scripts/check_doc_coherence.py
```

// turbo

Exit 0 → coherent, stop. Exit 1 → it prints each violation tagged
`[C1..C5]`. Map each tag to its fix below.

## 2. Fix by violation class (the cascade map)

### C1 — version SSoT (`VERSION` ≠ latest released CHANGELOG heading)

- If a release was cut: set `VERSION` to the latest dated `## [vX.Y.Z]` heading.
- If `VERSION` is ahead: the CHANGELOG is missing the dated heading — move the
  `[Unreleased]` lines under a new `## [vX.Y.Z] — YYYY-MM-DD`.
- **Never** rewrite an already-released dated heading (STOP).

### C2 — `llms.txt` version drift

- Update the `> Version:` line to match `VERSION`.
- If `llms.txt` is intentionally a spec snapshot, add the `legacy-snapshot`
  marker (CONSULT — confirm intent first).

### C3 — anti-pattern count drift

- Canonical = highest `D-NN` in `AGENTS.md`. Propagate to: README
  "N anti-patterns", `llms.txt` `(D-01 to D-NN)`, CLAUDE.md header + table,
  `rule-audit` + `debug-ml-inference` skills.

### C4 — agentic surface count drift

- Recount on disk: `ls agentic/rules/*.md`,
  `ls -d agentic/skills/*/SKILL.md`, `ls agentic/workflows/*.md`.
- Update the "N rules + N skills + N workflows" line in CLAUDE.md (and any
  mirror in `llms.txt` / AGENTS.md index).

### C5 — ADR traceability / numbering gap

- A missing ADR number with no tombstone → add a `Status: Withdrawn`
  tombstone file documenting why (see `ADR-012`). **Never** renumber or
  delete an ADR (STOP).
- A new ADR not referenced anywhere → add a `CHANGELOG.md` entry + ADR index row.

## 3. Adapter parity (if you touched `agentic/`)

```bash
python3 scripts/sync_agentic_adapters.py
python3 scripts/sync_agentic_adapters.py --check   # CI parity gate
```

## 4. Re-run the gate (must be green)

```bash
python3 scripts/check_doc_coherence.py   # expect: [doc-coherence] OK
```

## 5. Release mode (`--release vX.Y.Z`) — CONSULT

1. Confirm the version bump with a human (CONSULT).
2. Move `[Unreleased]` lines under `## [vX.Y.Z] — <today>`.
3. Set `VERSION` = `X.Y.Z`; update `llms.txt`; refresh README badges.
4. Run the gate; hand off to the `release-checklist` skill for the deploy chain.

## Success criteria

- `check_doc_coherence.py` exits 0 (all 7 checks pass).
- `sync_agentic_adapters.py --check` is green (adapters in parity).
- Every changed fact traces decision → ADR → CHANGELOG → release → VERSION.
- No ADR renumbered/deleted; no released heading rewritten.

## Related

- Rule: `16-doc-coherence` (policy + SSoT register + cascade map)
- Rule: `06-documentation` (per-document standards)
- Skill: `release-checklist` (consumes a coherent tree for the deploy chain)
- Workflow: `agentic/workflows/doc-coherence.md` — `/doc-coherence`
- ADR-031 — Documentation coherence system
