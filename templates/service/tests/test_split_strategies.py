"""Train/test split-strategy hardening tests (ADR-015 PR-B3).

Verifies that ``Trainer._split_data`` honours the configured strategy:

- ``temporal``: orders by ``timestamp_column`` and puts the LATEST rows
  in test. The split must NOT shuffle; the largest train timestamp must
  be ≤ the smallest test timestamp.
- ``grouped``: a given ``entity_id_column`` value never appears in
  both splits — even if pure-random would have happened to do so.
- ``random``: refuses to run unless ``acknowledge_iid: true`` is set
  in the config; this is the load-bearing rule that makes leakage on
  temporal data impossible by accident.
- The resulting ``self._split_meta`` carries the strategy + counts so
  the training manifest (PR-B3 stage 2) records the audit trail.

We exercise the gate via a stand-in ``_SplitOnlyTrainer`` so we don't
need MLflow, Optuna, sklearn classifiers, or a real
``QualityGatesConfig`` round-trip — just the split dispatch.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("mlflow")
pytest.importorskip("optuna")
pytest.importorskip("sklearn")
pytest.importorskip("pandera")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

train_module = importlib.import_module("{service}.training.train")
config_module = importlib.import_module("{service}.config")

Trainer = train_module.Trainer
SplitConfig = config_module.SplitConfig
QualityGatesConfig = config_module.QualityGatesConfig


# ---------------------------------------------------------------------------
# Helpers — invoke _split_data without the rest of __init__
# ---------------------------------------------------------------------------


class _SplitOnlyTrainer:
    """Minimal stand-in that owns just enough state for ``_split_data``.

    The full ``Trainer.__init__`` would load YAML, validate quality
    gates, run the EDA gate, etc. None of that is needed for testing
    the split dispatch — we just need ``self.gates.split`` and the
    bound method.
    """

    _split_data = train_module.Trainer._split_data

    def __init__(self, split: SplitConfig) -> None:
        self.gates = QualityGatesConfig(
            primary_metric="roc_auc",
            primary_threshold=0.8,
            secondary_metric="f1",
            secondary_threshold=0.55,
            protected_attributes=[],
            split=split,
        )


def _make_temporal_data(n: int = 200) -> tuple[pd.DataFrame, pd.Series]:
    """Synthetic frame with a strict ascending timestamp."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "feature": rng.normal(0, 1, n),
            "ts": pd.date_range("2024-01-01", periods=n, freq="h"),
        }
    )
    y = pd.Series(rng.integers(0, 2, n), name="target")
    return df, y


def _make_grouped_data(n_groups: int = 50, rows_per_group: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    """Synthetic frame with multiple rows per entity_id."""
    rng = np.random.default_rng(1)
    rows = []
    for g in range(n_groups):
        for _ in range(rows_per_group):
            rows.append({"feature": rng.normal(0, 1), "customer_id": f"cust_{g}"})
    df = pd.DataFrame(rows)
    y = pd.Series(rng.integers(0, 2, len(df)), name="target")
    return df, y


# ---------------------------------------------------------------------------
# Temporal split
# ---------------------------------------------------------------------------


def test_temporal_split_puts_latest_rows_in_test() -> None:
    X, y = _make_temporal_data(200)
    trainer = _SplitOnlyTrainer(
        SplitConfig(strategy="temporal", timestamp_column="ts", test_fraction=0.2)
    )
    splits = trainer._split_data(X, y)

    train_max_ts = splits["X_train"]["ts"].max()
    test_min_ts = splits["X_test"]["ts"].min()
    assert train_max_ts <= test_min_ts, (
        "temporal split leaked future into train: "
        f"train_max_ts={train_max_ts} > test_min_ts={test_min_ts}"
    )
    assert len(splits["X_test"]) == 40
    assert len(splits["X_train"]) == 160
    # Manifest metadata recorded
    assert trainer._split_meta == {
        "strategy": "temporal",
        "timestamp_column": "ts",
        "entity_id_column": None,
        "test_fraction": 0.2,
        "random_state": 42,
        "n_train": 160,
        "n_test": 40,
    }


def test_temporal_split_requires_timestamp_column() -> None:
    X, y = _make_temporal_data(50)
    trainer = _SplitOnlyTrainer(SplitConfig(strategy="temporal"))  # no timestamp_column
    with pytest.raises(ValueError, match="timestamp_column"):
        trainer._split_data(X, y)


def test_temporal_split_rejects_missing_column() -> None:
    X, y = _make_temporal_data(50)
    trainer = _SplitOnlyTrainer(SplitConfig(strategy="temporal", timestamp_column="not_a_real_col"))
    with pytest.raises(ValueError, match="not_a_real_col"):
        trainer._split_data(X, y)


# ---------------------------------------------------------------------------
# Grouped split
# ---------------------------------------------------------------------------


def test_grouped_split_keeps_groups_disjoint() -> None:
    X, y = _make_grouped_data(50, 4)
    trainer = _SplitOnlyTrainer(
        SplitConfig(strategy="grouped", entity_id_column="customer_id", test_fraction=0.25)
    )
    splits = trainer._split_data(X, y)
    train_ids = set(splits["X_train"]["customer_id"])
    test_ids = set(splits["X_test"]["customer_id"])
    overlap = train_ids & test_ids
    assert overlap == set(), f"grouped split leaked entities into both sides: {overlap}"
    # Size sanity
    assert len(splits["X_train"]) + len(splits["X_test"]) == len(X)
    assert trainer._split_meta["strategy"] == "grouped"
    assert trainer._split_meta["entity_id_column"] == "customer_id"


def test_grouped_split_requires_entity_id_column() -> None:
    X, y = _make_grouped_data(20, 3)
    trainer = _SplitOnlyTrainer(SplitConfig(strategy="grouped"))
    with pytest.raises(ValueError, match="entity_id_column"):
        trainer._split_data(X, y)


# ---------------------------------------------------------------------------
# Random split
# ---------------------------------------------------------------------------


def test_random_split_refuses_without_acknowledgement() -> None:
    """The default `random + acknowledge_iid=False` must raise. This
    is the load-bearing rule that makes accidental leakage on temporal
    data impossible.
    """
    X, y = _make_temporal_data(50)
    trainer = _SplitOnlyTrainer(SplitConfig(strategy="random"))  # acknowledge_iid defaults to False
    with pytest.raises(ValueError, match="acknowledge_iid"):
        trainer._split_data(X, y)


def test_random_split_runs_with_acknowledgement() -> None:
    X, y = _make_temporal_data(100)
    trainer = _SplitOnlyTrainer(
        SplitConfig(strategy="random", acknowledge_iid=True, test_fraction=0.2)
    )
    splits = trainer._split_data(X, y)
    assert len(splits["X_train"]) + len(splits["X_test"]) == 100
    assert trainer._split_meta["strategy"] == "random"


# ---------------------------------------------------------------------------
# Strategy enum
# ---------------------------------------------------------------------------


def test_unknown_strategy_rejected_at_config_load() -> None:
    """SplitConfig.strategy is constrained at construction time."""
    with pytest.raises(ValueError, match="strategy must be one of"):
        SplitConfig(strategy="temproal")  # typo
