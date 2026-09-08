#!/usr/bin/env python3
"""Contract: an "Enforced by X" claim must be traceable in both directions.

Why this exists
---------------
Three times in one review cycle, a comment asserted a control that was not
there:

* a tfsec suppression cited "the variable validation rule in
  ``variables.tf``" — there was none, and the GKE control plane could be
  public with no allowlist;
* ``ci_sa_user`` said "Scoped via condition (only acting on SAs in this
  project)" — no condition block, so CI could impersonate every service
  account in the project;
* ``check_baselines_expiry.py`` claimed to read ``exclude:`` blocks — it
  filtered on uppercase ids and read none.

Each survived review because **reviewing meant reading the claim**. A
comment cannot be verified; it can only be believed.

What this checks, and what it deliberately does not
---------------------------------------------------
The general problem — "does this prose claim hold?" — is not decidable. The
tractable slice is the repository's central contract: the ``D-NN``
anti-pattern table in ``AGENTS.md``, where each row names the test or script
that enforces it.

For every row whose "Enforced by" clause names a path, this asserts:

1. the named file **exists**, and
2. it **mentions the ``D-NN`` identifier** it claims to enforce.

The second half is the point. Measured on this repo, every named path
already resolved — so an existence check alone would have caught none of
the three failures above, because in all three the file existed and the
control inside it did not. Requiring the identifier makes the link
bidirectional: the table points at the enforcer, and the enforcer declares
what it enforces, so refactoring one without the other fails.

This does not verify that the test is *correct*, only that the traceability
link is real. Correctness is what the assertions in those files are for —
see ``templates/service/tests/test_iam_least_privilege.py`` §"Control
invariants" for the pattern.

Exit codes
----------
- 0: every path-shaped enforcement claim resolves and is acknowledged.
- 1: a claim names a file that does not exist, or one that never mentions
     the anti-pattern it is said to enforce.
- 2: setup error (``AGENTS.md`` missing, or its table shape changed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS = REPO_ROOT / "AGENTS.md"

# A row of the anti-pattern table: `| D-07 | ... | ... |`
#
# The optional `{% ... %}` is not cosmetic. Two rows (D-32, D-34) document
# Jinja tokens and are wrapped in a raw block so Copier does not try to render
# them — `| {% raw %}D-34 | ...`. This pattern used to require `D-` right after
# the pipe, so the moment those rows gained their wrapper the scan silently
# dropped from 38 anti-patterns to 36, and said nothing. The count assertion in
# `main` exists so that cannot happen again quietly.
_ROW = re.compile(r"^\|\s*(?:\{%[^%]*%\}\s*)?(?P<id>D-\d+)\s*\|")
# The clause naming an enforcer, when that enforcer is path-shaped.
_ENFORCED_BY = re.compile(r"[Ee]nforced by[^|]*?`?(?P<target>(?:[A-Za-z0-9_./-]*tests?|scripts)/[A-Za-z0-9_./-]+)")

# A claim may name the path as it appears from the repo root or from inside a
# generated service; both are legitimate, so both roots are tried.
_PREFIXES = ("", "templates/service/")
_SUFFIXES = ("", ".py", ".sh")


def _resolve(target: str) -> Path | None:
    for prefix in _PREFIXES:
        for suffix in _SUFFIXES:
            candidate = REPO_ROOT / f"{prefix}{target}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def main() -> int:
    if not AGENTS.is_file():
        sys.stderr.write(f"::error::{AGENTS} not found\n")
        return 2

    rows = [line for line in AGENTS.read_text(encoding="utf-8").splitlines() if _ROW.match(line)]
    if not rows:
        sys.stderr.write(
            "::error::no `| D-NN |` rows found in AGENTS.md. Either the anti-pattern "
            "table changed shape or this guard is reading the wrong file — both need "
            "a human, so this is a failure rather than a pass.\n"
        )
        return 2

    # Every D-NN from 1 to the highest must appear as a row. A scan that
    # silently sees fewer rows than the table holds is the failure mode this
    # gate exists to prevent, applied to itself.
    ids = sorted(int(_ROW.match(line).group("id")[2:]) for line in rows)  # type: ignore[union-attr]
    gaps = [n for n in range(1, max(ids) + 1) if n not in ids]
    if gaps:
        sys.stderr.write(
            f"::error::AGENTS.md's anti-pattern table has rows up to D-{max(ids):02d} but "
            f"this scan matched only {len(ids)}. Unmatched: "
            f"{', '.join(f'D-{n:02d}' for n in gaps)}. Either a row was deleted "
            f"without renumbering, or its shape changed and `_ROW` no longer "
            f"matches it — the second is how this scan once narrowed from 38 to 36 "
            f"without a word.\n"
        )
        return 1

    problems: list[str] = []
    checked = 0

    for line in rows:
        anti_pattern = _ROW.match(line).group("id")  # type: ignore[union-attr]
        match = _ENFORCED_BY.search(line)
        if not match:
            continue  # enforced by prose, a command, or nothing nameable
        target = match.group("target")
        checked += 1

        resolved = _resolve(target)
        if resolved is None:
            problems.append(f"{anti_pattern}: claims enforcement by '{target}', which does not exist")
            continue

        try:
            body = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            problems.append(f"{anti_pattern}: enforcer '{target}' is unreadable")
            continue

        if anti_pattern not in body:
            problems.append(
                f"{anti_pattern}: '{resolved.relative_to(REPO_ROOT)}' is named as its "
                f"enforcer but never mentions {anti_pattern}. The link is one-way — "
                f"refactor that file and nothing says {anti_pattern} depended on it. "
                f"Name the anti-pattern in a docstring or an assertion message."
            )

    if problems:
        sys.stderr.write(
            "FAIL: an 'Enforced by' claim in AGENTS.md is not traceable.\n"
            "A comment asserting a control is a checkable claim; this checks the\n"
            "half that is decidable — that the named enforcer exists and declares\n"
            "what it enforces.\n\n"
        )
        for problem in problems:
            sys.stderr.write(f"  - {problem}\n")
        sys.stderr.write(
            "\nFix: point the claim at the file that really enforces it, or add the\n"
            "D-NN identifier to that file so the traceability is bidirectional.\n"
        )
        return 1

    print(
        f"[control-claims] OK — {checked} of {len(rows)} anti-patterns name a "
        "path-shaped enforcer, and every one exists and acknowledges its D-NN."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
