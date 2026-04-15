---
name: drift-detection
description: Run and interpret PSI-based drift detection for an ML service
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(python:*)
  - Bash(kubectl:*)
  - Bash(curl:*)
when_to_use: >
  Use when checking data drift, interpreting PSI scores, or configuring drift thresholds.
  Examples: 'check drift for bankchurn', 'PSI alert fired', 'configure drift thresholds',
  'run drift check'
argument-hint: "<service-name>"
arguments:
  - service-name
---

# Drift Detection

## Step 1: Understand the Drift Metric

### PSI Interpretation Guide

| PSI Value | Status | Action | Exit Code |
|-----------|--------|--------|-----------|
| < 0.10 | Stable | No action | 0 |
| 0.10 – 0.20 | Warning | Monitor, increase check frequency | 1 |
| > 0.20 | Alert | Trigger retraining | 2 |

ALWAYS use quantile-based bins (not uniform):
```python
breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
```

Uniform bins can produce empty bins at extremes → PSI dominated by epsilon noise.

### Special Cases — When PSI Doesn't Apply

| Feature Type | Problem with PSI | Alternative |
|-------------|-----------------|-------------|
| **Time series** (seasonal) | PSI flags every seasonal change as "drift" | Year-over-Year comparison (same period last year) |
| **Text/NLP** features | PSI not meaningful for text | OOV (Out-of-Vocabulary) rate: warning > 20%, alert > 35% |
| **Low-cardinality categorical** | Quantile bins don't work with 3-5 categories | Categorical PSI variant: bins = unique categories |
| **Boolean** features | Only 2 bins → unstable PSI | Simple proportion test (chi-squared) |

### Exit Codes for CronJob Integration
- `exit 0` → all features stable
- `exit 1` → warning-level drift (monitor)
- `exit 2` → alert-level drift (retraining needed, GitHub Issue created)

## Step 2: Run Drift Detection Manually

```bash
python src/{service}/monitoring/drift_detection.py \
  --reference data/reference/{service}_reference.csv \
  --current data/production/{service}_latest.csv \
  --output drift_report.json
```

## Step 3: Interpret Results

For each feature, review:
```json
{
  "feature_name": "age",
  "psi": 0.15,
  "status": "warning",
  "reference_mean": 45.2,
  "current_mean": 48.1,
  "bins_detail": [...]
}
```

### Common Root Causes

| Pattern | Likely Cause | Action |
|---------|-------------|--------|
| Single feature PSI high | Upstream data change | Investigate ETL pipeline |
| All features PSI high | Data source change | Full retraining |
| Temporal features PSI high | Seasonal pattern | Use YoY comparison |
| Categorical OOV rate up | New categories in production | Update schema + retrain |

## Step 4: Configure Thresholds

Each feature needs per-feature thresholds with domain reasoning:
```python
THRESHOLDS = {
    "stable_feature": {"warning": 0.10, "alert": 0.20},
    "volatile_feature": {"warning": 0.15, "alert": 0.30},  # Higher natural variance
    "categorical_feature": {"warning": 0.10, "alert": 0.20},
}
```

For temporal data (e.g., time series, seasonal patterns):
- Standard PSI will flag EVERY seasonal change as drift
- Use Year-over-Year comparison instead

## Step 5: Push Metrics to Prometheus

```python
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

registry = CollectorRegistry()
psi_gauge = Gauge('service_psi_score', 'PSI per feature', ['feature'], registry=registry)

for feature, psi in results.items():
    psi_gauge.labels(feature=feature).set(psi)

push_to_gateway('pushgateway:9091', job='drift-detection', registry=registry)
```

## Step 6: Verify CronJob Health

```bash
# Check CronJob status
kubectl get cronjob drift-detection -n {namespace}

# Check last job
kubectl get jobs -l app=drift-detection -n {namespace} --sort-by=.metadata.creationTimestamp

# Check heartbeat
curl -s 'http://prometheus:9090/api/v1/query?query=drift_detection_last_run_timestamp'
```

## Trigger Retraining

If PSI exceeds alert threshold on critical features:
```bash
gh workflow run retrain-{service}.yml -f reason="PSI drift: {feature}={psi_value}"
```

Chain to `/retrain` workflow for the full retraining process.
