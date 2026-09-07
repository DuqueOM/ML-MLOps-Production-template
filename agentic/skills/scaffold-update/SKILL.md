---
name: scaffold-update
description: Update an existing scaffolded service with the latest template changes via copier update
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(python3:*)
  - Bash(copier:*)
when_to_use: >
  Use when a scaffolded service needs to absorb template improvements
  (new monitoring rules, updated CI workflows, agentic system upgrades,
  security patches to base images, etc.). Examples: 'update my service
  to the latest template', 'pull in the latest agentic rules', 'upgrade
  scaffolded service after template v2 release'.
argument-hint: "[service-path]"
arguments:
  - service-path
authorization_mode:
  check_drift: AUTO           # read-only diff
  update: CONSULT              # mutates service files — requires approval
  resolve_conflicts: CONSULT   # manual conflict resolution needed
  escalation_triggers:
    - uncommitted_changes: STOP    # clean working tree required
    - breaking_template_change: STOP # requires migration ADR
    - answers_file_missing: STOP   # .copier-answers.yml must exist
---

# Scaffold Update — Pull template improvements into an existing service

## When to use

When the template repository has shipped improvements (new D-XX rules,
updated CI workflows, security patches, agentic system upgrades) and a
scaffolded service needs to absorb them.

## When NOT to use

- **During active incidents** — stabilize first, update later.
- **On services with uncommitted changes** — `copier update` requires a
  clean working tree.
- **On services created outside the scaffolder** — no `.copier-answers.yml`
  means Copier cannot track the template version.

## Pre-conditions

1. The service was scaffolded via `copier copy` (or the equivalent
   `new-service.sh` wrapper).
2. `.copier-answers.yml` exists in the service root (created by the
   initial `copier copy` or a prior `copier update`).
3. The service working tree is clean (`git status` shows no changes).
4. The template repository is accessible (local path or git remote).

## Steps

### Step 1 — Pre-flight checks (AUTO, 30s)

```bash
cd "$service-path"
git status --porcelain  # must be empty
test -f .copier-answers.yml  # must exist
```

If either check fails → STOP with a clear message.

### Step 2 — Dry-run diff (AUTO, 1min)

Show what would change without applying:

```bash
# --vcs-ref is REQUIRED: a bare `copier update` resolves to the highest-
# sorting tag, which is a frozen v1.x audit snapshot, and DOWNGRADES the
# service while deleting .copier-answers.yml. Always pin the target release.
copier update --vcs-ref=<release-tag> --dry-run
```

Categorize the diff:

- **No-op**: files the service hasn't customized → safe to auto-apply.
- **Conflict**: files the service has modified → require manual review.
- **New files**: template additions not present in the service → safe.

### Step 3 — Review with operator (CONSULT)

Present the categorized diff to the operator. For each conflict:

1. Show the template version (upstream).
2. Show the service version (local).
3. Propose a resolution strategy (keep local, adopt upstream, merge).

Wait for explicit approval before proceeding.

### Step 4 — Apply update (CONSULT → approved)

```bash
copier update --vcs-ref=<release-tag> --trust --defaults
```

Copier will:

- Re-render all template files with the latest template version.
- Preserve files the service has customized (via `.copier-answers.yml`
  conflict detection).
- Run post-generation tasks (`sync_agentic_adapters.py` +
  `validate_agentic_manifest.py --strict`).

### Step 5 — Resolve conflicts (CONSULT, if any)

For each conflict Copier reports:

1. Read both versions.
2. Propose a merge that preserves service customizations while
   absorbing template improvements.
3. Apply the merge.
4. Mark the conflict as resolved.

### Step 6 — Validate (AUTO, 2min)

Run the full validation suite on the updated service:

```bash
# Agentic system
python3 scripts/validate_agentic_manifest.py --strict
python3 scripts/sync_agentic_adapters.py

# CI/CD
python3 scripts/ci_verify_workflows.py

# K8s
for ov in gcp-dev gcp-staging gcp-prod aws-dev aws-staging aws-prod; do
  kubectl kustomize k8s/overlays/$ov > /dev/null
done

# Tests
pytest tests/ -v --tb=short
```

### Step 7 — Commit (CONSULT)

Propose a commit message summarizing the template version absorbed and
the files changed. Wait for operator approval before committing.

```bash
git add -A
git commit -m "chore: absorb template update $(date +%Y-%m-%d)

Template version: <sha or tag>
Files changed: <count>
Conflicts resolved: <count>
Post-gen tasks: sync_agentic_adapters.py + validate_agentic_manifest.py --strict"
```

## What this skill does NOT do

- Does NOT force-push or override branch protection.
- Does NOT update the template repository itself (that's a separate
  workflow for template maintainers).
- Does NOT skip the post-gen agentic validation — if
  `validate_agentic_manifest.py --strict` fails, the update is
  considered incomplete.

## Invariants

- `.copier-answers.yml` is the source of truth for template version
  tracking. Never delete or hand-edit it.
- Post-gen tasks MUST run to completion — a service with stale agentic
  adapters is worse than no update.
- Breaking template changes (renamed questions, removed files) require
  a migration ADR before the update can proceed.
