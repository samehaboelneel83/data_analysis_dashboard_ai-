"""A sync must not freeze the rest of the application.

WHAT THIS GUARDS
-----------------
FastAPI serves every request on one event loop. DuckDB calls are synchronous C
extension calls that never yield, so a stage doing them inline holds the loop
for as long as it runs — and nothing else is served.

That is not hypothetical. On a real 82-table source `infer_foreign_keys` took
~243 seconds of DuckDB queries on the loop, and the user watched the entire app
sit on "Loading…" for four minutes. Not the review page: every page.

The stages now hand blocking work to `asyncio.to_thread`, which is the same
shape widget_data already uses for CPU-bound pandas work. These tests assert
the loop keeps running while a stage is busy — a property no amount of
correctness testing on the stage itself would reveal.
"""
import asyncio
import time

import pytest
from sqlalchemy import create_engine, text

from app.models.models import DataSource, Organization
from app.services.metadata import catalog_sync, infer_keys


class SlowCache:
    """A cache whose calls block the calling thread, like DuckDB's do.

    `time.sleep` is deliberate rather than `asyncio.sleep`: the point is to
    simulate work that does NOT yield to the loop. An async sleep would pass
    these tests while the real thing still froze the app.
    """

    def __init__(self, delay=0.05, rows=None):
        self.delay = delay
        self._rows = rows or {}

    def get_sample(self, object_id):
        time.sleep(self.delay)
        return self._rows.get(object_id, [{"id": 1, "code": "a"}])

    def has_sample(self, object_id):
        time.sleep(self.delay)
        return True

    def put_sample(self, object_id, rows):
        time.sleep(self.delay)

    def evict_if_over_budget(self):
        return []

    def overlap(self, *a):
        time.sleep(self.delay)
        return 0.0

    def distinct_count(self, *a):
        time.sleep(self.delay)
        return 1

    def row_count(self, _):
        time.sleep(self.delay)
        return 1


async def _heartbeat(stop: asyncio.Event, ticks: list):
    """Stands in for the API still answering requests.

    Each tick is one turn of the event loop. If a stage blocks it, this stops
    counting — which is exactly what the user experienced.
    """
    while not stop.is_set():
        ticks.append(time.monotonic())
        await asyncio.sleep(0.01)


@pytest.fixture
async def source(db_session, tmp_path, monkeypatch):
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()

    path = tmp_path / "s.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, code TEXT)"))
        conn.execute(text("INSERT INTO t VALUES (1, 'a')"))
    # Both engine seams: discover uses the interactive pool, sampling its own.
    monkeypatch.setattr(catalog_sync, "_engine_for", lambda cfg: engine)
    monkeypatch.setattr(catalog_sync, "_sampling_engine_for", lambda cfg: engine)

    ds = DataSource(name="s", type="sqlite", org_id=org.id, config={"filepath": str(path)})
    db_session.add(ds)
    await db_session.commit()
    yield {"org": org, "source": ds, "cfg": {"type": "sqlite", "filepath": str(path)}}
    engine.dispose()


class TestLoopStaysResponsive:
    async def test_a_whole_sync_leaves_the_loop_free(self, db_session, source):
        """The regression, end to end. Every stage is slow; the loop must still
        turn throughout."""
        stop = asyncio.Event()
        ticks: list = []
        beat = asyncio.create_task(_heartbeat(stop, ticks))

        started = time.monotonic()
        await catalog_sync.run_catalog_sync(
            db_session, source["source"], cache=SlowCache(delay=0.05),
            source_config=source["cfg"],
        )
        await db_session.commit()
        elapsed = time.monotonic() - started

        stop.set()
        await beat

        # Asserted as a RATE, not a count. How long this sync takes depends on
        # the machine and on what else the suite is running, so an absolute
        # threshold is a flake waiting to happen — it failed exactly that way
        # under a full-suite run. What does not vary is the shape of the
        # failure: a blocked loop ticks a handful of times however long the run
        # lasts, while a free one keeps pace with its 10ms heartbeat.
        expected = elapsed / 0.01
        assert len(ticks) > expected * 0.25, (
            f"event loop ticked {len(ticks)} times in {elapsed:.2f}s "
            f"(≈{expected:.0f} expected if free) — a stage is blocking it"
        )

    async def test_no_single_gap_starves_the_loop(self, db_session, source):
        """A total tick count can look healthy while hiding one long freeze.
        This asserts the worst gap, which is what a user actually feels."""
        stop = asyncio.Event()
        ticks: list = []
        beat = asyncio.create_task(_heartbeat(stop, ticks))

        await catalog_sync.run_catalog_sync(
            db_session, source["source"], cache=SlowCache(delay=0.05),
            source_config=source["cfg"],
        )
        await db_session.commit()
        stop.set()
        await beat

        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        worst = max(gaps) if gaps else 0
        assert worst < 1.0, (
            f"the loop was blocked for {worst:.2f}s in one stretch — "
            "requests would hang for that long"
        )


class TestInferenceIsOffloaded:
    async def test_inference_runs_in_a_worker_thread(self, db_session, source, monkeypatch):
        """The single most expensive stage, and the one that caused the outage.

        Asserts the thread identity rather than timing, because timing tests
        pass on a fast machine while the defect remains.
        """
        import threading

        main_thread = threading.get_ident()
        seen = {}

        original = infer_keys.infer_foreign_keys

        def record(*args, **kwargs):
            seen["thread"] = threading.get_ident()
            return original(*args, **kwargs)

        monkeypatch.setattr(infer_keys, "infer_foreign_keys", record)

        await catalog_sync.run_catalog_sync(
            db_session, source["source"], cache=SlowCache(),
            source_config=source["cfg"],
        )
        await db_session.commit()

        assert seen.get("thread") is not None, "inference never ran"
        assert seen["thread"] != main_thread, (
            "foreign-key inference ran on the event loop; on a real source that "
            "is minutes of DuckDB work with the API answering nothing"
        )

    async def test_profiling_runs_in_a_worker_thread(self, db_session, source, monkeypatch):
        import threading

        main_thread = threading.get_ident()
        seen = {}

        original = catalog_sync._profile_object

        def record(*args, **kwargs):
            seen["thread"] = threading.get_ident()
            return original(*args, **kwargs)

        monkeypatch.setattr(catalog_sync, "_profile_object", record)

        await catalog_sync.run_catalog_sync(
            db_session, source["source"], cache=SlowCache(),
            source_config=source["cfg"],
        )
        await db_session.commit()

        assert seen.get("thread") != main_thread
