# Runbook — Secret History Scan + Pipeline Bypass Tests

- **Authority**: ADR-020 §S1-3, R4 audit findings H5 + H6.
- **Mode**: **STOP — delegated** (Platform / Security executes).
- **Approver**: Platform Lead AND Security Lead (joint sign-off required).
- **Audit trail**: every execution writes an entry to `VALIDATION_LOG.md` and an `AuditEntry` to `ops/audit.jsonl` via `scripts/audit_record.py`.

---

## Why this runbook exists

R4 finding **H6** flagged that `git log --all -p | gitleaks detect --pipe` had never been executed against the full
repository history, despite gitleaks running on every commit (workdir-only). A secret committed before gitleaks adoption
could still live in history without anyone knowing.

R4 finding **H5** flagged that the pipeline's three primary security gates — **deploy-bypass-staging**,
**model-fails-fairness**, **secret-in-commit** — had never been actively probed. They were assumed to work; no
adversarial test had ever produced evidence.

This runbook closes both findings via a single coordinated procedure.

---

## Why STOP-delegated

The procedure is harmless in itself (gitleaks is read-only; bypass tests run on a sandbox branch), but it produces
evidence that touches secrets disclosure. Therefore:

1. The procedure MUST NOT be executed by an autonomous agent.
2. The output MUST be reviewed by Security before being committed to `VALIDATION_LOG.md` (in case a real leak is
   discovered, the runbook switches to incident-response mode — see §"If a real leak is found").
3. Any positive finding triggers `/secret-breach` per the global rule on secrets.

---

## Pre-conditions

- Local clone of the repository (do not execute on shared CI runners).
- `gitleaks >= 8.18.0` installed (`gitleaks version`).
- Network egress permitted (gitleaks may fetch its default config).
- Working directory clean: `git status` shows nothing.
- Approval recorded in the audit channel; ticket ID assigned.

---

## Procedure 1 — Full history secret scan

### Step 1.1 — Cold clone (recommended)

To eliminate confusion with local untracked files and to validate the
**published** state of the repo:

```bash
cd "$(mktemp -d)"
git clone --mirror https://github.com/DuqueOM/ml-service-template.git history-scan.git
cd history-scan.git
```

### Step 1.2 — Run gitleaks against full history

```bash
mkdir -p /tmp/r4-secret-history-scan
gitleaks detect \
  --source "$(pwd)" \
  --config /path/to/repo/.gitleaks.toml \
  --redact \
  --report-format json \
  --report-path /tmp/r4-secret-history-scan/findings.json \
  --no-banner 2>&1 | tee /tmp/r4-secret-history-scan/scan.log
```

Notes:

- `--redact` ensures any matching secret is redacted in stdout/log.
- `--report-format json` captures structured findings even if the human-readable log is truncated.
- The `--config` MUST point at the canonical `.gitleaks.toml` from the repo to avoid drift.

### Step 1.3 — Verify exit code + record evidence

```bash
echo "exit_code=$?"
wc -l /tmp/r4-secret-history-scan/findings.json
# Expected for a clean history:
#   exit code = 0
#   findings.json contains an empty array: []
```

Record in `VALIDATION_LOG.md` (a new Entry, not amending Entry 001):

- Date + operator name (the human, not the agent)
- Mirror clone SHA at scan time (`git rev-parse HEAD`)
- gitleaks version (`gitleaks version`)
- Total commits scanned (`git rev-list --all --count`)
- Exit code and finding count
- Truncated last 20 lines of `scan.log` (no secret values, all redacted)

### Step 1.4 — Cleanup

```bash
cd /
rm -rf "$(dirname "$(pwd)")"  # only if you used the mktemp clone
```

---

## Procedure 2 — Pipeline bypass tests

These three tests probe the gates from the **adversarial** angle: each test
intentionally constructs a PR that the pipeline MUST reject. If any gate
fails to reject, that is a Critical finding and the runbook escalates to
the incident workflow.

> **DANGER**: execute on a fork or sandbox branch only. Never on `main`.
> Each test produces a PR that is closed without merge.

### Test 2.1 — Deploy-bypass-staging

**Goal**: prove that a PR attempting to deploy directly to prod (skipping
staging) is rejected by the environment-promotion gate (D-26).

```bash
git checkout -b r4/bypass/skip-staging-$(date +%s)
# Modify .github/workflows/deploy-aws.yml or deploy-gcp.yml to swap the
# `needs:` chain so the prod job depends on `build` directly, not `staging`.
sed -i 's/needs: \[deploy-staging\]/needs: [build]/' \
    templates/service/.github/workflows/deploy-aws.yml
git add -A && git commit -s -m "r4-bypass-test: skip staging (must fail)"
git push origin HEAD
gh pr create --base main --title "[R4 bypass test] Skip staging (must fail)" \
  --body "Adversarial test of the staging-promotion gate. MUST be rejected."
```

**Expected**: the PR's CI fails on the environment-promotion check OR the
PR cannot merge due to branch protection rules. Capture the failure
output as evidence.

### Test 2.2 — Model fails fairness gate

**Goal**: prove that a model with `disparate_impact_ratio < 0.80` is
refused promotion (ADR-008 / D-12 quality gate).

```bash
git checkout -b r4/bypass/fairness-fail-$(date +%s)
# Inject a synthetic fairness failure into the quality-gate fixture:
#   Edit templates/service/tests/test_quality_gates_config.py to use a
#   fixture model with DIR=0.50 and assert that promote_model() raises
#   QualityGateFailure.
# Then push a PR that tries to override the gate.
```

**Expected**: the contract test refuses construction; the promotion
script exits non-zero with message `quality_gate.fairness: DIR 0.50 < 0.80`.

### Test 2.3 — Secret-in-commit

**Goal**: prove that a commit introducing an obvious secret pattern is
blocked by `gitleaks` (pre-commit) AND by CI.

```bash
git checkout -b r4/bypass/secret-leak-$(date +%s)
# Inject a fake AWS access key pattern into a NEW file. The pattern
# below is the canonical gitleaks test pattern (matches the rule but is
# NOT a real key):
echo "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE" > scratch_secret.txt
echo "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" >> scratch_secret.txt
git add scratch_secret.txt
# Pre-commit MUST refuse the commit:
git commit -s -m "r4-bypass-test: leak secret (must fail pre-commit)" \
  || echo "PRE-COMMIT BLOCKED — expected"
# If somehow it commits, push and verify CI gitleaks step rejects:
git push origin HEAD || echo "PUSH BLOCKED — expected"
```

**Expected**: pre-commit refuses the commit; if pre-commit is bypassed
with `--no-verify`, CI's gitleaks step rejects the push. Either gate
counts as success.

### Step 2.4 — Cleanup

For each bypass test:

```bash
gh pr close <PR-NUMBER>
git push origin --delete <branch>
git branch -D <branch>
```

---

## If a real leak is found

If Procedure 1 reports any finding (exit code != 0, or findings array
non-empty), STOP this runbook and switch immediately to:

1. Trigger `/secret-breach` workflow.
2. Follow `docs/runbooks/secret-rotation.md`.
3. Open an incident ticket; do NOT commit gitleaks output to the public
   repo until rotation is complete.
4. After rotation, complete `VALIDATION_LOG.md` entry redacting any
   reference to the leaked secret.

---

## Acceptance criteria for closing R4 H5 / H6

R4 H5 and H6 close when ALL of the following hold:

- [ ] Procedure 1 has been executed; output recorded in `VALIDATION_LOG.md`
      (Entry NNN). Exit code = 0; findings.json empty array.
- [ ] Test 2.1 (skip-staging) has been executed; PR closed; CI failure
      output recorded in `VALIDATION_LOG.md`.
- [ ] Test 2.2 (fairness fail) has been executed; quality-gate refusal
      recorded.
- [ ] Test 2.3 (secret-in-commit) has been executed; pre-commit OR CI
      gitleaks refusal recorded.
- [ ] `AuditEntry` for each procedure written to `ops/audit.jsonl` via
      `scripts/audit_record.py` with `mode=STOP`, `approver=<lead>`,
      `result=success`.

Until the four checkboxes flip, the maturity matrix in `README.md`
section "Production-ready scope" cannot upgrade the
"Security and supply chain" row from "Production-ready" to "Verified
end-to-end" — current honest status remains "Production-ready (untested
gates)".

---

## Cadence

Re-run this entire runbook:

- After every MAJOR release (per `docs/RELEASING.md`).
- After any change to `.gitleaks.toml`.
- After any change to a security gate in `templates/service/.github/workflows/`.
- Quarterly minimum, even if no triggering event occurred.
