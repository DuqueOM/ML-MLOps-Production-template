"""Training pipeline tests for {ServiceName}.

Covers data leakage detection, quality gates, feature engineering
consistency, inference latency, and model fairness.

How to run:
    pytest tests/test_training.py -v
    pytest tests/test_training.py -v -k "leakage"   # Run only leakage tests

TODO: Replace {service} with your actual service name in imports.
TODO: Update SAMPLE_DATA to match your service's input schema.
TODO: Set realistic thresholds for quality gates and latency SLA.
"""

import time

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

# TODO: Uncomment and update imports for your service
# from src.{service}.training.train import Trainer, PRIMARY_THRESHOLD, FAIRNESS_THRESHOLD
# from src.{service}.training.features import FeatureEngineer
# from src.{service}.training.model import build_pipeline

# ---------------------------------------------------------------------------
# Configuration — customize per service
# ---------------------------------------------------------------------------
PRIMARY_THRESHOLD = 0.80  # Minimum ROC-AUC for promotion
SECONDARY_THRESHOLD = 0.55  # Minimum F1 score
FAIRNESS_THRESHOLD = 0.80  # Minimum Disparate Impact Ratio
LEAKAGE_THRESHOLD = 0.99  # Metric above this → investigate leakage
LATENCY_SLA_MS = 100.0  # Max single prediction time in ms
N_EXPECTED_FEATURES = 10  # Expected number of model input features


# ---------------------------------------------------------------------------
# Fixtures — shared test data and models
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sample_data() -> tuple[pd.DataFrame, pd.Series]:
    """Generate synthetic classification dataset.

    TODO: Replace with a representative sample from your actual data.
    This ensures tests reflect real feature distributions.
    """
    X, y = make_classification(
        n_samples=500,
        n_features=N_EXPECTED_FEATURES,
        n_informative=6,
        n_redundant=2,
        random_state=42,
    )
    feature_names = [f"feature_{i}" for i in range(N_EXPECTED_FEATURES)]
    X_df = pd.DataFrame(X, columns=feature_names)
    y_series = pd.Series(y, name="target")
    return X_df, y_series


@pytest.fixture(scope="module")
def trained_pipeline(sample_data: tuple) -> Pipeline:
    """Train a simple pipeline for testing.

    TODO: Replace with build_pipeline() from your service.
    """
    X, y = sample_data
    pipe = Pipeline([("model", GradientBoostingClassifier(random_state=42))])
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)
    pipe.fit(X_train, y_train)
    return pipe


# ---------------------------------------------------------------------------
# Data Leakage Tests
# ---------------------------------------------------------------------------
class TestDataLeakage:
    """Regression tests for data leakage.

    If the primary metric is unrealistically high (> LEAKAGE_THRESHOLD),
    it's a strong signal that target information is leaking into features.
    """

    def test_no_data_leakage(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """Primary metric must not be unrealistically high."""
        X, y = sample_data
        _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        y_prob = trained_pipeline.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)

        assert auc < LEAKAGE_THRESHOLD, (
            f"Possible data leakage: ROC-AUC={auc:.4f} > {LEAKAGE_THRESHOLD}. "
            "Investigate feature engineering for target leakage."
        )

    def test_temporal_split_no_future_data(self) -> None:
        """If temporal data exists, test set must not contain dates before train set.

        Skipped until the service has a temporal feature in `sample_data`.
        To enable:
            1. Add a `transaction_date` (or similar) column to the
               `sample_data` fixture.
            2. Replace the body below with a real assertion, e.g.::

                X_train, X_test, _, _ = train_test_split(X, y, test_size=0.2)
                assert X_train['transaction_date'].max() < X_test['transaction_date'].min()

        Tracking: D-13 (data validation) + ADR-006 (closed-loop monitoring
        depends on temporally-ordered ground-truth labels).
        """
        pytest.skip(
            "Service-specific: enable after adding a temporal feature to sample_data. "
            "See test docstring for the assertion to write."
        )


# ---------------------------------------------------------------------------
# Quality Gate Tests
# ---------------------------------------------------------------------------
class TestQualityGates:
    """Tests that model meets minimum quality standards for promotion."""

    def test_model_meets_primary_gate(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """Primary metric (ROC-AUC) must be above production threshold."""
        X, y = sample_data
        _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        y_prob = trained_pipeline.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, y_prob)

        assert auc >= PRIMARY_THRESHOLD, f"Primary metric {auc:.4f} below threshold {PRIMARY_THRESHOLD}"

    def test_model_predicts_both_classes(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """Model must predict both classes (not degenerate)."""
        X, y = sample_data
        y_pred = trained_pipeline.predict(X)
        unique_predictions = np.unique(y_pred)

        assert len(unique_predictions) >= 2, f"Model only predicts {unique_predictions} — degenerate model"

    def test_probabilities_calibrated(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """Predicted probabilities must span a reasonable range."""
        X, _ = sample_data
        y_prob = trained_pipeline.predict_proba(X)[:, 1]

        assert y_prob.min() < 0.3, f"Min probability {y_prob.min():.3f} too high"
        assert y_prob.max() > 0.7, f"Max probability {y_prob.max():.3f} too low"

    def test_predictions_deterministic_under_seed(self, sample_data: tuple) -> None:
        """Two pipelines fit with the same random_state must produce
        identical predictions on the same input.

        Determinism is required for reproducible model promotion (ADR-002):
        the same data + code + seed must give the same model SHA256.
        """
        X, y = sample_data
        X_train, X_test, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)

        pipe_a = Pipeline([("model", GradientBoostingClassifier(random_state=42))])
        pipe_b = Pipeline([("model", GradientBoostingClassifier(random_state=42))])
        pipe_a.fit(X_train, y_train)
        pipe_b.fit(X_train, y_train)

        np.testing.assert_array_equal(
            pipe_a.predict(X_test),
            pipe_b.predict(X_test),
            err_msg="Same-seed pipelines produced different predictions — non-deterministic training.",
        )


# ---------------------------------------------------------------------------
# Feature Engineering Tests
# ---------------------------------------------------------------------------
class TestFeatureEngineering:
    """Tests for feature engineering consistency between train and inference."""

    def test_feature_engineer_output_shape(self, sample_data: tuple) -> None:
        """Feature engineer must produce expected number of columns."""
        X, _ = sample_data
        assert X.shape[1] == N_EXPECTED_FEATURES, f"Expected {N_EXPECTED_FEATURES} features, got {X.shape[1]}"

    def test_feature_engineer_no_nans(self, sample_data: tuple) -> None:
        """Feature engineer must not produce NaN values."""
        X, _ = sample_data
        nan_counts = X.isna().sum()
        assert nan_counts.sum() == 0, f"NaN values found in features: {nan_counts[nan_counts > 0].to_dict()}"

    def test_feature_engineer_no_infinities(self, sample_data: tuple) -> None:
        """Feature engineer must not produce infinite values."""
        X, _ = sample_data
        inf_mask = np.isinf(X.select_dtypes(include=[np.number]).values)
        assert not inf_mask.any(), "Infinite values found in features"

    def test_inference_uses_same_features(self, sample_data: tuple) -> None:
        """transform() and transform_inference() must produce identical columns.

        Train/inference feature drift is one of the most common silent
        failure modes in production. This test catches it at PR time.

        Skipped until the scaffolded service implements FeatureEngineer.
        To enable:
            1. Implement `src.{service}.training.features.FeatureEngineer`
               with `transform(df)` and `transform_inference(df)` methods.
            2. Uncomment the assertion below.
        """
        pytest.skip(
            "Service-specific: enable after implementing FeatureEngineer in "
            "src.{service}.training.features. Required by D-04 (SHAP feature "
            "space consistency) and ADR-006 (training/serving parity)."
        )
        # When ready, replace the skip with:
        #     from src.{service}.training.features import FeatureEngineer
        #     X_df, y_series = sample_data
        #     full_df = pd.concat([X_df, y_series.rename("target")], axis=1)
        #     fe = FeatureEngineer()
        #     X_train, _ = fe.transform(full_df)
        #     X_infer = fe.transform_inference(full_df.drop(columns=["target"]))
        #     assert list(X_train.columns) == list(X_infer.columns), (
        #         "Train/inference feature drift detected: "
        #         f"train={list(X_train.columns)} vs infer={list(X_infer.columns)}"
        #     )


# ---------------------------------------------------------------------------
# Inference Latency Tests
# ---------------------------------------------------------------------------
class TestInferenceLatency:
    """Tests that inference meets latency SLA."""

    def test_single_prediction_latency(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """Single prediction must complete within SLA."""
        X, _ = sample_data
        single_row = X.iloc[[0]]

        # Warm-up (first call has overhead from imports, JIT, etc.)
        trained_pipeline.predict_proba(single_row)

        # Measure over multiple runs
        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            trained_pipeline.predict_proba(single_row)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

        p95_latency = np.percentile(latencies, 95)
        assert p95_latency < LATENCY_SLA_MS, f"P95 inference latency {p95_latency:.1f}ms exceeds SLA {LATENCY_SLA_MS}ms"

    def test_batch_prediction_throughput(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """Batch of 100 predictions must complete within 10x single SLA."""
        X, _ = sample_data
        batch = X.head(100)

        start = time.perf_counter()
        trained_pipeline.predict_proba(batch)
        elapsed_ms = (time.perf_counter() - start) * 1000

        batch_sla = LATENCY_SLA_MS * 10
        assert elapsed_ms < batch_sla, f"Batch (100) latency {elapsed_ms:.1f}ms exceeds {batch_sla}ms"


# ---------------------------------------------------------------------------
# Fairness Tests
# ---------------------------------------------------------------------------
class TestFairness:
    """Tests for model fairness across protected attributes.

    Disparate Impact Ratio (DIR) = P(positive|unprivileged) / P(positive|privileged)
    Must be >= FAIRNESS_THRESHOLD (0.80 per four-fifths rule).
    """

    def test_disparate_impact_ratio(self, trained_pipeline: Pipeline, sample_data: tuple) -> None:
        """DIR must be >= 0.80 for synthesized protected attribute.

        TODO: Replace with actual protected attributes from your data.
        """
        X, _ = sample_data
        y_prob = trained_pipeline.predict_proba(X)[:, 1]

        # Simulate a protected attribute (binary group)
        # TODO: Use actual protected attribute column from your data
        np.random.seed(42)
        group = np.random.choice([0, 1], size=len(X))

        pos_rate_0 = (y_prob[group == 0] >= 0.5).mean()
        pos_rate_1 = (y_prob[group == 1] >= 0.5).mean()

        if max(pos_rate_0, pos_rate_1) > 0:
            dir_value = min(pos_rate_0, pos_rate_1) / max(pos_rate_0, pos_rate_1)
        else:
            dir_value = 1.0

        assert dir_value >= FAIRNESS_THRESHOLD, f"Fairness violation: DIR={dir_value:.3f} < {FAIRNESS_THRESHOLD}"
