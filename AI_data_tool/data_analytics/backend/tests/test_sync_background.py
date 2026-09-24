"""Starting a sync must return immediately, and must never wedge the source.

Two bugs motivated this file, both of which made a source permanently
unsyncable — a 409 with no way out short of restarting the backend:

  1. the advisory lock was taken on the request's session, then `db.commit()`
     handed that connection back to the pool, so the unlock ran on a different
     connection and did nothing;

  2. a run row left at "running" by a process that died would block every
     subsequent attempt forever.

Both are the same shape: a guard that can be acquired but not reliably
released. The tests below pin the escapes.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.models import DataSource, Organization, Role, SyncRun
from app.services.metadata import sync


@pytest.fixture
async def source(db_session, two_orgs):
    ds = DataSource(name="wh", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(ds)
    await db_session.commit()
    return ds


class TestReturnsImmediately:
    async def test_post_returns_a_run_id_without_waiting(self, client, auth_headers, source):
        """The request must not block for the length of the sync. It hands back
        an id and the client watches progress through it."""
        r = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                              headers=auth_headers["a"])
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "running"
        assert isinstance(body["sync_run_id"], int)

    async def test_the_run_row_exists_before_the_response(self, client, auth_headers,
                                                          source, db_session):
        """Committed before the work starts, or the client would poll an id that
        does not exist yet."""
        r = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                              headers=auth_headers["a"])
        run = await db_session.get(SyncRun, r.json()["sync_run_id"])
        assert run is not None
        assert run.data_source_id == source.id

    async def test_the_run_is_pollable_straight_away(self, client, auth_headers, source):
        started = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                                    headers=auth_headers["a"])
        run_id = started.json()["sync_run_id"]

        r = await client.get(f"/api/v1/data-sources/{source.id}/sync/{run_id}",
                             headers=auth_headers["a"])
        assert r.status_code == 200
        assert "stages" in r.json()


class TestConcurrency:
    async def test_a_second_sync_while_one_is_running_is_refused(
        self, client, auth_headers, source, db_session
    ):
        db_session.add(SyncRun(
            data_source_id=source.id, org_id=source.org_id,
            trigger="manual", status="running", stages=[],
            started_at=datetime.utcnow(),
        ))
        await db_session.commit()

        r = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                              headers=auth_headers["a"])
        assert r.status_code == 409

    async def test_a_finished_run_does_not_block_the_next_one(
        self, client, auth_headers, source, db_session
    ):
        db_session.add(SyncRun(
            data_source_id=source.id, org_id=source.org_id,
            trigger="manual", status="ok", stages=[],
            started_at=datetime.utcnow(), finished_at=datetime.utcnow(),
        ))
        await db_session.commit()

        r = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                              headers=auth_headers["a"])
        assert r.status_code == 200

    async def test_a_stale_running_run_is_treated_as_abandoned(
        self, client, auth_headers, source, db_session
    ):
        """A process that died mid-sync leaves its row saying "running" forever.
        Refusing new syncs on its behalf helps nobody — this is exactly the
        permanent-409 failure the fix exists to prevent."""
        db_session.add(SyncRun(
            data_source_id=source.id, org_id=source.org_id,
            trigger="manual", status="running", stages=[],
            started_at=datetime.utcnow() - timedelta(minutes=sync.STALE_RUN_MINUTES + 5),
        ))
        await db_session.commit()

        r = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                              headers=auth_headers["a"])
        assert r.status_code == 200, "a dead run must not wedge the source"

    async def test_a_run_on_another_source_does_not_block_this_one(
        self, client, auth_headers, source, db_session, two_orgs
    ):
        other = DataSource(name="wh2", type="postgresql", org_id=two_orgs["a"]["org"].id)
        db_session.add(other)
        await db_session.flush()
        db_session.add(SyncRun(
            data_source_id=other.id, org_id=other.org_id,
            trigger="manual", status="running", stages=[],
            started_at=datetime.utcnow(),
        ))
        await db_session.commit()

        r = await client.post(f"/api/v1/data-sources/{source.id}/sync",
                              headers=auth_headers["a"])
        assert r.status_code == 200


class TestFindActiveRun:
    async def test_returns_none_when_nothing_is_running(self, db_session, source):
        assert await sync.find_active_run(db_session, source.id) is None

    async def test_returns_a_fresh_running_row(self, db_session, source):
        db_session.add(SyncRun(
            data_source_id=source.id, org_id=source.org_id,
            trigger="manual", status="running", stages=[],
            started_at=datetime.utcnow(),
        ))
        await db_session.commit()
        assert await sync.find_active_run(db_session, source.id) is not None

    async def test_ignores_a_stale_row(self, db_session, source):
        db_session.add(SyncRun(
            data_source_id=source.id, org_id=source.org_id,
            trigger="manual", status="running", stages=[],
            started_at=datetime.utcnow() - timedelta(minutes=sync.STALE_RUN_MINUTES + 1),
        ))
        await db_session.commit()
        assert await sync.find_active_run(db_session, source.id) is None


class TestProgressIsPublished:
    async def test_stages_are_written_as_they_complete(self, db_session, source):
        """The point of the whole change: the row must change DURING the run, or
        polling shows nothing until it is over."""
        class Cache:
            def get_sample(self, _): return []
            def has_sample(self, _): return False
            def put_sample(self, *a): pass
            def evict_if_over_budget(self): return []
            def overlap(self, *a): return 0.0
            def distinct_count(self, *a): return 0
            def row_count(self, _): return 0

        run = SyncRun(data_source_id=source.id, org_id=source.org_id,
                      trigger="manual", status="running", stages=[])
        db_session.add(run)
        await db_session.commit()

        seen = []
        original = sync._run_stage

        async def watching(context, name, fn):
            result = await original(context, name, fn)
            # Snapshot what a poller would have seen at this moment.
            seen.append(len(context.run.stages or []))
            return result

        sync._run_stage = watching
        try:
            await sync.run_sync(db_session, source.id, source.org_id,
                                cache=Cache(), run=run)
            await db_session.commit()
        finally:
            sync._run_stage = original

        # Strictly increasing: one more stage visible after each one finishes.
        assert seen == sorted(seen)
        assert seen[-1] > seen[0], "progress never became visible mid-run"
