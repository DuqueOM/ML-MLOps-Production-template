"""Shared fixture: scaffolds a service ONCE per session for policy tests.

Scaffolding takes ~5-10 seconds and produces ~200 files. Running it per
test would dominate the suite runtime. Session scope is correct because
the policy tests never mutate the scaffolded output.

The fixture also exposes helpers to read scaffolded files efficiently
(file_text, glob_files, json_load, yaml_load_all) so individual tests
stay declarative.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up from this file to find the actual repo root.

    The scaffolder lives at `templates/scripts/new-service.sh` (NOT at
    `scripts/new-service.sh`), so we anchor on the templates/ directory's
    parent. Anchoring on templates/scripts directly would return the
    templates/ dir itself which then breaks `templates/templates` copy.
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if (ancestor / "templates" / "scripts" / "new-service.sh").is_file():
            return ancestor
    raise RuntimeError(
        "Could not locate templates/scripts/new-service.sh from this file's path"
    )


REPO_ROOT = _find_repo_root()


@pytest.fixture(scope="session")
def scaffold_dir() -> Iterator[Path]:
    """Run new-service.sh into an isolated tmpdir; yield service path.

    The fixture mirrors what `scripts/test_scaffold.sh` does:
    - copies `templates/` (and `common_utils/` if present) to a tmpdir
    - runs the scaffolder with a fixed slug (`policy_svc` / `PolicySvc`)
    - yields the path to the scaffolded service directory
    - cleans up on session teardown unless KEEP_SCAFFOLD=1 in the env

    Set KEEP_SCAFFOLD=1 to preserve the tmpdir for post-mortem inspection.
    """
    keep = os.environ.get("KEEP_SCAFFOLD", "") == "1"
    tmp_root = Path(tempfile.mkdtemp(prefix="mlops-policy-scaffold-"))

    try:
        # The scaffolder resolves PROJECT_ROOT as $TEMPLATE_ROOT/.. — so we
        # place templates/ inside tmp_root and the service lands beside it.
        shutil.copytree(REPO_ROOT / "templates", tmp_root / "templates")
        if (REPO_ROOT / "common_utils").is_dir():
            shutil.copytree(REPO_ROOT / "common_utils", tmp_root / "common_utils")

        scaffolder = tmp_root / "templates" / "scripts" / "new-service.sh"
        if not scaffolder.is_file():
            pytest.fail(f"Scaffolder not found at {scaffolder}")

        result = subprocess.run(
            ["bash", str(scaffolder), "PolicySvc", "policy_svc"],
            cwd=tmp_root,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            pytest.fail(
                "new-service.sh failed during policy fixture setup:\n"
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
            )

        # The scaffolder writes the service into a sibling directory of
        # templates/, named after the SERVICE_NAME (PascalCase).
        candidates = [
            tmp_root / "PolicySvc",
            tmp_root / "policy_svc",
        ]
        service_dir = next((c for c in candidates if c.is_dir()), None)
        if service_dir is None:
            pytest.fail(
                f"Scaffolder claimed success but no service directory found "
                f"under {tmp_root}. Contents: {list(tmp_root.iterdir())}"
            )

        yield service_dir

    finally:
        if not keep:
            shutil.rmtree(tmp_root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Convenience helpers exposed as fixtures so individual D-XX tests stay short.
# ---------------------------------------------------------------------------


def _resolve(scaffold_dir: Path, path_or_rel) -> Path:
    """Accept either an absolute Path or a string relative to scaffold_dir."""
    if isinstance(path_or_rel, Path) and path_or_rel.is_absolute():
        return path_or_rel
    return scaffold_dir / str(path_or_rel)


@pytest.fixture
def file_text(scaffold_dir: Path):
    """Return a callable that reads a file (relative str or absolute Path)."""

    def _read(path_or_rel) -> str:
        full = _resolve(scaffold_dir, path_or_rel)
        if not full.is_file():
            return ""
        return full.read_text(encoding="utf-8", errors="ignore")

    return _read


@pytest.fixture
def glob_files(scaffold_dir: Path):
    """Return a callable that globs files under the scaffold root.

    Uses `rglob` when the pattern contains `**` so callers can write
    natural patterns like `k8s/**/hpa*.yaml`.
    """

    def _glob(pattern: str) -> list[Path]:
        if "**" in pattern:
            # Path.glob supports ** but only with recursive=True on Python 3.13+
            # for non-top-level patterns — use rglob from the nearest anchor.
            return sorted(scaffold_dir.glob(pattern))
        return sorted(scaffold_dir.glob(pattern))

    return _glob


@pytest.fixture
def yaml_load_all(scaffold_dir: Path):
    """Return a callable that parses all docs from a YAML file.

    Accepts a relative string (from scaffold_dir) or an absolute Path.
    """
    yaml = pytest.importorskip("yaml")

    def _load(path_or_rel) -> list:
        full = _resolve(scaffold_dir, path_or_rel)
        if not full.is_file():
            return []
        return [d for d in yaml.safe_load_all(full.read_text()) if d is not None]

    return _load


@pytest.fixture
def json_load(scaffold_dir: Path):
    """Return a callable that parses JSON from a path (rel str or absolute)."""

    def _load(path_or_rel):
        full = _resolve(scaffold_dir, path_or_rel)
        if not full.is_file():
            return None
        return json.loads(full.read_text())

    return _load
