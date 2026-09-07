"""Contract test — every release-note file has a `Known follow-ons` section (R4-L1).

Authority: ACTION_PLAN_R4 §L1 + ACTION_PLAN_R5 §Sprint 3.

R4-L1 flagged that `v1.0`–`v1.9` release notes lacked a canonical
`## Known follow-ons (scoped, not regressions)` section, while
`v1.11.0` and `v1.12.0` did. The asymmetry made traceability rough:
a reader could not tell from a release whether a gap was deliberately
deferred or accidentally omitted. Sprint 3 backfilled those sections.

This test locks the invariant so future release notes can't omit it:

1. Every file matching ``releases/v*.md`` must contain a heading that
   starts with ``## Known follow-ons`` (tolerates minor phrasing
   drift in the suffix — "... (scoped, not regressions)" etc.).
2. The section must be non-empty — at least one bullet underneath.

Draft / hotfix release notes shorter than 30 lines are exempt
(they may only document a single-line fix). The threshold is
conservative: the smallest existing release note is ~80 lines.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASES = sorted((REPO_ROOT / "releases").glob("v*.md"))

_HEADING_RE = re.compile(r"^##\s+Known follow-ons", re.MULTILINE)


@pytest.mark.parametrize("release_path", RELEASES, ids=lambda p: p.name)
def test_release_has_known_follow_ons_section(release_path: Path) -> None:
    """Every versioned release note ships with a follow-ons section."""
    text = release_path.read_text(encoding="utf-8")
    # Exempt very short hotfix release notes.
    if text.count("\n") < 30:
        pytest.skip(
            f"{release_path.name} is shorter than 30 lines — treated as a "
            "hotfix note and exempted from the follow-ons requirement."
        )
    assert _HEADING_RE.search(text), (
        f"{release_path.name} is missing the canonical "
        "'## Known follow-ons (scoped, not regressions)' section. "
        "Backfill it (see CONTRIBUTING.md + audit-r4 L1)."
    )


@pytest.mark.parametrize("release_path", RELEASES, ids=lambda p: p.name)
def test_follow_ons_section_is_non_empty(release_path: Path) -> None:
    """The section must list at least one bullet; an empty header is
    as useless as no header and masks the real follow-ons.
    """
    text = release_path.read_text(encoding="utf-8")
    if text.count("\n") < 30:
        pytest.skip(f"{release_path.name} short-note exempt.")
    m = _HEADING_RE.search(text)
    if not m:
        pytest.skip("covered by the presence test above.")
    # Take the slice from the heading to the next `## ` heading or EOF.
    start = m.end()
    next_h = re.search(r"\n##\s", text[start:])
    body = text[start : start + (next_h.start() if next_h else len(text))]
    # Count bullet lines (markdown "- ..." at line start, any indent).
    bullets = [line for line in body.splitlines() if re.match(r"^\s*[-*]\s+\S", line)]
    assert bullets, (
        f"{release_path.name} has the follow-ons heading but no bullets. "
        "Either list the real scoped-out items or remove the heading."
    )
