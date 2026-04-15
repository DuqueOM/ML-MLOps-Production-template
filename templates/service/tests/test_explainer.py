"""SHAP explainer tests for {ServiceName}.

Self-contained regression tests that validate SHAP produces meaningful,
consistent explanations in the original feature space.

These tests use synthetic data and a simple pipeline so they run without
the full service deployed. Replace the fixtures with your actual pipeline
when integrating into a real service.

How to run:
    pytest tests/test_explainer.py -v
    pytest tests/test_explainer.py -v -k "consistency"
"""

import time

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Number of original features — SHAP must report this many, not post-encoding
ORIGINAL_FEATURE_NAMES = [f"feature_{i}" for i in range(8)]
MIN_INFORMATIVE_FEATURES = 2
SHAP_CONSISTENCY_TOLERANCE = 0.05
MAX_EXPLAIN_LATENCY_MS = 10000  # KernelExplainer is slow; adjust per service


@pytest.fixture(scope="module")
def pipeline_and_data():
    """Train a simple pipeline for SHAP testing.

    TODO: Replace with your actual pipeline + background data.
    """
    X, y = make_classification(
        n_samples=300,
        n_features=8,
        n_informative=5,
        random_state=42,
    )
    X_df = pd.DataFrame(X, columns=ORIGINAL_FEATURE_NAMES)
    X_train, X_test, y_train, _ = train_test_split(X_df, y, test_size=0.2, random_state=42)

    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", GradientBoostingClassifier(n_estimators=50, random_state=42)),
        ]
    )
    pipe.fit(X_train, y_train)

    # Background data: 30 representative samples for KernelExplainer
    background = X_train.sample(n=30, random_state=42)
    return pipe, background, X_test


@pytest.fixture(scope="module")
def explainer(pipeline_and_data):
    """Initialize KernelExplainer with predict_proba wrapper."""
    try:
        import shap
    except ImportError:
        pytest.skip("shap not installed")

    pipe, background, _ = pipeline_and_data
    feature_names = ORIGINAL_FEATURE_NAMES

    def wrapper(X_array: np.ndarray) -> np.ndarray:
        X_df = pd.DataFrame(X_array, columns=feature_names)
        return pipe.predict_proba(X_df)[:, 1]

    return shap.KernelExplainer(wrapper, background.values)


class TestSHAPValues:
    """Tests for SHAP KernelExplainer output."""

    def test_shap_values_not_all_zero(self, explainer, pipeline_and_data):
        """SHAP returning all zeros is a known failure mode — must never happen.

        Regression: this caught a production bug where background data had
        only one class, causing the explainer to produce all-zero SHAP.
        """
        _, _, X_test = pipeline_and_data
        sample = X_test.values[:1]
        shap_values = explainer.shap_values(sample, nsamples=50)

        non_zero = np.count_nonzero(np.abs(shap_values[0]) > 0.001)
        assert non_zero >= MIN_INFORMATIVE_FEATURES, (
            f"Only {non_zero} non-zero SHAP values — explainer may be broken. "
            "Check background data has both classes represented."
        )

    def test_shap_consistency_property(self, explainer, pipeline_and_data):
        """base_value + sum(shap_values) must approximate predict_proba.

        This is a mathematical property of SHAP (Shapley values are additive).
        Violation indicates a bug in the wrapper or background data.
        """
        pipe, _, X_test = pipeline_and_data
        sample = X_test.values[:1]
        shap_values = explainer.shap_values(sample, nsamples=100)

        actual = float(pipe.predict_proba(pd.DataFrame(sample, columns=ORIGINAL_FEATURE_NAMES))[:, 1][0])
        reconstructed = float(explainer.expected_value) + float(shap_values[0].sum())

        assert abs(actual - reconstructed) < SHAP_CONSISTENCY_TOLERANCE, (
            f"SHAP inconsistency: actual={actual:.4f}, reconstructed={reconstructed:.4f}, "
            f"diff={abs(actual - reconstructed):.4f}"
        )

    def test_feature_space_is_original(self, explainer, pipeline_and_data):
        """SHAP must compute in ORIGINAL feature space, not post-encoding.

        If this fails: the wrapper is computing SHAP post-ColumnTransformer
        → feature names like 'x0_category_A' instead of 'feature_c'.
        """
        _, _, X_test = pipeline_and_data
        sample = X_test.values[:1]
        shap_values = explainer.shap_values(sample, nsamples=50)

        # SHAP values shape must match original feature count
        assert shap_values.shape[1] == len(ORIGINAL_FEATURE_NAMES), (
            f"SHAP in wrong space: got {shap_values.shape[1]} features, "
            f"expected {len(ORIGINAL_FEATURE_NAMES)} (original space)"
        )

    def test_background_data_representative(self, pipeline_and_data):
        """Background data must contain samples that produce both classes."""
        pipe, background, _ = pipeline_and_data
        bg_probs = pipe.predict_proba(background)[:, 1]

        has_low = (bg_probs < 0.3).any()
        has_high = (bg_probs > 0.7).any()
        assert has_low and has_high, (
            f"Background data not representative: prob range [{bg_probs.min():.2f}, {bg_probs.max():.2f}]. "
            "Both low and high probability samples needed for meaningful SHAP."
        )


class TestExplainPerformance:
    """Performance tests for SHAP explanations."""

    def test_explain_latency_acceptable(self, explainer, pipeline_and_data):
        """SHAP explanation latency must be within documented bounds."""
        _, _, X_test = pipeline_and_data
        sample = X_test.values[:1]

        start = time.perf_counter()
        explainer.shap_values(sample, nsamples=50)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < MAX_EXPLAIN_LATENCY_MS, (
            f"SHAP latency {elapsed_ms:.0f}ms > SLA {MAX_EXPLAIN_LATENCY_MS}ms. "
            "Consider reducing nsamples or background data size."
        )
