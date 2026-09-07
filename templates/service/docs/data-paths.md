# Data Path Convention

Single canonical layout for the `data/` directory. All training, drift,
and CI workflows rely on it; deviations break the retrain pipeline and
the drift CronJob silently. See ADR-016 for the rationale, and Phase 1.4
of the v1.0 roadmap for the consolidation history.

## Layout

```text
data/
├── raw/                    # Untouched inputs (DVC-versioned)
│   ├── latest.csv          # Current training snapshot
│   └── holdout.csv         # Held-out partition for Champion/Challenger
├── processed/              # Cleaned + featurised data
│   └── *.parquet           # Optional cache; regenerated from raw/ at train time
├── reference/              # Frozen distributions for monitoring
│   ├── reference.csv       # Baseline for PSI drift comparison
│   ├── background.csv      # 50-row sample for SHAP KernelExplainer
│   └── labels_holdout.csv  # Holdout labels for sliced metrics
├── production/             # Mutable, daily snapshots from prediction logs
│   ├── YYYY-MM-DD.csv      # Daily exports (kept ≥ 30 days)
│   └── latest.csv          # Most recent — read by drift CronJob
└── validated/              # Pandera-validated frames (training-time cache)
    └── *.parquet
```

## Producers and consumers

| Path | Produced by | Consumed by |
| ------ | ------------- | ------------- |
| `raw/latest.csv` | DVC pull / data engineering pipeline | `train.py --data data/raw/latest.csv`, `cli.py train --input data/raw/latest.csv` |
| `raw/holdout.csv` | DVC pull | `champion_challenger.py --holdout data/raw/holdout.csv` |
| `processed/*.parquet` | (optional) `make features` | training cache |
| `reference/reference.csv` | manual snapshot at promotion time (`make freeze-reference`) | `drift_detection.py --reference` |
| `reference/background.csv` | output of `train.py` (sampled from training data) | FastAPI lifespan SHAP explainer cache (D-24) |
| `reference/labels_holdout.csv` | DVC pull / labelling pipeline | `performance_monitor.py --labels` |
| `production/latest.csv` | nightly export from `prediction_logger` Parquet (`make export-production`) | `drift_detection.py --current`, drift CronJob (`cronjob-drift.yaml`) |
| `validated/*.parquet` | first training run of the day | training cache (skip Pandera re-validate) |

## Why this matters

Three failure modes that this convention prevents:

1. **Drift CronJob silently fails** — the CronJob mounts a hostPath at
   `data/production/latest.csv`. If the directory does not exist at
   pod start, `--current data/production/latest.csv` hits FileNotFound
   and the metric `drift_detection_last_run_timestamp` never advances,
   which then causes the `{@ service_slug @}DriftDetectionHeartbeatMissing`
   alert to fire 48 h later. (Phase 1.4 fix: scaffolder now mkdir-s
   the directory on `new-service.sh`.)
2. **Retrain workflow points at a moving target** — `retrain-service.yml`
   downloads from `gs://<bucket>/<service>/training/latest.csv` →
   `data/raw/latest.csv`. Any other path means the workflow downloads
   into one place and `train.py` reads from another.
3. **SHAP background data leakage** — the explainer's background must
   come from `reference/background.csv` (frozen at promotion). Re-using
   `raw/latest.csv` would expose the model to its own training data
   during inference and inflate explanation quality scores.

## Quick reference (canonical paths)

The scaffolder (`templates/scripts/new-service.sh`) creates exactly the
following directories — `tests/test_data_paths.py` enforces this list
as a contract:

- `data/raw` — DVC-versioned inputs.
- `data/processed` — cleaned/featurised cache.
- `data/reference` — frozen distributions for monitoring.
- `data/production` — daily snapshots consumed by the drift CronJob.
- `data/validated` — Pandera-validated training cache.
- `models` — trained artifacts (output of `train.py`, input of init container).
- `reports` — JSON / HTML reports (champion-challenger, drift, performance).

## Refresh cadence

| Path | Refreshed | Triggered by |
| ------ | ----------- | -------------- |
| `raw/latest.csv` | weekly | data engineering pipeline |
| `reference/*.csv` | per model promotion | `make freeze-reference` (manual; documented in runbook) |
| `production/latest.csv` | daily 02:00 UTC | `cronjob-export-production.yaml` (TODO: Phase 4) |

## Out of scope

- Multi-region data residency: covered by the bucket choice (DVC remote
  per region), not by directory layout.
- Time-versioned snapshots: DVC handles this on the bucket side; the
  local `data/` layout is always "current".
- Streaming features: the template targets batch inference (D-08); a
  feature store is over-engineering at our scale.
