"""Contract test — ADR-019 Phase 1 shadow workflow invariants (R5-M1).

Authority: ACTION_PLAN_R5 §R5-M1 + ADR-019 Phase 1.

The shadow workflow ``.github/workflows/ci-self-healing-shadow.yml`` is
the first real-world surface of ADR-019's classifier. R5-M1 upgraded it
from stubbed-empty-log to:

1. Real log fetch via ``gh api /repos/.../actions/runs/{id}/logs``.
2. Optional replay via ``workflow_dispatch`` + ``log_artifact_url``.
3. PR-base diff (not just ``HEAD~1``) so red-team F1 is closed.

None of those additions is allowed to weaken the Phase-1 write-none
invariant. This contract test guards the workflow file structurally.

Failure of any assertion here MUST block Phase 1 → Phase 2 promotion
until a human re-ratifies the workflow under ADR-019 §Phase plan.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHADOW = REPO_ROOT / ".github" / "workflows" / "ci-self-healing-shadow.yml"


@pytest.fixture(scope="module")
def shadow_yaml() -> str:
    if not SHADOW.exists():
        pytest.skip(f"{SHADOW} missing — ADR-019 Phase 1 not shipped")
    return SHADOW.read_text(encoding="utf-8")


def test_shadow_workflow_exists() -> None:
    assert SHADOW.exists(), f"Shadow workflow missing: {SHADOW}"


# ---------------------------------------------------------------------------
# Permissions — MUST be read-only everywhere.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "permission",
    ["contents: read", "actions: read", "pull-requests: read"],
)
def test_permissions_are_read_only(shadow_yaml: str, permission: str) -> None:
    """The permissions block must grant each scope only `read`.

    `pull-requests: read` was added by R5-M1 to resolve the PR base SHA.
    If anyone ever bumps a scope to `write`, this test fails and forces
    a governance review.
    """
    assert permission in shadow_yaml, (
        f"Shadow workflow must declare `{permission}` in the permissions block (ADR-019 Phase 1 invariant)."
    )


def test_no_write_permissions_present(shadow_yaml: str) -> None:
    """No permission scope may be `write`. Enforced by regex to catch
    sloppy future edits (e.g., `contents: write`).
    """
    forbidden = re.findall(r"^\s*[a-z-]+:\s*write\b", shadow_yaml, flags=re.MULTILINE)
    assert not forbidden, (
        "Shadow workflow contains write permissions; Phase 1 must be "
        f"strictly read-only. Offending lines: {forbidden!r}"
    )


# ---------------------------------------------------------------------------
# Triggers — workflow_run (main) + workflow_dispatch with log_artifact_url.
# ---------------------------------------------------------------------------


def test_workflow_run_trigger_present(shadow_yaml: str) -> None:
    assert "workflow_run:" in shadow_yaml, "Shadow workflow must trigger on workflow_run completion (ADR-019 §Phase 1)."


def test_log_artifact_url_input_present(shadow_yaml: str) -> None:
    """R5-M1 added an optional replay input; the dispatch surface must
    keep exposing it so incident replays are possible without code
    changes.
    """
    assert "log_artifact_url:" in shadow_yaml, (
        "workflow_dispatch must expose `log_artifact_url` input (R5-M1) "
        "so incident logs can be replayed against the classifier."
    )


# ---------------------------------------------------------------------------
# Real log fetch — no longer stubbed to empty.
# ---------------------------------------------------------------------------


def test_real_log_fetch_via_gh_api(shadow_yaml: str) -> None:
    """The fetch-logs step must call the real GH API for workflow_run
    logs. Without this, the classifier would still operate on an empty
    file and R5-M1 would be half-shipped.
    """
    # Join backslash-continuations so the multi-line `gh api \\\n  "..."`
    # call collapses to a single line the regex can match against.
    joined = re.sub(r"\\\n\s*", " ", shadow_yaml)
    pat = re.compile(r"gh\s+api\s+.*actions/runs/\$\{UPSTREAM_RUN_ID\}/logs")
    assert pat.search(joined), (
        "Shadow workflow must fetch upstream logs via "
        "`gh api /repos/.../actions/runs/${UPSTREAM_RUN_ID}/logs` (R5-M1). "
        "Found only the Phase-1 stub."
    )


def test_log_artifact_url_replay_path_present(shadow_yaml: str) -> None:
    """When LOG_ARTIFACT_URL is set, the workflow must fetch it via
    curl. This is the replay path for on-demand incident classification.
    """
    joined = re.sub(r"\\\n\s*", " ", shadow_yaml)
    assert re.search(r"curl\s.*\"\$\{LOG_ARTIFACT_URL\}\"", joined), (
        "log_artifact_url replay path is missing; R5-M1 requires curl on "
        "the explicit replay URL before falling back to gh api."
    )


def test_fetch_source_output_declared(shadow_yaml: str) -> None:
    """The step must emit `fetch_source` so downstream provenance is
    auditable (used in the step summary + the upcoming Phase-2
    precision analysis).
    """
    assert "fetch_source=" in shadow_yaml, "fetch-logs must export a `fetch_source` output for provenance."


# ---------------------------------------------------------------------------
# PR-base diff — closes red-team F1.
# ---------------------------------------------------------------------------


def test_pr_base_diff_resolution_present(shadow_yaml: str) -> None:
    """The changed-files step must resolve the PR base SHA and diff
    against it. This closes red-team F1 (shadow lane previously saw
    only the last commit, not the full PR).
    """
    assert "pulls/${PR_NUMBER}" in shadow_yaml, (
        "changed-files step must resolve PR base via `gh api /repos/.../pulls/${PR_NUMBER}` (R5-M1 / red-team F1)."
    )
    assert 'DIFF_MODE="pr-base"' in shadow_yaml, (
        "Workflow must report diff_mode=pr-base when a PR context is "
        "available so downstream can tell which lane produced the diff."
    )


def test_diff_mode_and_pr_number_outputs_declared(shadow_yaml: str) -> None:
    """Both outputs are consumed by the step summary and the context
    collector; missing either would silently degrade provenance.
    """
    assert "diff_mode=" in shadow_yaml
    assert "pr_number=" in shadow_yaml
    assert "base_sha=" in shadow_yaml


# ---------------------------------------------------------------------------
# Phase 1 invariant — writes_allowed=false verification still present.
# ---------------------------------------------------------------------------


def test_phase1_invariant_check_present(shadow_yaml: str) -> None:
    """The script-level writes_allowed=false verification must remain.
    R5-M1 adds inputs to the classifier but cannot relax the core
    ADR-019 invariant.
    """
    assert "writes_allowed != false" in shadow_yaml, (
        "Phase 1 invariant guard removed — the workflow no longer asserts "
        "`writes_allowed=false`. This is a STOP-class regression; revert "
        "immediately."
    )


def test_no_pr_creation_or_push(shadow_yaml: str) -> None:
    """No step may invoke `gh pr create`, `git push`, or the
    `actions/create-pull-request` action. These are Phase 2+ only.
    """
    forbidden = [
        r"gh\s+pr\s+create",
        r"\bgit\s+push\b",
        r"peter-evans/create-pull-request",
        r"actions/github-script[^\n]*createPullRequest",
    ]
    for fp in forbidden:
        assert not re.search(fp, shadow_yaml), (
            f"Shadow workflow contains forbidden write op matching `{fp}`; Phase 1 is strictly read-only."
        )


# ---------------------------------------------------------------------------
# Trigger reachability — the workflow must be able to fire at all.
# ---------------------------------------------------------------------------
#
# Every structural invariant above passed for the whole life of this
# workflow while it recorded ZERO runs. `workflow_run.workflows` matches the
# upstream workflow's `name:` field, not its filename; the list held
# filename stems, so nothing ever matched. GitHub reports no error for an
# unmatchable entry, so a workflow that can never fire looks identical to
# one that simply has not fired yet.
#
# Guarding "the workflow is read-only" while never checking "the workflow
# can run" is how ADR-019's Phase 1 -> Phase 2 gate became unsatisfiable by
# construction: the gate needs 14 days of shadow data that nothing was
# producing.


def _declared_trigger_workflows(shadow_yaml: str) -> list[str]:
    """Return the `workflows:` entries under the `workflow_run:` trigger."""
    import yaml

    # `on` is parsed by PyYAML 1.1 semantics as the boolean True.
    doc = yaml.safe_load(shadow_yaml)
    triggers = doc.get("on", doc.get(True, {}))
    return list(triggers["workflow_run"]["workflows"])


def _actual_workflow_names() -> set[str]:
    import yaml

    names: set[str] = set()
    for path in (REPO_ROOT / ".github" / "workflows").glob("*.y*ml"):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict) and isinstance(doc.get("name"), str):
            names.add(doc["name"])
    return names


def test_trigger_workflows_resolve_to_real_workflow_names(shadow_yaml: str) -> None:
    declared = _declared_trigger_workflows(shadow_yaml)
    assert declared, "workflow_run trigger declares no upstream workflows — it can never fire."

    actual = _actual_workflow_names()
    unmatched = [entry for entry in declared if entry not in actual]

    assert not unmatched, (
        "workflow_run trigger references workflow names that do not exist:\n"
        + "\n".join(f"  - {entry!r}" for entry in unmatched)
        + "\n\nThese must be workflow `name:` values, NOT filenames. GitHub "
        "silently never fires on an unmatchable entry, so this workflow "
        "would record zero runs while appearing active.\n"
        "Available names:\n" + "\n".join(f"  - {name!r}" for name in sorted(actual))
    )
