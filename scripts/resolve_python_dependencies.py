#!/usr/bin/env python3
"""Resolve every tracked requirements file to exact pins, for vulnerability scanning.

Why this exists
---------------
The ``Trivy filesystem scan`` step in the ``Self-audit`` job is blocking
(``exit-code: 1``, ``CRITICAL,HIGH``) and **had never examined a single Python
dependency**. Its own CI log said so on every run:

    INFO  Number of language-specific files  num=0
    WARN  [report] Supported files for scanner(s) not found.  scanners=[vuln]

Trivy resolves a ``requirements.txt`` only when the versions are pinned
exactly (``==``). This repository mandates compatible-release pins (``~=``) —
a deliberate, documented choice, since numpy 2.x silently corrupts joblib
models — and ships no lock file. So trivy had nothing to read, found nothing,
and exited 0. A blocking gate that always passes is worse than no gate: it
produces the assurance without the check.

What this does
--------------
Asks pip to *resolve* each requirements file without installing anything
(``pip install --dry-run --report``), then writes the resolved set as exact
pins into an output directory that trivy can read. It answers the question the
gate was always meant to answer: **are the versions we would actually install
vulnerable?**

Resolving in CI rather than committing a lock file is deliberate. A lock file
under ``templates/service/`` would ship to every adopter and freeze their
transitive tree to ours, which is a product decision with its own trade-offs;
this changes nothing about what adopters receive.

Zero is a failure
-----------------
Both discovery steps assert they found something. A run that resolves no files,
or a file that resolves to no packages, exits non-zero — that is the exact
failure mode this script was written in response to, and reproducing it
silently would be the whole bug again.

Exit codes
----------
- 0: every discovered requirements file resolved to at least one package.
- 1: nothing discovered, a file resolved to nothing, or pip failed to resolve.
- 2: usage error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_requirements() -> list[str]:
    """Every tracked requirements file, discovered rather than listed."""
    result = subprocess.run(
        ["git", "ls-files", "*requirements*.txt"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line for line in result.stdout.split() if line)


def _resolve(req: Path, report: Path) -> list[str]:
    """Return `name==version` for everything pip would install."""
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--dry-run", "--report", str(report), "-r", str(req)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pip could not resolve {req}: {proc.stderr.strip()[-600:] or proc.stdout.strip()[-600:]}")
    data = json.loads(report.read_text(encoding="utf-8"))
    pins = []
    for item in data.get("install", []):
        meta = item.get("metadata") or {}
        name, version = meta.get("name"), meta.get("version")
        if name and version:
            pins.append(f"{name}=={version}")
    return sorted(set(pins))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", help="directory to write resolved requirements into")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    requirements = _tracked_requirements()
    if not requirements:
        sys.stderr.write(
            "::error::no tracked requirements files found. Either the layout moved or\n"
            "::error::this is reading the wrong tree — both need a human, so finding\n"
            "::error::nothing is a failure rather than a pass.\n"
        )
        return 1

    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        for rel in requirements:
            src = REPO_ROOT / rel
            try:
                pins = _resolve(src, report)
            except (RuntimeError, json.JSONDecodeError, OSError) as exc:
                sys.stderr.write(f"::error::{rel}: {exc}\n")
                return 1
            if not pins:
                sys.stderr.write(
                    f"::error::{rel} resolved to zero packages. An empty resolution is\n"
                    f"::error::indistinguishable from a clean scan, which is the defect\n"
                    f"::error::this script exists to remove.\n"
                )
                return 1
            # Every output file is named exactly `requirements.txt`, and the
            # source path becomes its DIRECTORY. Both halves are load-bearing:
            #
            #   * Trivy identifies a Python dependency file by name. Flattening
            #     to `templates__service__requirements.txt` took the finding
            #     count from 24 to 0 — silently, which is the same bug this
            #     script exists to fix.
            #   * Trivy matches `requirements.txt` EXACTLY. Keeping the original
            #     name would leave `requirements-heavy.txt` unparsed, again
            #     silently: measured, 3 of 4 files were scanned.
            #
            # The directory keeps provenance readable in trivy's own output —
            # the target it prints is the source path with the extension
            # dropped, plus the recognised filename — and makes collisions
            # impossible.
            stem = Path(rel).with_suffix("")
            target = out_dir / stem / "requirements.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(pins) + "\n", encoding="utf-8")
            print(f"  {rel}: {len(pins)} packages -> {target.relative_to(out_dir)}")
            total += len(pins)

    print(
        f"[resolve-python-deps] OK — {len(requirements)} requirements file(s), "
        f"{total} pinned packages written to {out_dir}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
