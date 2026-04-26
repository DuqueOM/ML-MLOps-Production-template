"""Unit tests for agent_context — typed handoffs + AuditLog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_COMMON = Path(__file__).resolve().parents[2] / "common_utils"
sys.path.insert(0, str(_COMMON.parent))

from common_utils.agent_context import (  # noqa: E402
    AgentMode,
    AuditEntry,
    AuditLog,
    BuildArtifact,
    DeploymentRequest,
    EDAHandoff,
    Environment,
    SecurityAuditResult,
    TrainingArtifact,
)
from common_utils.risk_context import RiskContext  # noqa: E402


# ---------------------------------------------------------------------------
# EDAHandoff
# ---------------------------------------------------------------------------
class TestEDAHandoff:
    def _valid_kwargs(self, **overrides):
        return {
            "service_name": "fraud_detector",
            "dataset_path": "data/raw/train.parquet",
            "target_column": "is_fraud",
            "baseline_distributions_path": "eda/artifacts/02_baseline.pkl",
            "feature_proposals_path": "eda/artifacts/05_features.yaml",
            "schema_proposal_path": "src/fraud_detector/schema_proposal.py",
            "leakage_gate_passed": True,
            **overrides,
        }

    def test_valid_construction(self):
        h = EDAHandoff(**self._valid_kwargs())
        assert h.leakage_gate_passed is True
        assert h.blocked_features == []

    def test_gate_failed_without_blocked_features_rejects(self):
        with pytest.raises(ValueError, match="leakage_gate_passed=False"):
            EDAHandoff(**self._valid_kwargs(leakage_gate_passed=False))

    def test_gate_passed_with_blocked_features_rejects(self):
        with pytest.raises(ValueError, match="conflicts"):
            EDAHandoff(**self._valid_kwargs(blocked_features=["target_next_day"]))


# ---------------------------------------------------------------------------
# TrainingArtifact
# ---------------------------------------------------------------------------
class TestTrainingArtifact:
    def _artifact(self, **overrides):
        return TrainingArtifact(
            **{
                "service_name": "fraud_detector",
                "model_path": "artifacts/model.joblib",
                "model_sha256": "a" * 64,
                "mlflow_run_id": "runs:/abc",
                "metrics": {"auc": 0.89, "f1": 0.84},
                "fairness_dir": 0.92,
                "quality_gates_passed": True,
                **overrides,
            }
        )

    def test_valid(self):
        art = self._artifact()
        assert art.fairness_dir == 0.92

    def test_bad_sha256_rejected(self):
        with pytest.raises(ValueError, match="sha256"):
            self._artifact(model_sha256="not-a-sha")

    def test_fairness_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="fairness_dir"):
            self._artifact(fairness_dir=3.0)

    def test_requires_consult_on_marginal_fairness(self):
        assert self._artifact(fairness_dir=0.82).requires_consult() is True

    def test_requires_consult_on_suspiciously_high_metric(self):
        assert self._artifact(metrics={"auc": 0.995}).requires_consult() is True

    def test_no_consult_on_healthy_artifact(self):
        assert self._artifact().requires_consult() is False


# ---------------------------------------------------------------------------
# BuildArtifact + SecurityAuditResult
# ---------------------------------------------------------------------------
class TestSecurityAudit:
    def _build(self):
        training = TrainingArtifact(
            service_name="s",
            model_path="m.joblib",
            model_sha256="b" * 64,
            mlflow_run_id="r",
            metrics={"auc": 0.9},
            fairness_dir=0.9,
            quality_gates_passed=True,
        )
        return BuildArtifact(
            service_name="s",
            image_ref="gcr.io/p/s@sha256:" + "c" * 64,
            image_digest="sha256:" + "c" * 64,
            sbom_path="sbom.json",
            trivy_report_path="trivy.json",
            training_artifact=training,
        )

    def test_build_requires_digest_pinned_ref(self):
        with pytest.raises(ValueError, match="digest-pinned"):
            BuildArtifact(
                service_name="s",
                image_ref="gcr.io/p/s:latest",  # no digest
                image_digest="sha256:" + "c" * 64,
                sbom_path="sbom.json",
                trivy_report_path="trivy.json",
                training_artifact=self._build().training_artifact,
            )

    def test_security_audit_passed_must_be_consistent(self):
        with pytest.raises(ValueError, match="inconsistent"):
            SecurityAuditResult(
                service_name="s",
                image_ref=self._build().image_ref,
                signature_verified=False,  # component fails
                sbom_attested=True,
                trivy_critical=0,
                trivy_high=0,
                gitleaks_findings=0,
                iam_least_privilege_verified=True,
                passed=True,  # but passed claims True → reject
            )

    def test_security_audit_high_findings_block_passed(self):
        # Audit High-5: HIGH findings now BLOCK the gate (matches what the
        # security-audit skill says). passed=True with trivy_high>0 should
        # raise ValueError because computed=False.
        with pytest.raises(ValueError, match="inconsistent"):
            SecurityAuditResult(
                service_name="s",
                image_ref=self._build().image_ref,
                signature_verified=True,
                sbom_attested=True,
                trivy_critical=0,
                trivy_high=5,
                gitleaks_findings=0,
                iam_least_privilege_verified=True,
                passed=True,
            )

    def test_security_audit_components_pass(self):
        r = SecurityAuditResult(
            service_name="s",
            image_ref=self._build().image_ref,
            signature_verified=True,
            sbom_attested=True,
            trivy_critical=0,
            trivy_high=0,  # Audit High-5: HIGH must also be zero
            gitleaks_findings=0,
            iam_least_privilege_verified=True,
            passed=True,
        )
        assert r.passed is True


# ---------------------------------------------------------------------------
# DeploymentRequest
# ---------------------------------------------------------------------------
class TestDeploymentRequest:
    def _passing_audit(self):
        digest = "sha256:" + "d" * 64
        return SecurityAuditResult(
            service_name="s",
            image_ref=f"gcr.io/p/s@{digest}",
            signature_verified=True,
            sbom_attested=True,
            trivy_critical=0,
            trivy_high=0,
            gitleaks_findings=0,
            iam_least_privilege_verified=True,
            passed=True,
        )

    def _failing_audit(self):
        digest = "sha256:" + "e" * 64
        return SecurityAuditResult(
            service_name="s",
            image_ref=f"gcr.io/p/s@{digest}",
            signature_verified=False,
            sbom_attested=False,
            trivy_critical=5,
            trivy_high=0,
            gitleaks_findings=2,
            iam_least_privilege_verified=False,
            passed=False,
        )

    def test_prod_requires_stop_mode(self):
        with pytest.raises(ValueError, match="STOP"):
            DeploymentRequest(
                service_name="s",
                environment=Environment.PRODUCTION,
                image_ref=self._passing_audit().image_ref,
                kustomize_overlay="k8s/overlays/gcp-prod",
                security_audit=self._passing_audit(),
                required_mode=AgentMode.AUTO,
            )

    def test_prod_blocks_failing_audit(self):
        with pytest.raises(ValueError, match="security audit"):
            DeploymentRequest(
                service_name="s",
                environment=Environment.PRODUCTION,
                image_ref=self._failing_audit().image_ref,
                kustomize_overlay="k8s/overlays/gcp-prod",
                security_audit=self._failing_audit(),
                required_mode=AgentMode.STOP,
            )

    def test_dev_permits_auto_mode(self):
        dr = DeploymentRequest(
            service_name="s",
            environment=Environment.DEV,
            image_ref=self._passing_audit().image_ref,
            kustomize_overlay="k8s/overlays/gcp-dev",
            security_audit=self._passing_audit(),
            required_mode=AgentMode.AUTO,
        )
        assert dr.required_mode == AgentMode.AUTO


# ---------------------------------------------------------------------------
# AuditEntry validation
# ---------------------------------------------------------------------------
class TestAuditEntry:
    def test_success_in_consult_requires_approver(self):
        with pytest.raises(ValueError, match="approver"):
            AuditEntry(
                agent="A",
                operation="op",
                environment=Environment.STAGING,
                mode=AgentMode.CONSULT,
                inputs={},
                outputs={},
            )

    def test_failure_does_not_require_approver(self):
        # A halted CONSULT op is valid without approver (we halted without action)
        e = AuditEntry(
            agent="A",
            operation="op",
            environment=Environment.STAGING,
            mode=AgentMode.CONSULT,
            inputs={},
            outputs={},
            result="halted",
        )
        assert e.result == "halted"

    def test_bad_result_rejected(self):
        with pytest.raises(ValueError):
            AuditEntry(
                agent="A",
                operation="op",
                environment=Environment.DEV,
                mode=AgentMode.AUTO,
                inputs={},
                outputs={},
                result="partial",
            )

    def test_jsonl_round_trip(self):
        e = AuditEntry(
            agent="A",
            operation="build",
            environment=Environment.DEV,
            mode=AgentMode.AUTO,
            inputs={"ref": "v1"},
            outputs={"sha": "abc"},
        )
        decoded = json.loads(e.to_jsonl())
        assert decoded["environment"] == "dev"
        assert decoded["mode"] == "AUTO"
        assert decoded["inputs"] == {"ref": "v1"}


# ---------------------------------------------------------------------------
# AuditLog file writer
# ---------------------------------------------------------------------------
class TestAuditLog:
    def test_append_creates_parent_dir(self, tmp_path):
        log = AuditLog(str(tmp_path / "nested" / "audit.jsonl"))
        log.append(
            AuditEntry(
                agent="A",
                operation="op",
                environment=Environment.DEV,
                mode=AgentMode.AUTO,
                inputs={},
                outputs={},
            )
        )
        assert (tmp_path / "nested" / "audit.jsonl").exists()

    def test_read_all_parses_appended_entries(self, tmp_path):
        log = AuditLog(str(tmp_path / "audit.jsonl"))
        for i in range(3):
            log.append(
                AuditEntry(
                    agent=f"A{i}",
                    operation="op",
                    environment=Environment.DEV,
                    mode=AgentMode.AUTO,
                    inputs={},
                    outputs={},
                )
            )
        entries = log.read_all()
        assert len(entries) == 3
        assert [e["agent"] for e in entries] == ["A0", "A1", "A2"]

    def test_read_all_empty_when_no_file(self, tmp_path):
        log = AuditLog(str(tmp_path / "missing.jsonl"))
        assert log.read_all() == []

    def test_record_operation_extracts_risk_signals(self, tmp_path):
        log = AuditLog(str(tmp_path / "audit.jsonl"))
        ctx = RiskContext(
            available=True,
            source="file",
            incident_active=True,
            off_hours=True,
        )
        entry = log.record_operation(
            agent="Agent-MLTrainer",
            operation="train",
            environment=Environment.STAGING,
            base_mode=AgentMode.AUTO,
            final_mode=AgentMode.CONSULT,
            risk_context=ctx,
            inputs={"dataset": "v1"},
            outputs={"run_id": "r1"},
            approver="alice",
        )
        assert "incident_active" in entry.risk_signals
        assert "off_hours" in entry.risk_signals
        assert entry.base_mode == AgentMode.AUTO
        assert entry.mode == AgentMode.CONSULT
        # Persisted form includes base_mode
        decoded = json.loads(entry.to_jsonl())
        assert decoded["base_mode"] == "AUTO"

    def test_record_operation_omits_base_when_same(self, tmp_path):
        log = AuditLog(str(tmp_path / "audit.jsonl"))
        entry = log.record_operation(
            agent="A",
            operation="op",
            environment=Environment.DEV,
            base_mode=AgentMode.AUTO,
            final_mode=AgentMode.AUTO,
            risk_context=None,
            inputs={},
            outputs={},
        )
        assert entry.base_mode is None
        assert "base_mode" not in json.loads(entry.to_jsonl())

    def test_record_operation_marks_unavailable_context(self, tmp_path):
        log = AuditLog(str(tmp_path / "audit.jsonl"))
        ctx = RiskContext(available=False, source="unavailable")
        entry = log.record_operation(
            agent="A",
            operation="op",
            environment=Environment.DEV,
            base_mode=AgentMode.AUTO,
            final_mode=AgentMode.AUTO,
            risk_context=ctx,
            inputs={},
            outputs={},
        )
        assert "risk_signals:UNAVAILABLE" in entry.risk_signals
