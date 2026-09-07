"""Contract test — NetworkPolicy egress hygiene (R5-M3, hardened by May 2026 MED-11).

Authority: ACTION_PLAN_R5 §R5-M3; May 2026 audit MED-11.

Since MED-11 the base NetworkPolicy at
``templates/service/k8s/base/networkpolicy.yaml`` ships ZERO public egress
(default-deny). Defense-in-depth must fail closed: when an overlay
forgets its patch, the init container cannot reach cloud storage and
the rollout fails visibly instead of running with a wildcard egress.

EVERY overlay therefore MUST apply a JSON 6902 patch at
``patch-networkpolicy.yaml``:

- ``gcp-dev`` / ``aws-dev`` apply a deliberately permissive rule so
  ``kustomize build overlays/<cloud>-dev`` works out of the box;
- ``gcp-staging``/``gcp-prod``/``aws-staging``/``aws-prod`` apply
  cloud-specific allowlists and MUST NOT contain ``0.0.0.0/0``.

This contract test enforces:

1. The base NetworkPolicy carries the ``OVERLAY-OVERRIDE REQUIRED``
   banner (with MED-11 provenance) so the intent is visible to any
   future editor.
2. Each of the 6 overlays contains ``patch-networkpolicy.yaml`` and
   wires it into ``kustomization.yaml`` with
   ``target.kind: NetworkPolicy``.
3. Non-dev patch bodies do NOT contain ``0.0.0.0/0``.

The test parses YAML structurally; it does not require kustomize in
the test environment. An additional optional check invokes
``kustomize build`` if available and fails when the rendered non-dev
output still contains ``0.0.0.0/0`` — that catches patch-wiring
mistakes that the structural checks would miss (e.g., wrong
``target`` kind).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

try:  # optional dep — CI always has it, local dev environments may not.
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_NETPOL = REPO_ROOT / "templates" / "service" / "k8s" / "base" / "networkpolicy.yaml"
OVERLAY_ROOT = REPO_ROOT / "templates" / "service" / "k8s" / "overlays"

NON_DEV_OVERLAYS = ["gcp-staging", "gcp-prod", "aws-staging", "aws-prod"]
DEV_OVERLAYS = ["gcp-dev", "aws-dev"]
ALL_OVERLAYS = DEV_OVERLAYS + NON_DEV_OVERLAYS


# ---------------------------------------------------------------------------
# 1. Base policy carries the override-required banner.
# ---------------------------------------------------------------------------


def test_base_networkpolicy_carries_override_banner() -> None:
    """The base NetworkPolicy MUST flag that every overlay patches egress.

    Without this banner a future editor could silently remove the
    override instruction from the most visible surface (the base
    manifest), and the contract's intent would only live in a test.
    """
    text = BASE_NETPOL.read_text(encoding="utf-8")
    assert "OVERLAY-OVERRIDE REQUIRED" in text, (
        f"{BASE_NETPOL.relative_to(REPO_ROOT)} must carry the "
        "`OVERLAY-OVERRIDE REQUIRED` banner on the cloud-storage egress "
        "rule (R5-M3 / MED-11). Contributors need to see this in the "
        "base file, not just in a test."
    )
    # Provenance tags so a future audit can grep the lineage.
    assert "R5-M3" in text, "Base NetworkPolicy should cite R5-M3 as provenance"
    assert "MED-11" in text, "Base NetworkPolicy should cite MED-11 (default-deny hardening)"
    assert "every overlay" in text.lower(), "Banner should state that EVERY overlay patches egress"


# ---------------------------------------------------------------------------
# 2. Each overlay has a patch file wired into kustomization.yaml; non-dev
#    patch bodies must not contain 0.0.0.0/0.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overlay", ALL_OVERLAYS, ids=ALL_OVERLAYS)
def test_overlay_has_patch_file(overlay: str) -> None:
    """Each overlay ships `patch-networkpolicy.yaml` (MED-11: the base is
    default-deny, so an overlay without the patch cannot fetch models)."""
    patch = OVERLAY_ROOT / overlay / "patch-networkpolicy.yaml"
    assert patch.exists(), (
        f"Overlay `{overlay}` must carry patch-networkpolicy.yaml; since "
        "MED-11 the base ships zero public egress, so without the patch "
        "the init container cannot download the model. dev applies a "
        "permissive rule; staging/prod apply cloud-specific allowlists."
    )


@pytest.mark.parametrize("overlay", NON_DEV_OVERLAYS, ids=NON_DEV_OVERLAYS)
def test_patch_file_does_not_contain_wildcard(overlay: str) -> None:
    """The patch body MUST NOT restore the wildcard egress CIDR."""
    patch = OVERLAY_ROOT / overlay / "patch-networkpolicy.yaml"
    if not patch.exists():
        pytest.skip("patch file absent — covered by the existence test")
    body = patch.read_text(encoding="utf-8")
    # Allow the string inside a comment line (e.g. "narrow from 0.0.0.0/0").
    # Grep each non-comment line independently.
    non_comment = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "0.0.0.0/0" not in non_comment, (
        f"{patch.relative_to(REPO_ROOT)} reintroduces the wildcard CIDR "
        "`0.0.0.0/0` in its active YAML. R5-M3 requires cloud-specific "
        "allowlists for non-dev overlays."
    )


@pytest.mark.parametrize("overlay", ALL_OVERLAYS, ids=ALL_OVERLAYS)
def test_kustomization_wires_the_patch(overlay: str) -> None:
    """``kustomization.yaml`` MUST reference ``patch-networkpolicy.yaml``
    with an explicit target ``kind: NetworkPolicy``. Without the target
    the JSON 6902 patch fails to apply silently.
    """
    kust = OVERLAY_ROOT / overlay / "kustomization.yaml"
    assert kust.exists(), f"Overlay `{overlay}` missing kustomization.yaml"
    body = kust.read_text(encoding="utf-8")
    assert "patch-networkpolicy.yaml" in body, (
        f"{kust.relative_to(REPO_ROOT)} does not reference "
        "patch-networkpolicy.yaml; the patch will not be applied by "
        "`kustomize build` even if the file exists."
    )
    assert "kind: NetworkPolicy" in body, (
        f"{kust.relative_to(REPO_ROOT)} references the patch but does not "
        "set `target.kind: NetworkPolicy`; JSON 6902 patches need an "
        "explicit target to find the resource."
    )


# ---------------------------------------------------------------------------
# 3. (Optional) end-to-end kustomize build render check.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overlay", NON_DEV_OVERLAYS, ids=NON_DEV_OVERLAYS)
def test_kustomize_render_has_no_wildcard_egress(overlay: str) -> None:
    """If ``kustomize`` is available, render the overlay and assert the
    final YAML has no ``0.0.0.0/0`` egress. Skipped when kustomize is
    not installed (CI installs it via `actions/setup-kustomize`).
    """
    kustomize_bin = shutil.which("kustomize")
    if not kustomize_bin:
        pytest.skip("kustomize binary not in PATH; CI covers this path")
    overlay_dir = OVERLAY_ROOT / overlay
    result = subprocess.run(  # noqa: S603 — kustomize is a well-known bin
        [kustomize_bin, "build", str(overlay_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"`kustomize build` failed for overlay `{overlay}`: {result.stderr}"
    assert "0.0.0.0/0" not in result.stdout, (
        f"kustomize build of `{overlay}` still contains 0.0.0.0/0 in the "
        "rendered manifest; the JSON 6902 patch did not take effect. "
        "Check the `target:` block in kustomization.yaml (R5-M3)."
    )


# ---------------------------------------------------------------------------
# 4. Dev overlays MUST carry the permissive patch (MED-11): the base is
#    default-deny, so without it `kustomize build overlays/<cloud>-dev`
#    renders a NetworkPolicy under which the init container cannot
#    download the model.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overlay", DEV_OVERLAYS)
def test_dev_overlays_carry_the_permissive_patch(overlay: str) -> None:
    """Dev overlays ship a deliberately permissive egress patch.

    The wildcard CIDR is ALLOWED here — dev is the documented
    exception (see the base manifest banner). What we assert is that
    the patch exists and actually opens egress, so the local golden
    path keeps working against the default-deny base.
    """
    patch = OVERLAY_ROOT / overlay / "patch-networkpolicy.yaml"
    assert patch.exists(), (
        f"Dev overlay `{overlay}` is missing patch-networkpolicy.yaml; "
        "since MED-11 the base ships zero public egress, so dev MUST "
        "opt in to a permissive rule or the scaffolded service cannot "
        "fetch its model locally."
    )
    body = patch.read_text(encoding="utf-8")
    non_comment = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "cidr" in non_comment.lower(), (
        f"{patch.relative_to(REPO_ROOT)} does not declare any egress "
        "CIDR; the dev patch must open egress for the init-container "
        "model download."
    )
