---
description: Run the recurring 23-domain enterprise audit and enforce anti-patterns Q-01…Q-08 — scan is AUTO, fixes are CONSULT, weakening any gate is STOP (ADR-043)
---

# /audit-quality Workflow

Owner: `Agent-QualityGuardian`. Run quarterly, before a minor release,
or on demand ("is the repo still at the audit bar?"). The full procedure
lives in the `enterprise-audit` skill; this workflow is the operational
sequence.

## 1. Verify the deterministic gates

// turbo

```bash
python3 scripts/check_doc_coherence.py && \
python3 scripts/check_cicd_template_drift.py && \
python3 scripts/sync_agentic_adapters.py --check
```

// turbo

```bash
gitleaks detect --no-git --source=. --redact
```

Red gate → that IS a finding. Record it before fixing anything.

## 2. Quick Q-pattern sweep

// turbo

```bash
grep -rhoE "uses: [^@]+@(v[0-9][^ ]*|main|master)" .github/workflows templates | sort -u
```

Any output = Q-01 violation (unpinned action).

// turbo

```bash
grep -h "License" llms.txt pyproject.toml | head -4; head -2 LICENSE
```

Mismatch = Q-02 violation (license drift).

// turbo

```bash
git ls-files | grep -iE "\.(tar\.gz|tgz|zip|jar|bin|exe)$|coverage\.xml$"
```

Any output outside declared asset paths = Q-08 violation.

## 3. Full domain sweep

Load the `enterprise-audit` skill and execute its §2 (23 domains) and §3
(complexity scan). Scan mode is AUTO — read-only.

## 4. Findings triage

For each finding:

- Fixable now, low-risk → propose fix, **CONSULT**, apply on approval.
- Requires weakening/removing an existing gate → **STOP**. No exceptions;
  it needs an ADR amendment (rule 18 §When editing this rule).
- Credential pattern → **STOP**, chain `/secret-breach`.
- Organizational (e.g. reviewer counts, MFA) → record in the report with
  owner + revisit trigger; do not attempt a technical workaround.

## 5. Report + audit trail

Write the report to `docs/audit/AUDIT_R<N>_<TITLE>.md` (skill §4 format).

// turbo

```bash
python3 scripts/audit_record.py \
  --agent Agent-QualityGuardian \
  --operation enterprise-audit \
  --environment repo \
  --base-mode AUTO --final-mode AUTO \
  --result success \
  --inputs "23-domain sweep" \
  --outputs "docs/audit/AUDIT_R<N>_<TITLE>.md"
```

## 6. Chain documentation

If anything was changed in step 4, finish with:

```text
/document-changes
```

The audit is closed only when the coherence gate is green and CHANGELOG
references both the report and the fixes.
