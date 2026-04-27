"""Pandera DataFrameModel for {ServiceName} input validation.

Used at three validation points:
1. Before training (fail fast on invalid data)
2. At /predict endpoint (SchemaError → HTTP 422)
3. During drift detection (schema mismatch = immediate alert)

TODO: Replace example fields with your actual features.
"""

from typing import Optional

import pandera as pa


class ServiceInputSchema(pa.DataFrameModel):
    """Input data schema for {ServiceName}.

    Each field documents type, constraints, and business meaning.

    ``target`` is typed as ``Optional`` so the same schema can validate
    both training frames (target present) and serving / drift frames
    (target absent). Training validates target presence separately —
    see ``training/train.py`` — so making this column optional at the
    schema level does NOT weaken the training-time contract (PR-R2-4).
    """

    # TODO: Define your actual features
    feature_a: float = pa.Field(
        ge=0,
        le=150,
        description="Example numeric feature (e.g., age in years)",
    )
    feature_b: float = pa.Field(
        ge=0,
        description="Example numeric feature (e.g., account balance)",
    )
    feature_c: str = pa.Field(
        isin=["category_A", "category_B", "category_C"],
        description="Example categorical feature",
    )
    # Optional column — present at training, absent at /predict and in drift
    # reference/current frames. ``nullable=True`` additionally allows NaN
    # rows (e.g., rows awaiting ground-truth).
    target: Optional[int] = pa.Field(
        isin=[0, 1],
        description="Binary target (0=negative, 1=positive)",
        nullable=True,
    )

    class Config:
        coerce = True  # Auto-convert types where possible
        strict = False  # Allow extra columns (e.g., ID, timestamp)
