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

## Checklist

### Code Quality
- [ ] Follows project conventions (`AGENTS.md` invariants respected)
- [ ] No anti-patterns (D-01 through D-12)
- [ ] Compatible release pinning (`~=`) for ML packages
- [ ] Type hints on all public functions

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
