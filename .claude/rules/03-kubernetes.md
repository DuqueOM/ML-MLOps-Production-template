---
paths:
  - "k8s/**/*.yaml"
  - "**/k8s/**/*.yaml"
  - "templates/k8s/**/*"
---

# Kubernetes Rules

- NEVER `uvicorn --workers N` — always 1 worker, HPA handles horizontal scale
- HPA uses CPU only — NEVER memory for ML pods (fixed RAM prevents scale-down)
- NEVER bake models into Docker images — use Init Container + emptyDir
- ALWAYS use Workload Identity (GCP) / IRSA (AWS) — no hardcoded credentials
- ALWAYS verify `kubectl config current-context` before applying manifests
- NEVER overwrite existing container image tags — tags are immutable
