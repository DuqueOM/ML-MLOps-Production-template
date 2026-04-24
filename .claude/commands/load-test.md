---
description: Run Locust load tests against ML services to validate SLAs
allowed-tools:
  - Bash(locust:*)
  - Bash(kubectl:*)
  - Read
---

# /load-test

Pre-release gate. AUTO in dev/staging, NOT run in production.

## Targets
- p95 latency ≤ 500ms (or service-specific SLO)
- p99 latency ≤ 1s
- Error rate < 0.1%
- HPA stable (no thrashing; scaling events < 1 per minute)
- No memory leak (RSS stable over 10 min)

## Procedure
1. Deploy candidate to staging
2. Warm up: 10 RPS for 2 min (wait for HPA min + warm-up probe)
3. Ramp: 10 → 100 RPS over 5 min
4. Soak: 100 RPS for 10 min
5. Spike: 100 → 300 RPS for 30 sec, measure recovery
6. Cool-down: 10 RPS for 2 min (HPA scale-down behavior)

## Artifacts
- `reports/load-test-{date}.html` (Locust HTML report)
- `reports/load-test-{date}.csv` (raw request log)
- Prometheus snapshot: latency histogram, request rate, HPA replicas

## Pass criteria (all 5)
- [ ] p95 within SLO
- [ ] Error rate < 0.1%
- [ ] HPA scaled up + scaled down cleanly
- [ ] No memory leak
- [ ] No 5xx during spike recovery

**Canonical**: `.windsurf/workflows/load-test.md`.
