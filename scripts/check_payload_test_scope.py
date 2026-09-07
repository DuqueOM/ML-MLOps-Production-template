#!/usr/bin/env python3
"""Contract: a test inside the Copier payload must be about the generated service.

Why this exists
---------------
``templates/service/`` is the render root: everything in it is copied into an
adopter's repository. ``templates/service/tests/`` was therefore doing two
jobs at once — holding the test suite a generated service ships with, *and*
holding the tests that guard this template repository (its README wording, its
workflows, its ``templates/config/*.yaml``).

Nothing distinguished the two. They were told apart only by
``Path(__file__).resolve().parents[3]`` versus ``parents[1]``, which is
invisible at a glance and identical to read.

Measured on a freshly scaffolded service before this gate existed: **147 of
764 tests failed or errored on the very first run**, across 15 files, every
one of them a repository test looking for a path like
``templates/service/Makefile`` or ``docs/ADOPTION.md`` two directories above
the service root. An adopter's first ``pytest`` was a wall of red that said
nothing about their service.

What this checks
----------------
For every test file under the payload:

1. **Depth.** ``parents[N]`` for ``N >= 2`` walks above the service root. From
   a test file directly under the payload's tests directory that lands on
   this repository; from the same file in a generated service it lands on
   whatever happens to be two levels up
   from the adopter's checkout. ``parents[0]`` (the tests directory) and
   ``parents[1]`` (the service root) are the only meaningful anchors.

2. **Subject.** A literal path beginning ``templates/`` only exists here.
   A payload test naming one is asserting about the template repository.

Either signal means the file belongs in ``templates/tests/governance/``,
where ``parents[3]`` still resolves to this repository — the move is
depth-neutral and needs no code change.

What it deliberately does not check
-----------------------------------
Whether the test is *correct*, or whether a service-scoped test would be
valuable. It checks that a file shipped to adopters is about the thing they
were shipped.

Exit codes
----------
- 0: every payload test is service-scoped.
- 1: a payload test reaches above the service root or asserts about the
     template repository.
- 2: setup error (the payload test directory is missing).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_TESTS = REPO_ROOT / "templates" / "service" / "tests"
GOVERNANCE_DIR = "templates/tests/governance/"

# The defect is a module-level assignment binding the *only* root a test has
# to a directory above the service.
#
# The safe depth is not a constant: it depends on where the file sits. From
# a file directly under the payload's tests directory, parents[1] is the
# service root; from one a level deeper, under integration, it is
# parents[2]. So the check
# computes, per file, how far it sits below the payload root and flags anything
# that reaches past it — the same arithmetic an adopter's copy performs, since
# the file keeps its relative position after rendering.
#
# A `parents[N]` inside a *candidate list* is a different thing and is allowed:
# `test_day2_artifacts_contract.py` and `test_alert_routing_contract.py` try
# the service root first and the template repo second, so they resolve in both
# contexts. That dual-perspective idiom is the one
# `scripts/check_doc_path_refs.py` already uses; banning it would push authors
# toward the single hard root this gate exists to stop.
_SINGLE_ROOT = re.compile(r"^\s*_?[A-Z][A-Z0-9_]*\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[(?P<n>\d+)\]\s*$")


def _flag(rel: str, lineno: int, n: int, safe: int) -> str:
    return (
        f"{rel}:{lineno}: binds its only root to parents[{n}]. From this file "
        f"parents[{safe}] is the service root, so parents[{n}] reaches "
        f"{n - safe} level(s) above it — the template repository here, and two "
        f"directories above the adopter's checkout in a generated service."
    )


def main() -> int:
    if not PAYLOAD_TESTS.is_dir():
        sys.stderr.write(f"::error::{PAYLOAD_TESTS} not found\n")
        return 2

    problems: list[str] = []
    checked = 0

    for path in sorted(PAYLOAD_TESTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        checked += 1

        # `parents[N]` where N is the number of directories between the file
        # and the payload root: a file directly in the tests directory maps
        # to parents[1], one nested a level deeper maps to parents[2].
        # Anything larger leaves the service.
        safe = len(path.relative_to(PAYLOAD_TESTS.parent).parts) - 1

        for lineno, line in enumerate(lines, 1):
            match = _SINGLE_ROOT.match(line)
            if match and int(match.group("n")) > safe:
                problems.append(_flag(rel, lineno, int(match.group("n")), safe))

    if problems:
        sys.stderr.write(
            "FAIL: a test inside the Copier payload is about this repository, not\n"
            "about the service it ships to. An adopter would see it fail on their\n"
            "first `pytest`, with a message about a path they do not have.\n\n"
        )
        for problem in problems:
            sys.stderr.write(f"  - {problem}\n")
        sys.stderr.write(
            f"\nFix: move the file to `{GOVERNANCE_DIR}`. `parents[3]` resolves to this\n"
            f"repository from there too, so the move needs no code change — it is a\n"
            f"`git mv` plus a line in the CI lane that runs that directory.\n"
        )
        return 1

    print(f"[payload-test-scope] OK — {checked} payload tests are service-scoped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
