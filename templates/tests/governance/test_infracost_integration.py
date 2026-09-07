"""Contract test — infracost diff is wired into terraform-plan-nightly (R4-L3).

Authority: ACTION_PLAN_R4 §L3 + ADR-020 §L3.

R4-L3 flagged that the nightly `terraform plan` workflow emitted the
plan but did no cost analysis, so over-provisioning drifts (e.g.
someone bumping `node_count` from 3 to 30) landed silently.

Sprint 3 adds an `infracost breakdown` step to each cloud's plan
job. This test locks the integration so a future refactor can't
regress it:

1. The workflow must reference `infracost/actions/setup` exactly once
   per cloud (gcp + aws).
2. Each infracost step must be guarded by `env.INFRACOST_API_KEY != ''`
   so the workflow degrades cleanly when the secret is absent.
3. The cost data must land in an uploaded artifact + step summary —
   running infracost with no observable output is dead code.
4. The workflow's header must document the optional secret so operators
   know what to configure (preventing silent-feature syndrome).

The test parses the YAML structurally (not with regex) so cosmetic
reformatting cannot break it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / "templates" / "service" / ".github" / "workflows" / "terraform-plan-nightly.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    assert WORKFLOW.exists(), f"expected {WORKFLOW} to exist"
    # PyYAML renders the `on:` key as True (Python boolean) because YAML
    # 1.1 aliases `on` → true. This is a known PyYAML quirk; we handle
    # it by not asserting on `on:` here (the CI runner parses GHA's
    # own 1.2 dialect correctly).
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "workflow must parse to a mapping"
    return data


def _steps_for_job(workflow: dict[str, Any], job_id: str) -> list[dict[str, Any]]:
    jobs = workflow.get("jobs") or {}
    job = jobs.get(job_id)
    assert job, f"job {job_id!r} missing from workflow"
    steps = job.get("steps") or []
    assert isinstance(steps, list) and steps, f"job {job_id!r} has no steps"
    return steps


@pytest.mark.parametrize("job_id", ["plan-gcp", "plan-aws"])
def test_infracost_setup_step_present(workflow: dict[str, Any], job_id: str) -> None:
    """Each cloud plan job wires the infracost setup action."""
    steps = _steps_for_job(workflow, job_id)
    setups = [s for s in steps if "infracost/actions/setup" in str(s.get("uses", ""))]
    assert len(setups) == 1, (
        f"{job_id} must reference infracost/actions/setup exactly once; "
        f"found {len(setups)}. Refactor likely dropped the step."
    )
    step = setups[0]
    # The `if:` condition must guard on the env variable (so the step
    # is skipped cleanly when no API key is configured).
    assert "INFRACOST_API_KEY" in str(step.get("if", "")), (
        f"{job_id} infracost setup step missing INFRACOST_API_KEY guard; "
        "without it the workflow hard-fails on forks without the secret."
    )
    # The env must wire secrets.INFRACOST_API_KEY into env.INFRACOST_API_KEY.
    env = step.get("env") or {}
    assert "INFRACOST_API_KEY" in env, (
        f"{job_id} infracost setup must map secrets.INFRACOST_API_KEY "
        "into env.INFRACOST_API_KEY for the if-guard to see it."
    )


@pytest.mark.parametrize("job_id", ["plan-gcp", "plan-aws"])
def test_infracost_breakdown_emits_artifact_and_summary(workflow: dict[str, Any], job_id: str) -> None:
    """The breakdown must produce an artifact AND a step summary
    entry; cost data with no observer is effectively dead code.
    """
    steps = _steps_for_job(workflow, job_id)
    # Find the breakdown step by looking for `infracost breakdown` in
    # the `run:` body.
    breakdown = [s for s in steps if "infracost breakdown" in str(s.get("run", ""))]
    assert len(breakdown) == 1, f"{job_id} must have exactly one infracost breakdown step"
    body = breakdown[0]["run"]
    assert "GITHUB_STEP_SUMMARY" in body, (
        f"{job_id} breakdown must append to GITHUB_STEP_SUMMARY — otherwise the cost number is invisible to reviewers."
    )
    assert "totalMonthlyCost" in body, (
        f"{job_id} breakdown must read .totalMonthlyCost from the JSON "
        "output; silent parsing errors let over-provisioning slip."
    )
    # Artifact upload must exist and carry the breakdown JSON.
    uploads = [
        s
        for s in steps
        if "actions/upload-artifact" in str(s.get("uses", "")) and "infracost" in str(s.get("with", {}).get("name", ""))
    ]
    assert uploads, (
        f"{job_id} must upload an infracost-<cloud>-<run_id> artifact "
        "so the JSON is retrievable without re-running the job."
    )


def test_workflow_header_documents_infracost_secret() -> None:
    """Operators must discover the secret by reading the workflow file.
    A documented feature-flag is the difference between "optional" and
    "silently broken"."""
    raw = WORKFLOW.read_text(encoding="utf-8")
    head = raw.split("jobs:", 1)[0]
    assert "INFRACOST_API_KEY" in head, (
        "workflow header comment must document the optional INFRACOST_API_KEY secret (see R4-L3 rationale)."
    )
    assert "R4-L3" in raw, (
        "workflow should self-label the infracost integration with the "
        "audit finding id (R4-L3) to keep provenance discoverable."
    )
