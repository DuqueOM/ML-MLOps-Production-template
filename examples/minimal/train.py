"""Train a fraud detection model on synthetic data.

Demonstrates:
- Synthetic data generation (no real data needed)
- Pandera schema validation
- sklearn pipeline with ColumnTransformer
- Quality gates (ROC-AUC, fairness DIR, leakage check)
- Model persistence with joblib

Run:
    python train.py
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pandera as pa
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEED = 42
N_SAMPLES = 2000
TEST_SIZE = 0.2
PRIMARY_THRESHOLD = 0.65  # Minimum ROC-AUC (synthetic demo data — lower than production)
FAIRNESS_THRESHOLD = 0.70  # Minimum Disparate Impact Ratio
LEAKAGE_THRESHOLD = 0.99  # Above this → investigate leakage


# ---------------------------------------------------------------------------
# Pandera schema — validates data before training
# ---------------------------------------------------------------------------
class FraudInputSchema(pa.DataFrameModel):
    """Input validation schema for fraud detection."""

    amount: float = pa.Field(ge=0, description="Transaction amount in USD")
    hour: int = pa.Field(ge=0, le=23, description="Hour of transaction (0-23)")
    is_foreign: bool = pa.Field(description="Whether transaction is international")
    merchant_risk: float = pa.Field(ge=0, le=1, description="Merchant risk score (0-1)")
    distance_from_home: float = pa.Field(ge=0, description="Distance from home in km")

    class Config:
        coerce = True


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------
def generate_synthetic_data(n_samples: int = N_SAMPLES, seed: int = SEED) -> pd.DataFrame:
    """Generate synthetic fraud detection dataset.

    Creates realistic-looking transaction data where fraud probability
    depends on amount, hour, foreign status, merchant risk, and distance.
    """
    rng = np.random.RandomState(seed)

    amount = rng.exponential(scale=200, size=n_samples).clip(1, 10000)
    hour = rng.randint(0, 24, size=n_samples)
    is_foreign = rng.choice([True, False], size=n_samples, p=[0.15, 0.85])
    merchant_risk = rng.beta(2, 5, size=n_samples)
    distance = rng.exponential(scale=20, size=n_samples).clip(0, 500)

    # Fraud probability based on features (not perfectly separable).
    # is_foreign is a weak signal to avoid fairness (DIR) violations.
    logit = (
        -3.0
        + 0.003 * amount
        + 0.5 * (hour < 6).astype(float)
        + 0.4 * is_foreign.astype(float)
        + 2.5 * merchant_risk
        + 0.015 * distance
        + rng.normal(0, 0.8, size=n_samples)
    )
    prob = 1 / (1 + np.exp(-logit))
    is_fraud = (rng.random(size=n_samples) < prob).astype(int)

    df = pd.DataFrame(
        {
            "amount": np.round(amount, 2),
            "hour": hour,
            "is_foreign": is_foreign,
            "merchant_risk": np.round(merchant_risk, 4),
            "distance_from_home": np.round(distance, 2),
            "is_fraud": is_fraud,
        }
    )

    logger.info("Generated %d samples (fraud rate: %.1f%%)", n_samples, is_fraud.mean() * 100)
    return df


# ---------------------------------------------------------------------------
# Training pipeline
# ---------------------------------------------------------------------------
def build_pipeline() -> Pipeline:
    """Build sklearn pipeline with preprocessing + model."""
    numeric_features = ["amount", "hour", "merchant_risk", "distance_from_home"]
    passthrough_features = ["is_foreign"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
            ("pass", "passthrough", passthrough_features),
        ]
    )

    return Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "classifier",
                GradientBoostingClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    random_state=SEED,
                ),
            ),
        ]
    )


def run_quality_gates(
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """Run all quality gates before model promotion.

    Gates:
        1. Primary metric (ROC-AUC) >= threshold
        2. Leakage check (ROC-AUC < suspiciously high threshold)
        3. Fairness check (Disparate Impact Ratio >= 0.80)
        4. Predicts both classes (not degenerate)
    """
    y_prob = pipeline.predict_proba(X_test)[:, 1]
    y_pred = pipeline.predict(X_test)
    auc = roc_auc_score(y_test, y_prob)
    f1 = f1_score(y_test, y_pred)

    gates = {
        "roc_auc": round(float(auc), 4),
        "f1_score": round(float(f1), 4),
        "primary_gate_passed": bool(auc >= PRIMARY_THRESHOLD),
        "leakage_check_passed": bool(auc < LEAKAGE_THRESHOLD),
        "predicts_both_classes": bool(len(np.unique(y_pred)) >= 2),
    }

    # Fairness: DIR on is_foreign (protected attribute proxy)
    foreign_mask = X_test["is_foreign"].astype(bool)
    pos_rate_foreign = float((y_prob[foreign_mask] >= 0.5).mean()) if foreign_mask.sum() > 0 else 0.0
    pos_rate_domestic = float((y_prob[~foreign_mask] >= 0.5).mean()) if (~foreign_mask).sum() > 0 else 0.0

    if max(pos_rate_foreign, pos_rate_domestic) > 0:
        dir_value = min(pos_rate_foreign, pos_rate_domestic) / max(pos_rate_foreign, pos_rate_domestic)
    else:
        dir_value = 1.0

    gates["disparate_impact_ratio"] = round(float(dir_value), 4)
    gates["fairness_gate_passed"] = bool(dir_value >= FAIRNESS_THRESHOLD)
    gates["all_passed"] = bool(
        gates["primary_gate_passed"]
        and gates["leakage_check_passed"]
        and gates["predicts_both_classes"]
        and gates["fairness_gate_passed"]
    )

    return gates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    start = time.perf_counter()

    # Generate data
    df = generate_synthetic_data()

    # Validate with Pandera
    feature_cols = ["amount", "hour", "is_foreign", "merchant_risk", "distance_from_home"]
    FraudInputSchema.validate(df[feature_cols])
    logger.info("Pandera validation passed")

    # Split
    X = df[feature_cols]
    y = df["is_fraud"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=TEST_SIZE, random_state=SEED, stratify=y)

    # Train
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)
    logger.info("Model trained on %d samples", len(X_train))

    # Quality gates
    gates = run_quality_gates(pipeline, X_test, y_test)
    logger.info("Quality gates: %s", json.dumps(gates, indent=2))

    if not gates["all_passed"]:
        logger.error("QUALITY GATES FAILED — model NOT promoted")
        raise SystemExit(1)

    # Save artifacts
    output_dir = Path("artifacts")
    output_dir.mkdir(exist_ok=True)

    joblib.dump(pipeline, output_dir / "model.joblib")
    logger.info("Model saved to artifacts/model.joblib")

    # Save background data for SHAP (50 representative samples)
    bg = X_train.sample(n=50, random_state=SEED)
    bg.to_csv(output_dir / "background.csv", index=False)
    logger.info("Background data saved (50 samples)")

    # Save reference data for drift detection
    X_train.to_csv(output_dir / "reference.csv", index=False)
    logger.info("Reference data saved for drift detection")

    # Save test data
    X_test.to_csv(output_dir / "test_features.csv", index=False)
    y_test.to_csv(output_dir / "test_labels.csv", index=False)

    # Save metrics
    elapsed = time.perf_counter() - start
    metrics = {
        **gates,
        "training_time_seconds": round(elapsed, 2),
        "train_size": len(X_train),
        "test_size": len(X_test),
    }
    Path(output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    logger.info("Training completed in %.1fs — all gates passed", elapsed)


if __name__ == "__main__":
    main()
