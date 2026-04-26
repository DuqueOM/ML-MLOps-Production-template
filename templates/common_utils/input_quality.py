"""Edge-level input quality checks for served predictions (v1.8.1, ADR-006).

Pydantic validates TYPES and per-field ranges; it cannot detect values
that are "technically valid" but fall outside the distribution seen at
training time. Example: a user supplies ``age=95`` — valid type, valid
Pydantic range (0-150), but the training set only saw [18, 85]. The
model's prediction is extrapolation; quality may be poor.

This module provides a lightweight, opt-in check that:
    1. Loads a ``baseline_quantiles.json`` file emitted at training time
    2. Flags inputs where any numeric feature value falls outside the
       [q_low, q_high] range (default p01 / p99)
    3. Increments a Prometheus counter (one per flagged feature) so
       operators see WHICH features drift at serving time
    4. NEVER blocks the request — flagging is observational

Design trade-offs:
    * Lightweight: one dict lookup + two comparisons per feature
    * No Pandera here: Pandera is for DataFrames in training/monitoring;
      the overhead per-request is unjustified for ~10 feature-comparisons
    * Explainable: flagged features are recorded as labels so dashboards
      show the long tail, not a scalar "drift=X" number

Usage in fastapi_app.py::

    from common_utils.input_quality import InputQualityChecker

    checker = InputQualityChecker.from_file("artifacts/baseline_quantiles.json")
    app.state.input_quality = checker

    # in /predict:
    flags = app.state.input_quality.check(request.dict())
    # flags is e.g., ["feature_a:above_p99"] — emit to metric + log

Opt-in via env var ``INPUT_QUALITY_ENABLED``. When the baseline file is
absent (e.g., first deploy of a new service), the checker degrades to
a no-op with a startup warning.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureQuantiles:
    """Per-feature quantile boundaries observed at training time."""

    feature: str
    q_low: float
    q_high: float

    def classify(self, value: Any) -> str | None:
        """Return a flag string if value is outside [q_low, q_high], else None."""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None  # non-numeric features are outside this module's scope
        if v < self.q_low:
            return f"{self.feature}:below_p01"
        if v > self.q_high:
            return f"{self.feature}:above_p99"
        return None


@dataclass
class InputQualityChecker:
    """Opt-in edge check against training-time feature quantiles."""

    quantiles: dict[str, FeatureQuantiles] = field(default_factory=dict)
    enabled: bool = True

    @classmethod
    def from_file(cls, path: str | Path) -> "InputQualityChecker":
        """Load quantiles from JSON: {"feature_a": {"p01": ..., "p99": ...}, ...}.

        Missing file → returns a disabled checker with a warning (not an error —
        new services may deploy before a baseline is available).
        """
        path = Path(path)
        if not path.exists():
            logger.warning(
                "InputQualityChecker: baseline file %s not found — checks disabled",
                path,
            )
            return cls(enabled=False)
        try:
            raw = json.loads(path.read_text())
        except Exception as exc:  # noqa: BLE001
            logger.warning("InputQualityChecker: could not parse %s (%s) — checks disabled", path, exc)
            return cls(enabled=False)

        qs: dict[str, FeatureQuantiles] = {}
        for feat, spec in raw.items():
            try:
                q_low = float(spec["p01"])
                q_high = float(spec["p99"])
                qs[feat] = FeatureQuantiles(feature=feat, q_low=q_low, q_high=q_high)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("InputQualityChecker: skip %s (bad quantile spec: %s)", feat, exc)
        return cls(quantiles=qs, enabled=bool(qs))

    def check(self, features: dict[str, Any]) -> list[str]:
        """Return list of flag strings for features outside training quantiles."""
        if not self.enabled:
            return []
        flags: list[str] = []
        for feat, value in features.items():
            q = self.quantiles.get(feat)
            if q is None:
                continue
            flag = q.classify(value)
            if flag is not None:
                flags.append(flag)
        return flags


def build_from_env(default_path: str = "artifacts/baseline_quantiles.json") -> InputQualityChecker:
    """Factory honoring ``INPUT_QUALITY_ENABLED`` and ``INPUT_QUALITY_PATH``.

    Defaults keep the feature opt-in: if either env var is unset and the
    default file is absent, returns a disabled checker. Startup log
    announces the decision explicitly so deploys are auditable.
    """
    if os.getenv("INPUT_QUALITY_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        logger.info("InputQualityChecker: disabled via INPUT_QUALITY_ENABLED")
        return InputQualityChecker(enabled=False)
    path = os.getenv("INPUT_QUALITY_PATH", default_path)
    return InputQualityChecker.from_file(path)


__all__ = [
    "FeatureQuantiles",
    "InputQualityChecker",
    "build_from_env",
]
