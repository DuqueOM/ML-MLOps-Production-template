"""Policy tests — D-01..D-31 anti-patterns enforced on SCAFFOLDED output.

The contract tests in `templates/service/tests/test_*.py` verify the
TEMPLATE itself. This `policy/` suite verifies what users actually
RECEIVE after running `new-service.sh` — catching drift between the
template's claims and the rendered service.

Authority: ADR-016 PR-R2-11.
See: AGENTS.md `## Anti-Patterns` for the canonical D-XX table.
"""
