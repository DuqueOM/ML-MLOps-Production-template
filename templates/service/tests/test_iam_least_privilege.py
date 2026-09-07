"""Contract tests for the per-environment IAM split (ADR-017 / PR-A1, D-31).

These tests parse Terraform .tf files as text (no `terraform plan` required;
keeps the test suite hermetic and fast) and assert structural invariants
that must hold across both clouds.

Since 2026-09-05 the file also carries **control invariants**: assertions
that exist because a comment claimed a control and the control was absent.
See the section at the bottom — a comment cannot be verified, an assertion
is the claim.

Invariants:

1. **No wildcard principals**: `Principal: "*"` or `Principal: { AWS: "*" }`
   would let anyone in the world assume the role.
2. **No `Action: "*"`**: god-mode permissions defeat the split entirely.
3. **No `Resource: "*"` on mutating actions**: `s3:DeleteBucket`,
   `iam:*`, etc. with `Resource: "*"` is the audit anti-pattern.
4. **GitHub OIDC sub claim restricts to a specific repo**: the trust
   policy must reference `repo:${var.github_repo}:` so any other repo
   trying to assume CI/Deploy roles fails.
5. **6 GCP service accounts exist**: ci, deploy, runtime, drift, retrain,
   nodes (the last added 2026-09-05, ADR-017 §Amendment).
6. **AWS has CI + Deploy roles + drift IRSA + retrain IRSA**: separate
   from the per-service role, so a compromised drift CronJob cannot
   push images.

Why string parsing instead of `terraform show -json`:
- Terraform requires `terraform plan` against a real cloud to emit JSON.
- Hermetic tests cannot reach AWS/GCP — and shouldn't.
- The patterns we want to catch (wildcards, missing identities) are
  textual, not semantic.
- A future enhancement could call `terraform validate -json` and inspect
  the AST, but that adds a heavy dependency for marginal value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate the Terraform tree. Walks up looking for `infra/terraform`
# so the test runs both from the template root and from a scaffolded service.
# ---------------------------------------------------------------------------


def _find_tf_root() -> Path | None:
    here = Path(__file__).resolve()
    # `infra/terraform` relative to an ancestor covers both layouts: the
    # service root in a scaffolded service, and templates/service/ here. The
    # A first candidate pointed at the pre-ADR-030 layout, one level higher,
    # until June 2026 — dead but harmless, since this one matched anyway.
    for ancestor in [here.parent] + list(here.parents):
        candidate = ancestor / "infra" / "terraform"
        if candidate.is_dir():
            return candidate
    return None


TF_ROOT = _find_tf_root()


def _read_tf_files(cloud: str) -> str:
    """Read all .tf files for a cloud and return concatenated content.

    Concatenating is acceptable for textual lints — we are not parsing
    HCL semantics, just searching for forbidden patterns.
    """
    if TF_ROOT is None:
        pytest.skip("Terraform tree not found; test runs only against template/service layouts")
    cloud_dir = TF_ROOT / cloud
    if not cloud_dir.is_dir():
        pytest.skip(f"{cloud_dir} not present in this layout")
    parts = []
    for tf in sorted(cloud_dir.glob("*.tf")):
        parts.append(f"# === {tf.name} ===\n{tf.read_text()}\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Wildcard principal — most dangerous misconfiguration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_no_wildcard_principal(cloud: str) -> None:
    """No `Principal: "*"` or `Principal: { AWS: "*" }` in any policy.

    A wildcard principal lets anyone in the world (including other AWS
    accounts) assume the role. This is the audit anti-pattern that the
    least-privilege split is meant to prevent.

    Strips HCL comments to avoid false-positives against documentation
    that lists forbidden patterns by name.
    """
    content = _read_tf_files(cloud)
    code_only = "\n".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))

    # Match: Principal = "*" / Principal = { AWS = "*" } / Principal: "*"
    forbidden_patterns = [
        r'Principal\s*=\s*"\*"',
        r'Principal\s*:\s*"\*"',
        r'"AWS"\s*:\s*"\*"',
        r'AWS\s*=\s*"\*"',
    ]
    for pattern in forbidden_patterns:
        matches = re.findall(pattern, code_only)
        assert not matches, f"{cloud}: wildcard principal found ({pattern}): {matches}"


# ---------------------------------------------------------------------------
# Wildcard action on mutating policies
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_no_god_mode_action(cloud: str) -> None:
    """No `Action: "*"` outside narrow read-only contexts.

    AWS allows `Action: "*"` only in deliberately-scoped service-linked
    roles (e.g. EKS cluster role's AmazonEKSClusterPolicy). The template
    must never define a custom inline policy with `Action: "*"`.

    Strips HCL comments (lines starting with `#`) before scanning so the
    documentation block in iam.tf that LISTS the forbidden patterns
    doesn't false-positive against itself.
    """
    content = _read_tf_files(cloud)
    code_only = "\n".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))

    # Action = "*" or Action: "*" inside a Statement
    forbidden = re.findall(r'(?:Action)\s*[=:]\s*"\*"', code_only)
    assert not forbidden, f"{cloud}: god-mode 'Action = \"*\"' found {len(forbidden)} time(s)"


# ---------------------------------------------------------------------------
# GitHub OIDC trust policy must restrict by repo
# ---------------------------------------------------------------------------


def test_github_oidc_sub_claim_restricts_to_specific_repo() -> None:
    """AWS GitHub OIDC trust policies reference `repo:${var.github_repo}:`.

    Without this restriction, any GitHub repo with an OIDC token could
    assume the CI/Deploy roles. The sub claim binding is the only thing
    that limits assumption to OUR repository.
    """
    content = _read_tf_files("aws")
    if "aws_iam_openid_connect_provider" not in content:
        pytest.skip("AWS Terraform tree does not define a GitHub OIDC provider")

    # The trust policy must reference the github_repo variable in the sub claim.
    # Pattern: "repo:${var.github_repo}:" (with optional whitespace).
    repo_binding = re.search(
        r"repo:\$\{var\.github_repo\}:",
        content,
    )
    assert repo_binding is not None, (
        "GitHub OIDC trust policy must bind `repo:${var.github_repo}:` in the sub claim. "
        "Without this, any GitHub repo can assume the CI/Deploy roles."
    )

    # The audience claim must also be set, otherwise AWS IAM rejects.
    aud_binding = re.search(
        r"token\.actions\.githubusercontent\.com:aud",
        content,
    )
    assert aud_binding is not None, "GitHub OIDC trust policy must set the `aud` claim to sts.amazonaws.com"


# ---------------------------------------------------------------------------
# 5 GCP service accounts exist with the canonical names
# ---------------------------------------------------------------------------


def test_gcp_six_service_accounts_exist() -> None:
    """ADR-017 mandates 6 GCP SAs: ci, deploy, runtime, drift, retrain, nodes.

    `nodes` was added 2026-09-05 (ADR-017 §Amendment). Omitting it does not
    fail loudly — GKE silently falls back to the default Compute Engine
    service account, which typically holds `roles/editor` project-wide. That
    is exactly why it is asserted here rather than left to review.
    """
    content = _read_tf_files("gcp")
    if "google_service_account" not in content:
        pytest.skip("GCP Terraform tree does not define service accounts")

    required = ["ci", "deploy", "runtime", "drift", "retrain", "nodes"]
    for name in required:
        # Resource block: resource "google_service_account" "<name>" {
        pattern = rf'resource\s+"google_service_account"\s+"{name}"\s*\{{'
        match = re.search(pattern, content)
        assert match, f"GCP must declare google_service_account.{name} (ADR-017 PR-A1)"


# ---------------------------------------------------------------------------
# AWS has separate drift + retrain IRSA roles
# ---------------------------------------------------------------------------


def test_aws_drift_and_retrain_irsa_separate_from_service() -> None:
    """AWS drift + retrain roles are distinct resources from the per-service IRSA role.

    A compromised drift CronJob cannot push images, read predictions, or
    write into the production model prefix — it can only access reports.
    """
    content = _read_tf_files("aws")

    drift_role = re.search(r'resource\s+"aws_iam_role"\s+"drift"\s*\{', content)
    retrain_role = re.search(r'resource\s+"aws_iam_role"\s+"retrain"\s*\{', content)

    assert drift_role, "aws_iam_role.drift must exist (ADR-017 PR-A1)"
    assert retrain_role, "aws_iam_role.retrain must exist (ADR-017 PR-A1)"

    # Drift role must NOT reference iam:* or s3:DeleteBucket
    drift_section = _extract_resource_section(content, "aws_iam_policy", "drift")
    if drift_section:
        assert "iam:" not in drift_section, "drift policy must not include iam:* permissions"
        assert "DeleteBucket" not in drift_section, "drift policy must not allow s3:DeleteBucket"


def _extract_resource_section(content: str, resource_type: str, resource_name: str) -> str:
    """Extract a `resource "<type>" "<name>" { ... }` block."""
    # Find the opening line
    pattern = rf'resource\s+"{resource_type}"\s+"{resource_name}"\s*\{{'
    match = re.search(pattern, content)
    if not match:
        return ""
    start = match.start()
    # Walk forward counting braces until balanced
    depth = 0
    in_block = False
    for i, ch in enumerate(content[start:], start=start):
        if ch == "{":
            depth += 1
            in_block = True
        elif ch == "}":
            depth -= 1
            if in_block and depth == 0:
                return content[start : i + 1]
    return content[start:]


# ---------------------------------------------------------------------------
# Network mode variable exists on both clouds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_network_mode_variable_exists(cloud: str) -> None:
    """Both clouds expose `var.network_mode` with managed/existing validation."""
    content = _read_tf_files(cloud)
    var_block = re.search(
        r'variable\s+"network_mode"\s*\{[^}]*\}',
        content,
        re.DOTALL,
    )
    assert var_block, f"{cloud}: variable.network_mode must be defined (ADR-017)"

    block = var_block.group(0)
    assert "managed" in block and "existing" in block, (
        f"{cloud}: network_mode validation must accept 'managed' and 'existing'"
    )
    assert "validation" in block, f"{cloud}: network_mode must have a validation block"


# ---------------------------------------------------------------------------
# CI role does not have IAM mutation permissions
# ---------------------------------------------------------------------------


def test_aws_ci_role_no_iam_mutation() -> None:
    """CI role can read EKS/ECR/S3-state but cannot create roles or attach policies.

    A compromised CI key cannot self-elevate by creating new roles. IAM
    mutation must require explicit human action via the bootstrap flow.
    """
    content = _read_tf_files("aws")
    if 'resource "aws_iam_role" "ci"' not in content:
        pytest.skip("AWS CI role not defined (github_repo possibly unset)")

    ci_policy = _extract_resource_section(content, "aws_iam_policy", "ci")
    assert ci_policy, "aws_iam_policy.ci must exist alongside the role"

    # Forbidden actions on the CI role
    forbidden_actions = [
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:AttachRolePolicy",
        "iam:CreateUser",
        "iam:CreateAccessKey",
    ]
    for action in forbidden_actions:
        assert action not in ci_policy, f"CI role must not allow {action} (privilege escalation risk)"


# ---------------------------------------------------------------------------
# GCP runtime SA has Workload Identity binding
# ---------------------------------------------------------------------------


def test_gcp_runtime_drift_retrain_have_workload_identity_bindings() -> None:
    """runtime/drift/retrain are pod-scoped and must bind to a KSA via WI."""
    content = _read_tf_files("gcp")
    if "google_service_account" not in content:
        pytest.skip("GCP Terraform tree not present")

    for sa in ("runtime", "drift", "retrain"):
        wi_binding = re.search(
            rf'resource\s+"google_service_account_iam_member"\s+"{sa}_workload_identity"',
            content,
        )
        assert wi_binding, (
            f"GCP {sa} SA must have a Workload Identity binding to a KSA in ml-services namespace (ADR-017)"
        )


# ---------------------------------------------------------------------------
# Control invariants — asserted, not asserted-about
#
# Every check below exists because a COMMENT claimed the control and the
# control was absent. Three times in one review cycle:
#
#   * a tfsec suppression cited "the variable validation rule in
#     variables.tf" — there was none, and the GKE control plane could be
#     public with no allowlist (#93);
#   * `ci_sa_user` said "Scoped via condition (only acting on SAs in this
#     project)" — there was no condition block, and CI could impersonate
#     every service account in the project (#94);
#   * `check_baselines_expiry.py` claimed to read `exclude:` blocks — it
#     filtered on uppercase ids and read none (#88).
#
# A comment cannot be verified. An assertion is the claim, so it cannot
# drift from it. This is ADR-017's answer to that class of failure.
# ---------------------------------------------------------------------------


def test_gke_node_pools_declare_a_service_account() -> None:
    """Without `service_account`, nodes run as the default Compute Engine SA.

    Trivy reports it as GCP-0050. The failure is silent: the cluster comes up,
    the nodes work, and they carry whatever the project's default SA holds —
    `roles/editor` in most projects.
    """
    content = _read_tf_files("gcp")
    pools = re.findall(r'resource\s+"google_container_node_pool"\s+"(\w+)"', content)
    if not pools:
        pytest.skip("no GKE node pools in this layout")

    # Each pool's node_config must bind the dedicated identity.
    bound = re.findall(r"service_account\s*=\s*google_service_account\.nodes\.email", content)
    assert len(bound) >= len(pools), (
        f"every google_container_node_pool must set node_config.service_account "
        f"to the dedicated `nodes` identity: found {len(pools)} pool(s) {pools} "
        f"but only {len(bound)} binding(s) (ADR-017 §Amendment, Trivy GCP-0050)"
    )


def test_service_account_user_is_never_granted_project_wide() -> None:
    """`roles/iam.serviceAccountUser` at project level = impersonate anything.

    It must be granted per service account, with
    `google_service_account_iam_member`, so the blast radius is the accounts
    named rather than every account in the project.
    """
    content = _read_tf_files("gcp")
    if "google_project_iam_member" not in content:
        pytest.skip("no project-level IAM bindings in this layout")

    for block in re.findall(r'resource\s+"google_project_iam_member"\s+"(\w+)"\s*\{(.*?)\n\}', content, re.S):
        name, body = block
        assert "roles/iam.serviceAccountUser" not in body, (
            f"google_project_iam_member.{name} grants roles/iam.serviceAccountUser at the "
            "PROJECT level, which permits impersonating every service account in the "
            "project. Grant it per account with google_service_account_iam_member "
            "(ADR-017 §Amendment, Trivy GCP-0011)"
        )


def test_gke_master_authorized_networks_is_statically_visible() -> None:
    """A `dynamic` authorized-networks block hides the control from analysis.

    Worse than hiding it: gated on a list that defaults to empty, the block
    never rendered at all, and GKE with no authorized-networks block applies
    no restriction.
    """
    content = _read_tf_files("gcp")
    if "google_container_cluster" not in content:
        pytest.skip("no GKE cluster in this layout")

    assert re.search(r"^\s*master_authorized_networks_config\s*\{", content, re.M), (
        "google_container_cluster must declare master_authorized_networks_config "
        "as a static block. An empty list then means 'enabled, no external CIDR "
        "allowed'; omitting the block means no restriction at all (Trivy GCP-0061)"
    )
    assert not re.search(r'dynamic\s+"master_authorized_networks_config"', content), (
        "master_authorized_networks_config must not be a `dynamic` block — no static "
        "analyser evaluates those, and gating it on a list that defaults to empty "
        "silently disables the control"
    )


def test_public_control_plane_requires_an_allowlist() -> None:
    """The invariant a suppression once claimed `variables.tf` enforced.

    It did not. `enable_private_endpoint = false` with an empty
    `master_authorized_networks` is a publicly reachable control plane with
    no allowlist, and nothing rejected that combination.
    """
    content = _read_tf_files("gcp")
    if "google_container_cluster" not in content:
        pytest.skip("no GKE cluster in this layout")

    preconditions = re.findall(r"precondition\s*\{(.*?)\n\s*\}", content, re.S)
    guarding = [
        block for block in preconditions if "enable_private_endpoint" in block and "master_authorized_networks" in block
    ]
    assert guarding, (
        "google_container_cluster must carry a lifecycle precondition rejecting "
        "enable_private_endpoint = false together with an empty "
        "master_authorized_networks. Without it a documented dev opt-out exposes "
        "the control plane with no allowlist (ADR-017 §Amendment)"
    )
