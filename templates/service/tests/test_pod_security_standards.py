"""Contract — every workload satisfies the Pod Security Standard it declares (D-29).

Why this exists
---------------
``templates/service/k8s/base/cronjob-performance.yaml`` shipped two containers
with **no securityContext at all** — no ``allowPrivilegeEscalation: false``, no
``runAsNonRoot``, no dropped capabilities — while every namespace this template
creates is labelled ``pod-security.kubernetes.io/enforce: restricted``.

The golden-path E2E had been reporting it, weekly, since 2026-05-11:

    Warning: would violate PodSecurity "restricted:latest":
      allowPrivilegeEscalation != false (container "performance-monitor" ...)

Nobody read it, because that job runs on a schedule and its failures reach no
pull request. And ``grep -rl allowPrivilegeEscalation`` over the test trees
returned nothing: the invariant was declared in AGENTS.md, labelled on every
namespace, and asserted by no test.

Scope
-----
Every container and initContainer of every workload in ``k8s/base`` — the set
is discovered, never listed, so a workload added tomorrow is covered without
anyone remembering to add it here.

What is asserted is exactly what the ``restricted`` profile requires and a
manifest can satisfy statically — no more. Two details matter and the first
draft of this test got both wrong:

* ``runAsNonRoot`` and ``seccompProfile`` may be set on the **pod**, and apply
  to every container in it. Checking only the container level reported
  compliant workloads as violations.
* ``readOnlyRootFilesystem`` is **not** part of ``restricted``. Three of this
  template's own containers do not set it; asserting it here would have been
  this test inventing a requirement, which is the opposite of its job. It is
  reasonable hardening and a reasonable separate decision.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML is required to parse the manifests")

# `parents[1]` is the service root, in this repo and in a generated service.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR = SERVICE_ROOT / "k8s" / "base"

# Manifests are Copier templates, and a variable token is not valid YAML.
# Quoting the tokens makes them plain strings, which is enough to inspect
# structure.
#
# The pattern is assembled from adjacent literals on purpose: THIS FILE is
# itself inside the render root, so spelling the opening delimiter out would
# make Copier treat it as a variable and abort the scaffold. Caught by
# `scripts/check_template_render_safety.py`, which is exactly what it is for.
_OPEN, _CLOSE = "{" + "@", "@" + "}"
_TOKEN = re.compile(r"(?<!['\"])(" + re.escape(_OPEN) + r"[^@]*" + re.escape(_CLOSE) + r")(?!['\"])")


# Only manifests that declare a workload are parsed. `slo-prometheusrule.yaml`
# and its siblings embed PromQL, whose braces are not YAML, and they contain no
# pod spec — they are irrelevant to this contract and are validated properly by
# `scripts/validate_k8s_manifests.sh` with kubeconform. A file that DOES declare
# a workload and fails to parse is a hard failure, never a skip.
_WORKLOAD_KIND = re.compile(r"^kind:\s*(Deployment|StatefulSet|DaemonSet|Job|CronJob|Rollout)\s*$", re.M)


def _load(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if not _WORKLOAD_KIND.search(raw):
        return []
    text = _TOKEN.sub(r'"\1"', raw)
    try:
        return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
    except yaml.YAMLError as exc:  # pragma: no cover - a broken manifest
        raise AssertionError(
            f"{path.name} declares a workload but does not parse as YAML, so its "
            f"containers cannot be checked against the Pod Security Standard: {exc}"
        ) from exc


def _pod_specs(doc: dict) -> list[tuple[str, dict]]:
    """(workload label, podSpec) for every shape of workload in this tree."""
    kind, name = doc.get("kind", "?"), (doc.get("metadata") or {}).get("name", "?")
    spec = doc.get("spec") or {}
    candidates = [
        spec.get("template"),  # Deployment, Job
        ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template"),  # CronJob
    ]
    return [(f"{kind}/{name}", c["spec"]) for c in candidates if isinstance(c, dict) and "spec" in c]


def _workload_containers() -> list[tuple[str, str, dict, dict]]:
    """(workload, container name, container, POD securityContext).

    The pod-level context travels with each container because `restricted`
    lets a pod satisfy `runAsNonRoot` and `seccompProfile` on behalf of every
    container in it.
    """
    out: list[tuple[str, str, dict, dict]] = []
    for path in sorted(BASE_DIR.glob("*.yaml")):
        if path.name == "kustomization.yaml":
            continue
        for doc in _load(path):
            for label, pod in _pod_specs(doc):
                pod_sc = pod.get("securityContext") or {}
                for key in ("initContainers", "containers"):
                    for container in pod.get(key) or []:
                        out.append((f"{path.name}::{label}", container.get("name", "?"), container, pod_sc))
    return out


CONTAINERS = _workload_containers()
_IDS = [f"{w}::{c}" for w, c, _, _ in CONTAINERS]


def test_workloads_were_discovered() -> None:
    """An empty parametrize set is reported as a pass; this makes it a failure."""
    assert BASE_DIR.is_dir(), f"{BASE_DIR} is missing"
    assert CONTAINERS, f"no containers found under {BASE_DIR} — nothing would be checked"


@pytest.mark.parametrize(("workload", "name", "container", "pod_sc"), CONTAINERS, ids=_IDS or ["none"])
def test_container_satisfies_restricted_profile(workload: str, name: str, container: dict, pod_sc: dict) -> None:
    """D-29: the namespaces enforce `restricted`; the containers must comply."""
    sc = container.get("securityContext") or {}

    def inherited(field: str):
        """Container value if set, else the pod's — the order the kubelet uses."""
        return sc[field] if field in sc else pod_sc.get(field)

    missing = []
    # Container-scoped: `restricted` does not let a pod set these for you.
    if sc.get("allowPrivilegeEscalation") is not False:
        missing.append("allowPrivilegeEscalation: false")
    if (sc.get("capabilities") or {}).get("drop") != ["ALL"]:
        missing.append('capabilities.drop: ["ALL"]')
    # Pod-or-container scoped.
    if inherited("runAsNonRoot") is not True:
        missing.append("runAsNonRoot: true (on the pod or the container)")
    seccomp = inherited("seccompProfile") or {}
    if seccomp.get("type") not in ("RuntimeDefault", "Localhost"):
        missing.append("seccompProfile.type: RuntimeDefault (on the pod or the container)")

    assert not missing, (
        f"{workload} container `{name}` does not satisfy the `restricted` Pod "
        f"Security Standard its namespace enforces (D-29). Missing: "
        f"{', '.join(missing)}. Every namespace this template creates carries "
        f"`pod-security.kubernetes.io/enforce: restricted`, so the kubelet will "
        f"reject or warn on this pod."
    )
