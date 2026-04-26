"""Inter-agent handoff contract.

Defines the typed data contracts that specialist agents pass to each other.
Using dataclasses instead of JSON Schema — equivalent contract, 10× less code,
and directly usable in Python (AGENTS.md anti-pattern #over-engineering).

Usage:
    from common_utils.agent_context import TrainingArtifact, DeploymentRequest

    # Agent-MLTrainer produces:
    artifact = TrainingArtifact(
        service_name="fraud_detector",
        model_path="artifacts/model.joblib",
        model_sha256="abc123...",
        mlflow_run_id="runs:/abc",
        metrics={"auc": 0.89, "f1": 0.84},
        fairness_dir=0.92,
        quality_gates_passed=True,
    )

    # Agent-DockerBuilder consumes:
    build_request = DockerBuildRequest.from_training(artifact, base_image="python:3.11-slim")

    # Agent-K8sBuilder consumes:
    deploy_request = DeploymentRequest.from_build(build_result, environment="staging")

Invariants:
    - Every handoff artifact is validated at construction (fail-fast)
    - Required fields are enforced by dataclass (no None defaults for critical state)
    - Agents must NOT mutate a received artifact — create a new one via factory methods
    - Audit trail is emitted automatically via to_audit_entry()
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════
# Common types
# ═══════════════════════════════════════════════════════════════════


class AgentMode(str, Enum):
    """Behavior protocol modes per AGENTS.md."""

    AUTO = "AUTO"
    CONSULT = "CONSULT"
    STOP = "STOP"


class Environment(str, Enum):
    """Deployment environments with ordered trust (local < dev < staging < prod)."""

    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_DIGEST_PATTERN = re.compile(r"^[^@]+@sha256:[a-f0-9]{64}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════
# Agent-EDAProfiler → Agent-MLTrainer
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class EDAHandoff:
    """Artifacts produced by Agent-EDAProfiler, consumed by Agent-MLTrainer."""

    service_name: str
    dataset_path: str
    target_column: str
    baseline_distributions_path: str  # eda/artifacts/02_baseline_distributions.pkl
    feature_proposals_path: str  # eda/artifacts/05_feature_proposals.yaml
    schema_proposal_path: str  # src/<service>/schema_proposal.py
    leakage_gate_passed: bool  # False = STOP — chain to /incident
    blocked_features: list[str] = field(default_factory=list)
    n_rows: int = 0
    n_features: int = 0
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.leakage_gate_passed and not self.blocked_features:
            raise ValueError("EDAHandoff: leakage_gate_passed=False requires at least one blocked feature")
        if self.leakage_gate_passed and self.blocked_features:
            raise ValueError("EDAHandoff: leakage_gate_passed=True conflicts with non-empty blocked_features")


# ═══════════════════════════════════════════════════════════════════
# Agent-MLTrainer → Agent-DockerBuilder
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TrainingArtifact:
    """Artifacts produced by Agent-MLTrainer, consumed by Agent-DockerBuilder."""

    service_name: str
    model_path: str
    model_sha256: str
    mlflow_run_id: str
    metrics: dict[str, float]
    fairness_dir: float  # Disparate Impact Ratio — must be >= 0.80 to pass
    quality_gates_passed: bool
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not _SHA256_PATTERN.match(self.model_sha256):
            raise ValueError(f"model_sha256 must be hex sha256, got: {self.model_sha256!r}")
        if not 0 <= self.fairness_dir <= 2:
            raise ValueError(f"fairness_dir out of sane range [0, 2]: {self.fairness_dir}")

    def requires_consult(self) -> bool:
        """Does this artifact require CONSULT mode before downstream processing?"""
        return 0.80 <= self.fairness_dir < 0.85 or any(  # marginal fairness
            v > 0.99 for v in self.metrics.values()
        )  # D-06 suspicion


# ═══════════════════════════════════════════════════════════════════
# Agent-DockerBuilder → Agent-SecurityAuditor → Agent-K8sBuilder
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BuildArtifact:
    """Artifacts produced by Agent-DockerBuilder, consumed by Agent-SecurityAuditor."""

    service_name: str
    image_ref: str  # e.g., "us-docker.pkg.dev/proj/fraud-detector@sha256:..."
    image_digest: str  # sha256:...
    sbom_path: str  # CycloneDX JSON
    trivy_report_path: str
    training_artifact: TrainingArtifact
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not _IMAGE_DIGEST_PATTERN.match(self.image_ref):
            raise ValueError(f"image_ref must be digest-pinned: {self.image_ref!r}")


@dataclass(frozen=True)
class SecurityAuditResult:
    """Artifacts produced by Agent-SecurityAuditor, consumed by Agent-K8sBuilder."""

    service_name: str
    image_ref: str
    signature_verified: bool  # Cosign verify passed
    sbom_attested: bool  # SBOM attached as attestation
    trivy_critical: int
    trivy_high: int
    gitleaks_findings: int
    iam_least_privilege_verified: bool
    passed: bool  # overall gate
    findings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        # Derive `passed` from components — prevents inconsistent state.
        # Audit High-5: trivy_high must also be zero. The security-audit skill
        # declares HIGH+CRITICAL as blocking; without the explicit check here,
        # a HIGH finding could pass the gate even though the skill said it
        # shouldn't.
        computed = (
            self.signature_verified
            and self.sbom_attested
            and self.trivy_critical == 0
            and self.trivy_high == 0
            and self.gitleaks_findings == 0
            and self.iam_least_privilege_verified
        )
        if self.passed != computed:
            raise ValueError(
                "SecurityAuditResult.passed "
                f"({self.passed}) inconsistent with components ({computed}). "
                "Components: signature_verified={}, sbom_attested={}, "
                "trivy_critical={}, trivy_high={}, gitleaks_findings={}, "
                "iam_least_privilege_verified={}".format(
                    self.signature_verified,
                    self.sbom_attested,
                    self.trivy_critical,
                    self.trivy_high,
                    self.gitleaks_findings,
                    self.iam_least_privilege_verified,
                )
            )


@dataclass(frozen=True)
class DeploymentRequest:
    """Artifacts produced by Agent-K8sBuilder, submitted to the cluster."""

    service_name: str
    environment: Environment
    image_ref: str
    kustomize_overlay: str
    security_audit: SecurityAuditResult
    required_mode: AgentMode  # AUTO for dev, CONSULT for staging, STOP for prod
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.environment == Environment.PRODUCTION and self.required_mode != AgentMode.STOP:
            raise ValueError(f"Production deployments must require STOP mode (got {self.required_mode})")
        if self.environment == Environment.PRODUCTION and not self.security_audit.passed:
            raise ValueError("Production deploy blocked: security audit did not pass")


# ═══════════════════════════════════════════════════════════════════
# Audit trail
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AuditEntry:
    """Single append-only audit log entry for an agentic operation."""

    agent: str  # e.g., "Agent-DockerBuilder"
    operation: str  # e.g., "build_image"
    environment: Environment
    mode: AgentMode
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    approver: str | None = None  # populated when mode in {CONSULT, STOP}
    result: str = "success"  # success | failure | halted
    risk_signals: list[str] = field(default_factory=list)  # ADR-010 signals present at op time
    base_mode: AgentMode | None = None  # mode before dynamic escalation; None if same as `mode`
    timestamp: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.result not in {"success", "failure", "halted"}:
            raise ValueError(f"result must be success|failure|halted, got {self.result!r}")
        if self.mode in {AgentMode.CONSULT, AgentMode.STOP} and self.result == "success" and not self.approver:
            # Non-AUTO success requires a recorded approver — human accountability.
            raise ValueError(f"mode={self.mode.value} success entry must record an approver")

    def to_jsonl(self) -> str:
        """Append-safe JSON lines representation for ops log."""
        d = asdict(self)
        d["environment"] = self.environment.value
        d["mode"] = self.mode.value
        if self.base_mode is not None:
            d["base_mode"] = self.base_mode.value
        else:
            d.pop("base_mode", None)
        return json.dumps(d, sort_keys=True)


# ═══════════════════════════════════════════════════════════════════
# Append-only audit log writer (ops/audit.jsonl)
# ═══════════════════════════════════════════════════════════════════
class AuditLog:
    """Append-only JSONL writer for `ops/audit.jsonl`.

    Thread-safety: uses per-instance lock + open/append/close on each write.
    Safe for CI step summaries (which mirror this file) and for concurrent
    agents running in the same workspace.

    Usage:
        log = AuditLog()  # defaults to ops/audit.jsonl
        log.append(AuditEntry(...))

        # Or from a risk-scored operation:
        from common_utils.risk_context import get_risk_context
        ctx = get_risk_context()
        final_mode = ctx.escalate(AgentMode.AUTO)
        log.record_operation(
            agent="Agent-MLTrainer",
            operation="train_model",
            environment=Environment.STAGING,
            base_mode=AgentMode.AUTO,
            final_mode=final_mode,
            risk_context=ctx,
            inputs={"dataset_sha": "..."},
            outputs={"run_id": "..."},
        )
    """

    def __init__(self, path: str = "ops/audit.jsonl") -> None:
        self.path = path
        import threading

        self._lock = threading.Lock()

    def append(self, entry: AuditEntry) -> None:
        """Append a single AuditEntry to the log. Parent dir auto-created."""
        import os

        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(entry.to_jsonl() + "\n")

    def record_operation(
        self,
        *,
        agent: str,
        operation: str,
        environment: Environment,
        base_mode: AgentMode,
        final_mode: AgentMode,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        risk_context: Any = None,  # common_utils.risk_context.RiskContext or None
        approver: str | None = None,
        result: str = "success",
    ) -> AuditEntry:
        """Record an operation and return the persisted entry.

        Extracts active signals from `risk_context` if provided. Keeps
        `base_mode` only if it differs from `final_mode` (reduces noise).
        """
        signals: list[str] = []
        if risk_context is not None:
            for name in (
                "incident_active",
                "drift_severe",
                "error_budget_exhausted",
                "off_hours",
                "recent_rollback",
            ):
                if getattr(risk_context, name, False):
                    signals.append(name)
            if getattr(risk_context, "available", True) is False:
                signals.append("risk_signals:UNAVAILABLE")

        entry = AuditEntry(
            agent=agent,
            operation=operation,
            environment=environment,
            mode=final_mode,
            inputs=inputs,
            outputs=outputs,
            approver=approver,
            result=result,
            risk_signals=signals,
            base_mode=base_mode if base_mode != final_mode else None,
        )
        self.append(entry)
        return entry

    def read_all(self) -> list[dict[str, Any]]:
        """Load all entries (for audits/reports). Returns [] if no file."""
        import os

        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


__all__ = [
    "AgentMode",
    "Environment",
    "EDAHandoff",
    "TrainingArtifact",
    "BuildArtifact",
    "SecurityAuditResult",
    "DeploymentRequest",
    "AuditEntry",
    "AuditLog",
]
