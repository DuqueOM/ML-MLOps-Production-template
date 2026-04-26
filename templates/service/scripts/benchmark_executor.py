#!/usr/bin/env python3
"""Benchmark the inference ThreadPoolExecutor sizing (docs/threadpool-sizing.md).

Sweeps `max_workers` ∈ {1, 2, 4, 8, cpu_count, 2*cpu_count} and reports
p50/p95/p99 latency and RPS under a fixed concurrent-client load. The
best value is typically `cpu_count` or `cpu_limit_cores`, whichever is
smaller.

Usage:
    python scripts/benchmark_executor.py \\
        --model-path artifacts/model.joblib \\
        --sample-input eda/artifacts/sample_request.json \\
        --duration 30 \\
        --concurrent-clients 16

Writes JSON to ops/benchmarks/{date}-executor.json for audit.

Exit code:
    0 success, 1 on setup error. Benchmark results never fail the
    script — they are advisory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def _load_model(model_path: str):
    import joblib  # noqa: F811 — startup probe at __main__ runs first

    return joblib.load(model_path)


def _load_input(sample_input: str):
    with open(sample_input, encoding="utf-8") as fh:
        return json.load(fh)


async def _run_load(model, payload, executor: ThreadPoolExecutor, duration_s: int, concurrency: int) -> list[float]:
    """Fire `concurrency` clients for `duration_s`, return latencies (ms)."""
    loop = asyncio.get_event_loop()
    latencies: list[float] = []
    stop_at = time.time() + duration_s

    async def _one_client() -> None:
        while time.time() < stop_at:
            t0 = time.perf_counter()
            await loop.run_in_executor(executor, lambda: model.predict([payload]))
            latencies.append((time.perf_counter() - t0) * 1000)

    await asyncio.gather(*[_one_client() for _ in range(concurrency)])
    return latencies


def _quantile(data: list[float], q: float) -> float:
    if not data:
        return float("nan")
    s = sorted(data)
    idx = int(q * (len(s) - 1))
    return s[idx]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True)
    p.add_argument("--sample-input", required=True)
    p.add_argument("--duration", type=int, default=30, help="seconds per config")
    p.add_argument("--concurrent-clients", type=int, default=16)
    p.add_argument("--output-dir", default="ops/benchmarks")
    args = p.parse_args()

    try:
        model = _load_model(args.model_path)
        payload = _load_input(args.sample_input)
    except Exception as exc:
        print(f"error: cannot load model/input ({exc})", file=sys.stderr)
        return 1

    cpu = os.cpu_count() or 1
    configs = sorted({1, 2, 4, 8, cpu, 2 * cpu})

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_count": cpu,
        "duration_s": args.duration,
        "concurrent_clients": args.concurrent_clients,
        "configs": [],
    }

    print(f"cpu_count={cpu}  duration={args.duration}s  concurrency={args.concurrent_clients}")
    print(f"{'max_workers':>12} {'p50_ms':>8} {'p95_ms':>8} {'p99_ms':>8} {'rps':>8}")

    for mw in configs:
        with ThreadPoolExecutor(max_workers=mw, thread_name_prefix="bench") as ex:
            latencies = asyncio.run(_run_load(model, payload, ex, args.duration, args.concurrent_clients))
        p50 = _quantile(latencies, 0.50)
        p95 = _quantile(latencies, 0.95)
        p99 = _quantile(latencies, 0.99)
        rps = len(latencies) / args.duration if args.duration else float("nan")
        print(f"{mw:>12} {p50:>8.1f} {p95:>8.1f} {p99:>8.1f} {rps:>8.1f}")
        report["configs"].append(
            {"max_workers": mw, "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "rps": rps, "n": len(latencies)}
        )

    out = Path(args.output_dir) / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-executor.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {out}")
    print("Pick the max_workers value with lowest p95 at acceptable p50 + rps.")
    print("Document in service README §Configuration with INFERENCE_CPU_LIMIT=<value>.")
    return 0


if __name__ == "__main__":
    try:
        import joblib  # noqa: F401

        raise SystemExit(main())
    except ImportError:
        print("joblib not installed — add it to the service requirements", file=sys.stderr)
        raise SystemExit(1)
