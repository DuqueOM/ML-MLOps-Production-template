#!/usr/bin/env python3
"""Validate every ``configs/quality_gates.yaml`` in the repo against the JSON
Schema at ``templates/service/configs/quality_gates.schema.json``.

ADR-015 PR-B1 — quality gates as an executable contract.

Why a JSON-Schema-based validator and not just Pydantic?
------------------------------------------------------
The Pydantic ``QualityGatesConfig`` model is the authoritative source of
truth, but importing it requires the full service package on ``sys.path``
(it lives at ``templates/service/src/{service}/config.py`` — a literal
placeholder directory). That works fine inside a scaffolded service but
is a heavy lift in a multi-service monorepo CI step that just wants to
say "no quality_gates.yaml is malformed before we waste 4 minutes
running pytest". A JSON Schema export is tool-agnostic:

- This script needs only stdlib + ``pyyaml`` + ``jsonschema``.
- Editors (VS Code's yaml-language-server, JetBrains) can pick up the
  ``# yaml-language-server: $schema=`` directive for inline validation.
- The schema lives next to the YAML in the template, so adopters keep
  them in lockstep.

Drift between the two is prevented by
``templates/service/tests/test_quality_gates_schema_sync.py`` which
confirms behavioural equivalence (every test payload accepted by one
must be accepted by the other, and vice-versa).

Usage
-----
::

    # Validate every quality_gates.yaml in the working tree.
    python scripts/validate_quality_gates.py

    # Validate a specific file (e.g. CI matrix).
    python scripts/validate_quality_gates.py path/to/configs/quality_gates.yaml

    # Override the schema path (e.g. for a downstream fork that has
    # extended the contract).
    python scripts/validate_quality_gates.py --schema custom.schema.json

Exit codes
----------
- ``0`` — all discovered files validate.
- ``1`` — at least one file failed validation, OR no files were found
  AND ``--require-at-least-one`` was passed (default behaviour: a repo
  with no ``quality_gates.yaml`` exits 0, since the template itself
  ships with one and a scaffolded repo always has one — the empty case
  is "we ran this in a non-template repo by mistake", which we surface
  as a warning, not a failure).
- ``2`` — internal error (schema missing, bad YAML).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable, Sequence

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

# Repo root = parent of ``scripts/``. We resolve relative to ``__file__``
# so the validator works whether invoked from the repo root, from CI, or
# from a scaffolded service via ``../scripts/validate_quality_gates.py``.
REPO_ROOT = Path(__file__).resolve().parent.parent

# The schema lives in two different places depending on whether this
# script is invoked from the template repo (where it sits next to
# every service template) or from a scaffolded service (where the
# `templates/` tree no longer exists — its contents have been
# extracted to the repo root). We probe both, template-repo location
# first because a scaffolded repo usually does NOT have a
# ``templates/`` directory at all.
_SCHEMA_CANDIDATES = (
    REPO_ROOT / "templates" / "service" / "configs" / "quality_gates.schema.json",
    REPO_ROOT / "configs" / "quality_gates.schema.json",
)


def _default_schema() -> Path:
    """Resolve the schema location for the current repo layout.

    Returns the first existing candidate, or — if neither exists yet —
    the template-repo path so the resulting error message ("schema
    not found at ...") points operators at the canonical home rather
    than a layout-specific guess.
    """
    for candidate in _SCHEMA_CANDIDATES:
        if candidate.exists():
            return candidate
    return _SCHEMA_CANDIDATES[0]


DEFAULT_SCHEMA = _default_schema()

# Directories to skip during auto-discovery. ``.git`` and ``node_modules``
# are obvious; ``site/`` is the mkdocs build output; venvs come in many
# names so we match the marker file ``pyvenv.cfg`` instead of names.
_PRUNE_DIR_NAMES = {".git", "node_modules", "site", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}

logger = logging.getLogger("validate_quality_gates")


def _is_venv(path: Path) -> bool:
    """Return True if ``path`` looks like a Python virtualenv root."""
    return (path / "pyvenv.cfg").exists()


def _discover(root: Path) -> list[Path]:
    """Find every ``configs/quality_gates.yaml`` under ``root``.

    Returns paths sorted for stable CI output.
    """
    found: list[Path] = []
    for candidate in root.rglob("quality_gates.yaml"):
        # Skip hidden / pruned / venv trees. Walk up the parents to detect.
        parts = set(candidate.parts)
        if parts & _PRUNE_DIR_NAMES:
            continue
        if any(_is_venv(p) for p in candidate.parents if p.is_dir()):
            continue
        # Only validate files under a directory literally called ``configs``
        # — this is the template convention. Anything else with this name
        # is almost certainly a fixture or test artefact and validating it
        # would produce false positives.
        if candidate.parent.name != "configs":
            continue
        found.append(candidate)
    return sorted(found)


def _load_yaml(path: Path) -> dict:
    """Load ``path`` as YAML, raising RuntimeError on failure."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{path}: invalid YAML — {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path}: top-level value must be a YAML mapping, got {type(data).__name__}")
    return data


def validate_file(path: Path, validator: Draft202012Validator) -> list[str]:
    """Validate one file. Returns a list of human-readable error strings.

    An empty list means the file passed.
    """
    try:
        data = _load_yaml(path)
    except RuntimeError as exc:
        return [str(exc)]

    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if not errors:
        return []

    out: list[str] = []
    for err in errors:
        loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{path}: {loc}: {err.message}")
    return out


def _build_validator(schema_path: Path) -> Draft202012Validator:
    if not schema_path.exists():
        raise FileNotFoundError(f"JSON Schema not found: {schema_path}")
    with schema_path.open("r", encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Specific YAML files to validate. If omitted, every quality_gates.yaml under the repo is discovered.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help=(
            "Path to the JSON Schema. Default is auto-detected: "
            "templates/service/configs/quality_gates.schema.json in the "
            "template repo, or configs/quality_gates.schema.json in a "
            "scaffolded service."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repo root for auto-discovery (default: parent of scripts/).",
    )
    parser.add_argument(
        "--require-at-least-one",
        action="store_true",
        help="Fail with exit code 1 if discovery finds zero files (use in CI to catch a missing scaffold step).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Emit DEBUG-level logs."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        validator = _build_validator(args.schema)
    except (FileNotFoundError, ValidationError, json.JSONDecodeError) as exc:
        print(f"FATAL: cannot load schema {args.schema}: {exc}", file=sys.stderr)
        return 2

    files: Iterable[Path]
    if args.files:
        files = [Path(f).resolve() for f in args.files]
    else:
        files = _discover(args.root.resolve())

    files = list(files)

    if not files:
        msg = f"No quality_gates.yaml files found under {args.root}"
        if args.require_at_least_one:
            print(f"ERROR: {msg}", file=sys.stderr)
            return 1
        print(f"WARN: {msg} (pass --require-at-least-one to make this fatal)")
        return 0

    failed = 0
    for f in files:
        errors = validate_file(f, validator)
        if errors:
            failed += 1
            for line in errors:
                print(f"FAIL: {line}", file=sys.stderr)
        else:
            logger.info("OK   %s", f.relative_to(args.root) if f.is_relative_to(args.root) else f)

    print(f"Validated {len(files)} file(s); {failed} failure(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
