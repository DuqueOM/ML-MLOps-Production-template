#!/usr/bin/env python3
"""Contract: runtime tools and runbooks that a SCAFFOLDED service needs at
runtime are vendored into ``templates/service/`` and MUST stay byte-identical
to their canonical repo-root originals.

Why this exists
---------------
Copier renders only the ``templates/service/`` subtree (``_subdirectory`` in
``copier.yml``). The meta layer at the repo root — ``scripts/``,
``docs/runbooks/``, etc. — is NOT part of a generated project. But a freshly
scaffolded service still needs a handful of those repo-root tools to function
on its very first CI run and deploy:

- ``scripts/validate_quality_gates.py`` — invoked by the generated
  ``Makefile`` (``make ci``/lint) and ``.github/workflows/ci.yml``.
- ``scripts/audit_record.py`` — invoked by the generated
  ``.github/workflows/deploy-common.yml`` (and retrain / nightly-plan)
  on every deploy, success AND failure (ADR-014 §3.5 audit trail).
- ``docs/runbooks/drift-detection.md`` and ``docs/runbooks/model-retrain.md``
  — linked from the generated ``Makefile`` and operator docs.

The old ``new-service.sh`` solved this by ``cp``-ing these files from the
repo root into each scaffold at generation time. Under Copier there is no
such copy step — the template is the single source of truth — so the files
must physically live inside ``templates/service/``.

That creates a divergence hazard: an edit to the canonical
``scripts/audit_record.py`` would silently leave the vendored copy stale, and
every service generated thereafter would ship outdated audit logic. This gate
closes that hazard exactly like ``check_common_utils_drift.py`` and
``check_cicd_template_drift.py`` close theirs.

What this enforces
------------------
For every (canonical -> vendored) pair below, the two files must be
byte-identical. The vendored copies carry no Copier tokens (verified: zero
``{@`` / ``{%`` / ``{#`` sequences), so Copier renders them as an identity
transform and the runtime behaviour in a generated service matches the
canonical tool exactly.

Usage
-----
    python3 scripts/check_vendored_runtime_drift.py          # check (CI)
    python3 scripts/check_vendored_runtime_drift.py --fix    # resync copies

Exit codes
----------
    0 — all vendored copies are in sync (or --fix succeeded)
    1 — drift detected (a vendored copy differs from its canonical original)
    2 — internal error (a canonical source is missing)
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

# Repo root = parent of ``scripts/``.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical (repo-root) -> vendored (render-root) mapping. Paths are relative
# to REPO_ROOT. Keep this list in sync with what a generated service invokes;
# add a pair here whenever a new repo-root tool becomes a runtime dependency
# of the scaffolded service.
VENDORED_PAIRS: list[tuple[str, str]] = [
    # --- Runtime tools (W1.3a) ---
    (
        "scripts/audit_record.py",
        "templates/service/scripts/audit_record.py",
    ),
    (
        "scripts/validate_quality_gates.py",
        "templates/service/scripts/validate_quality_gates.py",
    ),
    (
        "docs/runbooks/drift-detection.md",
        "templates/service/docs/runbooks/drift-detection.md",
    ),
    (
        "docs/runbooks/model-retrain.md",
        "templates/service/docs/runbooks/model-retrain.md",
    ),
    # --- Agentic system scripts (W1.3b) — byte-identical ---
    (
        "scripts/sync_agentic_adapters.py",
        "templates/service/scripts/sync_agentic_adapters.py",
    ),
    (
        "scripts/validate_agentic_manifest.py",
        "templates/service/scripts/validate_agentic_manifest.py",
    ),
    (
        "scripts/validate_agentic.py",
        "templates/service/scripts/validate_agentic.py",
    ),
    (
        # Doc-coherence gate (rule 16, ADR-031). Invoked by the generated
        # Makefile (`make doc-coherence`); context-adaptive so it runs
        # correctly inside a scaffolded service that tracks no VERSION/CHANGELOG.
        "scripts/check_doc_coherence.py",
        "templates/service/scripts/check_doc_coherence.py",
    ),
    (
        # The expiry authority for `.security-baselines/`. Vendored 2026-09-07
        # so a scaffolded service can hold itself to the same IaC gate. The
        # template repo ran trivy at LOW while the service ran at HIGH, and
        # the stated reason was that the service had nowhere to record an
        # accepted finding — a fixable gap, not a reason.
        "scripts/check_baselines_expiry.py",
        "templates/service/scripts/check_baselines_expiry.py",
    ),
    (
        "scripts/ci_verify_yaml.py",
        "templates/service/scripts/ci_verify_yaml.py",
    ),
    (
        "scripts/ci_verify_targeted.py",
        "templates/service/scripts/ci_verify_targeted.py",
    ),
    (
        "scripts/generate_report.py",
        "templates/service/scripts/generate_report.py",
    ),
    (
        # Kubernetes manifest validator. Vendored 2026-09-07 so the template
        # repo and a generated service validate the same tree with the same
        # rules: before this, the repo checked 7 of 14 base manifests and no
        # overlay, and the service's overlay steps were `continue-on-error`
        # loops over globs that missed the `batch-only` overlay. Byte-identity
        # is the point — a validator that differs between the two is how a
        # template ends up shipping a bar it does not hold itself to.
        "scripts/validate_k8s_manifests.sh",
        "templates/service/scripts/validate_k8s_manifests.sh",
    ),
    # --- Agentic system config (W1.3b) — byte-identical ---
    (
        "templates/config/context.schema.json",
        "templates/service/config/context.schema.json",
    ),
    (
        # Adopter/infra context (ADR-029 Wave 3, template-onboard skill) — a
        # distinct shape from context.schema.json (ADR-023 company/project
        # risk context). Kept as its own pair to avoid conflating the two.
        "templates/config/adopter_context.schema.json",
        "templates/service/config/adopter_context.schema.json",
    ),
    (
        "templates/config/company_context.example.yaml",
        "templates/service/config/company_context.example.yaml",
    ),
    (
        "templates/config/project_context.example.yaml",
        "templates/service/config/project_context.example.yaml",
    ),
    (
        # ML-problem spec (ADR-041, new-service-spec skill) — a third,
        # distinct shape: neither company/project risk context (ADR-023)
        # nor infra wiring (ADR-029) but the ML problem definition itself.
        "templates/config/service_spec.schema.json",
        "templates/service/config/service_spec.schema.json",
    ),
    (
        "templates/config/service_spec.example.yaml",
        "templates/service/config/service_spec.example.yaml",
    ),
    (
        "templates/config/report_schema.json",
        "templates/service/config/report_schema.json",
    ),
    (
        "templates/config/model_routing_policy.yaml",
        "templates/service/config/model_routing_policy.yaml",
    ),
    (
        "templates/config/mcp_registry.yaml",
        "templates/service/config/mcp_registry.yaml",
    ),
    (
        "templates/config/surface_capabilities.yaml",
        "templates/service/config/surface_capabilities.yaml",
    ),
    # --- Key ADRs referenced by the manifest (W1.3b) — byte-identical ---
    (
        "docs/decisions/ADR-010-dynamic-behavior-protocol.md",
        "templates/service/docs/decisions/ADR-010-dynamic-behavior-protocol.md",
    ),
    (
        "docs/decisions/ADR-014-gap-remediation-plan.md",
        "templates/service/docs/decisions/ADR-014-gap-remediation-plan.md",
    ),
    (
        "docs/decisions/ADR-018-operational-memory-plane.md",
        "templates/service/docs/decisions/ADR-018-operational-memory-plane.md",
    ),
    (
        "docs/decisions/ADR-019-agentic-ci-self-healing.md",
        "templates/service/docs/decisions/ADR-019-agentic-ci-self-healing.md",
    ),
    (
        "docs/decisions/ADR-023-agentic-portability-and-context.md",
        "templates/service/docs/decisions/ADR-023-agentic-portability-and-context.md",
    ),
    # --- Agentic identity files (W1.3b) — byte-identical ---
    (
        "AGENTS.md",
        "templates/service/AGENTS.md",
    ),
    (
        "AGENT_CONTEXT.md",
        "templates/service/AGENT_CONTEXT.md",
    ),
    (
        ".devin_context.md",
        "templates/service/.devin_context.md",
    ),
    (
        ".cursor_context.md",
        "templates/service/.cursor_context.md",
    ),
    (
        ".claude_context.md",
        "templates/service/.claude_context.md",
    ),
    (
        ".codex_context.md",
        "templates/service/.codex_context.md",
    ),
]

# Directory pairs — every file inside the canonical dir must have a
# byte-identical counterpart at the same relative path under the vendored dir.
VENDORED_DIRS: list[tuple[str, str]] = [
    # The canonical agentic store (ADR-027) — 43 files across rules/skills/workflows.
    ("agentic", "templates/service/agentic"),
]

# Files that are intentionally NOT byte-identical (service-adapted paths).
# Listed here for documentation; not checked. A separate structural check
# could verify these in the future.
ADAPTED_FILES: list[tuple[str, str]] = [
    ("templates/config/agentic_manifest.yaml", "templates/service/config/agentic_manifest.yaml"),
    ("templates/config/ci_autofix_policy.yaml", "templates/service/config/ci_autofix_policy.yaml"),
    ("scripts/ci_verify_workflows.py", "templates/service/scripts/ci_verify_workflows.py"),
]


def _check(canonical: Path, vendored: Path) -> str | None:
    """Return a human-readable drift reason, or None when in sync."""
    if not canonical.exists():
        raise FileNotFoundError(f"canonical source missing: {canonical}")
    if not vendored.exists():
        return f"vendored copy missing: {vendored}"
    if not filecmp.cmp(canonical, vendored, shallow=False):
        return f"vendored copy differs from canonical: {vendored}"
    return None


def _check_dir(canonical_dir: Path, vendored_dir: Path) -> list[str]:
    """Return a list of drift reasons for every file in the directory pair."""
    reasons: list[str] = []
    for canonical_file in sorted(canonical_dir.rglob("*")):
        if not canonical_file.is_file():
            continue
        rel = canonical_file.relative_to(canonical_dir)
        vendored_file = vendored_dir / rel
        reason = _check(canonical_file, vendored_file)
        if reason is not None:
            reasons.append(reason)
    # Check for extra files in vendored dir that don't exist in canonical
    if vendored_dir.exists():
        for vendored_file in sorted(vendored_dir.rglob("*")):
            if not vendored_file.is_file():
                continue
            rel = vendored_file.relative_to(vendored_dir)
            canonical_file = canonical_dir / rel
            if not canonical_file.exists():
                reasons.append(f"vendored file has no canonical source: {vendored_file}")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Resync vendored copies from their canonical originals.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    fixed: list[str] = []

    for canonical_rel, vendored_rel in VENDORED_PAIRS:
        canonical = REPO_ROOT / canonical_rel
        vendored = REPO_ROOT / vendored_rel
        try:
            reason = _check(canonical, vendored)
        except FileNotFoundError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 2

        if reason is None:
            continue

        if args.fix:
            vendored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(canonical, vendored)
            fixed.append(vendored_rel)
        else:
            failures.append(reason)

    for canonical_rel, vendored_rel in VENDORED_DIRS:
        canonical_dir = REPO_ROOT / canonical_rel
        vendored_dir = REPO_ROOT / vendored_rel
        if not canonical_dir.exists():
            sys.stderr.write(f"ERROR: canonical source dir missing: {canonical_dir}\n")
            return 2

        if args.fix:
            for canonical_file in sorted(canonical_dir.rglob("*")):
                if not canonical_file.is_file():
                    continue
                rel = canonical_file.relative_to(canonical_dir)
                vendored_file = vendored_dir / rel
                vendored_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(canonical_file, vendored_file)
                fixed.append(str(vendored_file.relative_to(REPO_ROOT)))
        else:
            dir_failures = _check_dir(canonical_dir, vendored_dir)
            failures.extend(dir_failures)

    if args.fix:
        if fixed:
            sys.stdout.write("[vendored-drift] resynced:\n")
            for path in fixed:
                sys.stdout.write(f"  - {path}\n")
        else:
            sys.stdout.write("[vendored-drift] OK — nothing to resync.\n")
        return 0

    if failures:
        sys.stderr.write(
            "FAIL: vendored runtime files drifted from their canonical "
            "originals.\n"
            "These files are vendored into templates/service/ because Copier "
            "renders only that subtree, yet a generated service needs them at "
            "runtime (see module docstring).\n\n"
        )
        for reason in failures:
            sys.stderr.write(f"  - {reason}\n")
        sys.stderr.write("\nFix: python3 scripts/check_vendored_runtime_drift.py --fix\n")
        return 1

    sys.stdout.write(
        f"[vendored-drift] OK — {len(VENDORED_PAIRS)} vendored file(s) and "
        f"{len(VENDORED_DIRS)} vendored director(y/ies) match their canonical originals.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
