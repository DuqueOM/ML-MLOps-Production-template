"""Tests for the data-path contract (Phase 1.4).

The training pipeline, retrain workflow, and drift CronJob all read from
`data/`. If they disagree on the directory layout, the workflow runs
green in CI but produces empty datasets, NaN drift scores, or models
trained on yesterday's snapshot. This test file pins the contract.

Three orthogonal invariants:

1. **All canonical directories exist** in the scaffolded service.
   Catches the regression where `data/production/` was missing from
   `new-service.sh::mkdir -p` (the drift CronJob then crashes on first
   run with FileNotFound).
2. **The drift CronJob's `--current` path matches the scaffolded
   directory.** Hand-edit the YAML to point at `data/prod/latest.csv`
   and the test fails.
3. **The retrain workflow downloads to the same path that `train.py`
   reads from.** A typo in `retrain-service.yml` like `data/raw/latests.csv`
   would otherwise be invisible until the next retrain cycle.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


CANONICAL_DIRS = [
    "data/raw",
    "data/processed",
    "data/reference",
    "data/production",
    "data/validated",
    "models",
    "reports",
]


@pytest.mark.scaffold_context
@pytest.mark.parametrize("relpath", CANONICAL_DIRS)
def test_canonical_directory_exists(relpath: str) -> None:
    """Every directory listed in `docs/data-paths.md` must exist."""
    target = REPO_ROOT / relpath
    assert target.is_dir(), (
        f"missing canonical directory `{relpath}` — the layout is shipped as "
        f"a `.gitkeep` placeholder in the template, and `.gitignore` keeps it "
        f"while ignoring the payloads. Check the placeholder still exists and "
        f"that the `docs/data-paths.md` table is in sync."
    )


def test_drift_cronjob_uses_canonical_paths() -> None:
    """The drift CronJob must read from `data/reference/` and `data/production/`.

    Hand-coded paths in the YAML are the most common source of silent
    breakage; this test treats the directory layout as a hard contract.
    """
    cron_path = REPO_ROOT / "k8s" / "base" / "cronjob-drift.yaml"
    if not cron_path.is_file():
        pytest.skip("k8s/base/cronjob-drift.yaml not present in this layout")
    text = cron_path.read_text(encoding="utf-8")

    # The CronJob's command list contains `--reference <path>` and
    # `--current <path>` as adjacent YAML list items. We do a simple
    # token scan — full schema parsing is overkill for two flags.
    ref_match = re.search(r"-\s*--reference\s*\n\s*-\s*(\S+)", text)
    cur_match = re.search(r"-\s*--current\s*\n\s*-\s*(\S+)", text)
    assert ref_match, "cronjob-drift.yaml does not pass --reference"
    assert cur_match, "cronjob-drift.yaml does not pass --current"
    # Accept both local-relative ("data/reference/…") and container-absolute
    # ("/data/reference/…").  The K8s CronJob legitimately uses the latter
    # because the reference dataset is served from a volume mounted at /data.
    assert ref_match.group(1).lstrip("/").startswith("data/reference/"), (
        f"--reference points at {ref_match.group(1)!r}; expected data/reference/* "
        "or /data/reference/* (see docs/data-paths.md)"
    )
    assert cur_match.group(1).lstrip("/").startswith("data/production/"), (
        f"--current points at {cur_match.group(1)!r}; expected data/production/* "
        "or /data/production/* (see docs/data-paths.md)"
    )


def test_retrain_workflow_downloads_to_training_path() -> None:
    """retrain-service.yml downloads → `train.py --data` reads.

    Without this test, a path typo on either side passes CI (the
    `Validate data` step might still find the file by coincidence) and
    silently produces an empty model.
    """
    wf_path = REPO_ROOT / ".github" / "workflows" / "retrain-service.yml"

    if not wf_path.is_file():
        # Scaffolded layout copies retrain-service.yml under .github/workflows
        # OR keeps it under the template root depending on the run mode.
        candidate = REPO_ROOT / "retrain-service.yml"
        if candidate.is_file():
            wf_path = candidate
        else:
            pytest.skip("retrain-service.yml not present in this layout")

    text = wf_path.read_text(encoding="utf-8")
    # The workflow downloads to `data/raw/latest.csv`. Check the convention.
    assert "data/raw/latest.csv" in text, (
        "retrain-service.yml does not download to data/raw/latest.csv "
        "— update either the workflow or docs/data-paths.md."
    )
    assert "--data data/raw/latest.csv" in text, (
        "retrain-service.yml does not invoke `train.py --data data/raw/latest.csv` "
        "— path inconsistency between download and training step."
    )


def test_data_paths_doc_lists_every_directory() -> None:
    """`docs/data-paths.md` is the source of truth — keep it in sync.

    Catches the case where someone adds `data/streaming/` to the
    scaffolder but never documents it (or vice versa).
    """
    doc = REPO_ROOT / "docs" / "data-paths.md"
    if not doc.is_file():
        pytest.skip("docs/data-paths.md not present")
    text = doc.read_text(encoding="utf-8")
    for relpath in CANONICAL_DIRS:
        assert relpath in text, f"`docs/data-paths.md` does not mention `{relpath}`"
