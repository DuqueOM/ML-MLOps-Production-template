# Contributing to ML-MLOps Production Template

Thanks for contributing. This repository is meant to be a serious production template, so we optimize for changes that improve reliability, clarity, security, and repeatability in real ML systems.

## Ground rules

- Follow the invariants and operating model in [AGENTS.md](AGENTS.md).
- Keep solutions proportional to the problem. This repo is intentionally opinionated, but it should not drift into platform over-engineering.
- Prefer production-backed patterns over purely theoretical abstractions.
- If a change affects architecture, governance, security posture, or default behavior, document it with an ADR.

## How to contribute

1. Fork the repository.
2. Create a branch for your change.
3. Install local checks:

   ```bash
   pip install pre-commit
   pre-commit install
   ```

4. Make your changes.
5. Run the relevant quality gates locally.
6. Commit with sign-off:

   ```bash
   git commit -s -m "feat: describe your change"
   ```

7. Push and open a pull request.

## Developer Certificate of Origin (DCO)

This project uses the Developer Certificate of Origin (DCO).

By contributing, you certify that:

- you created the contribution or otherwise have the right to submit it
- you understand the contribution will be distributed under the Apache License 2.0

Every commit must include a `Signed-off-by` line. The simplest way is to use `git commit -s`.

## Commit style

We recommend Conventional Commits:

```text
feat: add guarded CI autofix policy
fix: align SLO metric names with service exporter
docs: clarify operational memory plane boundaries
```

## What kinds of contributions are useful here

- improvements extracted from real production usage
- stronger tests for template guarantees
- better cloud parity between GCP and AWS
- security, observability, and CI/CD hardening
- documentation that reduces ambiguity for adopters
- safer agentic workflows and clearer operating boundaries

## Contribution expectations

### Template code

- Keep scaffolded repos self-contained.
- Do not introduce hidden runtime dependencies on the template root.
- Preserve the separation between training, serving, monitoring, and infrastructure concerns.
- Avoid mutable image tags and static cloud credentials.
- Keep production defaults safe by default.

### Documentation

- Use measured evidence where possible.
- Be explicit about boundaries and non-goals.
- Keep README, ADRs, runbooks, and contribution guidance in sync when behavior changes.

### Agentic system

- `AUTO`, `CONSULT`, and `STOP` behavior must remain auditable.
- Dynamic risk escalation must only increase caution, never silently weaken policy.
- New automated repair paths need bounded blast radius and deterministic verification.

## Pull request review

Reviewers will look for:

- operational safety
- alignment with template invariants
- clarity of documentation
- test coverage proportional to risk
- open-source maintainability

## License

All contributions are accepted under the Apache License 2.0. No Contributor License Agreement (CLA) is required.

By submitting a contribution, you agree to the terms defined in the DCO.

## Code of conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
