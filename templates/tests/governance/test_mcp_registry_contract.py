"""Contract test — MCP portability registry (ADR-023 F4).

Authority: `docs/decisions/ADR-023-agentic-portability-and-context.md`.

Locks invariants of the cross-surface MCP layer:

I-3 — MCP install is never automatic
  Enforced structurally: `scripts/mcp_doctor.py` has no install
  entry point. This test asserts the script's CLI exposes only the
  three diagnostic modes (`check`, `doctor`, `render-docs`) and no
  hidden installer flag.

Cross-check coherence
  * Every `required_for` / `recommended_for` ref in
    `mcp_registry.yaml` resolves to a skill/workflow id present in
    `agentic_manifest.yaml`.
  * Every surface in the registry exists in
    `surface_capabilities.yaml` and vice versa.
  * Every MCP's `install_mode` covers every known surface.
  * Every skill listed in the manifest is supported (capability-wise)
    by every surface that claims it.

Renderer idempotence
  Running `mcp_doctor.py --mode render-docs` against an unchanged
  registry produces a no-op diff against `docs/agentic/mcp-portability.md`.
  Prevents drift between the YAML source and the human-readable doc.

Forbidden modes
  No `automatic`, `silent`, or `credentialed` strings appear in any
  install_mode entry of `mcp_registry.yaml` (ADR-023 §F4 §install-mode
  semantics § three modes deliberately absent).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR = REPO_ROOT / "scripts" / "mcp_doctor.py"
REGISTRY = REPO_ROOT / "templates" / "config" / "mcp_registry.yaml"
SURFACES = REPO_ROOT / "templates" / "config" / "surface_capabilities.yaml"
MANIFEST = REPO_ROOT / "templates" / "config" / "agentic_manifest.yaml"
DOCS = REPO_ROOT / "docs" / "agentic" / "mcp-portability.md"


def test_doctor_script_exists_and_is_executable() -> None:
    """Sanity — the CLI is at the documented path."""
    assert DOCTOR.exists(), f"missing doctor script: {DOCTOR}"
    assert DOCTOR.is_file()


def test_doctor_check_mode_passes() -> None:
    """The four cross-checks (skill_references / surface_symmetry /
    install_matrix / capability_support) all pass for the committed
    registry. Caught regressions in F4 development.
    """
    proc = subprocess.run(
        [sys.executable, str(DOCTOR), "--mode", "check"],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"mcp_doctor.py --mode check failed (rc={proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )


def test_doctor_has_only_diagnostic_modes() -> None:
    """I-3 — the doctor CLI exposes ONLY check / doctor / render-docs.

    A future PR adding `--install` or `--rotate` would silently break
    the invariant. This test asserts the help output does not contain
    those terms.
    """
    proc = subprocess.run(
        [sys.executable, str(DOCTOR), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0
    forbidden = ("install", "rotate", "credential", "deploy", "apply")
    for term in forbidden:
        assert term not in proc.stdout.lower(), (
            f"mcp_doctor.py --help mentions forbidden term {term!r}; diagnostics only (ADR-023 I-3)"
        )


def test_render_docs_is_idempotent(tmp_path: Path) -> None:
    """Running --mode render-docs against an unchanged registry leaves
    the docs file byte-identical.

    Uses a workspace copy so we never mutate the live tree even on
    test failure.
    """
    work = tmp_path / "repo"
    work.mkdir()
    for rel in (
        "scripts/mcp_doctor.py",
        "templates/config/mcp_registry.yaml",
        "templates/config/surface_capabilities.yaml",
        "templates/config/agentic_manifest.yaml",
        "docs/agentic/mcp-portability.md",
    ):
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, dst)
    before = (work / "docs/agentic/mcp-portability.md").read_bytes()
    proc = subprocess.run(
        [sys.executable, str(work / "scripts/mcp_doctor.py"), "--mode", "render-docs"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=work,
    )
    assert proc.returncode == 0, proc.stderr
    after = (work / "docs/agentic/mcp-portability.md").read_bytes()
    assert before == after, (
        "render-docs produced a diff against the committed file. "
        "Run `make mcp-render-docs` and commit the result so the "
        "generated section stays in sync with the registry."
    )


def test_no_forbidden_install_modes() -> None:
    """ADR-023 §F4 §install-mode semantics deliberately omits three
    modes: automatic, silent, credentialed. Their reintroduction
    would imply an agent-driven installer path — STOP-class concern.
    """
    raw = REGISTRY.read_text(encoding="utf-8")
    forbidden_tokens = ('"automatic"', '"silent"', '"credentialed"', "'automatic'", "'silent'", "'credentialed'")
    hits = [tok for tok in forbidden_tokens if tok in raw]
    assert not hits, (
        f"mcp_registry.yaml contains forbidden install_mode tokens: {hits}. "
        "These modes deliberately do not exist. If you genuinely need "
        "to relax I-3, bump ADR-023 first."
    )


@pytest.mark.parametrize(
    "mcp_id",
    ["github", "kubectl", "terraform", "prometheus", "playwright"],
)
def test_canonical_mcp_present(mcp_id: str) -> None:
    """The five MCPs documented in `AGENTS.md §MCP Integrations` are
    present in the registry. Catches an accidental deletion of one
    of them — they form the canonical baseline.
    """
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    assert mcp_id in (doc.get("mcps") or {}), (
        f"MCP {mcp_id!r} is documented in AGENTS.md but missing from templates/config/mcp_registry.yaml"
    )


def test_every_skill_in_manifest_has_capability_decision() -> None:
    """For every skill in `agentic_manifest.yaml` the doctor either
    finds an explicit capability override OR falls back to the
    documented default. This prevents a future skill from silently
    skipping the cross-check by being absent from both maps.
    """
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    surfaces = yaml.safe_load(SURFACES.read_text(encoding="utf-8"))
    overrides = surfaces.get("skill_capability_requirements", {}).get("overrides") or {}
    default_present = bool(surfaces.get("skill_capability_requirements", {}).get("default", {}).get("requires"))
    assert default_present, (
        "surface_capabilities.yaml must define a non-empty default requires list (read_file at minimum)"
    )
    skill_ids = [s["id"] for s in manifest.get("skills") or []]
    for sid in skill_ids:
        # Either the skill is in overrides, or it inherits the default —
        # both are acceptable; we just ensure the data structure does
        # not regress to a state where the doctor has no decision path.
        _ = overrides.get(sid)  # may be None — default applies
        assert isinstance(sid, str) and sid, "manifest contains a skill with no id"
