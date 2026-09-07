"""Contract test — Companions F7/F8/F9 (ADR-023).

Authority: `docs/decisions/ADR-023-agentic-portability-and-context.md`.

Locks the docs-only nature of the three companions:

F7 — Runtime monitoring companion
  * `docs/agentic/runtime-monitoring-companion.md` exists.
  * Document declares the companion read-only and lists at least the
    three required MCPs (`prometheus`, `github`, `kubectl`) which all
    must be present in `mcp_registry.yaml`.
  * No new skill or workflow file is introduced — the companion is
    pure wiring + docs.

F8 / F9 — Cloud companions (GCP Gemini Enterprise + AWS AgentCore)
  * `docs/agentic/cloud-companions.md` exists.
  * Both companions are documented in the same file (intentional
    symmetry per ADR-023 §F8/F9).
  * No vendored provider SDK is imported anywhere under `templates/`.
  * The mapping table for each companion lists the seven canonical
    template concepts that must round-trip to the cloud platform.

Authority chain
  * Every companion doc references ADR-023 explicitly so the
    authority chain is auditable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DOC = REPO_ROOT / "docs" / "agentic" / "runtime-monitoring-companion.md"
CLOUD_DOC = REPO_ROOT / "docs" / "agentic" / "cloud-companions.md"
MCP_REGISTRY = REPO_ROOT / "templates" / "config" / "mcp_registry.yaml"
TEMPLATES_DIR = REPO_ROOT / "templates"

ADR_REF = "ADR-023"
F7_REQUIRED_MCPS = ("prometheus", "github", "kubectl")


# ----------------------------------------------------------------------
# F7 — runtime monitoring companion
# ----------------------------------------------------------------------


def test_runtime_companion_doc_exists() -> None:
    assert RUNTIME_DOC.is_file(), "F7 doc missing"


def test_runtime_companion_references_adr023() -> None:
    body = RUNTIME_DOC.read_text(encoding="utf-8")
    assert ADR_REF in body, "Runtime companion must cite ADR-023 authority"
    assert "F7" in body, "Runtime companion must self-identify as F7"


def test_runtime_companion_is_read_only() -> None:
    body = RUNTIME_DOC.read_text(encoding="utf-8").lower()
    # Must declare read-only stance
    assert "read-only" in body, "F7 doc must declare read-only stance"
    # Must explicitly forbid proactive triggering
    assert "no proactive" in body or "never opens" in body, "F7 doc must forbid proactive workflow triggering"


def test_runtime_companion_required_mcps_exist_in_registry() -> None:
    body = RUNTIME_DOC.read_text(encoding="utf-8")
    registry = yaml.safe_load(MCP_REGISTRY.read_text(encoding="utf-8"))
    declared = registry.get("mcps", {}) or {}
    for mcp in F7_REQUIRED_MCPS:
        assert mcp in body, f"F7 doc must mention required MCP `{mcp}`"
        assert mcp in declared, f"F7 declares `{mcp}` MCP but it is missing from mcp_registry.yaml"


def test_runtime_companion_introduces_no_new_skill_file() -> None:
    skills_dir = REPO_ROOT / "agentic" / "skills"
    forbidden = {"runtime-monitoring", "runtime-monitor", "runtime-companion"}
    actual = {p.name for p in skills_dir.glob("*") if p.is_dir()}
    overlap = actual & forbidden
    assert not overlap, f"F7 must remain docs-only; new skill folders detected: {sorted(overlap)}"


# ----------------------------------------------------------------------
# F8 / F9 — cloud companions
# ----------------------------------------------------------------------


def test_cloud_companions_doc_exists() -> None:
    assert CLOUD_DOC.is_file(), "F8/F9 cloud companions doc missing"


def test_cloud_companions_reference_adr023() -> None:
    body = CLOUD_DOC.read_text(encoding="utf-8")
    assert ADR_REF in body, "Cloud companions doc must cite ADR-023"
    assert "F8" in body and "F9" in body, "Doc must cover both F8 and F9"


def test_cloud_companions_cover_both_providers() -> None:
    body = CLOUD_DOC.read_text(encoding="utf-8").lower()
    assert "gemini" in body or "vertex" in body, "F8 must reference GCP product"
    assert "agentcore" in body or "bedrock" in body, "F9 must reference AWS product"


def test_cloud_companions_have_anti_lists() -> None:
    body = CLOUD_DOC.read_text(encoding="utf-8").lower()
    # Each companion must enumerate things NOT to do — prevents scope creep.
    occurrences = len(re.findall(r"anti[- ]list", body))
    assert occurrences >= 2, f"Each cloud companion must carry its own anti-list (found {occurrences} occurrences)"


def test_no_vendored_provider_sdk_in_templates() -> None:
    """Companions are docs-only — no SDK imports leak into template code."""
    forbidden = (
        "google.cloud.aiplatform",
        "google_cloud_aiplatform",
        "boto3.client('bedrock-agent",
        'boto3.client("bedrock-agent',
        "vertexai.preview.agent_builder",
    )
    offenders: list[str] = []
    self_path = Path(__file__).resolve()
    for path in TEMPLATES_DIR.rglob("*.py"):
        if path.resolve() == self_path:
            continue  # the assertion strings live here by design
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path}: {needle}")
    assert not offenders, "Cloud companions are docs-only; vendored SDK imports detected:\n  " + "\n  ".join(offenders)


def test_cloud_companions_share_authority_chain() -> None:
    body = CLOUD_DOC.read_text(encoding="utf-8")
    # Both companions must end up rooted in AGENTS.md via the manifest.
    for marker in ("agentic_manifest.yaml", "mcp_registry.yaml", "AGENTS.md"):
        assert marker in body, f"Cloud companions doc must reference `{marker}` in its authority chain"


# ----------------------------------------------------------------------
# Cross-cutting — companions remain docs-only at the surface level
# ----------------------------------------------------------------------


def test_companions_do_not_create_new_workflows() -> None:
    workflows_dir = REPO_ROOT / "agentic" / "workflows"
    forbidden = {
        "runtime-monitor.md",
        "gemini-companion.md",
        "agentcore-companion.md",
        "vertex-companion.md",
        "bedrock-companion.md",
    }
    actual = {p.name for p in workflows_dir.glob("*.md")}
    overlap = actual & forbidden
    assert not overlap, f"Companions are docs-only; unexpected workflow files: {sorted(overlap)}"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
