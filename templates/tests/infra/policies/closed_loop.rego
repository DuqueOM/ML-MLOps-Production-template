# =============================================================================
# Closed-Loop Monitoring + Warm-up + Disruption Policies (Rego v1)
# ML-MLOps Production Template
#
# Enforces invariants introduced by v1.7.x closed-loop roadmap:
#   D-23 — probe split (liveness vs readiness MUST differ)
#   D-25 — graceful shutdown (termGrace > uvicorn timeout)
#   D-27 — PodDisruptionBudget selector + zero-acknowledgment annotation
#
# Usage (CI and local):
#   conftest test --policy tests/infra/policies/ k8s/
# =============================================================================
package main

import rego.v1

# ---------------------------------------------------------------------------
# D-23: readiness and liveness probes MUST target different paths
# ---------------------------------------------------------------------------
# Readiness must hit /ready (503 until warm-up done); liveness /health
# (always 200 while process alive). Shared path re-creates the cold-start
# traffic-spike failure mode that /ready is designed to prevent.
deny contains msg if {
	input.kind == "Deployment"
	some container in input.spec.template.spec.containers
	container.livenessProbe.httpGet.path == container.readinessProbe.httpGet.path
	msg := sprintf(
		"Deployment '%s': container '%s' uses same path for liveness and readiness (D-23) — split into /health (liveness) and /ready (readiness)",
		[input.metadata.name, container.name],
	)
}

# ---------------------------------------------------------------------------
# D-25: graceful shutdown must be configured
# ---------------------------------------------------------------------------
warn contains msg if {
	input.kind == "Deployment"
	not input.spec.template.spec.terminationGracePeriodSeconds
	msg := sprintf(
		"Deployment '%s': missing terminationGracePeriodSeconds (D-25) — in-flight requests will be killed on pod termination",
		[input.metadata.name],
	)
}

# uvicorn's --timeout-graceful-shutdown must be STRICTLY LESS than the pod
# grace period so SIGKILL headroom remains.
warn contains msg if {
	input.kind == "Deployment"
	some container in input.spec.template.spec.containers
	some arg in container.args
	startswith(arg, "--timeout-graceful-shutdown=")
	tgs := to_number(trim_prefix(arg, "--timeout-graceful-shutdown="))
	grace := input.spec.template.spec.terminationGracePeriodSeconds
	tgs >= grace
	msg := sprintf(
		"Deployment '%s': uvicorn timeout-graceful-shutdown (%d) must be STRICTLY LESS than terminationGracePeriodSeconds (%d) — D-25",
		[input.metadata.name, tgs, grace],
	)
}

# ---------------------------------------------------------------------------
# D-27: PodDisruptionBudget hygiene
# ---------------------------------------------------------------------------
deny contains msg if {
	input.kind == "PodDisruptionBudget"
	not input.spec.selector.matchLabels.app
	msg := sprintf(
		"PodDisruptionBudget '%s': MUST select by matchLabels.app (D-27)",
		[input.metadata.name],
	)
}

# minAvailable: 0 effectively disables the budget. Allow it ONLY when the
# operator explicitly acknowledges the downtime via annotation.
deny contains msg if {
	input.kind == "PodDisruptionBudget"
	input.spec.minAvailable == 0
	not input.metadata.annotations["mlops.template/pdb-zero-acknowledged"]
	msg := sprintf(
		"PodDisruptionBudget '%s': minAvailable=0 disables the gate (D-27). Add annotation 'mlops.template/pdb-zero-acknowledged: \"<ADR-url>\"' to explicitly accept downtime",
		[input.metadata.name],
	)
}
