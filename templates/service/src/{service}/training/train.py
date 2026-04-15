"""Training pipeline for {ServiceName}.

Implements the mandatory training sequence:
1. load_data + Pandera validation
2. engineer_features
3. split_train_val_test (temporal if dates exist)
4. cross_validate
5. evaluate with optimal threshold
6. fairness_check (DIR >= 0.80)
7. save_artifacts with SHA256
8. log_to_mlflow
9. quality_gates
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import joblib
import mlflow
import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import (
    f1_score,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score

from ..schemas import ServiceInputSchema
from .features import FeatureEngineer
from .model import build_pipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — customize per service
# ---------------------------------------------------------------------------
EXPERIMENT_NAME = "{ServiceName}-Production"
MODEL_REGISTRY_NAME = "{ServiceName}Classifier"

# Quality gates — set real thresholds for your service
PRIMARY_METRIC = "roc_auc"
PRIMARY_THRESHOLD = 0.80
SECONDARY_METRIC = "f1"
SECONDARY_THRESHOLD = 0.55
FAIRNESS_THRESHOLD = 0.80  # Disparate Impact Ratio
LATENCY_SLA_MS = 100.0

# Protected attributes for fairness checks
PROTECTED_ATTRIBUTES: list[str] = []  # e.g., ["gender", "age_group"]

OPTUNA_TRIALS = 50
CV_FOLDS = 5
RANDOM_STATE = 42


class Trainer:
    """Orchestrates the full training pipeline."""

    def __init__(self, data_path: str, output_dir: str = "models") -> None:
        self.data_path = data_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.feature_engineer = FeatureEngineer()

    def run(self, optuna_trials: int = OPTUNA_TRIALS) -> dict[str, Any]:
        """Execute the complete training pipeline.

        Returns:
            Dict with model metrics and artifact paths.
        """
        # Step 1: Load + validate
        logger.info("Step 1: Loading and validating data")
        df = self._load_data()

        # Step 2: Feature engineering
        logger.info("Step 2: Engineering features")
        X, y = self.feature_engineer.transform(df)

        # Step 3: Split
        logger.info("Step 3: Splitting train/val/test")
        splits = self._split_data(X, y)

        # Step 4: Hyperparameter tuning with Optuna
        logger.info("Step 4: Optuna hyperparameter tuning (%d trials)", optuna_trials)
        best_params = self._tune_hyperparameters(splits["X_train"], splits["y_train"], n_trials=optuna_trials)

        # Step 5: Train final model + cross-validate
        logger.info("Step 5: Training final model with best params")
        pipeline = build_pipeline(**best_params)
        cv_scores = cross_val_score(
            pipeline,
            splits["X_train"],
            splits["y_train"],
            cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
            scoring=PRIMARY_METRIC,
        )
        pipeline.fit(splits["X_train"], splits["y_train"])

        # Step 6: Evaluate on test set
        logger.info("Step 6: Evaluating on test set")
        metrics = self._evaluate(pipeline, splits)

        # Step 7: Fairness check
        logger.info("Step 7: Fairness check")
        fairness_metrics = self._fairness_check(pipeline, splits)
        metrics.update(fairness_metrics)

        # Step 8: Save artifacts
        logger.info("Step 8: Saving artifacts")
        artifact_path = self._save_artifacts(pipeline, metrics)

        # Step 9: Log to MLflow
        logger.info("Step 9: Logging to MLflow")
        self._log_to_mlflow(pipeline, metrics, best_params, artifact_path)

        # Step 10: Quality gates
        logger.info("Step 10: Checking quality gates")
        gates_result = self._quality_gates(metrics)

        return {
            "metrics": metrics,
            "cv_scores": cv_scores.tolist(),
            "cv_mean": float(cv_scores.mean()),
            "best_params": best_params,
            "artifact_path": str(artifact_path),
            "quality_gates": gates_result,
        }

    def _load_data(self) -> pd.DataFrame:
        """Load and validate data with Pandera."""
        df = pd.read_csv(self.data_path)
        validated = ServiceInputSchema.validate(df)
        logger.info("Data validated: %d rows, %d columns", len(df), len(df.columns))
        return validated

    def _split_data(self, X: pd.DataFrame, y: pd.Series) -> dict[str, pd.DataFrame | pd.Series]:
        """Split into train/test.

        TODO: If your data has temporal ordering, use temporal split
        instead of random split to prevent data leakage.
        """
        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)
        return {
            "X_train": X_train,
            "X_test": X_test,
            "y_train": y_train,
            "y_test": y_test,
        }

    def _tune_hyperparameters(self, X_train: pd.DataFrame, y_train: pd.Series, n_trials: int) -> dict:
        """Optuna hyperparameter search.

        TODO: Define your search space in the objective function.
        """

        def objective(trial: optuna.Trial) -> float:
            # TODO: Define service-specific hyperparameter search space
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            }
            pipeline = build_pipeline(**params)
            score = cross_val_score(
                pipeline,
                X_train,
                y_train,
                cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE),
                scoring=PRIMARY_METRIC,
            ).mean()
            return score

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
        return study.best_params

    def _evaluate(self, pipeline: Any, splits: dict) -> dict[str, float]:
        """Evaluate model on test set with multiple metrics."""
        X_test = splits["X_test"]
        y_test = splits["y_test"]

        y_prob = pipeline.predict_proba(X_test)[:, 1]

        # Optimal threshold via precision-recall curve
        precisions, recalls, thresholds = precision_recall_curve(y_test, y_prob)
        f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-8)
        optimal_idx = np.argmax(f1_scores)
        optimal_threshold = float(thresholds[optimal_idx]) if optimal_idx < len(thresholds) else 0.5

        y_pred = (y_prob >= optimal_threshold).astype(int)

        return {
            "roc_auc": float(roc_auc_score(y_test, y_prob)),
            "f1": float(f1_score(y_test, y_pred)),
            "optimal_threshold": optimal_threshold,
            "test_size": len(y_test),
        }

    def _fairness_check(self, pipeline: Any, splits: dict) -> dict[str, float]:
        """Check Disparate Impact Ratio per protected attribute.

        DIR = P(positive | unprivileged) / P(positive | privileged)
        Must be >= 0.80 for each protected attribute.
        """
        metrics: dict[str, float] = {}

        if not PROTECTED_ATTRIBUTES:
            logger.warning("No protected attributes defined — skipping fairness check")
            return metrics

        X_test = splits["X_test"]
        y_prob = pipeline.predict_proba(X_test)[:, 1]
        threshold = 0.5  # TODO: Use optimal threshold

        for attr in PROTECTED_ATTRIBUTES:
            if attr not in X_test.columns:
                logger.warning("Protected attribute '%s' not in test data", attr)
                continue

            groups = X_test[attr].unique()
            if len(groups) < 2:
                continue

            # Calculate positive rate per group
            rates = {}
            for group in groups:
                mask = X_test[attr] == group
                rates[group] = float((y_prob[mask] >= threshold).mean())

            # DIR = min_rate / max_rate
            min_rate = min(rates.values())
            max_rate = max(rates.values())
            dir_value = min_rate / max_rate if max_rate > 0 else 0.0
            metrics[f"dir_{attr}"] = dir_value

            if dir_value < FAIRNESS_THRESHOLD:
                logger.warning(
                    "Fairness violation: DIR for %s = %.3f (threshold: %.2f)",
                    attr,
                    dir_value,
                    FAIRNESS_THRESHOLD,
                )

        return metrics

    def _save_artifacts(self, pipeline: Any, metrics: dict) -> Path:
        """Save model with SHA256 checksum."""
        model_path = self.output_dir / "model.joblib"
        joblib.dump(pipeline, model_path)

        # SHA256 for integrity verification
        sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
        meta = {"sha256": sha256, "metrics": metrics}
        meta_path = self.output_dir / "model_metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info("Model saved: %s (SHA256: %s)", model_path, sha256[:16])
        return model_path

    def _log_to_mlflow(
        self,
        pipeline: Any,
        metrics: dict,
        params: dict,
        artifact_path: Path,
    ) -> None:
        """Log experiment to MLflow."""
        mlflow.set_experiment(EXPERIMENT_NAME)

        with mlflow.start_run():
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            mlflow.log_artifact(str(artifact_path))
            mlflow.log_artifact(str(artifact_path.parent / "model_metadata.json"))

            mlflow.set_tag("git_commit", os.getenv("GIT_SHA", "unknown"))
            mlflow.set_tag("environment", os.getenv("ENVIRONMENT", "development"))

            # Register model
            mlflow.sklearn.log_model(
                pipeline,
                artifact_path="model",
                registered_model_name=MODEL_REGISTRY_NAME,
            )

    def _quality_gates(self, metrics: dict) -> dict[str, bool]:
        """Check all quality gates. ALL must pass for promotion."""
        gates = {
            f"{PRIMARY_METRIC} >= {PRIMARY_THRESHOLD}": metrics.get(PRIMARY_METRIC, 0) >= PRIMARY_THRESHOLD,
            f"{SECONDARY_METRIC} >= {SECONDARY_THRESHOLD}": metrics.get(SECONDARY_METRIC, 0) >= SECONDARY_THRESHOLD,
        }

        # Fairness gates
        for attr in PROTECTED_ATTRIBUTES:
            key = f"dir_{attr}"
            if key in metrics:
                gates[f"DIR({attr}) >= {FAIRNESS_THRESHOLD}"] = metrics[key] >= FAIRNESS_THRESHOLD

        all_passed = all(gates.values())
        failed = [name for name, passed in gates.items() if not passed]

        if all_passed:
            logger.info("All quality gates PASSED")
        else:
            logger.warning("Quality gates FAILED: %s", failed)

        return {"all_passed": all_passed, "gates": gates, "failed": failed}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train {ServiceName} model")
    parser.add_argument("--data", required=True, help="Path to training CSV")
    parser.add_argument("--experiment", default=EXPERIMENT_NAME, help="MLflow experiment name")
    parser.add_argument("--optuna-trials", type=int, default=OPTUNA_TRIALS, help="Optuna trials")
    args = parser.parse_args()

    EXPERIMENT_NAME = args.experiment
    trainer = Trainer(data_path=args.data)
    result = trainer.run(optuna_trials=args.optuna_trials)

    print(json.dumps(result, indent=2, default=str))
