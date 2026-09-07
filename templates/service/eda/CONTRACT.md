# EDA Artifact Contract (PR-B2)

ADR-015 PR-B2 — five canonical machine-readable artifacts produced
by `eda_pipeline.py` under `eda/artifacts/` and consumed by training,
drift, and retrain via the loaders in
`@common_utils/eda_artifacts.py`.

## The five artifacts

| File | Format | Producer (phase) | Consumer | Loader |
| ------ | -------- | ------------------ | ---------- | -------- |
| `eda_summary.json` | JSON | `main()` (post-phase 6) | retrain (provenance) | `load_eda_summary` |
| `schema_ranges.json` | JSON | phase 6 | training (Pandera synthesis), drift (range checks) | `load_schema_ranges` |
| `baseline_distributions.parquet` | Parquet | phase 2 | drift CronJob (PSI) | `load_baseline_distributions` |
| `feature_catalog.yaml` | YAML | phase 5 | training (`features.py`) | `load_feature_catalog` |
| `leakage_report.json` | JSON | phase 4 | training (refuse-to-start gate, PR-B3) | `load_leakage_report` |

## Versioning

Every artifact embeds an `eda_artifact_version` integer.

- Currently: `ARTIFACT_VERSION = 1`.
- Bumped on BREAKING schema changes only. New optional fields → no bump.
- Loaders compare strict equality and raise `EDAArtifactVersionError`
  on mismatch. A producer-consumer skew surfaces at load time, not as
  silently-corrupted PSI scores or training failures.

## Why we kept the legacy filenames

For one transition cycle, the pipeline still emits the pre-PR-B2 names:

- `01_dtypes_map.json`
- `02_baseline_distributions.pkl`
- `03_feature_ranking_initial.csv`
- `04_leakage_audit.md`
- `05_feature_proposals.yaml`

This protects existing notebooks and ad-hoc scripts. **New code MUST
import via `common_utils.eda_artifacts`** — the legacy names will be
removed at version bump 2.

## Adding a new artifact

1. Add the canonical filename + loader to
   `common_utils/eda_artifacts.py` (with version check).
2. Add a writer helper to `eda/eda_pipeline.py` that stamps
   `eda_artifact_version`.
3. Wire the helper into the appropriate `phase*` function.
4. Add an end-to-end test in `eda/tests/test_eda_artifacts.py`.
5. Document the new file in this table.

## Adding a new field to an existing artifact

If the field is **optional** with a sensible default:

1. Update the loader to read it via `payload.get(...)`.
2. Update the producer to emit it.
3. No version bump.

If the field is **required**:

1. Bump `ARTIFACT_VERSION` in `common_utils/eda_artifacts.py`.
2. Update both loader and producer in lock-step.
3. Update every consumer to handle the new field before merging.
4. Update this document.

## Out of scope

- Distributed-training artifacts (per-shard EDA): the contract assumes
  one logical dataset. Multi-shard runs concatenate to a single
  baseline before invoking the pipeline.
- Streaming / online EDA: this contract is batch-only. Online drift
  uses the parquet baseline as a fixed reference window.
- Cross-service artifact federation: each service's EDA stays in its
  own `eda/artifacts/`. We do not yet ship a registry.
