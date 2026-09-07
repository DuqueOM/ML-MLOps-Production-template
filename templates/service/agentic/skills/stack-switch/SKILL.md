---
name: stack-switch
description: Switch a scaffolded service between stack profiles (local, staging, prod)
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(python3:*)
  - Bash(make:*)
when_to_use: >
  Use when a scaffolded service needs to change its stack profile —
  e.g. from local to staging for cluster testing, or from staging to
  prod for production deployment. Examples: 'switch to staging profile',
  'change from local to prod', 'activate cloud profile'.
argument-hint: "[service-path] [profile]"
arguments:
  - service-path
  - profile
authorization_mode:
  check_current: AUTO          # read-only inspection
  switch_to_local: AUTO        # local is always safe
  switch_to_staging: CONSULT   # affects staging deploy targets
  switch_to_prod: CONSULT      # affects prod deploy targets
  escalation_triggers:
    - uncommitted_changes: STOP    # clean working tree required
    - cloud_creds_in_local: STOP   # D-35 violation detected
    - active_incident: STOP        # do not switch profiles during incident
---

# Stack Switch — Change the active stack profile of a service

## When to use

When a scaffolded service needs to transition between stack profiles
(`local`, `staging`, `prod`) as defined by ADR-033. This changes which
infrastructure targets are active and what dependencies are required.

## When NOT to use

- **During active incidents** — stabilize first, switch profiles later.
- **On services with uncommitted changes** — the profile switch writes
  to `configs/profiles/active_profile.yaml` and requires a clean tree.
- **To bypass D-35** — the `local` profile MUST NOT accept cloud
  credentials. If you need cloud deps, switch to `staging` or `prod`.

## Pre-conditions

1. The service was scaffolded via `copier copy` (or `new-service.sh`).
2. `configs/profiles/active_profile.yaml` exists.
3. The target profile YAML exists in `configs/profiles/<profile>.yaml`.
4. The service working tree is clean (`git status` shows no changes).

## Steps

### Step 1 — Pre-flight checks (AUTO, 10s)

```bash
cd "$service-path"
git status --porcelain  # must be empty
test -f configs/profiles/active_profile.yaml  # must exist
test -f configs/profiles/$profile.yaml  # must exist
```

If any check fails → STOP with a clear message.

### Step 2 — Inspect current profile (AUTO, 5s)

Read `configs/profiles/active_profile.yaml` and report:

- Current profile name
- What dependencies are currently required
- What deploy targets are currently active

### Step 3 — Review target profile (CONSULT)

Read `configs/profiles/$profile.yaml` and present:

- What dependencies the target profile requires
- What deploy targets the target profile activates
- The mode change (e.g. AUTO → CONSULT for staging, AUTO → STOP for prod)
- Any D-35 implications (if switching to `local`, cloud creds must be absent)

Wait for explicit approval before proceeding.

### Step 4 — Apply switch (CONSULT → approved)

```bash
make switch-profile PROFILE=$profile
```

This updates `configs/profiles/active_profile.yaml` to reference the
new profile.

### Step 5 — Validate (AUTO, 30s)

```bash
# Verify the active profile was updated
cat configs/profiles/active_profile.yaml

# Run D-35 check if switching to local
python3 -c "
import yaml
data = yaml.safe_load(open('configs/profiles/local.yaml'))
assert data['requires']['cloud_credentials'] is False
assert data['requires']['kubernetes'] is False
assert data['requires']['docker'] is False
assert data['deploy']['enabled'] is False
print('D-35 check passed')
"

# Run agentic manifest validation
python3 scripts/validate_agentic_manifest.py --strict
```

### Step 6 — Commit (CONSULT)

Propose a commit message and wait for operator approval:

```bash
git add configs/profiles/active_profile.yaml
git commit -m "chore: switch stack profile to $profile

Previous profile: <old>
New profile: $profile
Deploy mode: <AUTO|CONSULT|STOP>"
```

## What this skill does NOT do

- Does NOT provision cloud resources — that's Terraform's job.
- Does NOT deploy the service — that's `make deploy` or the deploy skills.
- Does NOT modify the profile YAML files themselves — those are
  template-managed and updated via `copier update`.
- Does NOT skip D-35 — if the `local` profile has cloud creds, this
  skill will STOP.

## Invariants

- `configs/profiles/active_profile.yaml` is the single source of truth
  for the active profile. Never hand-edit it — use `make switch-profile`
  or this skill.
- Switching to `prod` is a CONSULT-class operation that requires
  explicit approval and a clean working tree.
- The `local` profile MUST NOT accept cloud credentials (D-35).
