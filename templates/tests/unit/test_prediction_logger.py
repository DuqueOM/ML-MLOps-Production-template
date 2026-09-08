"""Unit tests for common_utils.prediction_logger.

Covers:
- PredictionEvent invariant validation (D-20)
- SQLiteBackend + ParquetBackend write_batch correctness
- PredictionLogger buffered flush behavior
- D-21/D-22: logger NEVER raises + NEVER blocks (fire-and-forget semantics)
- Factory fallback & unknown backend rejection
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "service"))

from common_utils.prediction_logger import (  # noqa: E402
    ParquetBackend,
    PredictionEvent,
    PredictionLogger,
    SQLiteBackend,
    StdoutBackend,
    build_backend,
    utc_now_iso,
)


# ---------------------------------------------------------------------------
# PredictionEvent invariants (D-20)
# ---------------------------------------------------------------------------
class TestPredictionEventInvariants:
    def test_valid_event_constructs(self) -> None:
        e = PredictionEvent(
            prediction_id="p1",
            entity_id="u1",
            timestamp=utc_now_iso(),
            model_version="v1",
            features={"a": 1.0},
            score=0.8,
            prediction_class="HIGH",
        )
        assert e.prediction_id == "p1"
        assert e.slices == {}

    def test_missing_prediction_id_raises(self) -> None:
        with pytest.raises(ValueError, match="prediction_id"):
            PredictionEvent(
                prediction_id="",
                entity_id="u1",
                timestamp=utc_now_iso(),
                model_version="v1",
                features={},
                score=0.5,
                prediction_class="LOW",
            )

    def test_missing_entity_id_raises(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            PredictionEvent(
                prediction_id="p1",
                entity_id="",
                timestamp=utc_now_iso(),
                model_version="v1",
                features={},
                score=0.5,
                prediction_class="LOW",
            )

    def test_missing_model_version_raises(self) -> None:
        with pytest.raises(ValueError, match="model_version"):
            PredictionEvent(
                prediction_id="p1",
                entity_id="u1",
                timestamp=utc_now_iso(),
                model_version="",
                features={},
                score=0.5,
                prediction_class="LOW",
            )

    def test_is_frozen(self) -> None:
        e = PredictionEvent(
            prediction_id="p1",
            entity_id="u1",
            timestamp=utc_now_iso(),
            model_version="v1",
            features={},
            score=0.5,
            prediction_class="LOW",
        )
        with pytest.raises((AttributeError, Exception)):
            e.score = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SQLiteBackend
# ---------------------------------------------------------------------------
class TestSQLiteBackend:
    def test_write_batch_persists_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "pred.db"
        backend = SQLiteBackend(path=str(db))
        events = [
            PredictionEvent(
                prediction_id=f"p{i}",
                entity_id=f"u{i}",
                timestamp=utc_now_iso(),
                model_version="v1",
                features={"x": i},
                score=0.1 * i,
                prediction_class="LOW",
                slices={"country": "MX"},
            )
            for i in range(3)
        ]
        backend.write_batch(events)
        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT COUNT(*) FROM predictions_log").fetchone()
        assert rows[0] == 3
        sample = conn.execute("SELECT entity_id, score FROM predictions_log WHERE prediction_id='p2'").fetchone()
        assert sample == ("u2", 0.2)

    def test_write_batch_is_idempotent_on_duplicate_prediction_id(self, tmp_path: Path) -> None:
        db = tmp_path / "pred.db"
        backend = SQLiteBackend(path=str(db))
        e = PredictionEvent(
            prediction_id="p1",
            entity_id="u1",
            timestamp=utc_now_iso(),
            model_version="v1",
            features={},
            score=0.5,
            prediction_class="LOW",
        )
        backend.write_batch([e])
        backend.write_batch([e])  # same PK — OR REPLACE semantics
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM predictions_log").fetchone()[0]
        assert count == 1

    def test_health_check_returns_true(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(path=str(tmp_path / "h.db"))
        assert backend.health_check() is True


# ---------------------------------------------------------------------------
# ParquetBackend
# ---------------------------------------------------------------------------
class TestParquetBackend:
    def test_write_batch_creates_partitioned_parquet(self, tmp_path: Path) -> None:
        backend = ParquetBackend(base_path=str(tmp_path))
        events = [
            PredictionEvent(
                prediction_id=f"p{i}",
                entity_id=f"u{i}",
                timestamp="2026-04-23T10:00:00+00:00",
                model_version="v1",
                features={"x": i},
                score=0.5,
                prediction_class="LOW",
                slices={"country": "MX"},
            )
            for i in range(2)
        ]
        backend.write_batch(events)
        partition_dir = tmp_path / "year=2026" / "month=04" / "day=23"
        assert partition_dir.exists()
        files = list(partition_dir.glob("batch_*.parquet"))
        assert len(files) == 1
        df = pd.read_parquet(files[0])
        assert len(df) == 2
        assert "slice_country" in df.columns
        assert df["slice_country"].iloc[0] == "MX"
        assert "features_json" in df.columns


# ---------------------------------------------------------------------------
# PredictionLogger — buffered + async (D-21, D-22)
# ---------------------------------------------------------------------------
class TestPredictionLogger:
    @pytest.mark.asyncio
    async def test_flush_on_buffer_full(self, tmp_path: Path) -> None:
        """Reaching max_buffer_size flushes without waiting for the interval.

        The wait here is on an ``asyncio.Event`` the backend sets, not on the
        clock. The previous version slept 0.1s and hoped the size-triggered
        task had run; it failed intermittently on CI, and the failure was real
        — the flush task was unreferenced, so it could be garbage-collected
        mid-``run_in_executor``, leaving the rows written but ``logged_count``
        at 0. A sleep long enough to hide that is also long enough to hide a
        genuinely broken trigger.

        The timeout is a failsafe, not a race: it only decides how long the
        suite waits before declaring the trigger broken.
        """
        flushed = asyncio.Event()

        class SignallingBackend:
            def __init__(self) -> None:
                self.inner = SQLiteBackend(path=str(tmp_path / "t.db"))

            def write_batch(self, events: list[PredictionEvent]) -> None:
                self.inner.write_batch(events)
                flushed.set()

            def health_check(self) -> bool:
                return self.inner.health_check()

        logr = PredictionLogger(backend=SignallingBackend(), max_buffer_size=3, flush_interval_s=60.0)
        await logr.start()
        try:
            for i in range(3):
                await logr.log_prediction(
                    PredictionEvent(
                        prediction_id=f"p{i}",
                        entity_id=f"u{i}",
                        timestamp=utc_now_iso(),
                        model_version="v1",
                        features={},
                        score=0.5,
                        prediction_class="LOW",
                    )
                )
            # Fails only if the size trigger never fires — `flush_interval_s`
            # is 60s, so nothing else can flush within this window.
            await asyncio.wait_for(flushed.wait(), timeout=10.0)
        finally:
            await logr.close()
        count = sqlite3.connect(tmp_path / "t.db").execute("SELECT COUNT(*) FROM predictions_log").fetchone()[0]
        assert count == 3
        assert logr.logged_count == 3

    @pytest.mark.asyncio
    async def test_close_waits_for_an_inflight_size_flush(self, tmp_path: Path) -> None:
        """`close()` must not return while a size-triggered flush is in flight.

        Regression test for silent batch loss. A size-triggered flush takes the
        events out of the buffer before writing them, so if `close()` does not
        wait for it, the final drain finds an empty buffer and writes nothing,
        and the orphaned task dies with the event loop. Measured against a
        backend taking 300ms: 0 of 3 events had reached it when `close()`
        returned, and all 3 arrived afterwards — which during a real shutdown
        is never.
        """

        class SlowBackend:
            def __init__(self) -> None:
                self.written: list[PredictionEvent] = []

            def write_batch(self, events: list[PredictionEvent]) -> None:
                time.sleep(0.3)
                self.written.extend(events)

            def health_check(self) -> bool:
                return True

        backend = SlowBackend()
        logr = PredictionLogger(backend=backend, max_buffer_size=3, flush_interval_s=60.0)
        await logr.start()
        for i in range(3):
            await logr.log_prediction(
                PredictionEvent(
                    prediction_id=f"p{i}",
                    entity_id=f"u{i}",
                    timestamp=utc_now_iso(),
                    model_version="v1",
                    features={},
                    score=0.5,
                    prediction_class="LOW",
                )
            )
        await logr.close()
        assert len(backend.written) == 3, (
            "close() returned while a size-triggered flush was still in flight — "
            "those events are lost when the event loop stops"
        )
        assert logr.logged_count == 3

    @pytest.mark.asyncio
    async def test_drain_on_close(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(path=str(tmp_path / "t.db"))
        logr = PredictionLogger(backend=backend, max_buffer_size=1000, flush_interval_s=60.0)
        await logr.start()
        await logr.log_prediction(
            PredictionEvent(
                prediction_id="p1",
                entity_id="u1",
                timestamp=utc_now_iso(),
                model_version="v1",
                features={},
                score=0.5,
                prediction_class="LOW",
            )
        )
        await logr.close()
        count = sqlite3.connect(tmp_path / "t.db").execute("SELECT COUNT(*) FROM predictions_log").fetchone()[0]
        assert count == 1

    @pytest.mark.asyncio
    async def test_backend_failure_does_not_raise(self, tmp_path: Path) -> None:
        """D-22: flush errors are swallowed and counted, not propagated."""

        class ExplodingBackend:
            def write_batch(self, events):  # noqa: D401
                raise RuntimeError("backend down")

            def health_check(self):  # noqa: D401
                return False

        logr = PredictionLogger(backend=ExplodingBackend(), max_buffer_size=1, flush_interval_s=60.0)
        await logr.start()
        await logr.log_prediction(
            PredictionEvent(
                prediction_id="p1",
                entity_id="u1",
                timestamp=utc_now_iso(),
                model_version="v1",
                features={},
                score=0.5,
                prediction_class="LOW",
            )
        )
        # No sleep: `close()` awaits the in-flight size-triggered flush, so by
        # the time it returns the failing write has been attempted and counted.
        await logr.close()
        # D-22 contract: error count grew but no exception reached the handler
        assert logr.error_count >= 1
        assert logr.logged_count == 0

    @pytest.mark.asyncio
    async def test_log_after_close_is_dropped_silently(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(path=str(tmp_path / "t.db"))
        logr = PredictionLogger(backend=backend, max_buffer_size=10, flush_interval_s=60.0)
        await logr.start()
        await logr.close()
        await logr.log_prediction(
            PredictionEvent(
                prediction_id="p1",
                entity_id="u1",
                timestamp=utc_now_iso(),
                model_version="v1",
                features={},
                score=0.5,
                prediction_class="LOW",
            )
        )
        assert logr.dropped_count == 1


# ---------------------------------------------------------------------------
# build_backend factory
# ---------------------------------------------------------------------------
class TestBuildBackend:
    def test_stdout_backend(self) -> None:
        assert isinstance(build_backend("stdout"), StdoutBackend)

    def test_sqlite_backend(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PREDICTION_LOG_SQLITE_PATH", str(tmp_path / "x.db"))
        assert isinstance(build_backend("sqlite"), SQLiteBackend)

    def test_parquet_backend(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("PREDICTION_LOG_PARQUET_PATH", str(tmp_path))
        assert isinstance(build_backend("parquet"), ParquetBackend)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            build_backend("nosuchbackend")

    def test_env_default_is_parquet(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("PREDICTION_LOG_BACKEND", raising=False)
        monkeypatch.setenv("PREDICTION_LOG_PARQUET_PATH", str(tmp_path))
        assert isinstance(build_backend(), ParquetBackend)


# ---------------------------------------------------------------------------
# Smoke: utc_now_iso is UTC and parseable
# ---------------------------------------------------------------------------
def test_utc_now_iso_is_parseable() -> None:
    from datetime import datetime

    ts = utc_now_iso()
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
