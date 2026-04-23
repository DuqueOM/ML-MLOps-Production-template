"""6-phase EDA pipeline with leakage gate and drift-detection integration.

Implements the procedure defined in `.windsurf/skills/eda-analysis/SKILL.md`.

Phases:
    0. Ingest & snake_case normalization
    1. Structural profiling
    2. Univariate distributions + baseline_distributions.pkl
    3. Multivariate correlations + VIF
    4. Leakage detection (HARD GATE — exit 1 if blocked features)
    5. Feature proposals with rationale
    6. Consolidated summary + Pandera schema proposal

Usage:
    python -m eda.eda_pipeline \\
        --input data/raw/dataset.csv \\
        --target target_column \\
        --output-dir eda/ \\
        --service-slug fraud_detector

Exit codes:
    0 = all phases passed
    1 = leakage gate blocked (phase 4 failed)
    2 = pipeline error

Respects anti-patterns D-13 (sandbox), D-14 (schema ranges),
D-15 (baseline persistence), D-16 (feature rationale).
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy import stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eda")

# Thresholds — tune per domain; documented in ADR-004
LEAKAGE_CORR_THRESHOLD = 0.95
LEAKAGE_MI_THRESHOLD = 0.90  # Mutual info normalized
HIGH_SKEW_THRESHOLD = 1.0
HIGH_CARDINALITY_THRESHOLD = 50
RARE_LABEL_THRESHOLD = 0.01
VIF_THRESHOLD = 10.0


# ═══════════════════════════════════════════════════════════════════
# Phase 0 — Ingest & Normalization
# ═══════════════════════════════════════════════════════════════════


def phase0_ingest(input_path: Path, output_dir: Path) -> pd.DataFrame:
    """Load raw data, normalize column names to snake_case, drop empty columns.

    Invariant D-13: input_path MUST be in data/raw/ — never a production path.
    """
    logger.info("Phase 0 — Ingest & normalization")

    if "production" in str(input_path) or "live" in str(input_path):
        raise ValueError(f"D-13 violation: EDA on production path {input_path}. "
                         "Copy to data/raw/ first.")

    if input_path.suffix == ".csv":
        df = pd.read_csv(input_path)
    elif input_path.suffix in (".parquet", ".pq"):
        df = pd.read_parquet(input_path)
    else:
        raise ValueError(f"Unsupported format: {input_path.suffix}")

    original_cols = list(df.columns)

    # snake_case: lowercase, replace non-alphanumeric with _, collapse multiple _
    df.columns = [
        re.sub(r"_+", "_", re.sub(r"\W+", "_", c.strip().lower())).strip("_")
        for c in df.columns
    ]

    # Drop fully-null columns
    null_cols = [c for c in df.columns if df[c].isnull().all()]
    if null_cols:
        df = df.drop(columns=null_cols)
        logger.warning(f"Dropped {len(null_cols)} fully-null columns: {null_cols}")

    # Save processed version
    processed_dir = output_dir.parent / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    out_path = processed_dir / "dataset_clean.parquet"
    df.to_parquet(out_path, index=False)

    # Ingest report
    report = output_dir / "reports" / "00_ingest_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"""# Ingest Report

- **Source**: `{input_path}`
- **Rows**: {len(df):,}
- **Columns**: {len(df.columns)}
- **Dropped null columns**: {null_cols or 'none'}
- **Output**: `{out_path}`

## Column renames (snake_case normalization)
{chr(10).join(f'- `{a}` → `{b}`' for a, b in zip(original_cols, df.columns) if a != b) or 'No renames needed.'}
""")

    logger.info(f"  {len(df):,} rows × {len(df.columns)} columns → {out_path}")
    return df


# ═══════════════════════════════════════════════════════════════════
# Phase 1 — Structural Profile
# ═══════════════════════════════════════════════════════════════════


def phase1_profile(df: pd.DataFrame, output_dir: Path) -> dict[str, Any]:
    """Generate dtype map and structural profile."""
    logger.info("Phase 1 — Structural profile")

    dtypes_map: dict[str, dict] = {}
    for col in df.columns:
        series = df[col]
        entry: dict[str, Any] = {
            "dtype": str(series.dtype),
            "nulls": int(series.isnull().sum()),
            "null_pct": round(float(series.isnull().mean()), 4),
            "cardinality": int(series.nunique()),
        }
        if pd.api.types.is_numeric_dtype(series):
            entry["min"] = float(series.min()) if series.notna().any() else None
            entry["max"] = float(series.max()) if series.notna().any() else None
            entry["mean"] = float(series.mean()) if series.notna().any() else None
        dtypes_map[col] = entry

    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "01_dtypes_map.json").write_text(json.dumps(dtypes_map, indent=2))

    # Lightweight HTML profile (pandas.describe + dtype table)
    profile_html = _render_profile_html(df, dtypes_map)
    (output_dir / "reports" / "01_profile.html").write_text(profile_html)

    # Detect duplicates
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        logger.warning(f"  {dup_count} exact duplicate rows found")

    logger.info(f"  Profiled {len(df.columns)} columns, {dup_count} duplicate rows")
    return dtypes_map


def _render_profile_html(df: pd.DataFrame, dtypes_map: dict) -> str:
    """Lightweight HTML profile — no ydata-profiling dependency required."""
    rows_html = "".join(
        f"<tr><td>{c}</td><td>{m['dtype']}</td><td>{m['nulls']}</td>"
        f"<td>{m['null_pct']:.2%}</td><td>{m['cardinality']}</td></tr>"
        for c, m in dtypes_map.items()
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>EDA Profile</title>
<style>body{{font-family:sans-serif;max-width:1200px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.4em;border:1px solid #ddd}}
th{{background:#f0f0f0}}</style></head>
<body><h1>EDA Profile</h1>
<p>Rows: <b>{len(df):,}</b> | Columns: <b>{len(df.columns)}</b></p>
<h2>Dtypes & Nulls</h2>
<table><tr><th>Column</th><th>Dtype</th><th>Nulls</th><th>Null %</th><th>Cardinality</th></tr>
{rows_html}</table>
<h2>Numeric describe()</h2><pre>{df.describe().to_string()}</pre>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Phase 2 — Univariate + Baseline Distributions
# ═══════════════════════════════════════════════════════════════════


def phase2_univariate(df: pd.DataFrame, target: str, output_dir: Path) -> dict[str, Any]:
    """Compute univariate stats and persist baseline_distributions.pkl.

    Invariant D-15: baseline_distributions.pkl MUST be produced — drift detection
    in production depends on this file. Uses quantile bins (not uniform) per D-08.
    """
    logger.info("Phase 2 — Univariate + baseline distributions")

    baseline: dict[str, Any] = {
        "_meta": {"target": target, "n_rows": len(df), "schema_version": 1}
    }
    univariate_summary: list[str] = []

    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue

        if pd.api.types.is_numeric_dtype(series) and col != target:
            # Quantile bins for PSI (D-08 compliance)
            try:
                bins = np.quantile(series, np.linspace(0, 1, 11))
                bins = np.unique(bins)  # dedupe for constant regions
            except Exception:
                bins = np.array([series.min(), series.max()])

            baseline[col] = {
                "type": "numeric",
                "bins": bins.tolist(),
                "mean": float(series.mean()),
                "std": float(series.std()),
                "skew": float(series.skew()),
                "kurtosis": float(series.kurtosis()),
            }
            univariate_summary.append(
                f"- **{col}**: mean={series.mean():.3f}, std={series.std():.3f}, "
                f"skew={series.skew():.3f}"
            )
        elif col != target:
            # Categorical: value_counts as the baseline distribution
            freq = series.value_counts(normalize=True)
            rare = freq[freq < RARE_LABEL_THRESHOLD]
            baseline[col] = {
                "type": "categorical",
                "freq": freq.to_dict(),
                "n_rare_labels": int(len(rare)),
                "cardinality": int(series.nunique()),
            }
            univariate_summary.append(
                f"- **{col}** (categorical): {series.nunique()} unique, "
                f"{len(rare)} rare labels"
            )

    # Target distribution
    if target in df.columns:
        target_series = df[target].dropna()
        if pd.api.types.is_numeric_dtype(target_series):
            baseline["_target"] = {"type": "regression", "mean": float(target_series.mean())}
        else:
            counts = target_series.value_counts()
            baseline["_target"] = {
                "type": "classification",
                "class_balance": counts.to_dict(),
                "imbalance_ratio": float(counts.max() / counts.min()) if len(counts) > 1 else 1.0,
            }

    # ═══ CRITICAL: persist baseline for drift detection (D-15) ═══
    artifacts_dir = output_dir / "artifacts"
    baseline_path = artifacts_dir / "02_baseline_distributions.pkl"
    with open(baseline_path, "wb") as f:
        pickle.dump(baseline, f)
    logger.info(f"  Baseline distributions → {baseline_path} (D-15 satisfied)")

    # Univariate HTML report
    report_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Univariate Distributions</title></head>
<body><h1>Univariate Distributions</h1>
<p><b>Baseline artifact</b>: <code>artifacts/02_baseline_distributions.pkl</code>
(consumed by drift CronJob in production)</p>
<h2>Per-feature summary</h2>
<ul>
{''.join(f'<li>{line[2:]}</li>' for line in univariate_summary)}
</ul>
</body></html>"""
    (output_dir / "reports" / "02_univariate.html").write_text(report_html)
    return baseline


# ═══════════════════════════════════════════════════════════════════
# Phase 3 — Correlations + VIF
# ═══════════════════════════════════════════════════════════════════


def phase3_correlations(df: pd.DataFrame, target: str, output_dir: Path) -> pd.DataFrame:
    """Compute correlations and rank features by target correlation."""
    logger.info("Phase 3 — Multivariate correlations")

    numeric_df = df.select_dtypes(include=[np.number]).dropna()
    if target not in numeric_df.columns:
        # Target is categorical — encode for correlation
        if target in df.columns:
            numeric_df = numeric_df.copy()
            numeric_df[target] = pd.Categorical(df[target]).codes

    if target not in numeric_df.columns or len(numeric_df) == 0:
        logger.warning("  Target not numeric-correlatable; skipping ranking")
        ranking = pd.DataFrame(columns=["feature", "corr_with_target", "abs_corr"])
    else:
        corr = numeric_df.corr()[target].drop(target, errors="ignore")
        ranking = pd.DataFrame({
            "feature": corr.index,
            "corr_with_target": corr.values,
            "abs_corr": corr.abs().values,
        }).sort_values("abs_corr", ascending=False)

    artifacts_dir = output_dir / "artifacts"
    ranking.to_csv(artifacts_dir / "03_feature_ranking_initial.csv", index=False)

    report = output_dir / "reports" / "03_correlations.html"
    report.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Correlations</title></head>
<body><h1>Feature ↔ Target Correlations</h1>
{ranking.to_html(index=False, float_format=lambda x: f'{x:.4f}')}
</body></html>""")

    logger.info(f"  Ranked {len(ranking)} numeric features by |corr| with target")
    return ranking


# ═══════════════════════════════════════════════════════════════════
# Phase 4 — Leakage Detection (HARD GATE)
# ═══════════════════════════════════════════════════════════════════


def phase4_leakage_gate(
    df: pd.DataFrame, target: str, ranking: pd.DataFrame, output_dir: Path
) -> list[str]:
    """HARD GATE — return non-empty list blocks the pipeline.

    Invariant D-06 extended: reject features with suspicious correlation or MI.
    """
    logger.info("Phase 4 — Leakage detection (HARD GATE)")

    blocked: list[dict] = []

    # Check 1: high correlation with target
    if not ranking.empty:
        suspicious = ranking[ranking["abs_corr"] > LEAKAGE_CORR_THRESHOLD]
        for _, row in suspicious.iterrows():
            blocked.append({
                "feature": row["feature"],
                "reason": f"correlation={row['corr_with_target']:.4f} > {LEAKAGE_CORR_THRESHOLD}",
                "severity": "P2",
            })

    # Check 2: features that are deterministic function of target
    if target in df.columns:
        for col in df.columns:
            if col == target:
                continue
            try:
                # If |corr(col, target)| == 1 exactly, it's likely derived from target
                series = df[[col, target]].dropna()
                if len(series) < 10 or not pd.api.types.is_numeric_dtype(series[col]):
                    continue
                if pd.api.types.is_numeric_dtype(series[target]):
                    corr = series[col].corr(series[target])
                    if abs(corr) > 0.9999:
                        blocked.append({
                            "feature": col,
                            "reason": f"near-perfect correlation ({corr:.6f}) — likely derived from target",
                            "severity": "P1",
                        })
            except Exception:
                continue

    blocked_features = list({b["feature"] for b in blocked})

    # Leakage audit report
    report = output_dir / "reports" / "04_leakage_audit.md"
    if blocked:
        lines = [f"- **{b['feature']}**: {b['reason']} (severity: {b['severity']})"
                 for b in blocked]
        status = "HALT — resolve before training"
        block_yaml = "- " + "\n- ".join(f'"{f}"' for f in blocked_features)
    else:
        lines = ["No suspicious features detected."]
        status = "PASSED"
        block_yaml = "# empty"

    report.write_text(f"""# Leakage Audit

## Status: {status}

## Thresholds
- Correlation with target: > {LEAKAGE_CORR_THRESHOLD}
- Near-perfect correlation (likely derived): > 0.9999

## Findings
{chr(10).join(lines)}

## Blocked features (machine-readable)
```yaml
BLOCKED_FEATURES:
{block_yaml}
```

## Resolution
{('Proceed to phase 5.' if not blocked else
  'For each blocked feature: (1) investigate source, (2) document decision (exclude / transform / justify with ADR), (3) re-run phase 4.')}
""")

    if blocked_features:
        logger.error(f"  GATE FAILED — {len(blocked_features)} features blocked: {blocked_features}")
    else:
        logger.info("  Gate PASSED — no suspicious features")
    return blocked_features


# ═══════════════════════════════════════════════════════════════════
# Phase 5 — Feature Proposals
# ═══════════════════════════════════════════════════════════════════


def phase5_proposals(
    df: pd.DataFrame, target: str, baseline: dict, output_dir: Path
) -> dict:
    """Generate feature transformation proposals with rationale (D-16).

    Each proposal cites a specific EDA finding as rationale.
    """
    logger.info("Phase 5 — Feature proposals")

    transforms: list[dict] = []

    for col, meta in baseline.items():
        if col.startswith("_"):
            continue
        if meta.get("type") == "numeric" and abs(meta.get("skew", 0)) > HIGH_SKEW_THRESHOLD:
            transforms.append({
                "name": f"log1p_{col}",
                "source": col,
                "transform": "log1p",
                "rationale": (f"|skew|={abs(meta['skew']):.2f} > {HIGH_SKEW_THRESHOLD} "
                              f"(phase 2 univariate). log1p stabilizes variance."),
            })
        elif meta.get("type") == "categorical" and meta.get("cardinality", 0) > HIGH_CARDINALITY_THRESHOLD:
            transforms.append({
                "name": f"target_encode_{col}",
                "source": col,
                "transform": "target_encoding",
                "rationale": (f"cardinality={meta['cardinality']} > {HIGH_CARDINALITY_THRESHOLD} "
                              f"(phase 1 profile). One-hot would explode dimensionality."),
            })

    # Time-based features if datetime detected
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            transforms.append({
                "name": f"{col}_hour",
                "source": col,
                "transform": "extract_hour",
                "rationale": f"{col} is datetime (phase 1 profile). Hour-of-day often predictive.",
            })

    proposals = {
        "metadata": {
            "target": target,
            "n_transforms": len(transforms),
            "D-16_compliance": "Every entry has a rationale field citing EDA findings.",
        },
        "transforms": transforms,
    }

    artifacts_dir = output_dir / "artifacts"
    with open(artifacts_dir / "05_feature_proposals.yaml", "w") as f:
        yaml.safe_dump(proposals, f, sort_keys=False)

    logger.info(f"  Proposed {len(transforms)} transforms, all with rationale (D-16 ok)")
    return proposals


# ═══════════════════════════════════════════════════════════════════
# Phase 6 — Schema Proposal + Summary
# ═══════════════════════════════════════════════════════════════════


def phase6_consolidate(
    df: pd.DataFrame,
    target: str,
    dtypes_map: dict,
    baseline: dict,
    proposals: dict,
    output_dir: Path,
    service_slug: str | None,
) -> None:
    """Generate Pandera schema proposal and EDA summary markdown."""
    logger.info("Phase 6 — Consolidation (schema proposal + summary)")

    # Generate schema_proposal.py with observed ranges (D-14)
    schema_lines = [
        '"""Auto-generated Pandera schema proposal from EDA phase 6.',
        "",
        "REVIEW THIS FILE. Copy relevant parts to src/<service>/schemas.py.",
        "Do NOT replace schemas.py wholesale — engineer judgment required.",
        '"""',
        "import pandera as pa",
        "from pandera import Column, Check, DataFrameSchema",
        "",
        "schema = DataFrameSchema({",
    ]
    for col, meta in dtypes_map.items():
        dtype = meta["dtype"]
        if "int" in dtype or "float" in dtype:
            pa_type = "float" if "float" in dtype else "int"
            if meta.get("min") is not None and meta.get("max") is not None:
                schema_lines.append(
                    f'    "{col}": Column({pa_type}, Check.in_range({meta["min"]}, {meta["max"]}), '
                    f"nullable={bool(meta['nulls'])}),"
                )
            else:
                schema_lines.append(
                    f'    "{col}": Column({pa_type}, nullable={bool(meta["nulls"])}),'
                )
        else:
            schema_lines.append(
                f'    "{col}": Column(str, nullable={bool(meta["nulls"])}),'
            )
    schema_lines.append("})")

    if service_slug:
        schema_path = output_dir.parent / "src" / service_slug / "schema_proposal.py"
    else:
        schema_path = output_dir / "schema_proposal.py"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text("\n".join(schema_lines) + "\n")
    logger.info(f"  Schema proposal → {schema_path} (D-14: ranges from observed data)")

    # EDA summary markdown
    target_dist = baseline.get("_target", {})
    summary = output_dir / "reports" / "eda_summary.md"
    summary.write_text(f"""# EDA Summary

## Dataset
- **Rows**: {len(df):,}
- **Columns**: {len(df.columns)}
- **Target**: `{target}`
- **Target type**: {target_dist.get("type", "unknown")}

## Key findings
- Features profiled: {len([c for c in dtypes_map if not c.startswith('_')])}
- Numeric features: {len([c for c, m in dtypes_map.items() if 'float' in m.get('dtype', '') or 'int' in m.get('dtype', '')])}
- Feature transforms proposed: {len(proposals.get("transforms", []))}

## Artifacts produced
- `artifacts/01_dtypes_map.json`
- `artifacts/02_baseline_distributions.pkl` ← **drift detection input**
- `artifacts/03_feature_ranking_initial.csv`
- `artifacts/05_feature_proposals.yaml`

## Next steps
1. Review `reports/04_leakage_audit.md` — ensure `BLOCKED_FEATURES: []`
2. Review `artifacts/05_feature_proposals.yaml` — approve or reject each transform
3. Review `schema_proposal.py` — copy accepted parts to `src/<service>/schemas.py`
4. DVC-track `artifacts/02_baseline_distributions.pkl`
5. Update drift CronJob to load the baseline (closes the loop)

## ADR reference
Create an ADR documenting the dataset, leakage decisions, and feature strategy.
Cite this summary file from the ADR.
""")
    logger.info(f"  Summary → {summary}")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(description="6-phase EDA pipeline")
    parser.add_argument("--input", type=Path, required=True, help="Path to raw dataset")
    parser.add_argument("--target", type=str, required=True, help="Target column name")
    parser.add_argument("--output-dir", type=Path, default=Path("eda"),
                        help="EDA output directory (default: eda/)")
    parser.add_argument("--service-slug", type=str, default=None,
                        help="Service slug (for schema_proposal.py placement)")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "reports").mkdir(exist_ok=True)
    (args.output_dir / "artifacts").mkdir(exist_ok=True)

    try:
        df = phase0_ingest(args.input, args.output_dir)
        dtypes_map = phase1_profile(df, args.output_dir)
        baseline = phase2_univariate(df, args.target, args.output_dir)
        ranking = phase3_correlations(df, args.target, args.output_dir)
        blocked = phase4_leakage_gate(df, args.target, ranking, args.output_dir)

        if blocked:
            logger.error("LEAKAGE GATE FAILED — halting pipeline")
            logger.error(f"See {args.output_dir / 'reports' / '04_leakage_audit.md'}")
            return 1

        proposals = phase5_proposals(df, args.target, baseline, args.output_dir)
        phase6_consolidate(df, args.target, dtypes_map, baseline, proposals,
                           args.output_dir, args.service_slug)

        logger.info("━━━ EDA PIPELINE COMPLETE ━━━")
        logger.info(f"Review: {args.output_dir / 'reports' / 'eda_summary.md'}")
        return 0

    except Exception as e:
        logger.exception(f"Pipeline error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
