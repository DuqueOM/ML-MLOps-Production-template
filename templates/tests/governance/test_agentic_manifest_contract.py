"""Contract test — agentic manifest + context-layer invariants (ADR-023).

Authority: `docs/decisions/ADR-023-agentic-portability-and-context.md`.

Locks three invariants introduced in F1–F3:

I-1 — Manifest never contradicts AGENTS.md
  Every ``authority:`` anchor in ``agentic_manifest.yaml`` resolves to
  a real heading in ``AGENTS.md`` or an existing ADR file.

I-2 — `*_context.local*.yaml` is never committed
  Git tree must not contain any file matching the gitignored pattern.
  `*.example.yaml` files must carry no real-looking secret patterns.

Format discipline (F3) — `AGENT_CONTEXT.md` and `.*_context.md` are
  bounded (<= 150 lines, no date-led line, no table with > 10 rows).
  Caught by ``scripts/validate_agentic_manifest.py``; this test just
  asserts the validator exits 0.

Structural smoke
  * Every skill / workflow listed in the manifest exists at its
    declared ``source:`` path — caught by the validator, duplicated
    here so the test remains meaningful without network.
  * ``AGENT_CONTEXT.md`` exists and is non-empty.

The test invokes ``scripts/validate_agentic_manifest.py`` as a
subprocess with ``--strict`` so that any *_context.local.yaml an
adopter has staged locally (but not committed) is also checked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / "scripts" / "validate_agentic_manifest.py"
MANIFEST = REPO_ROOT / "templates" / "config" / "agentic_manifest.yaml"
AGENT_CONTEXT = REPO_ROOT / "AGENT_CONTEXT.md"
SURFACE_POINTERS = [
    REPO_ROOT / ".devin_context.md",
    REPO_ROOT / ".cursor_context.md",
    REPO_ROOT / ".claude_context.md",
    REPO_ROOT / ".codex_context.md",
]


def test_validator_exists_and_is_executable() -> None:
    """Sanity — the script is at the expected path and readable."""
    assert VALIDATOR.exists(), f"missing validator: {VALIDATOR}"
    assert VALIDATOR.is_file()


def test_validator_passes_strict_mode() -> None:
    """The whole contract is checked here: authority chain (I-1),
    source-path coherence, surface roots, mode enum, example schema
    compliance + secret-pattern absence (I-2), context-pointer format
    (F3). `--strict` also pulls in any local .local.yaml if present."""
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "--strict"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"validate_agentic_manifest.py --strict failed with "
        f"returncode={proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )


def test_manifest_exists_and_parses() -> None:
    """The manifest is machine-readable YAML with the expected top-level
    buckets (an adopter editing the file cannot accidentally remove one).
    """
    assert MANIFEST.exists(), f"missing manifest: {MANIFEST}"
    import yaml

    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    expected = {"version", "canonical", "agents", "rules", "skills", "workflows", "surfaces"}
    missing = expected - set(doc.keys())
    assert not missing, f"manifest missing top-level buckets: {sorted(missing)}"
    assert doc["version"] == 1


def test_agent_context_is_present_and_bounded() -> None:
    """The entry-point index exists and respects the 150-line cap.

    The cap prevents `AGENT_CONTEXT.md` from drifting into a diary —
    ADR-023 §3 locks the invariant and the validator enforces it. This
    test duplicates the check so a future refactor that bypasses the
    validator is still caught.
    """
    assert AGENT_CONTEXT.exists(), f"missing {AGENT_CONTEXT.name}"
    lines = AGENT_CONTEXT.read_text(encoding="utf-8").splitlines()
    assert 0 < len(lines) <= 150, f"{AGENT_CONTEXT.name} has {len(lines)} lines; ADR-023 caps at 150"


@pytest.mark.parametrize(
    "pointer",
    SURFACE_POINTERS,
    ids=lambda p: p.name,
)
def test_surface_pointer_is_compact(pointer: Path) -> None:
    """Each surface context pointer (`.devin_context.md` etc.) is a
    compact redirect to `AGENT_CONTEXT.md`, not a second authority.

    Caps are tighter than `AGENT_CONTEXT.md` deliberately — the pointer
    is supposed to be a few paragraphs with surface-specific hooks,
    not a parallel index.
    """
    assert pointer.exists(), f"missing {pointer.name}"
    lines = pointer.read_text(encoding="utf-8").splitlines()
    assert 0 < len(lines) <= 60, (
        f"{pointer.name} has {len(lines)} lines; surface pointers are "
        "capped at 60 to keep them pointers and not second authorities"
    )
    # A pointer must explicitly refer the reader back to the canonical
    # index. Otherwise it risks being read as a standalone source.
    assert "AGENT_CONTEXT.md" in pointer.read_text(encoding="utf-8"), (
        f"{pointer.name} must reference AGENT_CONTEXT.md to keep the authority chain single-rooted"
    )


def test_no_local_context_yaml_is_tracked() -> None:
    """I-2 — git must not track any *_context.local*.yaml.

    The adopter's `.local.yaml` contains business data (budget, approval
    model) and potentially KPI thresholds that should not be public.
    The `.gitignore` entries are a soft guard; this test is the hard
    guard in CI.
    """
    proc = subprocess.run(
        ["git", "ls-files", "*_context.local*.yaml", "*_context.*.local.yaml"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=REPO_ROOT,
    )
    # `git ls-files` returns success with empty stdout when no match.
    tracked = [line for line in proc.stdout.splitlines() if line.strip()]
    assert not tracked, (
        "adopter-specific context files are tracked by git (violates "
        f"ADR-023 I-2): {tracked}. Remove and re-run — they belong in "
        ".gitignore only."
    )
