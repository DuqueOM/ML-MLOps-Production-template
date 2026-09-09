"""Contract — a Makefile target must invoke Python code in a way that can work.

Why this exists
---------------
Three targets ran the trainer as a plain script::

    python src/<slug>/training/train.py --data <path>

``train.py`` begins with ``from ..config import QualityGatesConfig``. Running a
file that lives inside a package as a top-level script gives it no package
context, so Python raises before the first line of logic::

    ImportError: attempted relative import with no known parent package

``make train`` therefore could not work in any generated service, and had not
been able to for as long as those imports have been relative. Nothing noticed,
because no test ever asked whether a Makefile recipe was runnable — the shipped
suite tests the code the recipes call, never the calling.

What this checks
----------------
For every Makefile recipe that runs a repository Python file, whichever form it
uses must be consistent with that file's imports:

* a module invocation (``python -m pkg.mod``) always works;
* a script invocation (``python path/to/file.py``) works only if the file has
  no relative imports.

The check is static — it reads the recipe and the target file. It does not run
training, which needs data, an EDA artefact directory and a configured split.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = SERVICE_ROOT / "Makefile"

# `python path/to/file.py` — a script invocation of a repo file.
_SCRIPT_CALL = re.compile(r"python[0-9.]*\s+(?P<path>(?!-)[\w./$()-]+\.py)")
# A relative import at the start of a line: `from .x` / `from ..x`.
_RELATIVE_IMPORT = re.compile(r"^\s*from\s+\.", re.M)
# Make variables we can resolve well enough to find the file on disk.
_MAKE_VARS = {"$(SERVICE_SLUG)": None}


def _resolve(raw: str) -> Path | None:
    """Map a recipe path to a file on disk, expanding the slug variable."""
    if "$(" in raw:
        # In this repository the rendered slug is the single directory under
        # `src/`, so it can be discovered rather than assumed.
        src = SERVICE_ROOT / "src"
        pkgs = [d.name for d in src.iterdir() if d.is_dir() and not d.name.startswith("__")] if src.is_dir() else []
        if len(pkgs) != 1:
            return None
        raw = raw.replace("$(SERVICE_SLUG)", pkgs[0])
    candidate = SERVICE_ROOT / raw
    return candidate if candidate.is_file() else None


def _script_invocations() -> list[tuple[int, str, Path]]:
    if not MAKEFILE.is_file():
        return []
    out = []
    for lineno, line in enumerate(MAKEFILE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("\t"):
            continue  # not a recipe line
        for match in _SCRIPT_CALL.finditer(line):
            resolved = _resolve(match.group("path"))
            if resolved is not None:
                out.append((lineno, line.strip(), resolved))
    return out


INVOCATIONS = _script_invocations()
_IDS = [f"Makefile:{n}" for n, _, _ in INVOCATIONS]


def test_makefile_exists() -> None:
    assert MAKEFILE.is_file(), f"{MAKEFILE} is missing"


@pytest.mark.parametrize(("lineno", "recipe", "target"), INVOCATIONS, ids=_IDS or ["none"])
def test_script_invocation_has_no_relative_imports(lineno: int, recipe: str, target: Path) -> None:
    """A file run as a script cannot use relative imports."""
    source = target.read_text(encoding="utf-8")
    match = _RELATIVE_IMPORT.search(source)
    assert match is None, (
        f"Makefile:{lineno} runs `{target.relative_to(SERVICE_ROOT)}` as a script, but that "
        f"file uses a relative import ({source[match.start() : match.end() + 30].strip()!r}). "
        f"Python gives a script no package context, so this recipe raises "
        f"ImportError before any of its logic runs. Invoke it as a module instead: "
        f"`python -m {target.relative_to(SERVICE_ROOT).with_suffix('').as_posix().replace('/', '.')}`."
    )
