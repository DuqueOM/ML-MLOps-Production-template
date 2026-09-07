"""Contract test — anti-pattern catalog count consistency (R5-L1).

Authority: ACTION_PLAN_R5 §R5-L1.

The canonical source of truth for the anti-pattern catalog is the table
in ``AGENTS.md`` (the highest ``D-NN`` row). Secondary documentation —
IDE-specific rules, CLAUDE.md, ADRs, the IDE parity audit, and skills —
must cite the same maximum count, or contributors quoting outdated
ranges (e.g. "D-01..D-30") create review-time confusion that is hard to
catch by eye.

This test:

1. Parses ``AGENTS.md`` for the highest ``D-NN`` token and uses that as
   the canonical maximum.
2. Walks a curated set of secondary docs and asserts no ``D-01..D-MM``
   range string with ``MM < canonical_max`` survives.

The curated allowlist below is intentionally tight: only files that
quote the CATALOG SIZE (a range or a count). Files that mention a
specific D-NN by ID are not in scope — those are valid references.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_MD = REPO_ROOT / "AGENTS.md"

# This module reconciles template-repo documents. Inside a scaffolded service
# `parents[3]` walks above the service root and none of them exist, so every
# subject would now fail rather than skip. Skip the module there instead: it
# is a repo-only check that happens to live in the payload directory.
if not AGENTS_MD.exists():  # pragma: no cover — layout probe
    pytest.skip(
        "AGENTS.md not found at the repo root; this module reconciles "
        "template-repo documents and does not apply to a scaffolded service",
        allow_module_level=True,
    )

# Documents that quote the CATALOG SIZE (range or count). Each must
# match the canonical maximum derived from AGENTS.md.
# `.claude/rules/01-serving.md` and `09-mlops-conventions.md` were listed here
# and neither has ever existed under those names — the rules are
# `04a-python-serving.md` and `01-mlops-conventions.md`, and being thin
# adapter pointers they do not quote the catalog range at all. The test
# skipped on both, so two of its six subjects were decorative. Removed rather
# than repointed: there is nothing at those files to check.
RANGE_QUOTING_DOCS: list[Path] = [
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / "agentic" / "skills" / "debug-ml-inference" / "SKILL.md",
    REPO_ROOT / "docs" / "ide-parity-audit.md",
    REPO_ROOT / "docs" / "decisions" / "ADR-014-gap-remediation-plan.md",
]

# Patterns we look for; if they cite an upper bound less than canonical_max,
# the test fails. We use a forgiving capture group on `\d{2}` so a future
# bump to D-40 / D-50 still works without touching this test.
RANGE_PATTERNS = [
    re.compile(r"D-?01\s*\.\.\s*D-?(\d{2})"),  # D-01..D-32
    re.compile(r"D-?01\s*(?:to|through)\s*D-?(\d{2})"),  # D-01 to D-32
    re.compile(r"D-?01\s+through\s+D-?(\d{2})"),
]


def _canonical_max() -> int:
    """Return the highest D-NN row id from AGENTS.md."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    ids = [int(m.group(1)) for m in re.finditer(r"^\|\s*D-(\d{2})\s*\|", text, flags=re.MULTILINE)]
    assert ids, "AGENTS.md must contain at least one anti-pattern row"
    return max(ids)


@pytest.fixture(scope="module")
def canonical_max() -> int:
    return _canonical_max()


def _is_in_partition_row(text: str, pos: int) -> bool:
    """Return True if ``pos`` falls inside a markdown table row (line begins with `|`).

    Markdown tables in CLAUDE.md / AGENTS.md partition the catalog into
    sub-ranges (e.g. ``| D-01..D-08 | Serving + ML quality |``). Those
    cells are valid partition references, NOT catalog-size claims, so
    they MUST NOT be flagged as drift even when they appear to match a
    ``D-01..D-NN`` regex.
    """
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].lstrip()
    return line.startswith("|")


@pytest.mark.parametrize(
    "doc",
    RANGE_QUOTING_DOCS,
    ids=[str(p.relative_to(REPO_ROOT)) for p in RANGE_QUOTING_DOCS],
)
def test_doc_cites_canonical_max(doc: Path, canonical_max: int) -> None:
    """Every catalog-size range quote in ``doc`` MUST cite the canonical max.

    Partition references inside markdown table rows (e.g.
    ``| D-01..D-08 | Serving |``) are excluded; they describe sub-ranges
    of the catalog, not its size.
    """
    if not doc.exists():
        # A named subject that is absent is a defect in this list, not a
        # reason to pass. Skipping here is what let two dead entries sit in
        # RANGE_QUOTING_DOCS unnoticed. In a scaffolded service none of these
        # exist, and the module-level guard below skips the whole file rather
        # than letting individual subjects vanish silently.
        pytest.fail(
            f"{doc.relative_to(REPO_ROOT)} is listed as quoting the anti-pattern "
            "catalog range but does not exist. Fix the path or remove the entry."
        )
    text = doc.read_text(encoding="utf-8")
    matches: list[tuple[int, int]] = []
    for pat in RANGE_PATTERNS:
        for m in pat.finditer(text):
            if _is_in_partition_row(text, m.start()):
                continue
            matches.append((m.start(), int(m.group(1))))
    if not matches:
        pytest.skip(f"{doc} does not currently quote the catalog range outside partition rows")
    drifted = [(pos, val) for (pos, val) in matches if val != canonical_max]
    assert not drifted, (
        f"{doc.relative_to(REPO_ROOT)} quotes D-01..D-{drifted[0][1]:02d} but "
        f"AGENTS.md canon is D-01..D-{canonical_max:02d}. "
        f"Bump every range cite (offsets={[d[0] for d in drifted]})."
    )


def test_canonical_max_is_at_least_32() -> None:
    """Sanity check — the catalog has reached D-32 by R5-L1 close.

    A future contributor bumping the catalog forward should NOT need to
    bump this lower bound (R5-L1 is the floor, not the ceiling).
    """
    assert _canonical_max() >= 32, (
        f"AGENTS.md canon {_canonical_max()} is below the R5-L1 floor of 32. Did the canon table get truncated?"
    )
