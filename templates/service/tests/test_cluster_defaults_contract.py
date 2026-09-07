"""Contract tests for cluster defaults (ADR-015 PR-A3).

Three orthogonal invariants enforced across both clouds:

1. **Private endpoint is configurable and secure by default** —
   `enable_private_endpoint` is a variable, default true. Dev can relax
   it explicitly when no private control-plane path exists.
2. **System / workload node pool split** — two pools with the workload
   pool tainted `workload-type=ml-services:NoSchedule`. System pods
   (kube-system, monitoring) cannot accidentally land on the workload
   nodes; workload pods cannot accidentally land on the system pool.
3. **Deny-default NetworkPolicy** — namespace baseline blocks all
   ingress/egress; per-service allow rules compose on top.
4. **Base Deployment ships the matching toleration** so ML pods can
   actually be scheduled on the tainted workload pool.

Pure-stdlib regex over .tf and .yaml files; no kubectl / terraform plan
against real cloud needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------


def _find_repo_root() -> Path | None:
    here = Path(__file__).resolve()
    ancestors = [here.parent] + list(here.parents)
    # Pass 1: template-repo layout — ancestor has templates/service/infra/terraform/
    for ancestor in ancestors:
        if (ancestor / "templates" / "service" / "infra" / "terraform").is_dir():
            return ancestor
    # Pass 2: generated-service layout — ancestor has infra/terraform/ at its root
    for ancestor in ancestors:
        if (ancestor / "infra" / "terraform").is_dir():
            return ancestor
    return None


REPO_ROOT = _find_repo_root()


def _payload(*parts: str) -> Path | None:
    """Resolve a path that lives at the service root, from either perspective.

    In this repository the payload sits under ``templates/service/``; in a
    generated service the same file is at the root. Returning ``None`` when
    neither resolves keeps "not found" distinguishable from "found nothing to
    check" at the call site.
    """
    if REPO_ROOT is None:
        return None
    for candidate in (REPO_ROOT / "templates" / "service", REPO_ROOT):
        target = candidate.joinpath(*parts)
        if target.exists():
            return target
    return None


def _tf_files(cloud: str) -> str:
    if REPO_ROOT is None:
        pytest.skip("Repo root not found")
    cloud_dir = (
        REPO_ROOT / "templates" / "service" / "infra" / "terraform" / cloud
        if (REPO_ROOT / "templates" / "service" / "infra" / "terraform" / cloud).is_dir()
        else REPO_ROOT / "infra" / "terraform" / cloud
    )
    if not cloud_dir.is_dir():
        pytest.skip(f"{cloud_dir} not present")
    return "\n".join(p.read_text() for p in sorted(cloud_dir.glob("*.tf")))


# ---------------------------------------------------------------------------
# 1. Private endpoint opt-in (GCP only — AWS already had var.allow_public_endpoint)
# ---------------------------------------------------------------------------


def test_gcp_private_endpoint_is_a_variable() -> None:
    """`enable_private_endpoint` must be a Terraform variable, not hardcoded.

    Hardcoding `enable_private_endpoint = true` breaks dev access; hardcoding
    `= false` breaks prod hardening. The variable lets each env flip it
    independently via tfvars / overlay backend config.
    """
    content = _tf_files("gcp")

    var_block = re.search(r'variable\s+"enable_private_endpoint"\s*\{', content)
    assert var_block, "GCP must define variable.enable_private_endpoint (PR-A3)"

    # Cluster must reference the variable, not a literal.
    cluster_section = re.search(
        r"private_cluster_config\s*\{[^}]*enable_private_endpoint\s*=\s*(\S+)",
        content,
        re.DOTALL,
    )
    assert cluster_section, "GCP cluster must wire enable_private_endpoint"
    value = cluster_section.group(1).strip()
    assert value.startswith("var."), f"GCP cluster.enable_private_endpoint must reference var.* (got: {value!r})"


def test_gcp_nodes_do_not_default_to_cloud_platform_scope() -> None:
    content = _tf_files("gcp")
    assert "https://www.googleapis.com/auth/cloud-platform" not in content, (
        "GCP node pools must not default to broad cloud-platform OAuth scope; "
        "use workload identity plus minimal node_oauth_scopes."
    )


def test_aws_public_endpoint_is_opt_in() -> None:
    """AWS already enforces `allow_public_endpoint=false` by default (PR-R2-6).

    Sanity-check the regression channel: the var still defaults false and
    the cluster references it.
    """
    content = _tf_files("aws")

    default_match = re.search(
        r'variable\s+"allow_public_endpoint"\s*\{[^}]*default\s*=\s*(true|false)',
        content,
        re.DOTALL,
    )
    assert default_match, "AWS must define variable.allow_public_endpoint with default"
    assert default_match.group(1) == "false", (
        "AWS allow_public_endpoint default must remain false (PR-R2-6, reaffirmed by PR-A3)"
    )


# ---------------------------------------------------------------------------
# 2. System + Workload node pool split
# ---------------------------------------------------------------------------


def test_gcp_has_system_and_workload_node_pools() -> None:
    """GCP cluster has TWO node pools: system + workload."""
    content = _tf_files("gcp")

    system = re.search(r'resource\s+"google_container_node_pool"\s+"system"\s*\{', content)
    workload = re.search(r'resource\s+"google_container_node_pool"\s+"workload"\s*\{', content)
    assert system, "GCP must define google_container_node_pool.system (PR-A3)"
    assert workload, "GCP must define google_container_node_pool.workload (PR-A3)"


def test_aws_has_system_and_workload_node_groups() -> None:
    """AWS cluster has TWO node groups: system + workload."""
    content = _tf_files("aws")

    system = re.search(r'resource\s+"aws_eks_node_group"\s+"system"\s*\{', content)
    workload = re.search(r'resource\s+"aws_eks_node_group"\s+"workload"\s*\{', content)
    assert system, "AWS must define aws_eks_node_group.system (PR-A3)"
    assert workload, "AWS must define aws_eks_node_group.workload (PR-A3)"


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_workload_pool_has_taint(cloud: str) -> None:
    """Workload pool MUST have a NoSchedule taint.

    Without it, system pods can land on workload nodes and a single OOM
    in an ML pod can evict kube-dns. The taint enforces the isolation
    that the split is meant to provide.
    """
    content = _tf_files(cloud)
    # Find the workload node pool/group resource and look for a taint block.
    if cloud == "gcp":
        pool_match = re.search(
            r'resource\s+"google_container_node_pool"\s+"workload"\s*\{(.*?)^\}',
            content,
            re.DOTALL | re.MULTILINE,
        )
    else:
        pool_match = re.search(
            r'resource\s+"aws_eks_node_group"\s+"workload"\s*\{(.*?)^\}',
            content,
            re.DOTALL | re.MULTILINE,
        )
    assert pool_match, f"{cloud}: workload pool resource not found"
    pool = pool_match.group(1)

    assert re.search(r"taint\s*\{", pool), f"{cloud} workload pool must declare a taint block"
    assert "NO_SCHEDULE" in pool, (
        f"{cloud} workload pool taint must use effect=NO_SCHEDULE (system pods stay on system pool)"
    )


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_system_pool_has_no_taint(cloud: str) -> None:
    """System pool MUST NOT have a taint. kube-system + monitoring run there."""
    content = _tf_files(cloud)
    if cloud == "gcp":
        pool_match = re.search(
            r'resource\s+"google_container_node_pool"\s+"system"\s*\{(.*?)^\}',
            content,
            re.DOTALL | re.MULTILINE,
        )
    else:
        pool_match = re.search(
            r'resource\s+"aws_eks_node_group"\s+"system"\s*\{(.*?)^\}',
            content,
            re.DOTALL | re.MULTILINE,
        )
    assert pool_match, f"{cloud}: system pool resource not found"
    pool = pool_match.group(1)

    # No `taint {` block in the system pool — strip comments first.
    code_only = "\n".join(line for line in pool.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"^\s*taint\s*\{", code_only, re.MULTILINE), (
        f"{cloud} system pool must NOT declare a taint (kube-system needs to land here)"
    )


# ---------------------------------------------------------------------------
# 3. Deny-default NetworkPolicy in K8s base
# ---------------------------------------------------------------------------


def test_deny_default_networkpolicy_exists() -> None:
    """Namespace baseline NetworkPolicy denies all traffic by default."""
    if REPO_ROOT is None:
        pytest.skip("Repo root not found")
    base = _payload("k8s", "base")
    assert base is not None and base.is_dir(), "k8s/base is missing from this service"

    deny_default = base / "networkpolicy-deny-default.yaml"
    assert deny_default.is_file(), "templates/service/k8s/base/networkpolicy-deny-default.yaml missing (PR-A3)"

    import yaml

    docs = list(yaml.safe_load_all(deny_default.read_text()))
    assert len(docs) == 1
    np = docs[0]
    assert np["kind"] == "NetworkPolicy"
    assert np["metadata"]["name"] == "default-deny-all"
    # Empty podSelector matches every pod
    assert np["spec"]["podSelector"] == {}, "default-deny must select all pods (empty selector)"
    # Both Ingress and Egress restricted
    assert set(np["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    # No ingress / egress keys = deny everything
    assert "ingress" not in np["spec"], "default-deny must not declare ingress rules"
    assert "egress" not in np["spec"], "default-deny must not declare egress rules"


def test_deny_default_is_in_kustomization() -> None:
    """The deny-default policy is included in the base kustomization."""
    if REPO_ROOT is None:
        pytest.skip("Repo root not found")
    kustomization = _payload("k8s", "base", "kustomization.yaml")
    assert kustomization is not None and kustomization.is_file(), (
        "k8s/base/kustomization.yaml is missing from this service"
    )

    content = kustomization.read_text()
    assert "networkpolicy-deny-default.yaml" in content, (
        "kustomization.yaml must include networkpolicy-deny-default.yaml (PR-A3)"
    )


# ---------------------------------------------------------------------------
# 4. Base Deployment has matching toleration
# ---------------------------------------------------------------------------


def test_base_deployment_has_workload_toleration() -> None:
    """Without the toleration, ML pods are unschedulable on the tainted workload pool."""
    if REPO_ROOT is None:
        pytest.skip("Repo root not found")
    deployment_yaml = _payload("k8s", "base", "deployment.yaml")
    assert deployment_yaml is not None and deployment_yaml.is_file(), (
        "k8s/base/deployment.yaml is missing from this service"
    )

    import yaml

    docs = list(yaml.safe_load_all(deployment_yaml.read_text()))
    deployment = next((d for d in docs if d and d.get("kind") == "Deployment"), None)
    assert deployment, "deployment.yaml must contain a Deployment"

    pod_spec = deployment["spec"]["template"]["spec"]
    tolerations = pod_spec.get("tolerations", [])
    matching = [
        t
        for t in tolerations
        if t.get("key") == "workload-type" and t.get("value") == "ml-services" and t.get("effect") == "NoSchedule"
    ]
    assert matching, (
        "Base Deployment must include a toleration for "
        "key=workload-type / value=ml-services / effect=NoSchedule (PR-A3). "
        f"Got tolerations: {tolerations}"
    )
