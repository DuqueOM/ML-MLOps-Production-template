# Exporting to Vertex AI / SageMaker Pipelines

- **Audience**: teams that have already adopted Vertex AI Pipelines or
  SageMaker Pipelines end-to-end and want to reuse this template's serving
  image, contracts, and quality evidence instead of rebuilding them.
- **Authority**: `docs/decisions/ADR-001-template-scope-boundaries.md`
  (the template does not orchestrate Vertex/SageMaker pipelines — that is
  explicitly out of scope); this document is the "export surface"
  positioning promised by `README.md`'s non-claims list.

## What this is NOT

This template does not generate Vertex AI or SageMaker pipeline
definitions, and it will not grow that capability — orchestrating a
managed pipeline platform is a different problem than the one this
template solves (governed, self-hosted K8s serving with an agentic
operating model). If your team's pipelines already live in Vertex or
SageMaker, keep them there.

## What actually travels

Four artifacts this template produces are portable regardless of where
you deploy them, because none of them are Kubernetes-specific:

| Artifact | Where it lives | Why it's portable |
| --- | --- | --- |
| The predictor container image | `templates/service/Dockerfile` | A signed, SBOM-attested OCI image with no orchestrator-specific assumptions baked in |
| The API contract | `app/schemas.py`, `templates/service/docs/model-card-template.md` | `/health`, `/predict`, `/predict_batch` request/response shapes are plain JSON over HTTP |
| The data contract | `src/<service>/schemas.py` (Pandera) | Input validation is a Python library call, not a K8s resource |
| The quality evidence | `templates/service/docs/model-card-template.md`, `VALIDATION_LOG.md`-style entries | Fairness (DIR), SHAP, and quality-gate results are just numbers with provenance |

What does **not** travel as-is: `k8s/base/*.yaml`, `infra/terraform/*`,
the Kyverno admission policies, and the Prometheus/Grafana stack. Those
encode this template's specific deployment model (D-01..D-32); Vertex and
SageMaker have their own deployment abstractions and you should use those
natively rather than trying to run Kustomize/Terraform *inside* a managed
pipeline.

## Registering the same image in Vertex AI Model Registry

Vertex AI's custom-container contract expects an HTTP server exposing a
health route and a predict route, both configurable via environment
variables Vertex injects at serving time (`AIP_HTTP_PORT`,
`AIP_HEALTH_ROUTE`, `AIP_PREDICT_ROUTE`). This template's FastAPI app
already exposes `/health` and `/predict` on a fixed port (8000 by
default; see `templates/service/Dockerfile` `EXPOSE`), so the adapter
work is limited to pointing Vertex at those routes — no code change to
`app/main.py` is required:

```bash
# Push the SAME digest-pinned image your CI already built and signed —
# do not rebuild for Vertex; that would create a second, unsigned artifact.
gcloud ai models upload \
  --region=${REGION} \
  --display-name={@ service_kebab @} \
  --container-image-uri="${REGION}-docker.pkg.dev/${PROJECT_ID}/ml-images/{@ service_kebab @}-predictor@sha256:${DIGEST}" \
  --container-health-route=/health \
  --container-predict-route=/predict \
  --container-ports=8000
```

Model monitoring, batch prediction jobs, and endpoint deployment are then
Vertex AI's own mechanisms — configure them per Vertex's documentation,
using `templates/service/docs/model-card-template.md`'s recorded metrics as your baseline
for drift/skew thresholds.

## Registering the same image as a SageMaker Model Package

SageMaker's real-time inference contract expects `GET /ping` for health
and `POST /invocations` for scoring, conventionally on port 8080. This
template's contract uses `/health` and `/predict` on port 8000 (rule
04a-python-serving), so — unlike the Vertex path — SageMaker needs a thin
routing adapter rather than a pure configuration change:

```python
# app/sagemaker_adapter.py — thin routes only; no serving logic duplicated.
# Delegates to the SAME handlers app/main.py already registers, so the
# feature-parity and async-inference invariants (D-01, D-03) hold for
# both paths.
from app.main import app, health_check, predict

app.add_api_route("/ping", health_check, methods=["GET"])
app.add_api_route("/invocations", predict, methods=["POST"])
```

```bash
docker build -t {@ service_kebab @}-sagemaker \
  --build-arg PORT=8080 \
  -f templates/service/Dockerfile .   # same base image, adapter routes added

aws sagemaker create-model \
  --model-name {@ service_kebab @} \
  --primary-container Image=${ECR_URI}@sha256:${DIGEST},Environment={SAGEMAKER_PROGRAM=app.sagemaker_adapter}
```

Register the resulting model in a **Model Package Group** if your
organization uses SageMaker Model Registry for approval workflows — that
mirrors this template's own promotion-gate philosophy (ADR-002) and is
the natural place to attach the model card as package documentation.

## What you keep, what you lose

| Capability | Self-hosted (this template) | Exported to Vertex/SageMaker |
| --- | --- | --- |
| Async inference, SHAP caching, prediction logging | Yes (rule 04a, D-01/D-03/D-24) | Yes — same container, same code |
| Fairness + quality gates before promotion | CI-enforced (ADR-002, ADR-021) | You re-implement the gate in the platform's approval step; the *numbers* transfer via the model card |
| AUTO/CONSULT/STOP agentic governance | Yes (`AGENTS.md`) | No — Vertex/SageMaker pipeline steps are not covered by this template's behavior protocol |
| Anti-pattern contract tests (D-01..D-35) | Run in this repo's CI | Do not run against a Vertex/SageMaker deployment; they validate the K8s manifests and container, not the managed platform |
| Cost/ops model | K8s HPA + your cluster bill | Platform-managed autoscaling + its own pricing model |

## Related

- `docs/decisions/ADR-001-template-scope-boundaries.md` — why Vertex/SageMaker orchestration is out of scope
- `templates/service/docs/model-card-template.md` — the quality evidence that travels with the model
- `agentic/rules/04a-python-serving.md` — the serving contract this document assumes
- `README.md` §"How this compares" — positioning against platforms with native pipeline orchestration
