"""Contract test — Reports v1 (ADR-023 F6).

Authority: `docs/decisions/ADR-023-agentic-portability-and-context.md` §F6.

Locks the structural invariants of the typed report contract:

Schema is parsable + the four canonical types are declared
  `templates/config/report_schema.json` parses as JSON Schema 2020-12
  with exactly four `report_type` enum values.

Examples produced by the CLI round-trip the schema
  `python3 scripts/generate_report.py example <type>` produces a doc
  that the in-tree validator and (when installed) jsonschema both
  accept.

Library invariants
  ReportEnvelope is frozen; constructing with mismatched payload
  type, missing approver under CONSULT, or malformed service slug
  raises. Reports survive a JSON round-trip with no mutation.

Manifest reports block coherence
  `agentic_manifest.yaml#reports` lists exactly the four canonical
  types, each producer references a real skill/workflow, and the
  schema/library/cli paths exist.

CLI surface is read-only
  Subcommands: `validate`, `example`. No `generate`, no `delete`,
  no `mutate`. Forbidden keywords are absent from `--help` output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = REPO_ROOT / "templates/config/report_schema.json"
LIBRARY = REPO_ROOT / "common_utils/reports.py"
CLI = REPO_ROOT / "scripts/generate_report.py"
MANIFEST = REPO_ROOT / "templates/config/agentic_manifest.yaml"
DOCS = REPO_ROOT / "docs/agentic/reports.md"
STORAGE = REPO_ROOT / "ops/reports"
CANONICAL_TYPES = ("release", "drift", "training", "incident")

# Make `common_utils` importable for the library tests.
sys.path.insert(0, str(REPO_ROOT / "templates"))


def test_schema_parses_and_lists_canonical_types() -> None:
    doc = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert doc.get("$schema", "").startswith("https://json-schema.org/")
    types_enum = doc["properties"]["report_type"]["enum"]
    assert sorted(types_enum) == sorted(CANONICAL_TYPES), (
        f"report_type enum {sorted(types_enum)} != canonical {sorted(CANONICAL_TYPES)}"
    )
    # oneOf branches: one per canonical type.
    branches = doc.get("oneOf") or []
    assert len(branches) == len(CANONICAL_TYPES), f"oneOf must have one branch per canonical type (got {len(branches)})"


@pytest.mark.parametrize("rtype", CANONICAL_TYPES)
def test_cli_example_round_trips_validate(rtype: str, tmp_path: Path) -> None:
    """`generate_report.py example <type>` produces a doc that
    `generate_report.py validate` accepts.
    """
    proc = subprocess.run(
        [sys.executable, str(CLI), "example", rtype],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["report_type"] == rtype
    target = tmp_path / f"{rtype}.json"
    target.write_text(json.dumps(doc), encoding="utf-8")
    val = subprocess.run(
        [sys.executable, str(CLI), "validate", str(target)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=REPO_ROOT,
    )
    assert val.returncode == 0, val.stderr


def test_envelope_rejects_mismatched_payload() -> None:
    """report_type=release with a DriftPayload must raise."""
    from common_utils.agent_context import AgentMode, Environment
    from common_utils.reports import DriftFeature, DriftPayload, ReportEnvelope

    drift = DriftPayload(
        window_start="2026-05-01T00:00:00Z",
        window_end="2026-05-02T00:00:00Z",
        features=(DriftFeature(name="x", psi=0.1),),
        retrain_recommendation="none",
    )
    with pytest.raises(TypeError, match="release.*requires.*ReleasePayload"):
        ReportEnvelope(
            report_type="release",
            report_id="release-svc_a-20260501",
            service="svc_a",
            generated_at="2026-05-01T00:00:00Z",
            generated_by="test",
            mode=AgentMode.CONSULT,
            payload=drift,
            environment=Environment.STAGING,
            approver="t",
        )


def test_envelope_rejects_consult_without_approver() -> None:
    from common_utils.agent_context import AgentMode, Environment
    from common_utils.reports import ReleasePayload, build_release_report

    payload = ReleasePayload(
        version="v0.1.0",
        commit_sha="aabbccd",
        images=("img@sha256:" + "a" * 64,),
        quality_gates_passed=True,
        deploy_targets=("gcp",),
        sbom_present=True,
        images_signed=True,
    )
    with pytest.raises(ValueError, match="require a named approver"):
        build_release_report(
            service="svc_a",
            generated_by="t",
            mode=AgentMode.CONSULT,
            environment=Environment.STAGING,
            payload=payload,
            approver=None,
        )


def test_envelope_rejects_malformed_service_slug() -> None:
    from common_utils.agent_context import AgentMode
    from common_utils.reports import DriftFeature, DriftPayload, build_drift_report

    payload = DriftPayload(
        window_start="2026-05-01T00:00:00Z",
        window_end="2026-05-02T00:00:00Z",
        features=(DriftFeature(name="x", psi=0.1),),
        retrain_recommendation="none",
    )
    with pytest.raises(ValueError):
        build_drift_report(
            service="Bad Slug!",
            generated_by="t",
            mode=AgentMode.AUTO,
            payload=payload,
        )


def test_envelope_is_frozen() -> None:
    from common_utils.agent_context import AgentMode
    from common_utils.reports import DriftFeature, DriftPayload, build_drift_report

    rep = build_drift_report(
        service="svc_a",
        generated_by="t",
        mode=AgentMode.AUTO,
        payload=DriftPayload(
            window_start="2026-05-01T00:00:00Z",
            window_end="2026-05-02T00:00:00Z",
            features=(DriftFeature(name="x", psi=0.1),),
            retrain_recommendation="none",
        ),
    )
    with pytest.raises(Exception):
        rep.service = "svc_b"  # type: ignore[misc]


def test_envelope_round_trips_through_json(tmp_path: Path) -> None:
    from common_utils.agent_context import AgentMode, Environment
    from common_utils.reports import ReleasePayload, build_release_report, load_report

    payload = ReleasePayload(
        version="v0.1.0",
        commit_sha="aabbccd",
        images=("img@sha256:" + "a" * 64,),
        quality_gates_passed=True,
        deploy_targets=("gcp",),
        sbom_present=True,
        images_signed=True,
    )
    rep = build_release_report(
        service="round_trip",
        generated_by="t",
        mode=AgentMode.CONSULT,
        environment=Environment.STAGING,
        approver="ops",
        payload=payload,
    )
    target = tmp_path / "rt.json"
    written = rep.write(target)
    loaded = load_report(written)
    assert loaded["report_type"] == "release"
    assert loaded["service"] == "round_trip"
    assert loaded["payload"]["version"] == "v0.1.0"
    # Re-serialize and compare; idempotent.
    second = json.loads(target.read_text(encoding="utf-8"))
    assert second == loaded


def test_manifest_reports_block_lists_canonical_types() -> None:
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    block = doc.get("reports") or {}
    assert block, "manifest missing reports: block (ADR-023 F6)"
    types = {t["id"] for t in (block.get("types") or [])}
    assert types == set(CANONICAL_TYPES), f"manifest reports.types {types} != canonical {set(CANONICAL_TYPES)}"
    # Every path the manifest references must exist.
    for key in ("schema", "library", "cli"):
        rel = block.get(key)
        assert rel and (REPO_ROOT / rel).exists(), f"reports.{key} path missing: {rel!r}"
    storage = block.get("storage_root")
    assert storage and (REPO_ROOT / storage).is_dir(), (
        f"reports.storage_root must be an existing directory ({storage!r})"
    )


def test_cli_help_lists_only_read_only_subcommands() -> None:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.lower()
    # Must mention the two allowed subcommands…
    for cmd in ("validate", "example"):
        assert cmd in out, f"--help missing subcommand {cmd!r}"
    # …and must NOT advertise mutating ones.
    forbidden = ("delete", "rotate", "promote", "deploy", "rollback")
    for term in forbidden:
        assert term not in out, (
            f"generate_report.py --help advertises forbidden subcommand {term!r}; CLI must remain read-only"
        )


def test_storage_root_has_canonical_subdirs() -> None:
    """`ops/reports/<type>/` exists for each canonical type so producers
    don't have to mkdir at runtime."""
    for rtype in CANONICAL_TYPES:
        sub = STORAGE / rtype
        assert sub.is_dir(), f"missing canonical subdir: {sub.relative_to(REPO_ROOT)}"


def test_docs_reference_authority_and_storage_layout() -> None:
    body = DOCS.read_text(encoding="utf-8")
    assert "ADR-023" in body, "reports.md must reference ADR-023"
    for rtype in CANONICAL_TYPES:
        assert rtype in body, f"reports.md must mention canonical type {rtype}"
    assert "ops/reports" in body, "reports.md must document storage convention"
