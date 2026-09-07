#!/usr/bin/env bash
# Validate every Kubernetes manifest under a k8s/ tree — base and overlays.
#
# Why this exists
# ---------------
# Two separate copies of this validation existed, and both were narrower than
# the surface they guarded:
#
#   * the template repo's `Kubernetes Manifests` job named **seven** base
#     manifests literally. `k8s/base/` holds fourteen. Seven — including
#     `pdb.yaml` and `networkpolicy-deny-default.yaml`, both core API types
#     kubeconform validates fully — were never checked, and adding a
#     fifteenth would have been unchecked too. It validated no overlay at all.
#
#   * the generated service's `ci-infra.yml` looped over `k8s/overlays/gcp-*`
#     and `k8s/overlays/aws-*`. There are seven overlays; `batch-only` matches
#     neither glob. Both steps also carried `continue-on-error: true`, so
#     their result was advisory — and a loop over a glob that matches nothing
#     is indistinguishable from a loop that validated everything.
#
# This is one implementation with two callers, vendored byte-identical
# (`scripts/check_vendored_runtime_drift.py`), so the template cannot hold
# itself to a different bar than it ships.
#
# The contract it enforces beyond "these files parse"
# ---------------------------------------------------
# **Zero is a failure.** Every discovery step asserts it found something. A
# validator that silently validates nothing is the failure mode this repo
# keeps finding; it reports the same green as one that validated everything.
#
# Usage
# -----
#   validate_k8s_manifests.sh <k8s-dir>
#
#   <k8s-dir>  directory containing `base/` and `overlays/`, e.g. `k8s` in a
#              generated service or `templates/service/k8s` in this repo.
#
# Requires `kubeconform` and `kustomize` on PATH.
#
# Exit codes
# ----------
#   0  every discovered manifest and overlay validated.
#   1  a manifest failed validation, or a discovery step found nothing.
#   2  usage error, or a required tool is missing.

set -euo pipefail

# `-ignore-missing-schemas` is deliberate and load-bearing: the tree contains
# CRDs (Argo Rollouts, AnalysisTemplate, Prometheus PrometheusRule) whose
# schemas are not in the upstream catalogue. It weakens the check for those
# kinds only — every core-API object is still validated in full under
# `-strict`, which additionally rejects unknown fields.
readonly KUBECONFORM_ARGS=(-strict -ignore-missing-schemas)

usage() {
  echo "usage: $(basename "$0") <k8s-dir>" >&2
  echo "  <k8s-dir> must contain base/ and overlays/" >&2
}

main() {
  if [[ $# -ne 1 ]]; then
    usage
    return 2
  fi

  local k8s_dir="$1"
  if [[ ! -d "$k8s_dir" ]]; then
    echo "::error::'$k8s_dir' is not a directory" >&2
    return 2
  fi

  local tool
  for tool in kubeconform kustomize; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "::error::'$tool' is not on PATH. Install it before running this." >&2
      return 2
    fi
  done

  local status=0

  # --- 1. Every base manifest, individually -------------------------------
  # A glob, never a list. The previous hardcoded list was already seven files
  # behind the directory.
  local -a base_manifests=()
  local manifest
  for manifest in "$k8s_dir"/base/*.yaml; do
    [[ -f "$manifest" ]] || continue
    # kustomization.yaml is a kustomize input, not a Kubernetes object; it has
    # no apiVersion/kind and kubeconform correctly rejects it.
    [[ "$(basename "$manifest")" == "kustomization.yaml" ]] && continue
    base_manifests+=("$manifest")
  done

  if [[ ${#base_manifests[@]} -eq 0 ]]; then
    echo "::error::no base manifests found under '$k8s_dir/base/'. Either the" >&2
    echo "::error::layout moved or this is reading the wrong tree — both need a" >&2
    echo "::error::human, so finding nothing is a failure rather than a pass." >&2
    return 1
  fi

  echo "==> validating ${#base_manifests[@]} base manifests"
  if ! kubeconform "${KUBECONFORM_ARGS[@]}" "${base_manifests[@]}"; then
    echo "::error::base manifest validation failed" >&2
    status=1
  fi

  # --- 2. The base kustomization renders ----------------------------------
  echo "==> validating base kustomize build"
  local rendered
  if ! rendered=$(kustomize build "$k8s_dir/base"); then
    echo "::error::kustomize build failed for '$k8s_dir/base'" >&2
    return 1
  fi
  # Piping build output into kubeconform is not the same check as step 1:
  # kustomize applies patches, generators and common labels, so the rendered
  # object can be invalid while every input file is valid.
  if ! printf '%s\n' "$rendered" | kubeconform "${KUBECONFORM_ARGS[@]}"; then
    echo "::error::rendered base output failed validation" >&2
    status=1
  fi

  # --- 3. Every overlay ---------------------------------------------------
  # `overlays/*/`, not `overlays/gcp-*` + `overlays/aws-*`. The cloud-prefix
  # globs silently skipped `batch-only`.
  local -a overlays=()
  local overlay
  for overlay in "$k8s_dir"/overlays/*/; do
    [[ -d "$overlay" ]] && overlays+=("$overlay")
  done

  if [[ ${#overlays[@]} -eq 0 ]]; then
    echo "::error::no overlays found under '$k8s_dir/overlays/'. An overlay" >&2
    echo "::error::validator that validates zero overlays reports the same" >&2
    echo "::error::green as one that validated all of them." >&2
    return 1
  fi

  echo "==> validating ${#overlays[@]} overlays"
  for overlay in "${overlays[@]}"; do
    local name
    name=$(basename "$overlay")
    if ! rendered=$(kustomize build "$overlay"); then
      echo "::error::kustomize build failed for overlay '$name'" >&2
      status=1
      continue
    fi
    # Every overlay is reported, pass or fail, rather than stopping at the
    # first failure — one run should list everything that needs fixing.
    if printf '%s\n' "$rendered" | kubeconform "${KUBECONFORM_ARGS[@]}"; then
      echo "    $name: ok"
    else
      echo "::error::overlay '$name' failed validation" >&2
      status=1
    fi
  done

  if [[ $status -eq 0 ]]; then
    echo "[k8s-validate] OK — ${#base_manifests[@]} base manifests, base render, and ${#overlays[@]} overlays all valid."
  fi
  return "$status"
}

main "$@"
