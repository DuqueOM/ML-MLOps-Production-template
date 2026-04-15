# Model Card: {ServiceName}

> Based on [Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993) (Mitchell et al., 2019)

## Model Details

| Field | Value |
|-------|-------|
| **Model Name** | {ServiceName} |
| **Model Version** | v1.0.0 |
| **Model Type** | {Classification / Regression / NLP} |
| **Algorithm** | {e.g., StackingClassifier (LightGBM + XGBoost + LogisticRegression)} |
| **Framework** | scikit-learn ~= 1.5.0 |
| **Training Date** | YYYY-MM-DD |
| **MLflow Run ID** | `{run_id}` |
| **Artifact SHA256** | `{sha256_hash}` |

## Intended Use

- **Primary Use**: {e.g., Predict customer churn probability for retention targeting}
- **Primary Users**: {e.g., Marketing team, customer success managers}
- **Out-of-Scope**: {e.g., Credit scoring, insurance underwriting, hiring decisions}

## Training Data

| Field | Value |
|-------|-------|
| **Source** | {e.g., Internal CRM database, public dataset} |
| **Size** | {e.g., 10,000 rows, 14 features} |
| **Date Range** | {e.g., 2023-01 to 2024-12} |
| **Target Distribution** | {e.g., 20.4% positive, 79.6% negative} |
| **DVC Version** | `{dvc_hash}` |

### Feature Summary

| Feature | Type | Description |
|---------|------|-------------|
| feature_1 | Numeric | {description} |
| feature_2 | Categorical | {description} |
| ... | ... | ... |

## Evaluation Results

### Primary Metrics (Test Set)

| Metric | Value | Threshold |
|--------|-------|-----------|
| ROC-AUC | {0.XX} | >= 0.80 |
| F1 Score | {0.XX} | >= 0.55 |
| Precision | {0.XX} | — |
| Recall | {0.XX} | — |

### Fairness Metrics

| Protected Attribute | Disparate Impact Ratio | Threshold |
|---------------------|----------------------|-----------|
| {e.g., Gender} | {0.XX} | >= 0.80 |
| {e.g., Age Group} | {0.XX} | >= 0.80 |

### Performance by Subgroup

| Subgroup | ROC-AUC | F1 | N |
|----------|---------|-----|---|
| {Group A} | {0.XX} | {0.XX} | {n} |
| {Group B} | {0.XX} | {0.XX} | {n} |

## Inference Performance

| Metric | Value | SLA |
|--------|-------|-----|
| P50 Latency | {XX}ms | — |
| P95 Latency | {XX}ms | <= 100ms |
| P99 Latency | {XX}ms | — |
| Throughput | {XX} req/s | — |

## Ethical Considerations

- **Bias**: {Document known biases and mitigation steps taken}
- **Privacy**: {What PII is used? How is it protected?}
- **Fairness**: {DIR >= 0.80 enforced as quality gate. Describe any remaining gaps.}

## Limitations

- {e.g., Model trained on data from a single geographic region}
- {e.g., Performance degrades for customers with < 3 months of history}
- {e.g., Categorical features with unseen values fall back to mode imputation}

## Drift Monitoring

| Feature | PSI Warning | PSI Alert | Current PSI |
|---------|------------|-----------|-------------|
| feature_1 | 0.10 | 0.20 | {0.XX} |
| feature_2 | 0.10 | 0.20 | {0.XX} |

- **Monitoring Frequency**: Daily (K8s CronJob)
- **Heartbeat Alert**: Fires if CronJob hasn't run in 48h
- **Retraining Trigger**: PSI >= alert threshold on any critical feature

## SHAP Explainability

- **Method**: KernelExplainer (never TreeExplainer for ensemble models)
- **Background Data**: 50 representative samples from training set
- **Feature Space**: Original (pre-ColumnTransformer)
- **Top Features**: {feature_1, feature_2, feature_3}

## Caveats and Recommendations

- {e.g., Retrain quarterly or when drift alert fires}
- {e.g., Do not use for automated decisions without human review}
- {e.g., Monitor prediction distribution for concept drift}
