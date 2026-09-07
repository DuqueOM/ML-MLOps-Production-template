---
name: enterprise-audit
description: Recurring 23-domain enterprise/ISO repository audit — governance, traceability, security, supply chain, reproducibility, observability, architecture, technical debt, DX — produces a findings report with file:line evidence and risk ratings, and preserves the audit bar via anti-patterns Q-01…Q-08
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(grep:*)
  - Bash(rg:*)
  - Bash(python3:*)
  - Bash(gitleaks:*)
  - Bash(make:*)
when_to_use: >
  Invoke quarterly, before a minor-version release, after any external
  audit request, or when Agent-QualityGuardian detects Q-pattern
  violations accumulating. Also the procedure to follow when an adopter
  asks "is my fork still at the template's audit bar?"
argument-hint: "[--domains governance|security|supply-chain|debt|dx|all] [--report docs/audit/AUDIT_R<N>_<TITLE>.md]"
authorization_mode:
  scan: AUTO
  fix_findings: CONSULT
  weaken_any_gate: STOP
---

# Enterprise Audit — 23-domain repository audit procedure

Owner: `Agent-QualityGuardian` (ADR-043). Scanning is READ-ONLY (AUTO).
Fixing findings is CONSULT. Weakening any existing gate found along the
way is STOP, always.

## When NOT to use this skill

- **During an active incident** — run `/incident` or `/rollback`; audit
  in the post-mortem.
- **For D-invariant compliance only** — that is `rule-audit` (cheaper,
  focused). This skill *composes* rule-audit and adds the domains it
  does not cover.
- **For documentation drift only** — that is `doc-coherence`.

## Procedure

### 1. Baseline — all existing gates must be green first

```bash
python3 scripts/check_doc_coherence.py
python3 scripts/check_cicd_template_drift.py
python3 scripts/sync_agentic_adapters.py --check
gitleaks detect --no-git --source=. --redact
```

A red gate here is a finding by itself (Q-06/Q-07 class) — record it,
fix under CONSULT, then continue.

### 2. Domain sweep (evidence per domain, `file:line` or command+output)

| # | Domain | Primary probes |
| --- | -------- | ---------------- |
| 1 | Governance | `CODEOWNERS`, `docs/governance/branch-protection.md` vs ADR-026; bus-factor disclosure current? |
| 2 | Traceability | sample 20 commits: issue/PR linkage, Conventional Commits |
| 3 | Code quality | lint/type gates present and unweakened (Q-05) |
| 4 | Secrets in code | gitleaks (versioned files only); `os.environ` direct-read probe from rule 12 |
| 5 | Dependencies | Dependabot config live; `~=` pinning intact; open CVE PRs aging? |
| 6 | Licensing | Q-02 four-surface comparison |
| 7 | CI/CD | required checks list vs `branch-protection.md`; deploy approvals per environment |
| 8 | Reproducibility | lockfile present per release (`make lock`); image digest pinning in staging/prod overlays |
| 9 | Secret management | env-separation table intact; no cross-env secret copy proposals |
| 10 | Configuration | overlay parity gcp/aws × dev/staging/prod |
| 11 | Testing | `--cov-fail-under` values unchanged; negative/policy tests still collected |
| 12 | Documentation | ADR index gapless (tombstones allowed); runbooks referenced by alerts exist |
| 13 | Versioning | `VERSION` ⇄ CHANGELOG ⇄ latest tag; tags signed (`git verify-tag`) |
| 14 | Incidents | rollback/secret-breach runbooks current; post-mortems filed for closed incidents |
| 15 | Change management | no direct-to-main commits since last audit (`git log --first-parent`) |
| 16 | Commit hygiene | signature ratio trend (`git log --pretty=%G?`); Conventional Commits ratio |
| 17 | Supply chain | Q-01 SHA-pin sweep; Q-03 release-evidence check on the latest tag; Scorecard workflow green |
| 18 | MLOps | DVC + MLflow wiring; quality_gates schema sync test passing; promotion still STOP |
| 19 | Evidence | `ops/audit.jsonl` appending; CI step summaries produced |
| 20 | Observability | SLO rules present per service; alert routing test green; dashboards inventory in sync |
| 21 | Architecture | new cross-plane imports? contracts in `agent_context.py` still frozen dataclasses |
| 22 | Technical debt | §3 complexity scan; duplication beyond the declared vendored set |
| 23 | DX | QUICK_START tracks still complete within claimed times; `make help` targets all functional |

### 3. Complexity scan (advisory, Q-04)

```bash
python3 - <<'EOF'
import ast, subprocess
files = subprocess.check_output(['git','ls-files','*.py']).decode().split()
BRANCH=(ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.With,
        ast.BoolOp, ast.IfExp, ast.comprehension, ast.Match)
worst=[]
for f in files:
    if '/tests/' in f or f.startswith('tests/'): continue
    try: tree=ast.parse(open(f).read())
    except Exception: continue
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            cc=1+sum(isinstance(x,BRANCH) for x in ast.walk(n))
            ln=(n.end_lineno or n.lineno)-n.lineno+1
            if cc>15 or ln>100: worst.append((cc,ln,f,n.name))
worst.sort(reverse=True)
for cc,ln,f,name in worst: print(f"Q-04 {cc=} {ln=} {f}::{name}")
print(f"total flagged: {len(worst)}")
EOF
```

Compare against the previous report's list: **new entries are findings**;
pre-existing entries are tracked debt.

### 4. Report

Write `docs/audit/AUDIT_R<N>_<TITLE>.md` (increment N from the existing
series). Required structure: metadata (date, HEAD, scope, method),
executive table (domain / status / risk / evidence / recommendation),
detailed findings with IDs (M-x medium, L-x low, plus Q-pattern refs),
raw evidence per domain, and an explicit limitations section.

### 5. Chain documentation

Findings fixed during the audit are changes like any other:

```text
/document-changes
```

The audit is not closed until the coherence gate is green and the
CHANGELOG names the report.

## Escalation

- Any credential pattern found → **STOP**, chain `/secret-breach`.
- Any gate found weakened without an ADR → **STOP**, restore it, then
  investigate who/why via `git log -S`.
- Critical finding (data exposure, unsigned prod image path, broken
  promotion gate) → open a GitHub issue tagged `audit` + `incident`.
