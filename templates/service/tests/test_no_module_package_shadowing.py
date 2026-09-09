"""Contract — no ``X.py`` may sit beside an ``X/`` package in the same parent.

Why this exists
---------------
``src/<slug>/`` contained **both** ``evaluation.py`` (224 lines, defining
``ModelEvaluator``) and ``evaluation/`` (a package whose ``__init__.py`` held
only a docstring). A package always wins over a module of the same name, so::

    <slug>.evaluation  ->  <slug>/evaluation/__init__.py

``cli.py`` opens with ``from .evaluation import ModelEvaluator`` and therefore
raised ``ImportError: cannot import name 'ModelEvaluator'`` on import. The
whole CLI was dead, and every line of ``evaluation.py`` was unreachable.

Nothing caught it because nothing was looking. Python does not warn — this is
ordinary, specified import behaviour, and the loser is simply never consulted.
The collision arrived when ``evaluation/champion_challenger.py`` was added next
to a module that was already there; both files are individually valid, both
import fine on their own, and the linters are silent.

What this checks
----------------
The whole ``src/`` tree, not the one pair that broke. A guard scoped to
``evaluation`` would be a control narrower than its surface — the same defect
one level up.

Adding ``__init__.py`` to a directory whose sibling module has the same stem is
a two-file change nobody reads as dangerous, which is exactly why it needs a
gate rather than a convention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOTS = ("src", "app", "common_utils", "eda")


def _shadowed() -> list[tuple[Path, Path]]:
    """Every (module, package) pair that collide on the same dotted name."""
    collisions: list[tuple[Path, Path]] = []
    for root_name in SEARCH_ROOTS:
        root = SERVICE_ROOT / root_name
        if not root.is_dir():
            continue
        for directory in [root, *(p for p in root.rglob("*") if p.is_dir())]:
            if "__pycache__" in directory.parts:
                continue
            for child in directory.iterdir():
                if not child.is_dir() or child.name.startswith((".", "__")):
                    continue
                sibling = directory / f"{child.name}.py"
                if sibling.is_file():
                    collisions.append((sibling, child))
    return collisions


def _searched_dirs() -> int:
    total = 0
    for root_name in SEARCH_ROOTS:
        root = SERVICE_ROOT / root_name
        if root.is_dir():
            total += 1 + sum(1 for p in root.rglob("*") if p.is_dir() and "__pycache__" not in p.parts)
    return total


SHADOWED = _shadowed()


def test_the_tree_was_actually_searched() -> None:
    """An empty search reports as a pass; make a vacuous run fail instead."""
    assert _searched_dirs() >= 4, (
        f"only {_searched_dirs()} directories searched under {SEARCH_ROOTS} — this module "
        f"would pass without examining anything, which is the failure mode it exists to catch"
    )


@pytest.mark.parametrize(
    ("module", "package"),
    SHADOWED,
    ids=[f"{m.parent.name}/{m.name}" for m, _ in SHADOWED] or ["none"],
)
def test_module_is_not_shadowed_by_a_package(module: Path, package: Path) -> None:
    dotted = module.relative_to(SERVICE_ROOT).with_suffix("").as_posix().replace("/", ".")
    pytest.fail(
        f"{module.relative_to(SERVICE_ROOT)} and {package.relative_to(SERVICE_ROOT)}/ "
        f"claim the same import name '{dotted}'. Python resolves it to the PACKAGE, so "
        f"every name defined in the module is unreachable and any "
        f"`from ... import <name>` against it raises ImportError at import time — "
        f"silently, because this is specified behaviour and nothing warns.\n"
        f"Fix: move the module inside the package (e.g. "
        f"{package.relative_to(SERVICE_ROOT)}/{module.stem if module.stem != package.name else 'metrics'}.py) "
        f"and re-export its public names from {package.relative_to(SERVICE_ROOT)}/__init__.py."
    )
