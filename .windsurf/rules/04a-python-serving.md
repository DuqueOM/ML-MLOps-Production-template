---
trigger: glob
globs: ["**/app/*.py", "**/api/*.py"]
description: Python ML serving — async inference, SHAP wrappers, Prometheus metrics, FastAPI conventions
---

# Python ML Serving Rules

## Async Inference (MANDATORY)

`sklearn.predict()` and most ML frameworks are synchronous — they block asyncio's event loop.

ALWAYS use `asyncio.run_in_executor()`:
```python
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import asyncio

_inference_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="ml-infer"
)

def _sync_predict(input_dict: dict, explain: bool) -> dict:
    """CPU-bound — runs in thread pool, does not block event loop."""
    df = pd.DataFrame([input_dict])
    prob = float(model_pipeline.predict_proba(df)[:, 1][0])
    # ... build response
    return response

@app.post("/predict")
async def predict(input_data: InputSchema, explain: bool = False):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _inference_executor,
        partial(_sync_predict, input_data.model_dump(), explain)
    )
```

Why this works: sklearn, XGBoost, LightGBM release the GIL during C extensions → real parallelism with threads.

## SHAP KernelExplainer (MANDATORY for complex models)

NEVER use `TreeExplainer` with StackingClassifier, pipelines, or complex ensembles.

ALWAYS use `KernelExplainer` with a `predict_proba_wrapper`:
```python
def predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """SHAP in ORIGINAL feature space, not transformed space."""
    X_df = pd.DataFrame(X_array, columns=original_feature_names)
    return pipeline.predict_proba(X_df)[:, 1]

explainer = shap.KernelExplainer(
    model=predict_proba_wrapper,
    data=X_background.values[:50],  # 50 samples: precision/speed balance
)
```

ALWAYS verify the consistency property:
```
base_value + sum(shap_values) ≈ predict_proba(input)  (tolerance < 0.01)
```

## FastAPI Conventions

- `/predict` — main inference endpoint
- `/predict?explain=true` — SHAP explanation (opt-in)
- `/health` — liveness + readiness
- `/metrics` — Prometheus metrics
- Model loaded ONCE at startup (lifespan handler), never per-request

## Prometheus Metrics (MANDATORY per service)

```python
from prometheus_client import Counter, Histogram, Gauge

predictions_total = Counter('{service}_predictions_total', '...', ['risk_level', 'model_version'])
prediction_latency = Histogram('{service}_request_duration_seconds', '...', ['endpoint'])
prediction_score_distribution = Histogram('{service}_prediction_score', '...')
```

## Type Hints

Required on all public functions. Use Pydantic for config and API schemas:
```python
from pydantic import BaseModel, Field

class PredictionRequest(BaseModel):
    feature_a: float = Field(..., ge=0, le=100, description="Feature A value")
    feature_b: str = Field(..., description="Category")
```

## When NOT to Apply
- Test files (`test_*.py`) — test conventions are different
- Training scripts — use `04b-python-training` rules instead
- One-off scripts, migrations, CLI tools
