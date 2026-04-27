"""Asynchronous prediction logger for closed-loop monitoring.

Architecture (ADR-006):
- Fire-and-forget: inference endpoint NEVER blocks on logging
- Pluggable backend via PREDICTION_LOG_BACKEND env var:
  - parquet   (default, writes to GCS/S3/local)
  - bigquery  (GCP native, partitioned by date)
  - sqlite    (local development only)
  - stdout    (debugging only)
- Buffered: batched writes to reduce backend pressure

Invariants (see .windsurf/rules/13-closed-loop-monitoring.md):
- D-20: prediction_id (UUID) and entity_id are mandatory on every log event
- D-21: logger.log_prediction() MUST be awaitable and non-blocking; it returns
  immediately after enqueueing. Backend flush happens in a background task.
- D-22: logger MUST NOT raise from log_prediction() — failures are recorded to
  prometheus counter 'prediction_log_errors_total' and swallowed.

Usage (inside FastAPI handler, after calling run_in_executor):
    await logger.log_prediction(PredictionEvent(
        prediction_id=uuid4().hex,
        entity_id=request.entity_id,
        features=input_dict,
        score=prob,
        prediction_class=risk_level,
        model_version=version,
        slices={"country": request.country, "channel": request.channel},
    ))

Slices: the slices dict carries user-defined dimensions for sliced analysis
(see configs/slices.yaml and performance_monitor.py). Keep cardinality bounded.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event schema — frozen dataclass, validated at construction (D-20)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PredictionEvent:
    """Canonical prediction log event. Frozen to prevent post-hoc mutation.

    Fields marked required raise ValueError at construction if missing/empty.
    """

    prediction_id: str
    entity_id: str
    timestamp: str  # ISO-8601 UTC
    model_version: str
    features: dict[str, Any]
    score: float
    prediction_class: str | int
    slices: dict[str, str] = field(default_factory=dict)
    latency_ms: float | None = None
    # PR-C1 (ADR-015): deployment_id is the canonical correlation key
    # joining each prediction back to the deploy workflow that produced
    # the running pod. Optional (default None) so existing call sites
    # and tests continue to work; populated from $DEPLOYMENT_ID env var
    # by the FastAPI handler (sourced via the K8s Downward API). Maps
    # to a nullable column in BigQuery / Parquet backends; SQLite gets
    # a generated column for local development. See `docs/correlation-ids.md`.
    deployment_id: str | None = None

    def __post_init__(self) -> None:
        if not self.prediction_id:
            raise ValueError("prediction_id is required (D-20)")
        if not self.entity_id:
            raise ValueError("entity_id is required (D-20)")
        if not self.model_version:
            raise ValueError("model_version is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Backend protocol — all backends implement write_batch
# ---------------------------------------------------------------------------
class LogBackend(Protocol):
    """Pluggable backend contract."""

    def write_batch(self, events: list[PredictionEvent]) -> None: ...

    def health_check(self) -> bool: ...


# ---------------------------------------------------------------------------
# Built-in backends
# ---------------------------------------------------------------------------
class StdoutBackend:
    """Debugging backend — prints to stdout. DO NOT use in production."""

    def write_batch(self, events: list[PredictionEvent]) -> None:
        for e in events:
            print(json.dumps(e.to_dict()))

    def health_check(self) -> bool:
        return True


class SQLiteBackend:
    """Local-development backend. NOT production (single-writer limitation)."""

    def __init__(self, path: str | None = None) -> None:
        import sqlite3

        self.path = path or os.getenv("PREDICTION_LOG_SQLITE_PATH", "predictions.db")
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions_log (
              prediction_id TEXT PRIMARY KEY,
              entity_id TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              model_version TEXT NOT NULL,
              features_json TEXT NOT NULL,
              score REAL NOT NULL,
              prediction_class TEXT NOT NULL,
              slices_json TEXT NOT NULL,
              latency_ms REAL,
              deployment_id TEXT
            )
            """)
        # PR-C1: lazy schema migration for SQLite databases created by
        # earlier versions. ``ALTER TABLE ... ADD COLUMN`` is idempotent
        # via the ``OperationalError`` catch (sqlite3 raises if the column
        # already exists). Local-dev-only backend, so we do not need a
        # full migration framework.
        try:
            self._conn.execute("ALTER TABLE predictions_log ADD COLUMN deployment_id TEXT")
        except Exception:
            pass
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON predictions_log(entity_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON predictions_log(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_deploy ON predictions_log(deployment_id)")
        self._conn.commit()

    def write_batch(self, events: list[PredictionEvent]) -> None:
        rows = [
            (
                e.prediction_id,
                e.entity_id,
                e.timestamp,
                e.model_version,
                json.dumps(e.features, default=str),
                e.score,
                str(e.prediction_class),
                json.dumps(e.slices),
                e.latency_ms,
                e.deployment_id,
            )
            for e in events
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO predictions_log VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self._conn.commit()

    def health_check(self) -> bool:
        try:
            self._conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False


class ParquetBackend:
    """Default production backend. Writes daily partitions to GCS / S3 / local.

    Path format: {base}/year={yyyy}/month={mm}/day={dd}/batch_{ts}.parquet
    Requires pandas + pyarrow (part of base requirements).
    """

    def __init__(self, base_path: str | None = None) -> None:
        self.base_path = base_path or os.getenv(
            "PREDICTION_LOG_PARQUET_PATH",
            "data/predictions_log",
        )

    def write_batch(self, events: list[PredictionEvent]) -> None:
        import pandas as pd

        rows = []
        for e in events:
            row = e.to_dict()
            # Flatten slices into columns for efficient filtering
            slices = row.pop("slices", {})
            for k, v in slices.items():
                row[f"slice_{k}"] = v
            row["features_json"] = json.dumps(row.pop("features"), default=str)
            rows.append(row)

        df = pd.DataFrame(rows)
        # Partition by event date
        first_ts = datetime.fromisoformat(events[0].timestamp.replace("Z", "+00:00"))
        partition = f"year={first_ts.year:04d}/month={first_ts.month:02d}/day={first_ts.day:02d}"
        batch_fname = f"batch_{int(time.time() * 1000)}.parquet"

        if self.base_path.startswith(("gs://", "s3://")):
            full_path = f"{self.base_path}/{partition}/{batch_fname}"
            df.to_parquet(full_path, engine="pyarrow")
        else:
            local = Path(self.base_path) / partition
            local.mkdir(parents=True, exist_ok=True)
            df.to_parquet(local / batch_fname, engine="pyarrow")

    def health_check(self) -> bool:
        if self.base_path.startswith(("gs://", "s3://")):
            return True  # Assume bucket exists; IRSA/WI verified elsewhere
        return Path(self.base_path).parent.exists() or Path(self.base_path).parent == Path()


class BigQueryBackend:
    """GCP-native backend. Requires google-cloud-bigquery (optional dep).

    Uses load_table_from_json with WRITE_APPEND. Table must exist with schema
    defined in templates/infra/terraform/bigquery_predictions.tf.
    """

    def __init__(
        self,
        dataset: str | None = None,
        table: str | None = None,
        project: str | None = None,
    ) -> None:
        from google.cloud import bigquery  # type: ignore[import-not-found]

        self.client = bigquery.Client(project=project or os.getenv("GCP_PROJECT"))
        self.dataset = dataset or os.getenv("PREDICTION_LOG_BQ_DATASET", "mlops")
        self.table = table or os.getenv("PREDICTION_LOG_BQ_TABLE", "predictions_log")
        self.table_ref = f"{self.client.project}.{self.dataset}.{self.table}"

    def write_batch(self, events: list[PredictionEvent]) -> None:
        rows = []
        for e in events:
            row = e.to_dict()
            row["features_json"] = json.dumps(row.pop("features"), default=str)
            row["slices_json"] = json.dumps(row.pop("slices"))
            rows.append(row)
        errors = self.client.insert_rows_json(self.table_ref, rows)
        if errors:
            raise RuntimeError(f"BigQuery insert errors: {errors}")

    def health_check(self) -> bool:
        try:
            self.client.get_table(self.table_ref)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Async logger with buffered background flush
# ---------------------------------------------------------------------------
class PredictionLogger:
    """Buffered async logger. One instance per process, lifecycle-managed by FastAPI.

    Flushes buffer on:
    - Buffer size reaches max_buffer_size (default 100)
    - Time elapsed reaches flush_interval_s (default 5s)
    - Application shutdown (await close())
    """

    def __init__(
        self,
        backend: LogBackend,
        max_buffer_size: int = 100,
        flush_interval_s: float = 5.0,
    ) -> None:
        self.backend = backend
        self.max_buffer_size = max_buffer_size
        self.flush_interval_s = flush_interval_s
        self._buffer: list[PredictionEvent] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False
        # Counters (accessed by /metrics)
        self.logged_count = 0
        self.error_count = 0
        self.dropped_count = 0

    async def start(self) -> None:
        """Start background flush task. Call from FastAPI lifespan."""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def close(self) -> None:
        """Drain buffer and stop background task. Call from FastAPI lifespan shutdown."""
        self._closed = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_once()

    async def log_prediction(self, event: PredictionEvent) -> None:
        """Enqueue event. Non-blocking, swallows errors (D-22).

        Safe to call from any async context. Returns immediately.
        """
        if self._closed:
            self.dropped_count += 1
            return
        try:
            async with self._lock:
                self._buffer.append(event)
                if len(self._buffer) >= self.max_buffer_size:
                    asyncio.create_task(self._flush_once())
        except Exception as e:
            self.error_count += 1
            logger.warning("prediction_log enqueue failed: %s", e)

    async def _flush_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(self.flush_interval_s)
            await self._flush_once()

    async def _flush_once(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []
        try:
            # Backends are sync; run in default executor to avoid blocking loop (D-21)
            await asyncio.get_running_loop().run_in_executor(None, self.backend.write_batch, batch)
            self.logged_count += len(batch)
        except Exception as e:
            self.error_count += len(batch)
            logger.warning("prediction_log flush failed (%d events dropped): %s", len(batch), e)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def build_backend(kind: str | None = None) -> LogBackend:
    """Construct backend from env var or explicit kind."""
    kind = (kind or os.getenv("PREDICTION_LOG_BACKEND", "parquet")).lower()
    if kind == "parquet":
        return ParquetBackend()
    if kind == "bigquery":
        return BigQueryBackend()
    if kind == "sqlite":
        return SQLiteBackend()
    if kind == "stdout":
        return StdoutBackend()
    raise ValueError(f"Unknown PREDICTION_LOG_BACKEND: {kind}")


def build_logger() -> PredictionLogger:
    """Convenience factory: reads env, constructs backend + logger."""
    return PredictionLogger(
        backend=build_backend(),
        max_buffer_size=int(os.getenv("PREDICTION_LOG_BUFFER_SIZE", "100")),
        flush_interval_s=float(os.getenv("PREDICTION_LOG_FLUSH_INTERVAL_S", "5.0")),
    )


def utc_now_iso() -> str:
    """Helper for event timestamps."""
    return datetime.now(tz=timezone.utc).isoformat()
