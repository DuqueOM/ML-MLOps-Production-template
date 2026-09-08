---
name: template-lifecycle
trigger: glob
globs: ["copier.yml", "templates/service/**", "templates/scripts/new-service.sh", "scripts/test_scaffold.sh"]
description: Copier template lifecycle — scaffolding, upgrading, and maintaining the template itself — D-33/34
---

# Rule 15 — Template Lifecycle (Copier)

Applies to the **template repository** (this repo), not to scaffolded
services. Scaffolded services inherit the vendored copy at
`templates/service/agentic/rules/15-template-lifecycle.md` which carries
adjusted paths.

## D-33 — Manual file copying or sed-based placeholder substitution in the scaffolder

The scaffolder (`templates/scripts/new-service.sh`) MUST delegate to
`copier copy`. Manual `cp -r` + `sed -i` placeholder substitution is
forbidden because:

- It cannot handle conditional logic (e.g. skip files per variable).
- It cannot rename directories dynamically (Copier renders path templates).
- It drifts from the template source — `copier update` is impossible.
- Placeholder regexes miss edge cases (e.g. `{service}` inside JSON strings).

**Check**: `rg -n "sed.*-i.*\{service\}|cp.*-r.*templates/service"
templates/scripts/new-service.sh` must return zero hits.

## D-34 — Unquoted Jinja tokens in YAML lists

{% raw %}Copier's custom delimiters `{@ @}` produce valid YAML **only when
quoted** in list contexts. An unquoted `- {@ service_name @}` is invalid
YAML because the `@` character cannot start a token.

**Rule**: All `{@ @}` tokens in YAML list items MUST be quoted:

```yaml
# WRONG — invalid YAML
service:
  - {@ service_name @}

# CORRECT — valid YAML, Copier renders to "MyService"
service:
  - "{@ service_name @}"
```

**Check**: `rg -n '^\s+- \{@' templates/service/ --glob "*.yml"` must
return zero hits. Every match is an unquoted Jinja token in a YAML list.{% endraw %}

## D-35 — Local profile accepting cloud credentials or targeting a cluster

The `local` stack profile (`configs/profiles/local.yaml`) MUST NOT accept
cloud credentials, target a Kubernetes cluster, or require Docker. This
enforces the local-first contract (ADR-033): the `local` profile is the
zero-cloud-dependency on-ramp for adopters evaluating the template.

**Required fields in `configs/profiles/local.yaml`**:

```yaml
requires:
  cloud_credentials: false
  kubernetes: false
  docker: false
deploy:
  enabled: false
```

**Check**: `tests/policy/test_anti_patterns.py::test_d35_local_profile_no_cloud_deps`
parses the scaffolded `configs/profiles/local.yaml` and asserts all four
fields are `false`.

## Scaffolding invariant

`scripts/test_scaffold.sh` MUST validate:

{% raw %}1. Zero unreplaced Jinja tokens (`{@ @}`, `{% %}`, `{# #}`) in rendered output.{% endraw %}
2. Post-gen agentic tasks ran (`.devin/rules/` exists, manifest present).
3. Every Kustomize overlay renders from the scaffolded service. CI discovers
   them rather than listing them: a hardcoded list named the six cloud x env
   overlays while the tree held seven, and `batch-only` went unrendered and
   untested for as long as that list stood.
4. `ci_verify_workflows.py` passes on the scaffolded service.

## Upgrade path

`copier update` is the canonical upgrade mechanism for scaffolded
services. The template MUST maintain backward-compatible `copier.yml`
question names — renaming a question breaks `.copier-answers.yml` on
every scaffolded service.

The `scaffold-update` skill and `/scaffold-update` workflow codify the
upgrade procedure:

1. Pre-flight: clean working tree + `.copier-answers.yml` present.
2. Dry-run diff to categorize changes (no-op / conflict / new).
3. Review with operator (CONSULT mode).
4. Apply via `copier update --vcs-ref=<release-tag> --trust --defaults`.
   **`--vcs-ref` is mandatory.** Unpinned, Copier resolves to the
   highest-sorting tag — a frozen `v1.x` audit snapshot — and downgrades
   the service, deleting `.copier-answers.yml` and with it the update path.
5. Resolve conflicts manually.
6. Validate (agentic manifest, CI workflows, K8s overlays, tests).
7. Commit with template version reference.

Breaking template changes (renamed questions, removed files) require a
migration ADR before the update can proceed.
