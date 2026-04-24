# Claude Code Skills Index

Claude Code discovers skills from this directory. To maintain a single
source of truth, each skill here is a **pointer** to the canonical
`.windsurf/skills/<name>/SKILL.md`. Agent behavior is identical.

## Skills catalog (16 skills)

| Skill | Authorization | Canonical |
|-------|---------------|-----------|
| **new-service** | AUTO | [.windsurf/skills/new-service/SKILL.md](../../.windsurf/skills/new-service/SKILL.md) |
| **eda-analysis** | AUTO (STOP on leakage gate fail) | [.windsurf/skills/eda-analysis/SKILL.md](../../.windsurf/skills/eda-analysis/SKILL.md) |
| **debug-ml-inference** | AUTO | [.windsurf/skills/debug-ml-inference/SKILL.md](../../.windsurf/skills/debug-ml-inference/SKILL.md) |
| **drift-detection** | AUTO → CONSULT (severe) | [.windsurf/skills/drift-detection/SKILL.md](../../.windsurf/skills/drift-detection/SKILL.md) |
| **concept-drift-analysis** | AUTO | [.windsurf/skills/concept-drift-analysis/SKILL.md](../../.windsurf/skills/concept-drift-analysis/SKILL.md) |
| **performance-degradation-rca** | AUTO | [.windsurf/skills/performance-degradation-rca/SKILL.md](../../.windsurf/skills/performance-degradation-rca/SKILL.md) |
| **model-retrain** | AUTO → CONSULT → STOP (prod) | [.windsurf/skills/model-retrain/SKILL.md](../../.windsurf/skills/model-retrain/SKILL.md) |
| **batch-inference** | AUTO → CONSULT → STOP (prod) | [.windsurf/skills/batch-inference/SKILL.md](../../.windsurf/skills/batch-inference/SKILL.md) |
| **deploy-gke** | AUTO → CONSULT → STOP (prod) | [.windsurf/skills/deploy-gke/SKILL.md](../../.windsurf/skills/deploy-gke/SKILL.md) |
| **deploy-aws** | AUTO → CONSULT → STOP (prod) | [.windsurf/skills/deploy-aws/SKILL.md](../../.windsurf/skills/deploy-aws/SKILL.md) |
| **release-checklist** | CONSULT | [.windsurf/skills/release-checklist/SKILL.md](../../.windsurf/skills/release-checklist/SKILL.md) |
| **rollback** | **STOP** (every step) | [.windsurf/skills/rollback/SKILL.md](../../.windsurf/skills/rollback/SKILL.md) |
| **security-audit** | AUTO (STOP on finding) | [.windsurf/skills/security-audit/SKILL.md](../../.windsurf/skills/security-audit/SKILL.md) |
| **secret-breach-response** | **STOP** (every step) | [.windsurf/skills/secret-breach-response/SKILL.md](../../.windsurf/skills/secret-breach-response/SKILL.md) |
| **rule-audit** | AUTO | [.windsurf/skills/rule-audit/SKILL.md](../../.windsurf/skills/rule-audit/SKILL.md) |
| **cost-audit** | AUTO → CONSULT (change) | [.windsurf/skills/cost-audit/SKILL.md](../../.windsurf/skills/cost-audit/SKILL.md) |

## Invocation

Slash commands (`.claude/commands/*.md`) reference these skills. The agent
should:

1. Read the canonical `.windsurf/skills/<name>/SKILL.md` in full
2. Honor the `authorization_mode` frontmatter (AUTO/CONSULT/STOP per phase)
3. Apply the Dynamic Behavior Protocol (ADR-010) — load `common_utils/risk_context.py`
4. Append each operation to `ops/audit.jsonl` via `record_operation()`

## Why pointers instead of copies

Maintaining 16 × ~200-line skill files across 3 IDEs = 48 files, each
drifting independently. Pointers keep `.windsurf/skills/` as the single
source of truth; Claude Code + Cursor read them transparently.

See also: `docs/ide-parity-audit.md` for the full parity matrix.
