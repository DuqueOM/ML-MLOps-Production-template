"""Contract — anything that invokes a repository Python file must invoke it a way that can work.

Why this exists
---------------
Three Makefile targets ran the trainer as a plain script::

    python src/<slug>/training/train.py --data <path>

``train.py`` begins with ``from ..config import QualityGatesConfig``. Running a
file that lives inside a package as a top-level script gives it no package
context, so Python raises before the first line of logic::

    ImportError: attempted relative import with no known parent package

``make train`` therefore could not work in any generated service, and had not
been able to for as long as those imports have been relative. Nothing noticed,
because no test ever asked whether a recipe was runnable — the shipped suite
tests the code the recipes call, never the calling.

Why this file is no longer about the Makefile
---------------------------------------------
The first version of this guard read the Makefile and nothing else. The
Makefile was fixed and the guard went green, and the identical broken
invocation stayed live in **eight other places**, including the two that
matter most:

* ``.github/workflows/retrain-service.yml`` — the shipped retraining workflow.
  The *same file* already used the module form four steps later, so one
  automated retrain would have died on the script form and the evidence of the
  correct form was sitting in the same YAML.
* ``dvc.yaml`` — the ``train`` stage of the data pipeline.
* ``README.md`` and ``docs/service-readme-template.md`` — the first command a
  new adopter runs.
* the ``model-retrain`` skill and the ``retrain`` workflow, in each of their
  three agentic copies.

A guard scoped to the Makefile while the defect lives in workflows, pipeline
definitions and documentation is a control narrower than its surface — the
same shape as the bug it was written to catch. This module now reads every
shipped surface that can invoke a repository Python file.

What this checks
----------------
For every invocation of a repository Python file found in any scanned surface,
whichever form it uses must be consistent with that file's imports:

* a module invocation (``python -m pkg.mod``) always works;
* a script invocation (``python path/to/file.py``) works only if the target
  file has no relative imports.

The check is static — it reads the invocation and the target file. It does not
run training, which needs data, an EDA artefact directory and a configured
split.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]

# Every shipped surface that can tell a human or a runner to execute a file
# here. Documentation counts: a README command that raises ImportError is a
# defect the adopter meets before anything else.
SCANNED_GLOBS = (
    "Makefile",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "dvc.yaml",
    "README.md",
    "docs/*.md",
    "docs/**/*.md",
    "agentic/skills/**/*.md",
    "agentic/workflows/*.md",
    "scripts/*.sh",
)

# `python path/to/file.py` — a script invocation of a repo file. `python -m x`
# is not matched, because it is always valid.
_SCRIPT_CALL = re.compile(r"python[0-9.]*\s+(?P<path>(?!-)[\w./${}()@-]+\.py)")
# A relative import at the start of a line: `from .x` / `from ..x`.
_RELATIVE_IMPORT = re.compile(r"^\s*from\s+\.", re.M)

# Placeholders that stand in for the rendered package name across the surfaces
# above: Make variables, GitHub Actions expressions, Copier tokens, shell vars
# and the skill docs' `{service}`.
_SLUG_PLACEHOLDERS = (
    "$(SERVICE_SLUG)",
    "${{ env.SERVICE_SLUG }}",
    "${SERVICE_SLUG}",
    "{@ service_slug @}",
    "{service}",
)


def _package_name() -> str | None:
    """The single directory under ``src/`` — discovered, never assumed."""
    src = SERVICE_ROOT / "src"
    if not src.is_dir():
        return None
    pkgs = [d.name for d in src.iterdir() if d.is_dir() and not d.name.startswith("__")]
    return pkgs[0] if len(pkgs) == 1 else None


def _resolve(raw: str) -> Path | None:
    """Map an invocation path to a file on disk, expanding any slug placeholder.

    Existence on disk is the only test of whether the expansion worked. An
    earlier version bailed out when the expanded path still contained ``$`` or
    ``{``, which looked like prudence and was a hole: in the *template*
    repository the package directory is literally named ``{@ service_slug @}``,
    so every Copier-token invocation expanded to itself and was then discarded
    as "unresolved". `dvc.yaml` was scanned and silently skipped, and the
    negative control for this guard passed when it should have failed. A path
    that does not resolve is simply not checked; one that resolves is.
    """
    slug = _package_name()
    for token in _SLUG_PLACEHOLDERS:
        if token in raw and slug is not None:
            raw = raw.replace(token, slug)
    candidate = (SERVICE_ROOT / raw).resolve()
    try:
        candidate.relative_to(SERVICE_ROOT.resolve())
    except ValueError:
        return None  # points outside the service
    return candidate if candidate.is_file() else None


def _scanned_files() -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in SCANNED_GLOBS:
        for path in SERVICE_ROOT.glob(pattern):
            if path.is_file():
                seen.setdefault(path, None)
    return sorted(seen)


SCANNED = _scanned_files()


def _script_invocations() -> list[tuple[Path, int, str, Path]]:
    out: list[tuple[Path, int, str, Path]] = []
    for path in SCANNED:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - defensive
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in _SCRIPT_CALL.finditer(line):
                resolved = _resolve(match.group("path"))
                if resolved is not None:
                    out.append((path, lineno, line.strip(), resolved))
    return out


INVOCATIONS = _script_invocations()
_IDS = [f"{p.relative_to(SERVICE_ROOT)}:{n}" for p, n, _, _ in INVOCATIONS]


def test_the_surface_was_actually_scanned() -> None:
    """A glob that matches nothing reports as a pass. Make that a failure.

    This is the assertion the first version of this guard did not have, and it
    is the one that would have said out loud that the Makefile was the only
    file being read.
    """
    assert len(SCANNED) >= 10, (
        f"only {len(SCANNED)} shipped file(s) matched {SCANNED_GLOBS}. This module would "
        f"pass while examining almost nothing — the exact failure mode it exists to catch."
    )
    assert (SERVICE_ROOT / "Makefile") in SCANNED, "the Makefile itself dropped out of the scan"


@pytest.mark.parametrize(
    ("source", "lineno", "invocation", "target"),
    INVOCATIONS,
    ids=_IDS or ["none"],
)
def test_script_invocation_has_no_relative_imports(source: Path, lineno: int, invocation: str, target: Path) -> None:
    """A file run as a script cannot use relative imports."""
    rel_source = source.relative_to(SERVICE_ROOT)
    rel_target = target.relative_to(SERVICE_ROOT)
    match = _RELATIVE_IMPORT.search(target.read_text(encoding="utf-8"))
    assert match is None, (
        f"{rel_source}:{lineno} runs `{rel_target}` as a script, but that file uses a "
        f"relative import. Python gives a script no package context, so this raises "
        f"ImportError before any of its logic runs.\n"
        f"  invocation: {invocation}\n"
        f"  fix:        python -m {rel_target.with_suffix('').as_posix().replace('/', '.')}"
    )
