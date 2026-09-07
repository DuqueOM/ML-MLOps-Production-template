---
description: Restore and verify cross-document coherence — version, CHANGELOG, ADRs, READMEs, llms.txt, agentic surface counts (rule 16, ADR-031)
---

# /doc-coherence Workflow

Run after any change that touches a fact restated across documents (a new ADR,
a new rule/skill/workflow, an anti-pattern, a version bump). The gate is the
authority; this workflow is the procedure that makes it green.

## 1. Run the coherence gate

```bash
python3 scripts/check_doc_coherence.py
```

// turbo

Exit 0 → done. Exit 1 → note each `[C1..C5]` violation and continue.

## 2. Apply the cascade map (rule 16)

For each violation, fix the SSoT first, then propagate to mirrors:

- **C1** version: `VERSION` ⇄ latest dated CHANGELOG heading.
- **C2** llms.txt: `> Version:` line ⇄ `VERSION`.
- **C3** anti-patterns: AGENTS.md max `D-NN` → README count, llms.txt range, CLAUDE.md, skills.
- **C4** surface counts: on-disk `agentic/` counts → CLAUDE.md "N rules + N skills + N workflows".
- **C5** ADRs: fill numbering gaps with a `Status: Withdrawn` tombstone; reference new ADRs in CHANGELOG.

> Prefer the `doc-coherence` skill — it knows the cascade map and the
> CONSULT/STOP boundaries (never renumber an ADR; never rewrite a released heading).

## 3. Regenerate adapters (if `agentic/` changed)

```bash
python3 scripts/sync_agentic_adapters.py
```

## 4. Verify everything is green

```bash
python3 scripts/check_doc_coherence.py            # [doc-coherence] OK
python3 scripts/sync_agentic_adapters.py --check  # adapter parity
python3 scripts/validate_agentic_manifest.py --strict
```

## 5. Commit with traceability

Reference the ADR / PR in the commit body so the change stays relatable
end-to-end (decision → ADR → CHANGELOG → release → VERSION).

## Related

- Rule: `16-doc-coherence` · Skill: `doc-coherence` · ADR-031
- Workflow: `release` (downstream — consumes a coherent tree)
- Workflow: `new-adr` (upstream — produces an ADR that this workflow propagates)
