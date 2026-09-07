# Runbook — Progressive delivery with Argo Rollouts

> **Closes external-feedback gap 6.2 (May 2026).** Argo Rollouts ships
> with the template but is **opt-in** — `templates/service/k8s/base/argo-rollout.yaml`
> is intentionally NOT in `templates/k8s/base/kustomization.yaml#resources`.
> Adopters reading the base manifest list miss it. This runbook makes
> the enable path explicit.

## Why this is opt-in

Two reasons, both deliberate:

1. **Resource collision.** `argo-rollout.yaml` and `deployment.yaml`
   manage the same Pods. Including both in `resources:` produces
   duplicate Pod owners and a broken cluster state. Kustomize cannot
   safely include both, so adopters MUST swap one for the other.
2. **Cluster prerequisite.** Argo Rollouts requires the
   `argoproj.io/v1alpha1` CRDs installed cluster-wide. A scaffolded
   service that hard-required them would fail `kubectl apply` on a
   vanilla cluster, surprising new adopters.

The base ships `Deployment`, the canonical opt-in is to swap to
`Rollout`. Both manifests have full security parity (PSS restricted,
init containers, liveness/readiness, the same `model-verifier` chain
v0.15.1 added).

## When to enable

Enable Argo Rollouts when **any** of:

- You need canary deploys with automatic rollback on metric regression.
- You run a champion/challenger statistical gate
  (`analysistemplate-champion-challenger.yaml` already ships in base).
- Your SLO burn rate must be evaluated as a deploy gate, not just an
  alert.
- You have an SRE on-call rotation that cannot be paged at 3 a.m. for
  a metric regression a Rollout could have detected at 30 % traffic.

Do NOT enable when: you have a single replica, no champion/challenger
gate, and a low-traffic service where a full rollback is cheap.

## Pre-flight

| Check | Command | Expected |
| ------- | --------- | ---------- |
| CRDs installed | `kubectl get crd rollouts.argoproj.io` | exists |
| Argo controller running | `kubectl get deploy -n argo-rollouts argo-rollouts` | `1/1 Available` |
| AnalysisTemplate present | `kubectl get analysistemplate -n <ns>` | matches `analysistemplate-champion-challenger.yaml` |
| RBAC for SA | `kubectl auth can-i list rollouts --as system:serviceaccount:<ns>:<service-name>-sa` | `yes` |

If `argo-rollouts` is not yet installed in the cluster, install via
the upstream manifest (kept out of this template by ADR-001 §"deferred
infrastructure components"):

```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f \
  https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
```

## Procedure

### 1. Switch the base resource

In `templates/service/k8s/base/kustomization.yaml`:

```yaml
resources:
  # Comment out the Deployment line:
  # - deployment.yaml
  # Add the Rollout (replaces it):
  - argo-rollout.yaml
  # ... rest unchanged
```

### 2. Adjust overlays per-environment

Each overlay's `patch-deployment.yaml` MUST be renamed and re-targeted:

```bash
# Per overlay (gcp-dev, gcp-staging, gcp-prod, aws-*):
git mv k8s/overlays/<cloud>-<env>/patch-deployment.yaml \
       k8s/overlays/<cloud>-<env>/patch-rollout.yaml
```

Update the `kind:` field in the patch from `Deployment` to `Rollout`,
keep the rest. The `model-downloader`/`model-verifier` init container
patches transfer 1:1.

### 3. Verify the rendered output

```bash
kustomize build k8s/overlays/gcp-dev/ | grep -E '^kind: '
# Expect: kind: Rollout (NOT kind: Deployment)
```

### 4. Apply

In dev: `kubectl apply -k k8s/overlays/gcp-dev/`. The first apply
spins up at 100 % (no canary on initial install).

For subsequent deploys, the Rollout strategy in `argo-rollout.yaml`
defines the canary steps. The default ships with a 10 % → 30 % → 60 %
→ 100 % progression with `pause` durations and an `analysisRunRef`
back to the champion/challenger AnalysisTemplate.

## Verification

| Check | Command | Expected |
| ------- | --------- | ---------- |
| Rollout status | `kubectl argo rollouts get rollout <service-name>-predictor -n <ns>` | `Phase: Healthy` |
| AnalysisRun verdict | `kubectl get analysisrun -n <ns>` | `Phase: Successful` after each canary step |
| Traffic split | `kubectl argo rollouts get rollout ... -w` | percentages match the configured steps |
| Pod parity | `kubectl get pods -n <ns> -l app=<service-name>` | both new + old replicas present during canary |

## Anti-patterns

- **Skipping the AnalysisTemplate**: a Rollout without an
  `analysisRunRef` is just a slower Deployment. The whole point is
  the metric-driven abort.
- **Disabling the verifier**: setting
  `MODEL_SIGNATURE_VERIFY=warn` in production while ALSO running a
  Rollout means a bad model can reach 100 % traffic without ever
  failing the canary. Keep enforce mode on (gcp-prod / aws-prod
  overlays already do this).
- **Setting all canary steps to 0 s pause**: defeats the metric
  observation window. Min recommended pause is 60 s for
  request-rate panels to populate.

## Failure paths

If the canary aborts, Argo Rollouts triggers an automatic revert to
the previous stable replica set. **No manual intervention needed.**

If the controller crashes mid-rollout, the cluster is left in the
last valid intermediate state (e.g. 30 % new + 70 % old). To recover:

```bash
kubectl argo rollouts abort <service-name>-predictor -n <ns>
kubectl argo rollouts undo  <service-name>-predictor -n <ns>
```

This is the same chain the `/rollback` workflow runs in CI.
