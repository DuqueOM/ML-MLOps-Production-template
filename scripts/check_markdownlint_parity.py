#!/usr/bin/env python3
"""Contract: the template lints itself by the same rules it ships.

Why this exists
---------------
There are two markdownlint configurations: this repository's
``.markdownlint-cli2.jsonc`` and the one shipped to every generated service at
``templates/service/.markdownlint-cli2.jsonc``.

They cannot be one file — the two trees are not the same shape, so the
``globs`` legitimately differ (a generated service has no ``releases/`` and no
``templates/``). But the **rule block must be identical**. A template that
holds itself to a stricter bar than it prescribes is the same credibility
problem as a gate that reports green without running: the standard in the
README stops describing the artefact.

Byte-identity via ``check_vendored_runtime_drift.py`` is not available here
precisely because the scope differs, so this checks the half that must match
and deliberately ignores the half that must not.

The second contract
-------------------
Every path-shaped exclusion in either config must resolve **in its own tree**.

This is not hypothetical. The repository's config shipped
``"!templates/service/eda/notebooks/**"`` — a directory that does not exist
and never did; the exclusion was inherited verbatim from the workflow's old
inline globs. An exclusion for a path that is not there is indistinguishable
from one that is working, and it is the same shape as every other finding in
this repository: a control whose scope is narrower than it appears, with
nothing checking the difference. ``check_doc_path_refs.py`` does not cover
``.jsonc``, so nothing caught it.

Only exclusions that point **into** the tree are checked — those containing a
``/``. A bare top-level name (``!.git``, ``!node_modules``, ``!.venv``) is a
defensive exclusion for something tooling creates, not a claim that the
directory is part of the repository, so requiring it to exist would be wrong.
That is a real limit: a stale bare-name exclusion would go unnoticed. It is
accepted because the class that has actually bitten here is the path-shaped
one, and because the alternative — a hand-maintained list of "environment"
names — is the kind of registry that quietly grows until it excuses the next
defect.

Exit codes
----------
- 0: the rule blocks match and every exclusion resolves.
- 1: the rule blocks differ, or an exclusion names a path that is not there.
- 2: setup error (a config is missing or is not parseable).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = REPO_ROOT / ".markdownlint-cli2.jsonc"
SERVICE_ROOT = REPO_ROOT / "templates" / "service"
SERVICE_CONFIG = SERVICE_ROOT / ".markdownlint-cli2.jsonc"

# `//` comments, but not inside a string (a glob may contain `//`… it does not
# today, and the negative lookbehind keeps a `":"`-prefixed URL safe anyway).
_LINE_COMMENT = re.compile(r"(?<!:)//.*$", re.M)


def _load(path: Path) -> dict[str, Any]:
    text = _LINE_COMMENT.sub("", path.read_text(encoding="utf-8"))
    return json.loads(text)


def _exclusions(config: dict[str, Any]) -> list[str]:
    out = []
    for glob in config.get("globs", []):
        if not isinstance(glob, str) or not glob.startswith("!"):
            continue
        pattern = glob[1:]
        if "/" not in pattern.rstrip("/"):
            continue  # a bare top-level name: defensive, not a claim
        if pattern.startswith("**"):
            continue  # "wherever this appears", by construction unanchored
        out.append(pattern)
    return out


def _resolves(root: Path, pattern: str) -> bool:
    # Strip a trailing `/**` or `/*` — the exclusion is about the directory.
    base = re.sub(r"/\*{1,2}$", "", pattern)
    if "*" in base:
        return any(root.glob(base))
    return (root / base).exists()


def main() -> int:
    for path in (REPO_CONFIG, SERVICE_CONFIG):
        if not path.is_file():
            sys.stderr.write(f"::error::{path.relative_to(REPO_ROOT)} not found\n")
            return 2

    try:
        repo = _load(REPO_CONFIG)
        service = _load(SERVICE_CONFIG)
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"::error::cannot parse a markdownlint config: {exc}\n")
        return 2

    problems: list[str] = []

    # --- 1. The rule block must be identical -----------------------------
    if repo.get("config") != service.get("config"):
        repo_rules = repo.get("config") or {}
        service_rules = service.get("config") or {}
        for key in sorted(set(repo_rules) | set(service_rules)):
            here, there = repo_rules.get(key, "<absent>"), service_rules.get(key, "<absent>")
            if here != there:
                problems.append(
                    f"rule `{key}` differs: repository has {here!r}, the shipped service config has {there!r}"
                )

    # --- 2. Every exclusion must resolve in its own tree ------------------
    for label, config, root in (
        (REPO_CONFIG.name, repo, REPO_ROOT),
        (f"templates/service/{SERVICE_CONFIG.name}", service, SERVICE_ROOT),
    ):
        for pattern in _exclusions(config):
            if not _resolves(root, pattern):
                problems.append(
                    f"{label}: excludes `{pattern}`, which does not exist. An "
                    f"exclusion for a path that is not there looks exactly like "
                    f"one that is working."
                )

    if problems:
        sys.stderr.write(
            "FAIL: the two markdownlint configurations disagree.\n"
            "The rule block must match — a template that lints itself to a\n"
            "stricter bar than it ships makes its own standard untrue — while\n"
            "the scope may differ, because the two trees are not the same shape.\n\n"
        )
        for problem in problems:
            sys.stderr.write(f"  - {problem}\n")
        sys.stderr.write(
            "\nFix: copy the `config` block from `.markdownlint-cli2.jsonc` into\n"
            "`templates/service/.markdownlint-cli2.jsonc` verbatim, or delete an\n"
            "exclusion that no longer names anything.\n"
        )
        return 1

    rules = len(repo.get("config") or {})
    print(f"[markdownlint-parity] OK — {rules} rule settings identical in both configs, and every exclusion resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
