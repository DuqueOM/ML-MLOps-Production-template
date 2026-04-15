---
trigger: glob
globs: ["**/training/*.py", "**/models/*.py", "**/features/*.py"]
description: Python ML training — pipeline structure, quality gates, fairness, MLflow
---

# Python ML Training Rules

## Training Pipeline Structure

Every trainer MUST follow this sequence:
1. `load_data()` + Pandera validation
2. `engineer_features()`
3. `split_train_val_test()` — no temporal leakage if dates exist
4. `cross_validate()` with StratifiedKFold
5. `evaluate()` with optimal threshold search
6. `fairness_check()` — DIR >= 0.80 per protected attribute
7. `save_artifacts()` with SHA256 checksum
8. `log_to_mlflow()` — parameters, metrics, artifacts, tags
9. `quality_gates()` — must ALL pass before promotion

## Quality Gates

```python
def should_promote(new_metrics: dict, current_prod_metrics: dict) -> bool:
    return all([
        new_metrics["primary_metric"] >= current_prod_metrics["primary_metric"] * 0.95,
        new_metrics["primary_metric"] >= MINIMUM_THRESHOLD,
        new_metrics["secondary_metric"] >= SECONDARY_THRESHOLD,
        new_metrics["p95_latency_ms"] <= current_prod_metrics["p95_latency_ms"] * 1.20,
        new_metrics["dir_attribute"] >= 0.80,  # Fairness
    ])
```

## Data Leakage Prevention

- NEVER allow future data in training set (temporal splits)
- ALWAYS check: if primary metric > 0.99, investigate leakage before promoting
- Feature engineering MUST be fit on train set only, transform on val/test

## Fairness Requirements

Disparate Impact Ratio (DIR) per protected attribute:
```python
dir_value = min(pos_rate_group_a, pos_rate_group_b) / max(pos_rate_group_a, pos_rate_group_b)
assert dir_value >= 0.80, f"Fairness violation: DIR={dir_value}"
```

## Testing Requirements

- `test_no_data_leakage()` — primary metric below suspicion threshold
- `test_shap_values_not_all_zero()` — SHAP returning zeros is a known failure
- `test_shap_consistency()` — base_value + sum = prediction
- `test_feature_space_is_original()` — SHAP in original, not transformed space
- `test_model_meets_quality_gate()` — metric above production threshold
- `test_inference_latency()` — within SLA
- `test_fairness_disparate_impact()` — DIR >= 0.80

## When NOT to Apply
- Serving code (`app/*.py`) — use `04a-python-serving` rules instead
- Test files — conventions differ (synthetic data OK, stubs OK)
- Notebook/exploration code
