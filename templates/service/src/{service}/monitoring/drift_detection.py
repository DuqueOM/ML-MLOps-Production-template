"""PSI-based drift detection for {ServiceName}.

Calculates Population Stability Index per feature using quantile-based bins.
Pushes results to Prometheus via Pushgateway and optionally triggers retraining.

Usage:
    python src/{service}/monitoring/drift_detection.py \\
        --reference data/reference/reference.csv \\
        --current data/production/latest.csv \\
        --output drift_report.json

    python src/{service}/monitoring/drift_detection.py --push-metrics
    python src/{service}/monitoring/drift_detection.py --update-reference
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — customize per service
# ---------------------------------------------------------------------------
PSI_BINS = 10
PSI_EPSILON = 1e-8

# Per-feature thresholds with domain reasoning
# TODO: Set real thresholds based on feature stability analysis
FEATURE_THRESHOLDS: dict[str, dict[str, float]] = {
    # "feature_a": {"warning": 0.10, "alert": 0.20, "reason": "historically stable"},
    # "feature_b": {"warning": 0.15, "alert": 0.30, "reason": "high natural variance"},
}

DEFAULT_WARNING = 0.10
DEFAULT_ALERT = 0.20

PUSHGATEWAY_URL = "pushgateway:9091"
JOB_NAME = "{service}-drift-detection"


def calculate_psi(
    reference: np.ndarray,
    current: np.ndarray,
    bins: int = PSI_BINS,
    epsilon: float = PSI_EPSILON,
) -> float:
    """Calculate PSI with quantile-based bins (NOT uniform bins).

    Why quantiles: uniform bins can have empty bins at extremes
    → PSI dominated by epsilon, not real data.
    Quantiles guarantee each bin has observations in the reference.

    Args:
        reference: Reference distribution (training data).
        current: Current distribution (production data).
        bins: Number of quantile bins.
        epsilon: Small value to prevent log(0).

    Returns:
        PSI value.
    """
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    ref_counts, _ = np.histogram(reference, bins=breakpoints)
    cur_counts, _ = np.histogram(current, bins=breakpoints)

    ref_pct = np.maximum(ref_counts / len(reference), epsilon)
    cur_pct = np.maximum(cur_counts / len(current), epsilon)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def detect_drift(
    reference_path: str,
    current_path: str,
    output_path: Optional[str] = None,
) -> dict:
    """Run drift detection on all numeric features.

    Args:
        reference_path: Path to reference CSV.
        current_path: Path to current production CSV.
        output_path: Optional path to save JSON report.

    Returns:
        Dict with per-feature PSI scores and status.
    """
    ref_df = pd.read_csv(reference_path)
    cur_df = pd.read_csv(current_path)

    # Only check numeric features
    numeric_cols = ref_df.select_dtypes(include=[np.number]).columns
    common_cols = [c for c in numeric_cols if c in cur_df.columns]

    results: dict = {"timestamp": time.time(), "features": {}}
    alerts: list[str] = []
    warnings: list[str] = []

    for col in common_cols:
        ref_vals = ref_df[col].dropna().values
        cur_vals = cur_df[col].dropna().values

        if len(ref_vals) == 0 or len(cur_vals) == 0:
            continue

        psi = calculate_psi(ref_vals, cur_vals)

        thresholds = FEATURE_THRESHOLDS.get(col, {})
        warning_thresh = thresholds.get("warning", DEFAULT_WARNING)
        alert_thresh = thresholds.get("alert", DEFAULT_ALERT)

        if psi >= alert_thresh:
            status = "alert"
            alerts.append(col)
        elif psi >= warning_thresh:
            status = "warning"
            warnings.append(col)
        else:
            status = "ok"

        results["features"][col] = {
            "psi": round(psi, 6),
            "status": status,
            "warning_threshold": warning_thresh,
            "alert_threshold": alert_thresh,
            "reference_mean": round(float(ref_vals.mean()), 4),
            "current_mean": round(float(cur_vals.mean()), 4),
            "reference_std": round(float(ref_vals.std()), 4),
            "current_std": round(float(cur_vals.std()), 4),
        }

    results["summary"] = {
        "total_features": len(common_cols),
        "alerts": alerts,
        "warnings": warnings,
        "requires_action": len(alerts) > 0,
    }

    if output_path:
        Path(output_path).write_text(json.dumps(results, indent=2))
        logger.info("Drift report saved to %s", output_path)

    return results


def push_metrics(results: dict) -> None:
    """Push PSI scores to Prometheus via Pushgateway."""
    registry = CollectorRegistry()

    psi_gauge = Gauge(
        "{service}_psi_score",
        "PSI drift score per feature",
        ["feature"],
        registry=registry,
    )

    timestamp_gauge = Gauge(
        "drift_detection_last_run_timestamp",
        "Unix timestamp of last successful drift detection run",
        registry=registry,
    )

    for feature, data in results.get("features", {}).items():
        psi_gauge.labels(feature=feature).set(data["psi"])

    timestamp_gauge.set(time.time())

    push_to_gateway(PUSHGATEWAY_URL, job=JOB_NAME, registry=registry)
    logger.info("Metrics pushed to Pushgateway")


def create_github_issue(results: dict, repo: str, token: str) -> None:
    """Create a GitHub Issue when drift alert fires.

    Called by the CronJob when exit code is 2 (alert).
    The CI/CD workflow can also call this via drift-detection.yml.
    """
    alerts = results["summary"]["alerts"]
    body_lines = [
        "## Drift Alert",
        "",
        f"**Features with alert-level PSI**: {', '.join(alerts)}",
        "",
        "| Feature | PSI | Status | Ref Mean | Cur Mean |",
        "|---------|-----|--------|----------|----------|",
    ]
    for feat, data in results["features"].items():
        body_lines.append(
            f"| {feat} | {data['psi']:.4f} | {data['status']} | "
            f"{data['reference_mean']:.4f} | {data['current_mean']:.4f} |"
        )
    body_lines += ["", "**Action required**: Investigate root cause and trigger `/retrain` if confirmed."]

    payload = json.dumps(
        {
            "title": f"[Drift Alert] {len(alerts)} feature(s) above PSI threshold",
            "body": "\n".join(body_lines),
            "labels": ["drift", "automated"],
        }
    ).encode("utf-8")

    req = Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            issue = json.loads(resp.read())
            logger.info("GitHub Issue created: %s", issue.get("html_url"))
    except Exception as e:
        logger.error("Failed to create GitHub Issue: %s", e)


def update_reference(current_path: str, reference_path: str) -> None:
    """Replace reference data with current production data.

    Called after a successful retraining to reset the drift baseline.
    Keeps a timestamped backup of the old reference.
    """
    ref = Path(reference_path)
    if ref.exists():
        backup = ref.with_suffix(f".backup_{int(time.time())}.csv")
        shutil.copy2(ref, backup)
        logger.info("Backed up old reference to %s", backup)

    shutil.copy2(current_path, reference_path)
    logger.info("Reference updated from %s", current_path)


def main() -> int:
    """CLI entry point with exit codes for CronJob integration.

    Exit codes:
        0 — No drift detected (all features OK)
        1 — Warning-level drift (some features elevated)
        2 — Alert-level drift (action required, triggers issue creation)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    parser = argparse.ArgumentParser(description="Drift detection for {ServiceName}")
    parser.add_argument("--reference", required=True, help="Path to reference CSV")
    parser.add_argument("--current", required=True, help="Path to current production CSV")
    parser.add_argument("--output", help="Path to save JSON report")
    parser.add_argument("--push-metrics", action="store_true", help="Push to Pushgateway")
    parser.add_argument("--create-issue", action="store_true", help="Create GitHub Issue on alert")
    parser.add_argument("--update-reference", action="store_true", help="Replace reference with current")
    args = parser.parse_args()

    results = detect_drift(args.reference, args.current, args.output)
    print(json.dumps(results["summary"], indent=2))

    if args.push_metrics:
        push_metrics(results)

    if args.update_reference:
        update_reference(args.current, args.reference)

    has_alerts = results["summary"]["requires_action"]
    has_warnings = len(results["summary"]["warnings"]) > 0

    if has_alerts:
        logger.warning("ALERT: Drift detected in %s", results["summary"]["alerts"])
        if args.create_issue:
            repo = os.getenv("GITHUB_REPOSITORY", "")
            token = os.getenv("GITHUB_TOKEN", "")
            if repo and token:
                create_github_issue(results, repo, token)
            else:
                logger.warning("GITHUB_REPOSITORY or GITHUB_TOKEN not set — skipping issue")
        return 2
    elif has_warnings:
        logger.info("WARNING: Elevated PSI in %s", results["summary"]["warnings"])
        return 1
    else:
        logger.info("OK: No drift detected")
        return 0


if __name__ == "__main__":
    sys.exit(main())
