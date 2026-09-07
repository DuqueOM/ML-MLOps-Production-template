#!/usr/bin/env python3
"""Generate (and verify) the ADR index at ``docs/decisions/README.md``.

Why this script exists
----------------------
``docs/COMPLIANCE_MAPPING.md`` cites an ADR index as EU AI Act Art. 11
evidence — "Documentation sufficient to assess compliance". The index did
not exist, and the same row claimed "ADRs (37)" when the directory held
45. A compliance mapping that points at a missing artefact and miscounts
the one it does have is worse than no mapping: it is an assertion an
auditor can falsify in one command.

Writing the index by hand would have reproduced the defect on the next
ADR. It is generated from the files themselves, and ``--check`` fails CI
when the committed index no longer matches, so the count in the mapping
can be replaced by a link to something that cannot drift.

Title parsing
-------------
Two heading conventions are in use and both are honoured::

    # ADR-001: Template Scope Boundaries          (older, colon)
    # ADR-045 — Separate the release-channel …    (newer, em dash)

Exit codes
----------
- 0: index written, or (with ``--check``) the committed index is current.
- 1: ``--check`` and the index is stale or missing.
- 2: an ADR filename or heading could not be parsed.

Usage
-----
::

    python3 scripts/generate_adr_index.py            # rewrite the index
    python3 scripts/generate_adr_index.py --check    # CI / pre-commit
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "decisions"
INDEX_FILE = ADR_DIR / "README.md"

_FILENAME = re.compile(r"^ADR-(?P<number>\d{3})-(?P<slug>[a-z0-9-]+)\.md$")
# `# ADR-001: Title` or `# ADR-045 — Title`; the separator drifted over time.
_HEADING = re.compile(r"^#\s*ADR-(?P<number>\d+)\s*[:—–-]\s*(?P<title>.+?)\s*$")

_PREAMBLE = """<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: python3 scripts/generate_adr_index.py
     Verified in CI by: python3 scripts/generate_adr_index.py --check -->

# Architecture Decision Records

Every non-trivial decision in this template is recorded here with its
measured trade-offs. This index is generated from the files themselves, so
it cannot drift from what the directory actually contains.

`docs/COMPLIANCE_MAPPING.md` cites this index as EU AI Act Art. 11
evidence (technical documentation sufficient to assess compliance). It is
therefore load-bearing: an auditor reading the mapping lands here.

Numbering is dense and gaps are deliberate — a withdrawn ADR keeps its
number and says so, rather than being deleted and leaving a hole
(`scripts/check_doc_coherence.py` C5 enforces this).

"""


def _collect() -> list[tuple[int, str, str]]:
    """Return ``[(number, title, filename)]`` sorted by number."""
    rows: list[tuple[int, str, str]] = []
    errors: list[str] = []
    for path in sorted(ADR_DIR.glob("ADR-*.md")):
        name_match = _FILENAME.match(path.name)
        if not name_match:
            errors.append(f"{path.name}: filename does not match ADR-NNN-slug.md")
            continue
        first_line = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else ""
        heading = _HEADING.match(first_line)
        if not heading:
            errors.append(f"{path.name}: first line is not '# ADR-NNN<sep> Title' (got {first_line!r})")
            continue
        if int(heading.group("number")) != int(name_match.group("number")):
            errors.append(f"{path.name}: heading number {heading.group('number')} != filename number")
            continue
        rows.append((int(name_match.group("number")), heading.group("title"), path.name))

    if errors:
        for error in errors:
            sys.stderr.write(f"::error::{error}\n")
        raise SystemExit(2)
    return rows


def _render(rows: list[tuple[int, str, str]]) -> str:
    # The emitted Markdown must satisfy `.markdownlint-cli2.jsonc`, or this
    # generator and the docs lint deadlock: regenerating fixes one gate and
    # breaks the other. Hence the padded separator (MD060 `compact`) and the
    # single trailing newline on the count line (MD012).
    lines = [
        _PREAMBLE.rstrip("\n"),
        "",
        f"**{len(rows)} decisions recorded.**",
        "",
        "| ADR | Decision |",
        "| --- | --- |",
    ]
    lines += [f"| {number:03d} | [{title}]({filename}) |" for number, title, filename in rows]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed index is stale")
    args = parser.parse_args()

    rendered = _render(_collect())

    if not args.check:
        INDEX_FILE.write_text(rendered, encoding="utf-8")
        print(f"[adr-index] wrote {INDEX_FILE.relative_to(REPO_ROOT)}")
        return 0

    if not INDEX_FILE.exists():
        sys.stderr.write("::error::docs/decisions/README.md is missing — run scripts/generate_adr_index.py\n")
        return 1
    if INDEX_FILE.read_text(encoding="utf-8") != rendered:
        sys.stderr.write(
            "::error::docs/decisions/README.md is stale. An ADR was added, renamed or "
            "retitled without regenerating the index.\n"
            "::error::Fix: python3 scripts/generate_adr_index.py\n"
        )
        return 1

    print(f"[adr-index] OK — index lists all {len(_collect())} ADRs and is current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
