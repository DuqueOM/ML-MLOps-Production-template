"""Contract — every ``dvc.yaml`` stage command must be able to run.

Why this exists
---------------
``dvc.yaml`` declared four stages. **Three of them could not run**, and had not
been able to for as long as the file existed:

* ``validate`` invoked ``training/validate_data.py`` — a file that has never
  existed in this template.
* ``featurize`` invoked ``training/features.py`` — a real file, but one that
  defines ``FeatureEngineer`` and has no ``__main__`` and no argument parser.
  The stage would exit 0 having produced nothing, and DVC would then fail on
  the missing output, blaming the output.
* ``train`` invoked ``training/train.py`` as a plain script, which raises
  ``ImportError: attempted relative import with no known parent package``.

Only ``evaluate``'s shape was right, and it pointed at ``training/evaluate.py``
— also non-existent. So `dvc repro` had never completed in any generated
service, and nothing said so, because no test read this file at all.

What this checks
----------------
For each stage command:

1. **The target exists.** A module invocation resolves to a real module; a
   script invocation resolves to a real file.
2. **The invocation form is sound.** A script invocation of a file with
   relative imports is rejected — see
   ``test_python_entrypoint_invocations.py`` for why that is fatal.
3. **The target is actually callable that way.** A module run with ``-m`` needs
   an entrypoint; a bare class definition is not one. This is the check that
   would have caught ``featurize``, whose file existed and whose form was legal
   and which still could not do anything.

Static throughout: it does not run DVC, which needs data, a remote and a
configured cache.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[1]
DVC_YAML = SERVICE_ROOT / "dvc.yaml"

_SLUG_TOKEN = "{@ service_slug @}"
# The Copier token contains spaces, which would make any dotted-name pattern
# either swallow the stage's arguments or stop at the token. It is swapped for
# a space-free sentinel before matching and mapped back when building paths.
_SLUG_SENTINEL = "__SERVICE_SLUG__"
_MODULE_CALL = re.compile(r"python[0-9.]*\s+-m\s+(?P<mod>[\w.]+)")
_SCRIPT_CALL = re.compile(r"python[0-9.]*\s+(?P<path>(?!-)[\w./]+\.py)")
_RELATIVE_IMPORT = re.compile(r"^\s*from\s+\.", re.M)


def _slug() -> str | None:
    src = SERVICE_ROOT / "src"
    if not src.is_dir():
        return None
    pkgs = [d.name for d in src.iterdir() if d.is_dir() and not d.name.startswith("__")]
    return pkgs[0] if len(pkgs) == 1 else None


def _stages() -> list[tuple[str, str]]:
    if not DVC_YAML.is_file():
        return []
    # The file is a Copier template; the slug token is swapped for a space-free
    # sentinel so the command patterns below can match dotted names.
    text = DVC_YAML.read_text(encoding="utf-8").replace(_SLUG_TOKEN, _SLUG_SENTINEL)
    doc = yaml.safe_load(text) or {}
    return [(name, " ".join(str(body.get("cmd", "")).split())) for name, body in (doc.get("stages") or {}).items()]


def _module_to_path(dotted: str) -> Path | None:
    """`src.pkg.mod` -> the file on disk, or None if it does not resolve."""
    slug = _slug()
    parts = [slug if (p == _SLUG_SENTINEL and slug) else p for p in dotted.strip().split(".")]
    direct = SERVICE_ROOT.joinpath(*parts).with_suffix(".py")
    if direct.is_file():
        return direct
    package = SERVICE_ROOT.joinpath(*parts) / "__init__.py"
    return package if package.is_file() else None


def _has_entrypoint(path: Path) -> bool:
    """True when the file can do something when executed, not merely imported."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # `if __name__ == "__main__":`
        if isinstance(node, ast.If):
            src = ast.unparse(node.test)
            if "__name__" in src and "__main__" in src:
                return True
    return False


STAGES = _stages()


def test_the_pipeline_was_actually_read() -> None:
    """Zero stages parses as a pass; make it a failure instead."""
    assert DVC_YAML.is_file(), f"{DVC_YAML} is missing"
    assert STAGES, "dvc.yaml declares no stages, so every assertion below would be vacuous"


@pytest.mark.parametrize(("stage", "cmd"), STAGES, ids=[s for s, _ in STAGES] or ["none"])
def test_stage_command_resolves_and_is_callable(stage: str, cmd: str) -> None:
    assert cmd, f"stage '{stage}' declares no cmd"

    module_match = _MODULE_CALL.search(cmd)
    script_match = _SCRIPT_CALL.search(cmd)
    assert module_match or script_match, (
        f"stage '{stage}' runs no Python entrypoint this test can check: {cmd!r}. "
        f"If it is deliberately a shell stage, it does not belong in this parametrize."
    )

    if module_match:
        dotted = module_match.group("mod").strip()
        target = _module_to_path(dotted)
        assert target is not None, (
            f"stage '{stage}' runs `python -m {dotted}`, which resolves to no file. "
            f"`dvc repro` fails with ModuleNotFoundError."
        )
    else:
        slug = _slug()
        raw = script_match.group("path").replace(_SLUG_SENTINEL, slug or _SLUG_SENTINEL)
        target = SERVICE_ROOT / raw
        assert target.is_file(), (
            f"stage '{stage}' runs `{raw}`, which does not exist. Three of this file's "
            f"four original stages failed exactly here."
        )
        match = _RELATIVE_IMPORT.search(target.read_text(encoding="utf-8"))
        assert match is None, (
            f"stage '{stage}' runs `{raw}` as a script, but it uses a relative import — "
            f"ImportError before any logic runs. Use "
            f"`python -m {target.relative_to(SERVICE_ROOT).with_suffix('').as_posix().replace('/', '.')}`."
        )

    assert _has_entrypoint(target), (
        f"stage '{stage}' invokes `{target.relative_to(SERVICE_ROOT)}`, which has no "
        f'`if __name__ == "__main__"` block. Running it defines its classes and exits 0 '
        f"having produced nothing; DVC then fails on the missing output and blames the "
        f"output. This is what the old `featurize` stage did — the file existed, the "
        f"invocation was legal, and the stage could still never work."
    )
