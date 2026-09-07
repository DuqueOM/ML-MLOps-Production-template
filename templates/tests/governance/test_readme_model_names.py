"""Contract test for R4 audit finding C1 — cadence-anticipated model names.

Three invariants:

1. **Section heading flagged** — `README.md` § "Recommended baseline" no longer
   carries the misleading "(verified 2026-04)" suffix; instead it reads
   "(cadence-anticipated, **NOT** vendor-verified)".

2. **Disclaimer banner present** — whenever speculative model name patterns
   (``gpt-5.<digit>`` / ``gemini-3.<digit>``) appear in the model-routing section,
   the section MUST also contain the canonical disclaimer phrase
   "cadence-anticipated" AND a reference to "Verifying model availability
   before adoption" so adopters cannot mistake these names for verified.

3. **Verification subsection exists** — the README contains the
   "Verifying model availability before adoption" subsection with provider
   dashboard links for OpenAI, Anthropic, and Google. Removing this
   subsection while speculative names are still present is blocked by
   this test.

These invariants together prevent silent regression of the R4-C1 finding:
"the model routing table presents anticipated names as if verified".

Authority: R4 audit C1, ADR-020, ACTION_PLAN_R4 §S0-1.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "README.md"

# Patterns that count as "speculative / cadence-anticipated".
SPECULATIVE_PATTERNS = [
    re.compile(r"gpt-5\.\d"),
    re.compile(r"gemini-3\.\d"),
]

# Phrases that MUST appear when any speculative pattern is in the section.
REQUIRED_DISCLAIMER_PHRASES = [
    "cadence-anticipated",
    "Verifying model availability before adoption",
]

# Section bounds — the model-routing block is delimited by these headings.
SECTION_START = "## Model routing policy"
SECTION_END_CANDIDATES = ["## Anti-patterns encoded", "---\n\n## Anti-patterns encoded"]


@pytest.fixture(scope="module")
def readme_text() -> str:
    assert README.exists(), f"README.md not found at {README}"
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def model_routing_section(readme_text: str) -> str:
    """Extract the §"Model routing policy" section from the README."""
    start = readme_text.find(SECTION_START)
    assert start != -1, f"README is missing the '{SECTION_START}' heading"
    # Find the next top-level section after start.
    end = -1
    for candidate in SECTION_END_CANDIDATES:
        end = readme_text.find(candidate, start + len(SECTION_START))
        if end != -1:
            break
    assert end != -1, "Could not locate the end of the §'Model routing policy' section"
    return readme_text[start:end]


def test_section_heading_no_longer_claims_verified(model_routing_section: str) -> None:
    """Invariant 1: the misleading '(verified 2026-04)' heading must be gone.

    R4 audit C1 explicitly flagged this string as "presents anticipated names
    as if verified". The honest replacement is "(cadence-anticipated, NOT
    vendor-verified)".
    """
    assert "(verified 2026-04)" not in model_routing_section, (
        "README still claims the model routing baseline is 'verified' — R4 finding "
        "C1 requires this heading to read 'cadence-anticipated, NOT vendor-verified'. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-1."
    )
    assert "cadence-anticipated" in model_routing_section.lower() or "Cadence-anticipated" in model_routing_section, (
        "Section heading must declare cadence-anticipated status. See docs/audit/ACTION_PLAN_R4.md §S0-1."
    )


def test_speculative_names_carry_disclaimer(model_routing_section: str) -> None:
    """Invariant 2: when speculative names appear, the section MUST also
    carry the canonical disclaimer phrases.

    If a future contributor swaps the speculative names for verified ones
    AND removes the disclaimer, this test passes (no speculative names →
    disclaimer not required). If they keep speculative names but drop
    the disclaimer, this test fails.
    """
    has_speculative = any(p.search(model_routing_section) for p in SPECULATIVE_PATTERNS)
    if not has_speculative:
        pytest.skip("No speculative model names in the section — disclaimer not required.")

    for phrase in REQUIRED_DISCLAIMER_PHRASES:
        assert phrase in model_routing_section, (
            f"Speculative model names are present in §'Model routing policy' but the required "
            f"disclaimer phrase {phrase!r} is missing. See docs/audit/ACTION_PLAN_R4.md §S0-1."
        )


def test_verification_subsection_lists_three_providers(model_routing_section: str) -> None:
    """Invariant 3: the verification subsection MUST link to all three
    provider dashboards (OpenAI, Anthropic, Google).

    Adopters need a single, unambiguous instruction: where to verify each
    name. A subsection that mentions only one provider would leave the
    other two cells of the table unverifiable.
    """
    has_speculative = any(p.search(model_routing_section) for p in SPECULATIVE_PATTERNS)
    if not has_speculative:
        pytest.skip("No speculative names — no verification subsection required.")

    assert "Verifying model availability before adoption" in model_routing_section, (
        "Section must include the 'Verifying model availability before adoption' subsection."
    )

    required_dashboards = [
        "platform.openai.com/docs/models",
        "docs.anthropic.com",
        "ai.google.dev",
    ]
    for dashboard in required_dashboards:
        assert dashboard in model_routing_section, (
            f"Verification subsection must link to {dashboard!r}. See docs/audit/ACTION_PLAN_R4.md §S0-1."
        )
