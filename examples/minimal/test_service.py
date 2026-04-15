"""Regression tests for fraud detection service.

Self-contained tests that run against the trained model.
Demonstrates the test patterns from the template:
- Data leakage detection
- Quality gates verification
- SHAP consistency
- Inference latency SLA
- Fairness (Disparate Impact Ratio)

Run:
    python train.py    # First, train the model
    pytest test_service.py -v
"""

from __future__ import annotations

import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_PATH = "artifacts/model.joblib"
BACKGROUND_PATH = "artifacts/background.csv"
TEST_FEATURES_PATH = "artifacts/test_features.csv"
TEST_LABELS_PATH = "artifacts/test_labels.csv"

PRIMARY_THRESHOLD = 0.80
LEAKAGE_THRESHOLD = 0.99
FAIRNESS_THRESHOLD = 0.80
LATENCY_SLA_MS = 100.0

skip_if_no_model = pytest.mark.skipif(
    not Path(MODEL_PATH).exists(),
    reason="Run 'python train.py' first to generate artifacts",
)


@pytest.fixture(scope="module")
def pipeline():
    return joblib.load(MODEL_PATH)


@pytest.fixture(scope="module")
def test_data():
    X = pd.read_csv(TEST_FEATURES_PATH)
    y = pd.read_csv(TEST_LABELS_PATH).squeeze()
    return X, y


# ---------------------------------------------------------------------------
# Data Leakage Tests
# ---------------------------------------------------------------------------
@skip_if_no_model
class TestDataLeakage:
    def test_no_data_leakage(self, pipeline, test_data):
        """ROC-AUC must not be suspiciously high (signals target leakage)."""
        X, y = test_data
        y_prob = pipeline.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, y_prob)
        assert auc < LEAKAGE_THRESHOLD, f"Possible data leakage: ROC-AUC={auc:.4f} > {LEAKAGE_THRESHOLD}"


# ---------------------------------------------------------------------------
# Quality Gate Tests
# ---------------------------------------------------------------------------
@skip_if_no_model
class TestQualityGates:
    def test_primary_metric(self, pipeline, test_data):
        """ROC-AUC must be above production threshold."""
        X, y = test_data
        y_prob = pipeline.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, y_prob)
        assert auc >= PRIMARY_THRESHOLD, f"ROC-AUC {auc:.4f} < {PRIMARY_THRESHOLD}"

    def test_predicts_both_classes(self, pipeline, test_data):
        """Model must not be degenerate (predicting only one class)."""
        X, _ = test_data
        preds = pipeline.predict(X)
        assert len(np.unique(preds)) >= 2, f"Degenerate: only predicts {np.unique(preds)}"

    def test_probabilities_calibrated(self, pipeline, test_data):
        """Probabilities should span a reasonable range."""
        X, _ = test_data
        probs = pipeline.predict_proba(X)[:, 1]
        assert probs.min() < 0.3, f"Min prob {probs.min():.3f} too high"
        assert probs.max() > 0.7, f"Max prob {probs.max():.3f} too low"


# ---------------------------------------------------------------------------
# SHAP Tests
# ---------------------------------------------------------------------------
@skip_if_no_model
class TestSHAP:
    def test_shap_values_not_all_zero(self, pipeline):
        """SHAP returning all zeros = broken explainer."""
        bg = pd.read_csv(BACKGROUND_PATH)
        feature_names = list(bg.columns)

        try:
            import shap
        except ImportError:
            pytest.skip("shap not installed")

        def wrapper(X_array):
            return pipeline.predict_proba(pd.DataFrame(X_array, columns=feature_names))[:, 1]

        explainer = shap.KernelExplainer(wrapper, bg.values[:20])
        sample = bg.values[:1]
        shap_values = explainer.shap_values(sample, nsamples=50)

        non_zero = np.count_nonzero(np.abs(shap_values[0]) > 0.001)
        assert non_zero >= 2, f"Only {non_zero} non-zero SHAP values — explainer may be broken"

    def test_shap_consistency(self, pipeline):
        """base_value + sum(SHAP) must approximate predict_proba."""
        bg = pd.read_csv(BACKGROUND_PATH)
        feature_names = list(bg.columns)

        try:
            import shap
        except ImportError:
            pytest.skip("shap not installed")

        def wrapper(X_array):
            return pipeline.predict_proba(pd.DataFrame(X_array, columns=feature_names))[:, 1]

        explainer = shap.KernelExplainer(wrapper, bg.values[:20])
        sample = bg.values[:1]
        shap_values = explainer.shap_values(sample, nsamples=50)

        actual = float(pipeline.predict_proba(pd.DataFrame(sample, columns=feature_names))[:, 1][0])
        reconstructed = float(explainer.expected_value) + float(shap_values[0].sum())

        assert (
            abs(actual - reconstructed) < 0.05
        ), f"SHAP inconsistency: actual={actual:.4f}, reconstructed={reconstructed:.4f}"


# ---------------------------------------------------------------------------
# Latency Tests
# ---------------------------------------------------------------------------
@skip_if_no_model
class TestLatency:
    def test_single_prediction_latency(self, pipeline, test_data):
        """P95 single prediction must be within SLA."""
        X, _ = test_data
        row = X.iloc[[0]]
        pipeline.predict_proba(row)  # warm-up

        latencies = []
        for _ in range(20):
            start = time.perf_counter()
            pipeline.predict_proba(row)
            latencies.append((time.perf_counter() - start) * 1000)

        p95 = np.percentile(latencies, 95)
        assert p95 < LATENCY_SLA_MS, f"P95={p95:.1f}ms > SLA={LATENCY_SLA_MS}ms"


# ---------------------------------------------------------------------------
# Fairness Tests
# ---------------------------------------------------------------------------
@skip_if_no_model
class TestFairness:
    def test_disparate_impact_ratio(self, pipeline, test_data):
        """DIR on is_foreign must be >= 0.80 (four-fifths rule)."""
        X, _ = test_data
        probs = pipeline.predict_proba(X)[:, 1]
        foreign = X["is_foreign"].astype(bool)

        pos_foreign = (probs[foreign] >= 0.5).mean() if foreign.sum() > 0 else 0
        pos_domestic = (probs[~foreign] >= 0.5).mean() if (~foreign).sum() > 0 else 0

        if max(pos_foreign, pos_domestic) > 0:
            dir_val = min(pos_foreign, pos_domestic) / max(pos_foreign, pos_domestic)
        else:
            dir_val = 1.0

        assert dir_val >= FAIRNESS_THRESHOLD, f"Fairness: DIR={dir_val:.3f} < {FAIRNESS_THRESHOLD}"
