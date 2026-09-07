# ThreadPoolExecutor sizing for ML inference

**Scope**: picking the `max_workers` value for the executor that wraps
`model.predict()` in async endpoints (D-03).

This is a **per-service tuning** exercise. The template ships with a
sensible default (`INFERENCE_CPU_LIMIT` env var) but no single number
fits every model; the cost of getting it wrong is visible at p95
latency and HPA stability.

## TL;DR

Set `max_workers = min(INFERENCE_CPU_LIMIT, os.cpu_count())`, where
`INFERENCE_CPU_LIMIT` is the K8s CPU limit in *cores*. Document your
chosen value in the service README with the profiling evidence below.

```python
# app/fastapi_app.py
import os
from concurrent.futures import ThreadPoolExecutor

_CPU_LIMIT = int(os.getenv("INFERENCE_CPU_LIMIT", str(os.cpu_count() or 1)))
_inference_executor = ThreadPoolExecutor(
    max_workers=min(_CPU_LIMIT, os.cpu_count() or 1),
    thread_name_prefix="ml-infer",
)
```

## Why sizing matters

| Symptom | Root cause |
| --------- | ----------- |
| p95 latency >> p50 | `max_workers` too small; queued tasks waiting |
| Throughput flat at N rps then bursts up | `max_workers` too small relative to CPU cores |
| CPU at 100% with high context-switch count | `max_workers` too large; threads fighting for CPU |
| HPA CPU signal oscillates | worker contention varies cycle to cycle |

## The right number (decision rule)

1. **Start**: `max_workers = min(cpu_limit_in_cores, cpu_count)`
2. If `predict()` uses **BLAS/OMP-threaded** libraries (xgboost,
   lightgbm, numpy with MKL), set `OMP_NUM_THREADS=1` and use
   `max_workers = cpu_limit_in_cores`. Otherwise they fight each other.
3. If `predict()` is **pure Python** with the GIL, threads add little;
   keep `max_workers` small (1–2) and scale horizontally with HPA.
4. Never exceed `2 × cpu_count` — diminishing returns, context-switching
   overhead wins.

## Benchmark script

The template ships `templates/service/scripts/benchmark_executor.py`
(created in v1.8.1). It sweeps `max_workers ∈ {1, 2, 4, 8, cpu_count,
2*cpu_count}` and prints the p50/p95/p99 latency and RPS for each.

```bash
python scripts/benchmark_executor.py \
  --model-path artifacts/model.joblib \
  --sample-input eda/artifacts/sample_request.json \
  --duration 30 \
  --concurrent-clients 16
```

Output example (fictional BankChurn service):

| max_workers | p50 ms | p95 ms | p99 ms | RPS | notes |
| ------------- | -------- | -------- | -------- | ----- | ------- |
| 1 | 18 | 82 | 140 | 52 | queue-dominated |
| 2 | 19 | 51 | 94 | 98 | **best p95, close to ideal** |
| 4 | 21 | 48 | 88 | 119 | slight p50 regression |
| 8 | 34 | 91 | 180 | 94 | context-switch overhead |
| 16 | 61 | 230 | 430 | 61 | fighting the GIL |

In this service, `max_workers=2` (equal to CPU limit) wins. Document:

> README.md §Configuration
>
> `INFERENCE_CPU_LIMIT=2` — tuned on 2-core K8s limit; `max_workers=2`
> gave lowest p95 (51ms) at 16 concurrent clients. Benchmark artifact:
> `ops/benchmarks/2026-04-24-bankchurn-executor.json`.

## Anti-patterns

- **Oversizing to "absorb bursts"** — HPA absorbs bursts better than a
  bloated thread pool. Threads inside one pod compete for CPU; pods
  compete for a larger pie (cluster).
- **Unbounded executor** — `ThreadPoolExecutor()` without `max_workers`
  defaults to `5 * cpu_count` (Python 3.13) or `min(32, cpu_count+4)`
  (older). Both are too large for single-worker uvicorn pods.
- **BLAS + threads** — if you use `OMP_NUM_THREADS=cpu_count` AND
  `max_workers=cpu_count`, you get `cpu_count²` logical threads. Use
  one or the other, not both.

## When to change the number

- Model swap (e.g., XGB → LightGBM): re-run the benchmark.
- CPU-limit change in HPA/Deployment: re-run or re-set the env var.
- p95 regression post-deploy without a code change: investigate
  whether worker contention exploded (check
  `prometheus: rate(cpu_context_switches_total[5m])`).

## References

- Rule `04a-python-serving.md` — ThreadPoolExecutor sizing section
- ADR-005 — Behavior Protocol (tuning is AUTO; adoption is CONSULT)
- Benchmark artifacts: `ops/benchmarks/*.json`
