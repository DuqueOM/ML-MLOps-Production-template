# Contributing to ML-MLOps Production Template

Thank you for considering contributing! This template aims to be the canonical reference for shipping ML models to production.

## How to Contribute

### Reporting Bugs
- Use [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) template
- Include which template file is affected and reproduction steps

### Suggesting Features
- Use [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) template
- Consider the **Engineering Calibration Principle** — is the proposed change proportional to the problem?

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Install pre-commit hooks: `pip install pre-commit && pre-commit install`
4. Make your changes
5. Run quality checks: `pre-commit run --all-files`
6. Commit using [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat: add GPU node pool to GKE Terraform template
   fix: correct HPA targetCPUUtilizationPercentage in deployment.yaml
   docs: add ADR for model versioning strategy
   ```
7. Push and open a Pull Request

### Contribution Guidelines

#### Template Code
- All template files must have thorough comments explaining customization points
- Use `{service}`, `{ServiceName}`, `{namespace}` as placeholders — never hardcoded names
- Follow the invariants in `AGENTS.md` — PRs violating anti-patterns D-01 through D-12 will be rejected
- Use compatible release pinning (`~=`) for Python ML packages

#### Agentic System (`.windsurf/`)
- Rules must specify correct glob patterns for context activation
- Skills must include `allowed-tools`, `when_to_use`, `argument-hint`, and per-step `Success criteria`
- Workflows must follow the YAML frontmatter + markdown format

#### Documentation
- Create an ADR for any non-trivial architectural decision
- Use measured data, not estimates
- Follow Google-style docstrings for Python

### What We're Looking For
- New template patterns extracted from production experience
- Improvements to existing templates based on real-world usage
- Additional anti-pattern detectors (D-13+)
- Multi-cloud parity improvements (GCP ↔ AWS)
- Load test scenarios and production baseline data

### Code of Conduct
This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
