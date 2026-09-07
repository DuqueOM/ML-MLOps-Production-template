## Summary
<!-- Brief description of what this PR does -->

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New template/feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing usage to not work)
- [ ] Documentation update
- [ ] Agentic system update (rules, skills, workflows)

## Related Issues

- Closes #
- Related to #

## Changes Made

-
-
-

## Testing

- [ ] Templates render correctly (`kustomize build`, `terraform validate`)
- [ ] Python code passes lint + type check (`pre-commit run --all-files`)
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] Docker build succeeds (`docker build -t test:dev .`)

## Evidence policy (per ADR-020 §S1-2 — required for new components)

**If this PR introduces a NEW** workflow, deploy YAML, overlay, contract test, `common_utils/` module, `scripts/`
script, or `templates/config/` policy YAML, the three blocks below are **required** and enforced by
`pr-evidence-check.yml`. For typical doc / refactor PRs that do not introduce a new component, you may delete this
section.

### Evidence — Schema / Contract Test
<!-- Path to the test file added or modified that pins the new component's contract. -->

### Evidence — Real Execution Output
<!-- Truncated raw output (stdout/stderr) from running the new component end-to-end. Not a description — actual output.
-->

### Evidence — CI Run Link
<!-- URL to the GitHub Actions run that produced the output above (or a link to a VALIDATION_LOG.md entry). -->

## Checklist

### Code Quality

- [ ] Follows project conventions (`AGENTS.md` invariants respected)
- [ ] No anti-patterns (D-01 through D-32 — see `AGENTS.md` Anti-Pattern Table)
- [ ] Compatible release pinning (`~=`) for ML packages
- [ ] Type hints on all public functions

### Versioning (per `docs/RELEASING.md`)

- [ ] Bump level (PATCH / MINOR / MAJOR) is correct per `docs/RELEASING.md` §1
- [ ] If MAJOR: `### Breaking for adopters` block in CHANGELOG entry + matching row in `MIGRATION.md`
- [ ] Status banners on README §"Operational Memory Plane" / §"Agentic CI self-healing" still match ADR-018 / ADR-019
  status (enforced by `test_phase0_disclosure.py`)

### Documentation

- [ ] README updated (if needed)
- [ ] CHANGELOG.md updated
- [ ] ADR created for non-trivial decisions
- [ ] Comments explain "why", not "what"

### Security

- [ ] No secrets or credentials hardcoded
- [ ] `gitleaks` scan passes
- [ ] Dependencies from trusted sources

## Deployment Notes
<!-- Any special considerations -->

## Engineering Calibration
<!-- Is this change proportional to the problem it solves? -->

<!-- GitHub renders this body under the pull request's own title,
     which is the H1. A top-level heading here would render a second
     one, so MD041 does not apply to this file. -->
<!-- markdownlint-configure-file { "MD041": false } -->
