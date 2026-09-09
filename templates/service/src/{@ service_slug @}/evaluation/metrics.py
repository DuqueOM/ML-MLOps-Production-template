"""Model evaluation and metrics for {@ service_name @}.

Provides comprehensive evaluation including:
- Standard classification metrics (accuracy, precision, recall, F1, AUC)
- ROC curves and optimal threshold selection
- Confusion matrix analysis
- Fairness metrics per sensitive feature (Disparate Impact Ratio)
- JSON export for CI/CD artifact upload

Usage:
    evaluator = ModelEvaluator.from_files("models/model.joblib")
    metrics = evaluator.evaluate(X_test, y_test, output_path="results/eval.json")
    fairness = evaluator.compute_fairness_metrics(X_test, y_test, ["Gender", "Geography"])

TODO: Adjust metric selection and fairness features for your domain.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Comprehensive model evaluation.

    Parameters
    ----------
    model : Pipeline or estimator
        Trained model with predict and predict_proba methods.
    preprocessor : optional
        Fitted preprocessor (required only if model is NOT a Pipeline).
    """

    def __init__(self, model: Any, preprocessor: Any = None) -> None:
        self.model = model
        self.preprocessor = preprocessor
        self.metrics_: dict[str, float] = {}

        # Auto-extract preprocessor from Pipeline if not explicitly provided
        if self.preprocessor is None and isinstance(self.model, Pipeline):
            try:
                self.preprocessor = self.model.named_steps["preprocessor"]
            except (KeyError, AttributeError):
                pass

    @classmethod
    def from_files(
        cls,
        model_path: str | Path,
        preprocessor_path: str | Path | None = None,
    ) -> ModelEvaluator:
        """Load model (and optional preprocessor) from disk."""
        model = joblib.load(model_path)
        preprocessor = None
        if preprocessor_path:
            try:
                preprocessor = joblib.load(preprocessor_path)
                logger.info("Loaded preprocessor from %s", preprocessor_path)
            except Exception as e:
                logger.warning("Could not load preprocessor: %s", e)
        logger.info("Loaded model from %s", model_path)
        return cls(model, preprocessor)

    def evaluate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Evaluate model performance on test data.

        Returns dict with accuracy, precision, recall, f1, roc_auc,
        confusion_matrix, and classification_report.
        """
        # Predict — handle both Pipeline and legacy (separate preprocessor) models
        if isinstance(self.model, Pipeline):
            y_pred = self.model.predict(X)
            try:
                y_proba = self.model.predict_proba(X)
                has_proba = True
            except AttributeError:
                y_proba = None
                has_proba = False
        else:
            if self.preprocessor is None:
                raise ValueError("Preprocessor required for non-Pipeline models")
            X_transformed = self.preprocessor.transform(X)
            y_pred = self.model.predict(X_transformed)
            try:
                y_proba = self.model.predict_proba(X_transformed)
                has_proba = True
            except AttributeError:
                y_proba = None
                has_proba = False

        # Core metrics
        metrics: dict[str, Any] = {
            "accuracy": accuracy_score(y, y_pred),
            "precision": precision_score(y, y_pred, average="weighted", zero_division=0),
            "recall": recall_score(y, y_pred, average="weighted", zero_division=0),
            "f1": f1_score(y, y_pred, average="weighted", zero_division=0),
            "confusion_matrix": confusion_matrix(y, y_pred).tolist(),
            "classification_report": classification_report(y, y_pred, output_dict=True, zero_division=0),
        }

        # AUC + ROC curve for binary classification
        if has_proba and len(np.unique(y)) == 2:
            metrics["roc_auc"] = roc_auc_score(y, y_proba[:, 1])
            fpr, tpr, thresholds = roc_curve(y, y_proba[:, 1])
            metrics["roc_curve"] = {
                "fpr": fpr.tolist(),
                "tpr": tpr.tolist(),
                "thresholds": thresholds.tolist(),
            }

        self.metrics_ = metrics

        logger.info(
            "Evaluation: acc=%.4f prec=%.4f rec=%.4f f1=%.4f",
            metrics["accuracy"],
            metrics["precision"],
            metrics["recall"],
            metrics["f1"],
        )
        if "roc_auc" in metrics:
            logger.info("  ROC AUC: %.4f", metrics["roc_auc"])

        if output_path:
            self._save_results(output_path)

        return metrics

    def _save_results(self, output_path: str | Path) -> None:
        """Save evaluation results to JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(self.metrics_, f, indent=2)
        logger.info("Evaluation saved to %s", output_path)

    def compute_fairness_metrics(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sensitive_features: list[str],
    ) -> dict[str, Any]:
        """Compute fairness metrics across sensitive features.

        Calculates per-group metrics and Disparate Impact Ratio:
        DIR = P(positive | min_group) / P(positive | max_group)
        Must be >= 0.80 per the 4/5 rule.

        TODO: List your actual sensitive features (e.g., ["Gender", "Geography"]).
        """
        if isinstance(self.model, Pipeline):
            y_pred = self.model.predict(X)
        else:
            X_transformed = self.preprocessor.transform(X)
            y_pred = self.model.predict(X_transformed)

        fairness_metrics: dict[str, Any] = {}

        for feature in sensitive_features:
            if feature not in X.columns:
                logger.warning("Sensitive feature '%s' not found", feature)
                continue

            groups = X[feature].unique()
            group_metrics: dict[str, Any] = {}

            for group in groups:
                mask = X[feature] == group
                if mask.sum() == 0:
                    continue
                y_true_g = y[mask]
                y_pred_g = y_pred[mask]
                group_metrics[str(group)] = {
                    "count": int(mask.sum()),
                    "accuracy": float(accuracy_score(y_true_g, y_pred_g)),
                    "precision": float(precision_score(y_true_g, y_pred_g, average="weighted", zero_division=0)),
                    "recall": float(recall_score(y_true_g, y_pred_g, average="weighted", zero_division=0)),
                    "f1": float(f1_score(y_true_g, y_pred_g, average="weighted", zero_division=0)),
                }

            # Disparate Impact Ratio
            positive_rates = {}
            for group in groups:
                mask = X[feature] == group
                if mask.sum() > 0:
                    positive_rates[str(group)] = float((y_pred[mask] == 1).mean())

            if len(positive_rates) >= 2:
                rates = list(positive_rates.values())
                di = min(rates) / max(rates) if max(rates) > 0 else 0.0
            else:
                di = 1.0

            fairness_metrics[feature] = {
                "groups": group_metrics,
                "disparate_impact": float(di),
            }
            logger.info("Fairness '%s': DI=%.4f", feature, di)

        return fairness_metrics
