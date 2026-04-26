#!/usr/bin/env python3
"""Append a structured audit entry from a CI step or local skill execution.

This is the CLI surface of `common_utils.agent_context.AuditLog.record_operation`.
CI steps invoke it at the end of agentic operations (deploy, retrain,
rollback, etc.) so `ops/audit.jsonl` reflects what actually happened —
not just what the docs said the agent should record.

Usage::

    python scripts/audit_record.py \\
        --agent Agent-K8sBuilder \\
        --operation deploy \\
        --environment production \\
        --base-mode CONSULT \\
        --final-mode STOP \\
        --result success \\
        --inputs '{"cloud":"gcp","cluster":"prod-1","version":"v1.9.0"}' \\
        --outputs '{"image":"registry/svc@sha256:...","sbom_attached":true}' \\
        --approver "alice-techlead"

In a GitHub Actions step::

    - name: Emit audit entry
      if: always()
      run: |
        python scripts/audit_record.py \\
          --agent "Agent-K8sBuilder" \\
          --operation "${{ inputs.cloud }}-${{ inputs.environment }}-deploy" \\
          --environment "${{ inputs.environment }}" \\
          --base-mode "${{ inputs.environment == 'production' && 'STOP' || 'CONSULT' }}" \\
          --final-mode "${{ inputs.environment == 'production' && 'STOP' || 'CONSULT' }}" \\
          --result "${{ job.status }}" \\
          --inputs '{"cloud":"${{ inputs.cloud }}","version":"${{ inputs.version }}"}' \\
          --outputs '{"overlay":"${{ inputs.overlay_path }}"}'

The script also writes a markdown summary to `$GITHUB_STEP_SUMMARY` if
that environment variable is set, so the audit shows up directly in
the PR / workflow UI without leaving the CI page.

Exit codes:
    0 — entry recorded
    1 — invalid inputs
    2 — file system error (audit log not writable)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _normalize_environment(value: str) -> str:
    """Map CI environment strings to the Environment enum names."""
    canonical = value.lower().strip()
    if canonical in ("dev", "development", "develop"):
        return "DEV"
    if canonical in ("staging", "stage", "preprod"):
        return "STAGING"
    if canonical in ("prod", "production"):
        return "PRODUCTION"
    if canonical in ("local",):
        return "LOCAL"
    return value.upper()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--agent", required=True, help="Agent identifier (e.g., Agent-K8sBuilder)")
    parser.add_argument("--operation", required=True, help="Operation name (free-form short slug)")
    parser.add_argument(
        "--environment",
        required=True,
        help="dev | staging | production | local",
    )
    parser.add_argument(
        "--base-mode",
        required=True,
        choices=["AUTO", "CONSULT", "STOP"],
        help="Static mode from authorization_mode",
    )
    parser.add_argument(
        "--final-mode",
        required=True,
        choices=["AUTO", "CONSULT", "STOP"],
        help="Effective mode after dynamic escalation (ADR-010)",
    )
    parser.add_argument(
        "--result",
        default="success",
        help="success | failure | halted | skipped (or job.status from CI)",
    )
    parser.add_argument(
        "--inputs",
        default="{}",
        help="JSON object describing operation inputs",
    )
    parser.add_argument(
        "--outputs",
        default="{}",
        help="JSON object describing operation outputs",
    )
    parser.add_argument(
        "--approver",
        default=None,
        help="GitHub user that approved (CONSULT/STOP modes only)",
    )
    parser.add_argument(
        "--audit-log",
        default="ops/audit.jsonl",
        help="Path to the audit log file",
    )
    args = parser.parse_args()

    # Late import: the helpers live inside templates/, so allow callers to
    # set TEMPLATE_PATH or rely on PYTHONPATH=.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates"))
    try:
        from common_utils.agent_context import AgentMode, AuditLog, Environment
    except ImportError as exc:
        print(f"error: cannot import common_utils.agent_context ({exc})", file=sys.stderr)
        print("hint: run from repo root or set PYTHONPATH=templates", file=sys.stderr)
        return 1

    try:
        inputs = json.loads(args.inputs)
        outputs = json.loads(args.outputs)
    except json.JSONDecodeError as exc:
        print(f"error: --inputs/--outputs must be valid JSON ({exc})", file=sys.stderr)
        return 1

    env_name = _normalize_environment(args.environment)
    try:
        environment = getattr(Environment, env_name)
    except AttributeError:
        print(f"error: unknown environment {env_name!r}", file=sys.stderr)
        return 1

    try:
        base_mode = getattr(AgentMode, args.base_mode)
        final_mode = getattr(AgentMode, args.final_mode)
    except AttributeError as exc:
        print(f"error: unknown mode ({exc})", file=sys.stderr)
        return 1

    # Map CI status strings to AuditEntry.result vocabulary.
    result_map = {"success": "success", "failure": "failure", "cancelled": "halted", "skipped": "skipped"}
    result = result_map.get(args.result.lower(), args.result)

    Path(args.audit_log).parent.mkdir(parents=True, exist_ok=True)
    log = AuditLog(path=args.audit_log)

    try:
        entry = log.record_operation(
            agent=args.agent,
            operation=args.operation,
            environment=environment,
            base_mode=base_mode,
            final_mode=final_mode,
            inputs=inputs,
            outputs=outputs,
            approver=args.approver,
            result=result,
        )
    except OSError as exc:
        print(f"error: cannot write audit log ({exc})", file=sys.stderr)
        return 2

    # Mirror to GitHub Actions step summary when running in CI.
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("### Audit entry\n")
            fh.write(f"- **agent**: `{entry.agent}`\n")
            fh.write(f"- **operation**: `{entry.operation}`\n")
            fh.write(f"- **environment**: `{entry.environment.name}`\n")
            fh.write(f"- **mode**: `{entry.mode.value}`")
            if entry.base_mode and entry.base_mode != entry.mode:
                fh.write(f" (escalated from `{entry.base_mode.value}`)")
            fh.write("\n")
            fh.write(f"- **result**: `{entry.result}`\n")
            if entry.approver:
                fh.write(f"- **approver**: `{entry.approver}`\n")
            if entry.risk_signals:
                fh.write(f"- **signals**: {', '.join(entry.risk_signals)}\n")

    print(f"audit entry recorded: {args.operation} → {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
