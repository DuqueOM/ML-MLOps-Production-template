"""Smoke test for the scaffold fixture itself.

If this fails, every other policy test will fail. Keeps the fixture
under its own assertion so failure messages are unambiguous.
"""

from __future__ import annotations

from pathlib import Path


def test_scaffold_fixture_creates_service(scaffold_dir: Path) -> None:
    """new-service.sh must produce a non-empty service directory."""
    assert scaffold_dir.is_dir()
    assert any(scaffold_dir.iterdir()), f"{scaffold_dir} is empty"


def test_scaffold_has_canonical_structure(scaffold_dir: Path) -> None:
    """Sanity check: top-level dirs that every scaffold must contain."""
    for required in ["src", "k8s", "tests"]:
        assert (scaffold_dir / required).is_dir(), (
            f"Scaffolded service missing {required}/ directory"
        )


def test_scaffold_replaces_placeholders(scaffold_dir: Path) -> None:
    """No raw `{service}` / `{ServiceName}` placeholders survive scaffolding."""
    # Walk the scaffolded tree and ensure no file still contains the raw
    # placeholder tokens. Excludes the scripts/ directory (which contains
    # the scaffolder itself) and any .git directory.
    bad: list[str] = []
    for path in scaffold_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(scaffold_dir)
        # Skip:
        # - cache/VCS dirs (__pycache__, .git, .dvc cache)
        # - the scaffolder's own scripts/ dir (contains placeholder docs)
        # - binary/compiled files (.pyc, .so, .whl, images)
        if any(
            part in {".git", "__pycache__", ".dvc", "scripts", "node_modules"}
            for part in rel.parts
        ):
            continue
        if path.suffix in {".pyc", ".pyo", ".so", ".whl", ".png", ".jpg", ".ico"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for token in ("{ServiceName}", "{SERVICE}"):
            if token in text:
                bad.append(f"{rel}: contains {token!r}")

    assert not bad, "Unsubstituted placeholders found:\n  " + "\n  ".join(bad[:20])
