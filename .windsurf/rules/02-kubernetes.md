---
trigger: glob
globs: ["k8s/**/*.yaml", "k8s/**/*.yml", "helm/**/*.yaml", "helm/**/*.yml"]
description: Kubernetes patterns for ML serving — single-worker pods, CPU-only HPA, init containers
---

# Kubernetes Rules for ML Services

## Single-Worker Pod Pattern (MANDATORY)

`uvicorn --workers N` is an anti-pattern in K8s:
- Multiple workers in one pod share CPU limits → CPU thrashing
- HPA cannot distinguish worker load → scaling signal diluted

Correct pattern: 1 worker per pod, HPA adds pods as needed.

```yaml
containers:
  - name: {service}-predictor
    command: ["uvicorn"]
    args:
      - "app.main:app"
      - "--host=0.0.0.0"
      - "--port=8000"
      # NO --workers flag — default = 1
```

## CPU-Only HPA (MANDATORY)

NEVER use memory as an HPA metric for ML services:
- Model memory footprint is constant (loaded model = fixed RAM)
- Memory-based HPA never scales down: `ceil(replicas × usage / target)` stays constant

```yaml
metrics:
  - type: Resource
    resource:
      name: cpu              # CPU ONLY — never memory
      target:
        type: Utilization
        averageUtilization: 60  # 50-70 based on model weight
behavior:
  scaleDown:
    stabilizationWindowSeconds: 300
    policies:
      - type: Percent
        value: 10
        periodSeconds: 60
  scaleUp:
    stabilizationWindowSeconds: 0
    policies:
      - type: Percent
        value: 100
        periodSeconds: 15
```

## Init Container for Model Download (MANDATORY)

Models are NOT in the Docker image. Downloaded at pod startup via init container:

```yaml
initContainers:
  - name: model-downloader
    image: google/cloud-sdk:slim
    command: ["gsutil", "cp", "gs://BUCKET/SERVICE/model.joblib", "/models/model.joblib"]
    volumeMounts:
      - name: model-storage
        mountPath: /models
volumes:
  - name: model-storage
    emptyDir: {}
```

Why `emptyDir` and not PVC: model is immutable during pod lifetime. No persistence needed.

## Health Probes

```yaml
readinessProbe:
  httpGet:
    path: /ready      # D-23: 503 until model warm-up completes
    port: 8000
  periodSeconds: 5
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /health     # always 200 while event loop alive
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 15
  failureThreshold: 5
startupProbe:         # D-23: absorbs cold-start + warm-up window
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 24   # up to 120s total
```

Liveness and readiness MUST target DIFFERENT paths. Using the same
endpoint for both recreates the cold-start traffic-spike failure mode
that `/ready` exists to prevent (D-23).

## Graceful Shutdown (MANDATORY — D-25)

Coordinate K8s `terminationGracePeriodSeconds` with uvicorn's
`--timeout-graceful-shutdown` so in-flight requests complete on SIGTERM:

```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 30   # MUST be > uvicorn timeout
      containers:
        - args:
            - "--timeout-graceful-shutdown=20"
```

The uvicorn timeout must be STRICTLY LESS than the pod grace period to
leave headroom for SIGKILL handling.

## PodDisruptionBudget (MANDATORY — D-27)

Every Deployment MUST ship with a `PodDisruptionBudget`. Without one, a
single `kubectl drain` of a node can evict all replicas simultaneously.

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: "{service}-pdb"
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: "{service}"
```

For this PDB to be effective, HPA `minReplicas` MUST be >= 2. Setting
`minAvailable: 0` is allowed ONLY with an annotation
`mlops.template/pdb-zero-acknowledged: "<ADR-url>"` documenting the
accepted downtime budget (enforced by OPA policy).

## Rolling Update Strategy

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0   # Zero downtime
```

## Kustomize Multi-Cloud

- `k8s/base/` — shared manifests (deployments, HPAs, services)
- `k8s/overlays/gcp/` — Artifact Registry image patches
- `k8s/overlays/aws/` — ECR image patches

Always use Kustomize for image patching, never hardcode registry URLs in base manifests.

## Labels (MANDATORY on every resource)

```yaml
labels:
  app: {service-name}
  version: {semver}
  environment: {staging|production}
  managed-by: {kustomize|helm}
```

## ServiceAccount Annotations

- GCP: `iam.gke.io/gcp-service-account: SA@PROJECT.iam.gserviceaccount.com`
- AWS: `eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/ROLE`

Never use hardcoded credentials. Always IRSA (AWS) or Workload Identity (GCP).
