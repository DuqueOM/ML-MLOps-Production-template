#!/usr/bin/env python3
"""MCP registry doctor — ADR-023 F4.

READ-ONLY diagnostic. Never installs, never writes an MCP config,
never reaches the network. Three modes:

    mcp-check       — fast pass/fail (exit 0 / 1) for CI.
    mcp-doctor      — long-form report (missing configs, orphans,
                      install matrix) for humans.
    mcp-render-docs — regenerates docs/agentic/mcp-portability.md
                      tables from the registry YAMLs. The only
                      writer in this script; limited to the docs file.

Invariants enforced
-------------------

I-3 (ADR-023 §3) — install is never automatic. This script enforces
that surface by design: there are no install entry points; every
command is read-only.

Cross-check consistency
  * Every `required_for` / `recommended_for` entry in mcp_registry.yaml
    references a skill id present in agentic_manifest.yaml.
  * Every surface in mcp_registry.surfaces is also declared in
    surface_capabilities.yaml.
  * Every MCP's install_mode covers every surface declared in
    surface_capabilities.yaml (missing surface → skill orphan).
  * Every skill/workflow's requires
    (surface_capabilities.skill_capability_requirements) is supported
    by every surface claiming the action in
    agentic_manifest.yaml.

Usage
-----

    make mcp-check                   # fast pass/fail
    make mcp-doctor                  # long-form report
    python3 scripts/mcp_doctor.py --mode check
    python3 scripts/mcp_doctor.py --mode doctor --json
    python3 scripts/mcp_doctor.py --mode render-docs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_REGISTRY = REPO_ROOT / "templates" / "config" / "mcp_registry.yaml"
SURFACES = REPO_ROOT / "templates" / "config" / "surface_capabilities.yaml"
MANIFEST = REPO_ROOT / "templates" / "config" / "agentic_manifest.yaml"
DOCS_FILE = REPO_ROOT / "docs" / "agentic" / "mcp-portability.md"


try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - bootstrap guard
    print("error: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: not a YAML mapping")
    return data


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _collect_errors(registry: dict, surfaces: dict, manifest: dict) -> dict[str, list[str]]:
    """Return a mapping of check-name → list of human error strings."""
    errors: dict[str, list[str]] = {
        "skill_references": [],
        "surface_symmetry": [],
        "install_matrix": [],
        "capability_support": [],
    }
    known_skills = {s["id"] for s in manifest.get("skills") or []}
    known_workflows = {w["id"] for w in manifest.get("workflows") or []}
    known_actions = known_skills | known_workflows

    # 1) Every required_for / recommended_for ref resolves to a skill or workflow.
    for mcp_id, spec in (registry.get("mcps") or {}).items():
        for key in ("required_for", "recommended_for"):
            for ref in spec.get(key) or []:
                if ref not in known_actions:
                    errors["skill_references"].append(
                        f"mcps.{mcp_id}.{key}: references unknown skill/workflow {ref!r} (not in agentic_manifest.yaml)"
                    )

    # 2) Every surface in mcp_registry is also in surface_capabilities
    #    and vice versa.
    reg_surfaces = set((registry.get("surfaces") or {}).keys())
    cap_surfaces = set((surfaces.get("surfaces") or {}).keys())
    for s in reg_surfaces - cap_surfaces:
        errors["surface_symmetry"].append(f"surfaces.{s}: in mcp_registry but missing from surface_capabilities.yaml")
    for s in cap_surfaces - reg_surfaces:
        errors["surface_symmetry"].append(f"surfaces.{s}: in surface_capabilities but missing from mcp_registry.yaml")

    # 3) Every MCP's install_mode covers every known surface.
    for mcp_id, spec in (registry.get("mcps") or {}).items():
        im = spec.get("install_mode") or {}
        for s in cap_surfaces:
            if s not in im:
                errors["install_matrix"].append(f"mcps.{mcp_id}.install_mode: missing entry for surface {s!r}")

    # 4) Every skill/workflow's required capabilities are supported by
    #    every surface that claims the action.
    overrides = surfaces.get("skill_capability_requirements", {}).get("overrides") or {}
    default_req = set(surfaces.get("skill_capability_requirements", {}).get("default", {}).get("requires") or [])
    surface_supports = {s: set((spec.get("supports") or [])) for s, spec in (surfaces.get("surfaces") or {}).items()}
    actions = [("skills", item) for item in (manifest.get("skills") or [])] + [
        ("workflows", item) for item in (manifest.get("workflows") or [])
    ]
    for kind, action in actions:
        sid = action.get("id")
        reqs = set((overrides.get(sid) or {}).get("requires") or default_req)
        for surface in action.get("surfaces") or []:
            supports = surface_supports.get(surface)
            if supports is None:
                # Caught by surface_symmetry; avoid double-reporting.
                continue
            missing = reqs - supports
            if missing:
                errors["capability_support"].append(
                    f"{kind}.{sid}: surface {surface!r} does not support required capabilities {sorted(missing)}"
                )

    return errors


# ---------------------------------------------------------------------------
# Long-form report
# ---------------------------------------------------------------------------


def _render_doctor(registry: dict, surfaces: dict, manifest: dict, errors: dict[str, list[str]]) -> str:
    buf: list[str] = []
    buf.append("MCP Doctor — full report")
    buf.append("=" * 50)
    buf.append("")
    buf.append(f"Registry: {MCP_REGISTRY.relative_to(REPO_ROOT)}")
    buf.append(f"Surfaces: {SURFACES.relative_to(REPO_ROOT)}")
    buf.append(f"Manifest: {MANIFEST.relative_to(REPO_ROOT)}")
    buf.append("")

    # MCPs summary
    buf.append("MCPs registered")
    buf.append("-" * 50)
    for mcp_id, spec in (registry.get("mcps") or {}).items():
        required = ", ".join(spec.get("required_for") or []) or "-"
        buf.append(f"  {mcp_id:<12} risk={spec.get('risk_mode'):<8} required_for={required}")
    buf.append("")

    # Install matrix
    buf.append("Install-mode matrix (surfaces × MCPs)")
    buf.append("-" * 50)
    surfs = sorted((surfaces.get("surfaces") or {}).keys())
    header = "  " + "MCP".ljust(14) + " | " + " | ".join(s.ljust(14) for s in surfs)
    buf.append(header)
    buf.append("  " + "-" * (len(header) - 2))
    for mcp_id, spec in (registry.get("mcps") or {}).items():
        im = spec.get("install_mode") or {}
        row = "  " + mcp_id.ljust(14) + " | "
        row += " | ".join(str(im.get(s, "-")).ljust(14) for s in surfs)
        buf.append(row)
    buf.append("")

    # Skill coverage
    buf.append("Skill coverage")
    buf.append("-" * 50)
    overrides = surfaces.get("skill_capability_requirements", {}).get("overrides") or {}
    for skill in manifest.get("skills") or []:
        sid = skill.get("id")
        reqs = (overrides.get(sid) or {}).get("requires") or ["read_file"]
        buf.append(f"  {sid:<30} requires={reqs} surfaces={skill.get('surfaces')}")
    buf.append("")

    # Errors
    total = sum(len(v) for v in errors.values())
    if total == 0:
        buf.append("[PASS] 0 issues found")
    else:
        buf.append(f"[FAIL] {total} issue(s) found")
        for check, items in errors.items():
            if items:
                buf.append(f"  {check}:")
                for it in items:
                    buf.append(f"    - {it}")
    return "\n".join(buf)


# ---------------------------------------------------------------------------
# Docs renderer
# ---------------------------------------------------------------------------


def _render_docs(registry: dict, surfaces: dict, manifest: dict) -> str:
    buf: list[str] = []
    buf.append("<!-- Generated by scripts/mcp_doctor.py --mode render-docs. -->")
    buf.append("<!-- DO NOT EDIT BELOW. Re-run the script after registry changes. -->")
    buf.append("")
    buf.append("## MCP Portability Matrix")
    buf.append("")
    buf.append("Source: `templates/config/mcp_registry.yaml` + `templates/config/surface_capabilities.yaml`.")
    buf.append("")
    buf.append("## Registered MCPs")
    buf.append("")
    buf.append("| MCP | Purpose | Risk | Required for |")
    buf.append("|-----|---------|------|--------------|")
    for mcp_id, spec in (registry.get("mcps") or {}).items():
        required = ", ".join(f"`{r}`" for r in (spec.get("required_for") or [])) or "—"
        buf.append(
            f"| `{mcp_id}` | {spec.get('purpose', '').strip()} | `{spec.get('risk_mode', 'AUTO')}` | {required} |"
        )
    buf.append("")
    buf.append("## Install mode by surface")
    buf.append("")
    surfs = sorted((surfaces.get("surfaces") or {}).keys())
    buf.append("| MCP | " + " | ".join(surfs) + " |")
    buf.append("|-----|" + "|".join("---" for _ in surfs) + "|")
    for mcp_id, spec in (registry.get("mcps") or {}).items():
        im = spec.get("install_mode") or {}
        cells = [str(im.get(s, "—")) for s in surfs]
        buf.append(f"| `{mcp_id}` | " + " | ".join(cells) + " |")
    buf.append("")
    return "\n".join(buf)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mode",
        choices=["check", "doctor", "render-docs"],
        default="check",
        help=(
            "check = pass/fail; doctor = long-form report; "
            "render-docs = overwrite mcp-portability.md generated section."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit structured JSON for check/doctor modes",
    )
    parser.add_argument(
        "--render",
        choices=["docs"],
        default=None,
        help="backward-compat shortcut for --mode render-docs",
    )
    args = parser.parse_args()
    if args.render == "docs":
        args.mode = "render-docs"

    registry = _load_yaml(MCP_REGISTRY)
    surfaces = _load_yaml(SURFACES)
    manifest = _load_yaml(MANIFEST)

    if args.mode == "render-docs":
        docs_body = _render_docs(registry, surfaces, manifest)
        # Preserve any human-authored prelude above the generated marker.
        if DOCS_FILE.exists():
            existing = DOCS_FILE.read_text(encoding="utf-8")
            marker = "<!-- Generated by scripts/mcp_doctor.py"
            if marker in existing:
                prelude = existing.split(marker, 1)[0]
            else:
                prelude = existing + "\n"
        else:
            DOCS_FILE.parent.mkdir(parents=True, exist_ok=True)
            prelude = ""
        DOCS_FILE.write_text(prelude + docs_body + "\n", encoding="utf-8")
        print(f"wrote {DOCS_FILE.relative_to(REPO_ROOT)}")
        return 0

    errors = _collect_errors(registry, surfaces, manifest)
    total = sum(len(v) for v in errors.values())

    if args.mode == "check":
        if args.json:
            print(json.dumps({"errors": errors, "total": total}, indent=2))
        else:
            for check, items in errors.items():
                if items:
                    print(f"[FAIL] {check}", file=sys.stderr)
                    for it in items:
                        print(f"  - {it}", file=sys.stderr)
                else:
                    print(f"[ OK ] {check}")
        return 0 if total == 0 else 1

    # doctor mode
    report = _render_doctor(registry, surfaces, manifest, errors)
    if args.json:
        print(json.dumps({"report": report, "errors": errors, "total": total}, indent=2))
    else:
        print(report)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
