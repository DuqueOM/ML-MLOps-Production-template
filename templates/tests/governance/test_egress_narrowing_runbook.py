"""Contract test — egress-narrowing runbook shipped (Sprint 3, R5-M3 follow-up).

Authority: VALIDATION_LOG Entry 005 §"Follow-ups recorded" +
ACTION_PLAN_R5 §R5-M3.

R5-M3 shipped per-non-dev-overlay NetworkPolicy patches but deferred
the adopter-facing runbook (`docs/runbooks/egress-narrowing.md`) to
Sprint 3. The patches' own comments reference the runbook. This test
enforces:

1. The runbook file exists.
2. It contains the four canonical sections (Procedure A, Procedure
   B.1/B.2/B.3) that operators are expected to follow.
3. No patch file still carries a `(TBD)` marker next to the runbook
   reference — if someone reverts the runbook, the patch comments
   would lie about its availability.

This catches two failure modes:
- The runbook is accidentally deleted (CI flags it immediately).
- A new overlay is added that references the runbook but never
  updates the `(TBD)` marker; the test scans all overlays for any
  `egress-narrowing.md (TBD)` occurrence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "egress-narrowing.md"
OVERLAY_ROOT = REPO_ROOT / "templates" / "service" / "k8s" / "overlays"


@pytest.fixture(scope="module")
def runbook_text() -> str:
    if not RUNBOOK.exists():
        pytest.fail(f"Runbook missing: {RUNBOOK.relative_to(REPO_ROOT)}")
    return RUNBOOK.read_text(encoding="utf-8")


def test_runbook_exists() -> None:
    assert RUNBOOK.exists(), (
        "docs/runbooks/egress-narrowing.md is required by VALIDATION_LOG "
        "Entry 005 (R5-M3 follow-up) and referenced from both GCP and "
        "AWS overlay patch files."
    )


@pytest.mark.parametrize(
    "section",
    [
        "Procedure A — AWS",
        "Procedure B — GCP",
        "B.1 — Private Google Access",
        "B.2 — Dedicated egress NAT CIDR",
        "B.3 — Layer-7 FQDN policy",
        "Update cadence",
        "When NOT to tighten",
        "Audit entry",
    ],
)
def test_runbook_has_canonical_sections(runbook_text: str, section: str) -> None:
    """Every canonical section must be present. If any is renamed, the
    overlay comments (`§A`, `§B.3`) become dead references.
    """
    assert section in runbook_text, (
        f"Runbook missing section: {section!r}. Overlay patch comments "
        "reference these section anchors (`§A`, `§B.3`) and would be "
        "dead links if the headings are renamed."
    )


def test_no_overlay_still_marks_runbook_as_tbd() -> None:
    """No patch file should carry the `(TBD)` marker now that the runbook
    ships. A stray TBD means someone added a new overlay without
    updating the wording to match reality.
    """
    offenders: list[str] = []
    for patch in OVERLAY_ROOT.glob("*/patch-networkpolicy.yaml"):
        body = patch.read_text(encoding="utf-8")
        if re.search(r"egress-narrowing\.md\s*\(TBD\)", body):
            offenders.append(str(patch.relative_to(REPO_ROOT)))
    assert not offenders, (
        "Overlay patches still say `egress-narrowing.md (TBD)` — the "
        "runbook now exists; update the wording to point to the correct "
        "section (`§A` for AWS, `§B.3` for GCP FQDN layering). "
        f"Offenders: {offenders}"
    )


def test_aws_overlays_reference_procedure_a() -> None:
    """AWS overlay patches should point operators at §A of the runbook.

    Prod patches are allowed to delegate to their staging sibling via
    a `See overlays/aws-staging/...` comment, because the two files
    share rationale and only the CIDR payload may diverge.
    """
    staging_body = (OVERLAY_ROOT / "aws-staging" / "patch-networkpolicy.yaml").read_text(encoding="utf-8")
    assert "egress-narrowing.md" in staging_body, (
        "aws-staging/patch-networkpolicy.yaml must reference the "
        "egress-narrowing runbook so operators find the AWS "
        "ip-ranges.json procedure."
    )
    prod_body = (OVERLAY_ROOT / "aws-prod" / "patch-networkpolicy.yaml").read_text(encoding="utf-8")
    assert "egress-narrowing.md" in prod_body or "aws-staging/patch-networkpolicy.yaml" in prod_body, (
        "aws-prod/patch-networkpolicy.yaml must either reference the "
        "runbook directly or delegate to overlays/aws-staging."
    )


def test_gcp_overlays_reference_fqdn_section() -> None:
    """GCP staging patch points operators at §B.3 (FQDN layering); the
    prod patch is allowed to delegate to staging via comment.
    """
    staging_body = (OVERLAY_ROOT / "gcp-staging" / "patch-networkpolicy.yaml").read_text(encoding="utf-8")
    assert "egress-narrowing.md" in staging_body, (
        "gcp-staging/patch-networkpolicy.yaml must reference the "
        "egress-narrowing runbook so operators find the FQDN "
        "layering procedure (§B.3)."
    )
    prod_body = (OVERLAY_ROOT / "gcp-prod" / "patch-networkpolicy.yaml").read_text(encoding="utf-8")
    assert "egress-narrowing.md" in prod_body or "gcp-staging/patch-networkpolicy.yaml" in prod_body, (
        "gcp-prod/patch-networkpolicy.yaml must either reference the "
        "runbook directly or delegate to overlays/gcp-staging."
    )
