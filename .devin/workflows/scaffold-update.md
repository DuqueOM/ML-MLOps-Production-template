---
description: Update an existing scaffolded service with the latest template changes via copier update
---

# /scaffold-update Workflow

## 1. Pre-flight Checks

```bash
cd "$SERVICE_PATH"
git status --porcelain          # must be empty
test -f .copier-answers.yml     # must exist
```

If either fails → STOP. Clean working tree and `.copier-answers.yml` are
required for `copier update`.

## 2. Dry-run Diff

```bash
# --vcs-ref is MANDATORY. Unpinned, Copier resolves to the highest-sorting
# tag — a frozen v1.x audit snapshot that sorts above the active v0.x line —
# and rewrites the service BACKWARDS, deleting .copier-answers.yml and with
# it the update path itself. Measured: 627 files → 435, 582 deleted.
# Latest tag: https://github.com/DuqueOM/ml-service-template/releases/latest
copier update --vcs-ref=<release-tag> --dry-run
```

Review the diff. Categorize:

- **No-op**: unchanged service files → safe to auto-apply
- **Conflict**: service-customized files → manual review
- **New**: template additions → safe

## 3. Review with Operator

Present the categorized diff. For each conflict, show both versions and
propose a resolution. Wait for approval.

## 4. Apply Update

```bash
copier update --vcs-ref=<release-tag> --trust --defaults
```

Copier re-renders all template files and runs post-gen tasks:

- `scripts/sync_agentic_adapters.py`
- `scripts/validate_agentic_manifest.py --strict`

## 5. Resolve Conflicts

For each conflict:

1. Read both versions
2. Propose merge preserving service customizations
3. Apply and mark resolved

## 6. Validate

```bash
python3 scripts/validate_agentic_manifest.py --strict
python3 scripts/ci_verify_workflows.py
for ov in gcp-dev gcp-staging gcp-prod aws-dev aws-staging aws-prod; do
  kubectl kustomize k8s/overlays/$ov > /dev/null
done
pytest tests/ -v --tb=short
```

## 7. Commit

```bash
git add -A
git commit -m "chore: absorb template update $(date +%Y-%m-%d)"
```
