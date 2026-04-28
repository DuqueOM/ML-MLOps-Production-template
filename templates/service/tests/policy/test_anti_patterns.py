"""D-XX anti-pattern policy tests enforced on SCAFFOLDED output.

Each test corresponds to exactly ONE AGENTS.md D-XX invariant and asserts
the absence of the anti-pattern in files produced by `new-service.sh`.

Naming convention: `test_d{NN}_<short_slug>` so test failures map directly
back to AGENTS.md. If a D-XX is process-only (runtime/behavioral) and not
statically inspectable, the test is present but decorated with
`@pytest.mark.skip` + a reason tying to the ADR that enforces it elsewhere.

Authority: ADR-016 PR-R2-11.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# D-01: `uvicorn --workers N` in Dockerfile or deployment
# ---------------------------------------------------------------------------


def test_d01_no_multi_worker_uvicorn(scaffold_dir: Path) -> None:
    """Dockerfile + k8s manifests must not invoke uvicorn with > 1 worker.

    Invariant: HPA provides horizontal scale. Multi-worker uvicorn competes
    for CPU against itself and dilutes the HPA signal (AGENTS.md D-01).
    """
    offenders: list[str] = []
    pattern = re.compile(r"--workers\s+([2-9]|\d{2,})")

    for path in scaffold_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {"Dockerfile"} or path.suffix in {".yaml", ".yml"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            match = pattern.search(text)
            if match:
                offenders.append(f"{path.relative_to(scaffold_dir)}: --workers {match.group(1)}")

    assert not offenders, (
        "D-01 violation: multi-worker uvicorn detected in:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# D-02: Memory metric in HPA
# ---------------------------------------------------------------------------


def test_d02_hpa_no_memory_metric(yaml_load_all, glob_files) -> None:
    """Any HorizontalPodAutoscaler must not reference a memory metric.

    ML pods have fixed RAM (model + runtime) so memory HPA never scales down
    after a warm-up spike (AGENTS.md D-02).
    """
    offenders: list[str] = []
    for hpa_file in glob_files("k8s/**/hpa*.yaml") + glob_files("k8s/**/*-hpa.yaml"):
        docs = yaml_load_all(hpa_file)
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "HorizontalPodAutoscaler":
                continue
            for metric in doc.get("spec", {}).get("metrics", []) or []:
                resource = metric.get("resource", {})
                if resource.get("name") == "memory":
                    offenders.append(f"{hpa_file.name}: memory metric present")
    assert not offenders, "D-02 violation: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# D-05: `==` pin for ML packages in requirements.txt
# ---------------------------------------------------------------------------


def test_d05_ml_packages_use_compatible_release(file_text) -> None:
    """ML packages (numpy/scipy/sklearn/…) must pin with `~=`, not `==`.

    `==` causes solver conflicts (numpy/pandas/scikit-learn have narrow
    compatibility windows); `~=` lets pip resolve patches while pinning
    minor versions (AGENTS.md D-05).
    """
    ml_packages = {"numpy", "pandas", "scipy", "scikit-learn", "xgboost", "lightgbm"}
    offenders: list[str] = []
    content = file_text("requirements.txt")
    if not content:
        pytest.skip("requirements.txt not produced by scaffolder (may be in Makefile)")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip any inline comment
        bare = line.split("#", 1)[0].strip()
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*==", bare)
        if match and match.group(1).lower() in ml_packages:
            offenders.append(line)
    assert not offenders, (
        "D-05 violation: ML packages pinned with `==` instead of `~=`:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# D-10: `terraform.tfstate` committed to repo
# ---------------------------------------------------------------------------


def test_d10_gitignore_blocks_tfstate(file_text) -> None:
    """.gitignore must include terraform.tfstate patterns."""
    gitignore = file_text(".gitignore")
    if not gitignore:
        pytest.skip(".gitignore not produced by scaffolder")
    # Any form that excludes tfstate is acceptable
    patterns = ["*.tfstate", "*.tfstate.*", "terraform.tfstate"]
    assert any(p in gitignore for p in patterns), (
        "D-10 violation: .gitignore does not block terraform.tfstate files. "
        f"Expected one of {patterns}, got:\n{gitignore[:500]}"
    )


# ---------------------------------------------------------------------------
# D-11: Models in Docker image
# ---------------------------------------------------------------------------


def test_d11_dockerfile_no_baked_models(file_text) -> None:
    """Dockerfile must not COPY models/ or artifacts/ into the image.

    The init-container pattern fetches models at pod startup so an image
    update never re-downloads an unchanged model (AGENTS.md D-11).
    """
    dockerfile = file_text("Dockerfile")
    if not dockerfile:
        pytest.skip("Dockerfile not produced by scaffolder")
    forbidden = [
        r"COPY\s+.*models/",
        r"COPY\s+.*artifacts/",
        r"COPY\s+.*\.joblib",
        r"COPY\s+.*\.pkl\b",
    ]
    offenders = [p for p in forbidden if re.search(p, dockerfile, re.IGNORECASE)]
    assert not offenders, (
        f"D-11 violation: Dockerfile COPIES model artifacts into image:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# D-17: Hardcoded credentials (os.environ direct-read of secret keys)
# ---------------------------------------------------------------------------


def test_d17_no_direct_env_secret_reads(scaffold_dir: Path) -> None:
    """Python code must go through `common_utils.secrets.get_secret(...)`
    rather than reading secret-bearing env vars directly.

    AGENTS.md D-17. Direct `os.environ["API_KEY"]` is permitted ONLY in
    `common_utils/secrets.py` (the loader itself).
    """
    secret_keys = r"(API_KEY|ADMIN_API_KEY|SECRET|PASSWORD|TOKEN|MLFLOW_PASSWORD)"
    pattern = re.compile(r'os\.environ\s*\[\s*["\']' + secret_keys + r'["\']')
    offenders: list[str] = []
    for py in scaffold_dir.rglob("*.py"):
        rel = py.relative_to(scaffold_dir)
        # Skip:
        # - common_utils/secrets.py (the allowed consumer)
        # - scripts/ (project-level tooling, not the service itself)
        # - tests/policy/ (THIS suite — contains regex literals
        #   that match themselves when scanning the scaffolded output)
        # - __pycache__/.git (binary/VCS noise)
        if any(
            part in {"__pycache__", ".git", "common_utils", "scripts"}
            for part in rel.parts
        ):
            continue
        if rel.parts[:2] == ("tests", "policy"):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in pattern.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            offenders.append(f"{rel}:{line_no}: {m.group(0)}")
    assert not offenders, (
        "D-17 violation: direct env-var reads for secret keys. Use "
        "common_utils.secrets.get_secret() instead:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# D-23: Liveness and readiness probes must not share a path
# ---------------------------------------------------------------------------


def test_d23_probes_use_distinct_paths(yaml_load_all, glob_files) -> None:
    """Every Deployment must have livenessProbe.path != readinessProbe.path.

    Shared path means readiness failure cascades to liveness and the kubelet
    kills the pod instead of just removing it from Service endpoints
    (AGENTS.md D-23).
    """
    offenders: list[str] = []
    # Base deployments only; overlay patches inherit probe specs.
    for dep_file in glob_files("k8s/base/deployment*.yaml") + glob_files(
        "k8s/base/*deployment.yaml"
    ):
        docs = yaml_load_all(dep_file)
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "Deployment":
                continue
            containers = (
                doc.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )
            for container in containers:
                liveness = (container.get("livenessProbe") or {}).get("httpGet", {})
                readiness = (container.get("readinessProbe") or {}).get("httpGet", {})
                lpath = liveness.get("path")
                rpath = readiness.get("path")
                if lpath and rpath and lpath == rpath:
                    offenders.append(
                        f"{dep_file.name}/{container.get('name')}: "
                        f"liveness and readiness share path {lpath!r}"
                    )
    assert not offenders, "D-23 violation: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# D-25: terminationGracePeriodSeconds > uvicorn graceful-shutdown timeout
# ---------------------------------------------------------------------------


def test_d25_grace_period_beats_uvicorn_shutdown(yaml_load_all, glob_files) -> None:
    """terminationGracePeriodSeconds must be strictly > uvicorn's
    `--timeout-graceful-shutdown` (default 20s) so in-flight requests
    complete before SIGKILL (AGENTS.md D-25).

    Practically this means either the grace period is ≥ 30 or we can see
    the uvicorn timeout explicitly and compare.
    """
    min_grace_default = 30  # matches AGENTS.md default
    offenders: list[str] = []
    # Only inspect BASE deployments; overlay patches legitimately omit
    # terminationGracePeriodSeconds because they touch specific fields
    # via strategic merge (the base value is inherited).
    for dep_file in glob_files("k8s/base/deployment*.yaml") + glob_files(
        "k8s/base/*deployment.yaml"
    ):
        docs = yaml_load_all(dep_file)
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "Deployment":
                continue
            pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
            grace = pod_spec.get("terminationGracePeriodSeconds")
            if grace is None:
                offenders.append(f"{dep_file.name}: no terminationGracePeriodSeconds set")
            elif grace < min_grace_default:
                offenders.append(
                    f"{dep_file.name}: terminationGracePeriodSeconds={grace} "
                    f"(< {min_grace_default}s default)"
                )
    assert not offenders, "D-25 violation: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# D-27: Every Deployment must ship with a PodDisruptionBudget
# ---------------------------------------------------------------------------


def test_d27_pdb_exists(yaml_load_all, glob_files) -> None:
    """k8s/base/ must contain a PodDisruptionBudget for the predictor.

    AGENTS.md D-27: prevents evictions from taking the service below its
    availability floor during node drains.
    """
    pdb_found = False
    for pdb_file in glob_files("k8s/**/pdb*.yaml") + glob_files("k8s/**/*-pdb.yaml"):
        docs = yaml_load_all(pdb_file)
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == "PodDisruptionBudget":
                pdb_found = True
                break
    assert pdb_found, (
        "D-27 violation: no PodDisruptionBudget found in k8s/ tree. "
        "Every Deployment must ship with a PDB (minAvailable >= 1)."
    )


# ---------------------------------------------------------------------------
# D-29: Namespace must carry Pod Security Standards labels
# ---------------------------------------------------------------------------


def test_d29_pss_labels_on_overlays(yaml_load_all, glob_files) -> None:
    """Every overlay namespace MUST carry `pod-security.kubernetes.io/enforce`.

    AGENTS.md D-29. Dev/staging may be `baseline`; prod must be `restricted`.
    """
    offenders: list[str] = []
    namespace_seen = False
    for ns_file in glob_files("k8s/overlays/**/namespace*.yaml") + glob_files(
        "k8s/overlays/**/*-namespace.yaml"
    ):
        docs = yaml_load_all(ns_file)
        for doc in docs:
            if not isinstance(doc, dict) or doc.get("kind") != "Namespace":
                continue
            namespace_seen = True
            labels = (doc.get("metadata") or {}).get("labels") or {}
            if "pod-security.kubernetes.io/enforce" not in labels:
                offenders.append(
                    f"{ns_file.relative_to(ns_file.parents[4])}: missing "
                    f"pod-security.kubernetes.io/enforce label"
                )
    if not namespace_seen:
        pytest.skip("No Namespace resources found under k8s/overlays/")
    assert not offenders, "D-29 violation: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# D-31: IAM must use 5-identity split (ci/deploy/runtime/drift/retrain)
# ---------------------------------------------------------------------------


def test_d31_five_identity_iam_split(scaffold_dir: Path) -> None:
    """Terraform IAM must define 5 distinct identities (AGENTS.md D-31).

    ADR-017 codifies the split. Both clouds' iam.tf/iam-*.tf must mention
    all 5 roles so scaffolded repos never collapse to a single over-
    privileged SA.
    """
    expected = {"ci", "deploy", "runtime", "drift", "retrain"}
    tf_dirs = [scaffold_dir / "infra" / "terraform" / cloud for cloud in ("gcp", "aws")]
    for tf_dir in tf_dirs:
        if not tf_dir.is_dir():
            pytest.skip(f"{tf_dir} not produced by scaffolder")
        combined = ""
        for tf_file in tf_dir.glob("iam*.tf"):
            combined += tf_file.read_text()
        missing = {role for role in expected if role not in combined}
        assert not missing, (
            f"D-31 violation: {tf_dir.name} IAM missing identities: "
            f"{sorted(missing)}. All 5 identities "
            f"({sorted(expected)}) must appear in iam*.tf."
        )


# ---------------------------------------------------------------------------
# Process-only anti-patterns — documented but not statically inspectable.
# These SKIP explicitly so the coverage table stays complete.
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="D-06 is runtime: suspicious metric → CONSULT per ADR-014")
def test_d06_suspicious_metrics_require_investigation() -> None:
    """D-06 escalation is handled at training time via quality gates."""


@pytest.mark.skip(reason="D-13 is process: EDA sandbox isolation is organizational")
def test_d13_eda_on_sandbox_data_only() -> None:
    """D-13 is enforced by EDA scaffolding (no production DB creds in EDA
    notebooks). Covered by test_secrets_security.py elsewhere."""
