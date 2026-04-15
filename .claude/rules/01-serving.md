---
paths:
  - "**/app/*.py"
  - "**/api/*.py"
---

# ML Serving Rules

## Invariants
- NEVER call `model.predict()` directly in async endpoint — blocks event loop (D-03)
- ALWAYS use `asyncio.run_in_executor(ThreadPoolExecutor, partial(_sync_predict, ...))` (D-03)
- ALWAYS use `KernelExplainer` for SHAP with ensemble/pipeline models, never TreeExplainer (D-04)
- ALWAYS compute SHAP in ORIGINAL feature space via `predict_proba_wrapper` (D-04)
- NEVER `uvicorn --workers N` — 1 worker, HPA provides horizontal scale (D-01)
- NEVER bake models into Docker — use Init Container + emptyDir (D-11)
- Model loaded ONCE at startup (lifespan handler), never per-request

## FastAPI Conventions
- `/predict` — main inference, `/predict?explain=true` — SHAP (opt-in)
- `/health` — liveness + readiness, `/metrics` — Prometheus
- Mandatory metrics: `{service}_predictions_total`, `{service}_request_duration_seconds`

See `AGENTS.md` for anti-pattern table D-01 to D-12.
