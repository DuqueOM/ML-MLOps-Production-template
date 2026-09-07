#!/usr/bin/env python3
"""Check that every entry in `.security-baselines/` carries an `expiry: YYYY-MM-DD`
annotation AND that none of them are past due.

Why this script exists
----------------------
The May 2026 audit (HIGH-1, ADR-024) flipped tfsec/checkov/trivy from
``soft_fail: true`` to hard-fail with explicit per-tool baselines. The baseline
contract is: every accepted finding is **explicit, dated, and reviewable**.

This script enforces the "dated and reviewable" half. Without it, an entry can
sit in `tfsec.yml` for years past its review window and silently degrade the
template's posture. With it, an expired entry blocks CI on the next push,
forcing either a fresh ADR + extension or a real fix.

Format contract
---------------
Each baseline file uses its native format (yaml for tfsec/checkov, plain text
for trivy). Expiry annotations are encoded as comments adjacent to each
non-empty entry:

  # expiry: 2026-08-01  reason: <ADR or issue reference>
  - "AWS001"

For trivy:

  CVE-2025-12345  # expiry: 2026-08-01  vendor advisory: ...

A baseline file with NO entries (the v0.15.0 default) is considered valid
regardless of the file's own date — there is nothing to expire.

Exit codes
----------
- 0: all baseline entries either non-existent or in-date.
- 1: at least one entry is expired OR an entry lacks an `expiry:` annotation.
- 2: a baseline file is malformed.

Usage
-----
::

    python3 scripts/check_baselines_expiry.py
    python3 scripts/check_baselines_expiry.py --as-of 2026-09-01   # dry-run a date

Wired into CI from `.github/workflows/validate-templates.yml`
(`security-baseline-expiry` job).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = REPO_ROOT / ".security-baselines"

# Lines we consider "entries" for the purpose of the expiry check. An empty
# list / empty file has no entries to expire, which is the valid v0.15.0
# default state.
ENTRY_PATTERNS = {
    # YAML files: a sequence item inside a suppression block. Case-insensitive
    # because checkov ids are upper (`CKV_AWS_18`) and tfsec ids are lower
    # (`google-gke-enable-master-networks`).
    #
    # The block-awareness is not decoration. This pattern used to require an
    # uppercase first character, so the three lowercase tfsec exclusions were
    # invisible: the gate that exists to stop suppressed HIGH findings from
    # ageing reported "no entries" while three HIGH GKE checks sat suppressed.
    # Matching lowercase alone is not enough either — `framework: [terraform,
    # kubernetes, dockerfile]` in checkov.yml is a sequence too, and is not a
    # suppression. Only items under `exclude:` / `skip-check:` are entries.
    "yaml_entry": re.compile(r"^\s*-\s+[\"']?[A-Za-z][A-Za-z0-9_.-]*[\"']?\s*(#.*)?$"),
    # Plain-format ignore ids: CVE-2025-12345 (advisories) and GCP-0061 /
    # AVD-AWS-0088 (trivy misconfiguration checks). The original pattern
    # required a four-digit year followed by a second number, so every
    # misconfiguration id was invisible.
    "trivy_entry": re.compile(r"^\s*([A-Z]+(?:-[A-Z]+)*-\d{3,}(?:-\d+)?)\s*(#.*)?$"),
}

# Top-level keys whose sequence items are suppressions subject to expiry.
SUPPRESSION_KEYS = ("exclude", "skip-check", "skip_check")
_BLOCK_KEY = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:")

EXPIRY_PATTERN = re.compile(r"#\s*expiry:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)


class BaselineFinding:
    __slots__ = ("file", "line_no", "raw", "expiry", "issue")

    def __init__(self, file: Path, line_no: int, raw: str, expiry: dt.date | None, issue: str) -> None:
        self.file = file
        self.line_no = line_no
        self.raw = raw
        self.expiry = expiry
        self.issue = issue

    def __str__(self) -> str:
        try:
            rel = self.file.relative_to(REPO_ROOT)
        except ValueError:
            rel = self.file
        return f"{rel}:{self.line_no}  {self.issue}: {self.raw.strip()}"


def _scan_yaml(path: Path, today: dt.date) -> list[BaselineFinding]:
    findings: list[BaselineFinding] = []
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_suppression_block = False
    for i, line in enumerate(lines, start=1):
        key_match = _BLOCK_KEY.match(line)
        if key_match:
            in_suppression_block = key_match.group("key") in SUPPRESSION_KEYS
            continue
        if not in_suppression_block:
            continue
        if not ENTRY_PATTERNS["yaml_entry"].match(line):
            continue
        # Look for an expiry annotation on the entry line OR the line above
        # (the more common style: `# expiry: ...\n  - "AWS001"`).
        ann = EXPIRY_PATTERN.search(line)
        if ann is None and i >= 2:
            ann = EXPIRY_PATTERN.search(lines[i - 2])
        if ann is None:
            findings.append(BaselineFinding(path, i, line, None, "missing expiry annotation"))
            continue
        try:
            expiry = dt.date.fromisoformat(ann.group(1))
        except ValueError:
            findings.append(BaselineFinding(path, i, line, None, f"malformed expiry: {ann.group(1)}"))
            continue
        if expiry < today:
            findings.append(BaselineFinding(path, i, line, expiry, f"expired on {expiry.isoformat()}"))
    return findings


def _scan_trivy(path: Path, today: dt.date) -> list[BaselineFinding]:
    findings: list[BaselineFinding] = []
    if not path.exists():
        return findings
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = ENTRY_PATTERNS["trivy_entry"].match(raw)
        if m is None:
            findings.append(BaselineFinding(path, i, raw, None, "malformed trivy entry"))
            continue
        # Same lookup as _scan_yaml: the annotation may sit inline
        # (`CVE-... # expiry: ...`) or on the line directly above, which is
        # the readable form when the justification needs a paragraph.
        ann = EXPIRY_PATTERN.search(raw)
        if ann is None and i >= 2:
            ann = EXPIRY_PATTERN.search(lines[i - 2])
        if ann is None:
            findings.append(BaselineFinding(path, i, raw, None, "missing expiry annotation"))
            continue
        try:
            expiry = dt.date.fromisoformat(ann.group(1))
        except ValueError:
            findings.append(BaselineFinding(path, i, raw, None, f"malformed expiry: {ann.group(1)}"))
            continue
        if expiry < today:
            findings.append(BaselineFinding(path, i, raw, expiry, f"expired on {expiry.isoformat()}"))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default=None,
        help="ISO date to evaluate against (default: today UTC). Use to dry-run a future date.",
    )
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.as_of) if args.as_of else dt.datetime.now(dt.timezone.utc).date()

    if not BASELINE_DIR.is_dir():
        print(f"[baselines] {BASELINE_DIR} not found — nothing to check.")
        return 0

    # Discover the baseline files rather than naming them.
    #
    # This used to be three hardcoded paths. A guard whose coverage is a
    # literal list only covers what someone last remembered to add — the
    # ADR-046 migration replaced tfsec.yml with a new file, and under the old
    # shape that file would have been unwatched while the gate reported
    # green. Anything dropped into this directory is now scanned, and an
    # unrecognised shape is a failure rather than a silent skip.
    findings: list[BaselineFinding] = []
    unknown: list[str] = []
    for path in sorted(BASELINE_DIR.iterdir()):
        if not path.is_file() or path.name == "README.md":
            continue
        if path.suffix in (".yml", ".yaml"):
            findings.extend(_scan_yaml(path, today))
        elif path.suffix == ".trivyignore" or path.name == ".trivyignore":
            findings.extend(_scan_trivy(path, today))
        else:
            unknown.append(path.name)

    if unknown:
        for name in unknown:
            sys.stderr.write(
                f"::error::{BASELINE_DIR.name}/{name}: unrecognised baseline format. "
                "Add a scanner for it — an unscanned baseline file is an "
                "unwatched set of suppressions.\n"
            )
        return 2

    if not findings:
        print(f"[baselines] OK — no expired or unannotated entries (as of {today.isoformat()}).")
        return 0

    print(f"[baselines] {len(findings)} issue(s) — see ADR-024 §'Review':")
    for f in findings:
        print(f"  - {f}")
    print()
    print("Resolution paths:")
    print("  1. Fix the underlying issue and remove the baseline entry.")
    print("  2. Open an ADR justifying the extension and update the `# expiry: YYYY-MM-DD` annotation.")
    print("  3. Re-run: python3 scripts/check_baselines_expiry.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
