# Runbook — Secrets Manager Integration End-to-End

- **Authority**: ADR-020 §S2-5, R4 audit finding M1.
- **Mode**: CONSULT (touches secret managers but only via existing helpers; no rotation).
- **Scope**: validate that `templates/service/common_utils/secrets.py` correctly reads from GCP Secret Manager (GSM) and
  AWS Secrets Manager (ASM) end-to-end, in dev / staging / prod, without ever falling through to `os.environ` in non-dev
  environments (D-17).
- **Approver**: Platform Lead.
- **Audit trail**: each successful execution writes an entry to `VALIDATION_LOG.md`.

---

## Why this runbook exists

R4 finding M1 flagged that `common_utils/secrets.py` was implemented and
unit-tested but had never been exercised against a real cloud secrets
manager end-to-end. The pattern this prevents is the v1.10 / v1.12
class: "the helper looks correct, no one has confirmed it works against
the live service."

---

## Pre-conditions

- `gcloud` CLI authenticated to a GCP project with `roles/secretmanager.secretAccessor` granted to your user.
- `aws` CLI authenticated to an AWS account with `secretsmanager:GetSecretValue` granted.
- A non-production project / account for both clouds; **never run against prod for this runbook**.
- Python 3.11 with `templates/service` installed editable (`pip install -e .`).

---

## Procedure 1 — GSM end-to-end

```bash
PROJECT_ID="$(gcloud config get-value project)"
SECRET_ID="r4-secrets-runbook-test"
SECRET_VALUE_FILE="$(mktemp)"
echo "this-is-a-test-secret-DO-NOT-USE-IN-PROD" > "$SECRET_VALUE_FILE"

# 1. Create the secret + version (idempotent retry-safe).
gcloud secrets create "$SECRET_ID" --replication-policy=automatic 2>/dev/null || true
gcloud secrets versions add "$SECRET_ID" --data-file="$SECRET_VALUE_FILE"

# 2. Read via the template helper. Set MLOPS_ENV explicitly so the helper
# refuses os.environ fallback in staging/prod regardless of caller env.
MLOPS_ENV=staging \
GCP_PROJECT_ID="$PROJECT_ID" \
python -c "
from common_utils.secrets import get_secret
v = get_secret('$SECRET_ID', backend='gcp')
print('len=%d, prefix=%s' % (len(v), v[:8]))
"

# 3. Negative test — request a non-existent secret. Helper must raise,
# never silently fall through to os.environ.
MLOPS_ENV=staging \
GCP_PROJECT_ID="$PROJECT_ID" \
python -c "
from common_utils.secrets import get_secret, SecretNotFoundError
try:
    get_secret('does-not-exist-r4', backend='gcp')
    print('FAIL: expected SecretNotFoundError')
except SecretNotFoundError as e:
    print('OK: refused to fall back, error=%s' % e)
"

# 4. Cleanup.
gcloud secrets delete "$SECRET_ID" --quiet
rm -f "$SECRET_VALUE_FILE"
```

Expected output: `len=` non-zero on step 2; `OK: refused to fall back` on step 3.

## Procedure 2 — ASM end-to-end

```bash
SECRET_NAME="r4-secrets-runbook-test"
aws secretsmanager create-secret --name "$SECRET_NAME" \
  --secret-string "this-is-a-test-secret-DO-NOT-USE-IN-PROD" \
  >/dev/null 2>&1 || \
  aws secretsmanager update-secret --secret-id "$SECRET_NAME" \
    --secret-string "this-is-a-test-secret-DO-NOT-USE-IN-PROD" >/dev/null

MLOPS_ENV=staging \
python -c "
from common_utils.secrets import get_secret
v = get_secret('$SECRET_NAME', backend='aws')
print('len=%d, prefix=%s' % (len(v), v[:8]))
"

# Negative test — same shape as Procedure 1 step 3.
MLOPS_ENV=staging \
python -c "
from common_utils.secrets import get_secret, SecretNotFoundError
try:
    get_secret('does-not-exist-r4', backend='aws')
    print('FAIL: expected SecretNotFoundError')
except SecretNotFoundError as e:
    print('OK: refused to fall back, error=%s' % e)
"

aws secretsmanager delete-secret --secret-id "$SECRET_NAME" --force-delete-without-recovery >/dev/null
```

## Procedure 3 — `os.environ` refusal in non-dev

This procedure validates the D-17 invariant: `secrets.py` MUST refuse
to read from `os.environ` when `MLOPS_ENV ∈ {staging, production}`.

```bash
# Set a bogus env var that the helper would have read in dev.
MLOPS_ENV=production R4_TEST_SECRET=should-be-refused \
python -c "
from common_utils.secrets import get_secret
import sys
try:
    v = get_secret('R4_TEST_SECRET')  # default backend env / dev only
    print('FAIL: returned %r in production mode' % v)
    sys.exit(1)
except Exception as e:
    print('OK: refused — %s' % type(e).__name__)
"
```

Expected: helper raises (refuses fallback); exit 0.

---

## Recording evidence

For each successful procedure, write a `VALIDATION_LOG.md` entry with:

- Date + operator + cloud project / account ID.
- Helper version (`git rev-parse HEAD` at the time of the run).
- Output excerpts (no actual secret value).
- Latency observation (cold call, warm call) if material.

## Acceptance criteria for closing M1

- [ ] Procedure 1 (GSM) executed with `OK` outputs on steps 2 and 3.
- [ ] Procedure 2 (ASM) executed with `OK` outputs on both calls.
- [ ] Procedure 3 (`os.environ` refusal) executed and the helper refused.
- [ ] `VALIDATION_LOG.md` entry recorded.

## Cadence

- After every change to `templates/service/common_utils/secrets.py`.
- Quarterly minimum.
- After any cloud-provider API deprecation notice that touches Secret Manager / Secrets Manager.
