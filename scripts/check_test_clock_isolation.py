#!/usr/bin/env python3
"""Contract: tests must not invoke wall-clock APIs without justification.

Why this exists
---------------
On 2026-05-04 a behavioral test broke when the user ran the suite at
20:52 UTC — the dynamic-risk evaluator's ``_is_off_hours()`` returned
True against the real wall clock, leaking an extra signal into every
context the test built. The bug shipped to main; the user noticed.
Root cause: a test helper called a function that, two layers down,
read the wall clock.

This script does NOT try to detect that pattern statically (it would
require taint analysis). Instead it locks down the **direct** uses
of wall-clock APIs in test files via a curated allowlist. The
intent is:

    "If a future PR adds a new ``datetime.now()`` / ``time.time()``
    call to a test file, force the author (or the CI reviewer) to
    audit whether the value is used to seed a fixture (safe) or
    to drive an assertion (the 2026-05-04 anti-pattern)."

Each entry in the ALLOWLIST below was reviewed when this script was
written. The PR that adds a new entry MUST link to evidence (a test
run, a code-review note) that the new use is fixture-only.

Sleeping is covered too, and was not always
----------------------------------------
The pattern originally matched only calls that *read* the clock, while the
contract in the title says tests must not depend on it. Waiting on the clock
is the same dependency wearing a different hat, and it produced a real CI
failure: ``test_flush_on_buffer_full`` slept 0.1s hoping a background flush
task had run, and intermittently it had not. Worse, the sleep was long enough
to usually hide a genuine production defect underneath it — an
``asyncio.create_task`` whose reference nobody kept, so the task could be
garbage-collected mid-write.

``time.sleep`` and ``asyncio.sleep`` are therefore findings. The fix is almost
always to wait on the *event you actually care about* — an ``asyncio.Event``,
a queue, a condition — with a generous timeout as a failsafe. A timeout only
decides how long the suite waits before declaring something broken; a sleep
decides whether the test is correct.

A sleep that simulates a slow dependency (inside a fake backend, say) is not
a clock dependency and belongs in the ALLOWLIST with that justification.

This is a **lightweight signal**, not a proof. It complements (does
not replace) the freeze_time / monkeypatch patterns that individual
tests should still apply when accuracy matters.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# What we look for: direct calls to wall-clock APIs.
# ---------------------------------------------------------------------------
# Module-qualified attribute access (avoid matching e.g. `data.timestamp`).
PATTERN = re.compile(
    r"""
    \b(
        datetime\.(now|utcnow)
        | time\.(time|monotonic|monotonic_ns|time_ns|sleep)
        | asyncio\.sleep
    )\b
    \s*\(
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Allowlist (file-relative-to-repo  ->  list of (line, justification))
# ---------------------------------------------------------------------------
# Each entry is reviewed. To add a new entry: include the line number,
# the API used, AND a one-line justification covering "why is the
# returned value not driving an assertion".
ALLOWLIST: dict[str, list[tuple[int, str, str]]] = {
    "templates/tests/unit/test_dora_metrics.py": [
        (
            88,
            "datetime.now",
            "seeds the timestamp inside a synthetic audit entry; "
            "the test asserts on aggregate counts, not on the timestamp value",
        ),
    ],
    "templates/tests/unit/test_risk_context_behavior.py": [
        (
            54,
            "datetime.now",
            "_now_iso() helper writes recent_rollback fixture; "
            "no assertion depends on the literal value (window check happens "
            "in production code, but tests force off_hours explicitly)",
        ),
    ],
    "templates/tests/unit/test_prediction_logger.py": [
        (
            257,
            "time.sleep",
            "inside a fake backend that SIMULATES a slow write, which is the "
            "condition under test (close() must wait for an in-flight flush); "
            "the test asserts on what the backend received, never on elapsed time",
        ),
    ],
    "templates/service/tests/integration/conftest.py": [
        (
            36,
            "time.sleep",
            "poll interval inside wait_for_service's deadline loop: the correct "
            "shape for waiting on an EXTERNAL dependency (poll + timeout), not a "
            "fixed sleep standing in for synchronisation; no assertion depends on "
            "how long it slept",
        ),
        (
            28,
            "time.time",
            "wait_for_service polling timeout: delta measurement, absolute clock value never asserted",
        ),
        (
            29,
            "time.time",
            "wait_for_service polling timeout: delta measurement, absolute clock value never asserted",
        ),
    ],
    "templates/service/tests/integration/test_service_integration.py": [
        (
            95,
            "time.time",
            "predict latency SLA delta measurement; assertion is on "
            "(end - start), not on either timestamp individually",
        ),
        (
            101,
            "time.time",
            "predict latency SLA delta measurement; assertion is on "
            "(end - start), not on either timestamp individually",
        ),
    ],
    "templates/tests/unit/test_risk_context.py": [
        (
            173,
            "datetime.now",
            "fixture seed: writes a recent rollback timestamp; assertion is on "
            "the loaded RiskContext.recent_rollback boolean, not the value",
        ),
        (
            176,
            "time.time",
            "cache_key uniqueness only; not used in any assertion",
        ),
        (
            183,
            "time.time",
            "cache_key uniqueness only; not used in any assertion",
        ),
        (
            361,
            "datetime.now",
            "fixture seed for an audit entry; assertion is on parsed dataclass",
        ),
    ],
}

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOTS = [
    REPO_ROOT / "templates" / "tests" / "unit",
    REPO_ROOT / "templates" / "service" / "tests" / "integration",
    REPO_ROOT / "templates" / "tests" / "contract",
]


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return [(line_no, matched_call), ...] for a single file."""
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return hits
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Skip comment-only lines and docstring lines (heuristic, not perfect).
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = PATTERN.search(line)
        if match:
            hits.append((line_no, match.group(1)))
    return hits


def main() -> int:
    failures: list[str] = []
    scanned = 0

    for root in TEST_ROOTS:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            scanned += 1
            rel_path = py_file.relative_to(REPO_ROOT).as_posix()
            allowed = {(ln, api) for ln, api, _ in ALLOWLIST.get(rel_path, [])}
            hits = _scan_file(py_file)
            for line_no, api in hits:
                if (line_no, api) not in allowed:
                    failures.append(
                        f"{rel_path}:{line_no}: {api}() called outside the "
                        f"clock-isolation allowlist. If this is a fixture seed "
                        f"(safe), add an entry to ALLOWLIST in "
                        f"scripts/check_test_clock_isolation.py with a "
                        f"one-line justification. If this drives an "
                        f"assertion, freeze the clock with monkeypatch / "
                        f"freezegun instead."
                    )

    if failures:
        print("FAIL: wall-clock isolation contract violations:", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\nContext: see docs/audit/feedback-may-2026-triage.md "
            '§"Closure summary" for the bug this contract prevents.',
            file=sys.stderr,
        )
        return 1

    print(
        f"[clock-isolation] OK — scanned {scanned} test file(s); "
        f"{sum(len(v) for v in ALLOWLIST.values())} allowlisted call(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
