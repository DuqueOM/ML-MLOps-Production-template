# Runbook: {@ service_name @}

## Service Overview

- **Service**: {@ service_name @}
- **Model**: {Model type}
- **SLA**: P95 < {X}ms, availability 99.9%
- **On-call**: {team/contact}

## P1 — Service Down (15 min SLA)

### Symptoms

- Error rate > 5%
- Health endpoint returning non-200
- Pods in CrashLoopBackOff

### Immediate Actions

```bash
# 1. Rollback to previous version
kubectl rollout undo deployment/{@ service_kebab @}-predictor -n {namespace}
kubectl rollout status deployment/{@ service_kebab @}-predictor -n {namespace}

# 2. Verify recovery
curl -f http://{@ service_kebab @}-service.{namespace}.svc.cluster.local:8000/health

# 3. Check error rate dropping
# Prometheus: rate(http_requests_total{service="{@ service_kebab @}",status=~"5.."}[5m])
```

### Escalation

- If rollback fails → page platform team
- If rollback succeeds → schedule P2 investigation

## P2 — Metric Degradation (4 hours SLA)

### Symptoms

- Rolling primary metric below quality gate
- Significant drift alert (PSI >= 0.20 on critical feature)

### Actions

```bash
# 1. Check drift scores (Prometheus metric — snake-case {@ service_slug @})
curl 'http://prometheus:9090/api/v1/query?query={@ service_slug @}_psi_score'

# 2. If drift confirmed, trigger retraining
gh workflow run retrain-{@ service_slug @}.yml -f reason="P2: metric degradation"

# 3. Monitor retraining quality gates
gh run list --workflow=retrain-{@ service_slug @}.yml --limit=1
```

## P3 — Warning Drift (24 hours SLA)

### Symptoms

- PSI between 0.10 and 0.20 on one or more features

### Actions

```bash
# 1. Run detailed drift analysis (Python module — snake-case {@ service_slug @})
python -m src.{@ service_slug @}.monitoring.drift_detection \
  --reference data/reference/reference.csv \
  --current data/production/latest.csv \
  --output drift_report.json

# 2. Review feature-level breakdown
cat drift_report.json | python -m json.tool

# 3. If single feature: investigate upstream data change
# 4. If multiple features: schedule retraining
# 5. Document findings in drift tracking log
```

## P4 — Incipient Drift (1 week SLA)

### Symptoms

- Small PSI increases trending upward over multiple days

### Actions

- Review Grafana PSI dashboard for trend
- Compare with seasonal patterns (YoY if applicable)
- Document in weekly review
- Schedule proactive retraining if trend continues

## P4 — Executor Saturation (capacity planning)

### Symptoms

- `ExecutorSaturated` fired: `inference_in_flight / inference_executor_capacity`
  has held at or near 1.0 for 5+ minutes — every inference thread is busy,
  new requests are queueing behind `run_in_executor` before they can start.
- Usually shows up alongside rising p95/p99 latency (not yet an SLO burn,
  but the leading indicator of one).

### Actions

- Check the Saturation panel (`dashboard-template.json`) to confirm this
  is sustained, not a brief spike from a batch job.
- If HPA has headroom (`current < maxReplicas`), confirm the CPU-based
  scale-up is actually happening — a saturated executor with idle CPU
  margin usually means `INFERENCE_THREADPOOL_WORKERS` is capped too low
  for the pod's CPU limit, not a scaling problem.
- If HPA is already at `maxReplicas`, this is real capacity pressure —
  raise `maxReplicas` (`hpa.yaml`) or increase per-pod CPU limit (which
  raises the auto-detected thread count via `INFERENCE_CPU_LIMIT`).
- Do NOT raise `INFERENCE_THREADPOOL_WORKERS` past the pod's CPU limit —
  more threads than cores just adds context-switch overhead without
  adding real throughput (D-01 class reasoning, see
  `agentic/rules/04a-python-serving.md`).

## Health Checks

```bash
# Pod status
kubectl get pods -l app={@ service_kebab @} -n {namespace}

# Resource usage
kubectl top pod -l app={@ service_kebab @} -n {namespace}

# Recent logs
kubectl logs -l app={@ service_kebab @} -n {namespace} --since=30m --tail=100

# HPA status
kubectl get hpa {@ service_kebab @}-hpa -n {namespace}
```

## Key URLs

- **Grafana Dashboard**: {URL}
- **Prometheus**: {URL}
- **AlertManager**: {URL}
- **MLflow**: {URL}
