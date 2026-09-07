---
description: Switch a scaffolded service between stack profiles (local, staging, prod)
---

# /stack-switch Workflow

## 1. Pre-flight Checks

```bash
cd "$SERVICE_PATH"
git status --porcelain                        # must be empty
test -f configs/profiles/active_profile.yaml  # must exist
test -f configs/profiles/$PROFILE.yaml        # must exist
```

If any fails → STOP. Clean working tree and profile files are required.

## 2. Inspect Current Profile

Read `configs/profiles/active_profile.yaml` and report:

- Current profile name
- Active dependencies and deploy targets

## 3. Review Target Profile

Read `configs/profiles/$PROFILE.yaml` and present:

- Required dependencies for the target profile
- Deploy targets and mode (AUTO / CONSULT / STOP)
- D-35 implications (local must not have cloud creds)

Wait for operator approval.

## 4. Apply Switch

```bash
make switch-profile PROFILE=$PROFILE
```

## 5. Validate

```bash
cat configs/profiles/active_profile.yaml
python3 scripts/validate_agentic_manifest.py --strict
```

If switching to `local`, verify D-35:

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('configs/profiles/local.yaml'))
assert d['requires']['cloud_credentials'] is False
assert d['requires']['kubernetes'] is False
assert d['requires']['docker'] is False
assert d['deploy']['enabled'] is False
print('D-35 check passed')
"
```

## 6. Commit

```bash
git add configs/profiles/active_profile.yaml
git commit -m "chore: switch stack profile to $PROFILE"
```
