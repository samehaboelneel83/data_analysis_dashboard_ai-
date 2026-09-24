"""The scheduler remembers failure, and one bad item no longer sinks its tick.

Three holes that only showed up in production:

  * **No memory of failure.** An item's timestamp advanced whether or not the
    work succeeded, so a source unreachable for a week was retried exactly as
    eagerly as one that failed once, and nothing recorded why.
  * **No isolation for datasets and dataflows.** Those two loops ran bare
    inside the tick's own try/except, so the FIRST raising item skipped every
    item after it -- while schedules and alerts were already isolated.
  * **Metadata syncs stuck at "running" forever.** `run_sync_background` is a
    detached task; if the process died mid-run, nothing corrected the row, and
    the UI showed a sync that nothing was progressing.
"""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.models import (DataSource, Dataset, Organization, Role,
                               ScheduleFailure, SyncRun, User)
from app.services import refresh_scheduler as rs


@pytest_asyncio.fixture
async def org(db_session):
    o = Organization(name="Tickland")
    db_session.add(o)
    await db_session.flush()
    role = Role(org_id=o.id, name="admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=o.id, role_id=role.id, email="ops@tickland.test",
                password_hash="x")
    db_session.add(user)
    await db_session.commit()
    return {"org": o, "user": user}


async def _failure(db_session, kind, item_id):
    return (await db_session.execute(
        select(ScheduleFailure).where(ScheduleFailure.kind == kind,
                                      ScheduleFailure.item_id == item_id)
    )).scalars().one()


class TestTheBackoffLadder:
    def test_it_widens_then_holds_at_a_day(self):
        # It never gives up: the fix is usually on the other side (a database
        # comes back, a credential is rotated) and nobody wants to hunt for a
        # "re-enable" button afterwards.
        assert [rs.backoff_minutes(n) for n in (1, 2, 3, 4, 5, 6)] == \
            [5, 15, 60, 240, 720, 1440]
        assert rs.backoff_minutes(50) == 1440
        assert rs.backoff_minutes(0) == 5      # defensive, never below the floor


class TestRememberingFailure:
    @pytest.mark.asyncio
    async def test_a_failure_is_counted_and_held_back(self, db_session, org):
        now = datetime.utcnow()
        assert await rs.in_backoff(db_session, "dataset", 7, now) is False

        attempts = await rs.record_failure(db_session, "dataset", 7,
                                           "connection refused", now)
        assert attempts == 1
        # Held back inside the window...
        assert await rs.in_backoff(db_session, "dataset", 7,
                                   now + timedelta(minutes=1)) is True
        # ...and due again after it.
        assert await rs.in_backoff(db_session, "dataset", 7,
                                   now + timedelta(minutes=6)) is False

    @pytest.mark.asyncio
    async def test_consecutive_failures_widen_the_window(self, db_session, org):
        now = datetime.utcnow()
        for expected in (1, 2, 3):
            assert await rs.record_failure(
                db_session, "dataset", 8, "boom", now) == expected
        row = await _failure(db_session, "dataset", 8)
        assert row.attempts == 3
        assert row.last_error == "boom"
        # The third failure waits an hour, not five minutes.
        assert row.next_attempt_at >= now + timedelta(minutes=59)

    @pytest.mark.asyncio
    async def test_success_forgets_the_streak(self, db_session, org):
        now = datetime.utcnow()
        await rs.record_failure(db_session, "alert", 9, "boom", now)
        await rs.clear_failure(db_session, "alert", 9)
        assert await rs.in_backoff(db_session, "alert", 9, now) is False
        # A healthy install carries NO rows -- "is anything broken?" is one
        # small select, not a scan.
        rows = (await db_session.execute(select(ScheduleFailure))).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_the_error_text_is_kept_but_bounded(self, db_session, org):
        await rs.record_failure(db_session, "schedule", 10, "x" * 5000)
        row = await _failure(db_session, "schedule", 10)
        assert len(row.last_error) == 2000

    @pytest.mark.asyncio
    async def test_kinds_do_not_collide(self, db_session, org):
        """Four categories share one table; id 5 in each is a different item."""
        now = datetime.utcnow()
        await rs.record_failure(db_session, "dataset", 5, "a", now)
        assert await rs.in_backoff(db_session, "dataflow", 5, now) is False
        assert await rs.in_backoff(db_session, "dataset", 5, now) is True


class TestOneBadItemDoesNotSinkTheTick:
    @pytest.mark.asyncio
    async def test_a_raising_dataset_no_longer_skips_the_rest(
            self, db_session, org, monkeypatch, tmp_path):
        """The regression that motivated per-item isolation."""
        src = DataSource(name="src", type="postgres", config={},
                         org_id=org["org"].id)
        db_session.add(src)
        await db_session.flush()

        made = []
        for i in range(3):
            f = tmp_path / f"d{i}.csv"
            f.write_text("a\n1\n", encoding="utf-8")
            ds = Dataset(name=f"d{i}", filename=str(f), org_id=org["org"].id,
                         data_source_id=src.id, source_table="t",
                         refresh_interval_minutes=5, mode="import")
            db_session.add(ds)
            made.append(ds)
        await db_session.commit()
        # Plain ints, captured while the instances are live: a rollback below
        # expires them, and reading `made[0].id` afterwards would be the very
        # lazy-IO trap this test exists to prove is gone.
        ids = [d.id for d in made]

        seen = []

        async def fake_refresh_one(session, ds):
            seen.append(ds.id)
            if ds.id == ids[0]:
                raise RuntimeError("first one explodes")
            return True

        monkeypatch.setattr(rs, "refresh_one", fake_refresh_one)

        # Mirrors the tick's own loop body, INCLUDING that it iterates ids:
        # recovering from a failure rolls the session back, which expires every
        # other loaded instance, and the next `ds.id` would then be lazy IO
        # from a sync attribute access (MissingGreenlet) -- thrown out of the
        # loop, killing the tick exactly as before. The clear is guarded, not
        # unconditional: an aggregate whose grain no longer covers its
        # source's rules records that failure INSIDE refresh_one and returns
        # True without raising (see test_aggregate_refresh.py), so clearing
        # right after on every tick would erase the row that same call just
        # wrote.
        now = datetime.utcnow()
        due_ids = [d.id for d in rs.due_datasets(made, now)]
        assert due_ids == ids
        for ds_id in due_ids:
            if await rs.in_backoff(db_session, "dataset", ds_id, now):
                continue
            try:
                row = await db_session.get(Dataset, ds_id)
                await rs.refresh_one(db_session, row)
                if not await rs.in_backoff(db_session, "dataset", ds_id, now):
                    await rs.clear_failure(db_session, "dataset", ds_id)
            except Exception as e:  # noqa: BLE001 - mirrors the tick
                await db_session.rollback()
                await rs.record_failure(db_session, "dataset", ds_id, str(e), now)

        # All three were attempted -- the old bare loop stopped at the first.
        assert seen == due_ids
        # ...and only the broken one holds a failure row.
        assert await rs.in_backoff(db_session, "dataset", ids[0], now) is True
        assert await rs.in_backoff(db_session, "dataset", ids[1], now) is False


class TestReapingStuckSyncRuns:
    @pytest.mark.asyncio
    async def test_a_restart_orphaned_run_is_closed(self, db_session, org):
        src = DataSource(name="s", type="postgres", config={},
                         org_id=org["org"].id)
        db_session.add(src)
        await db_session.flush()
        stuck = SyncRun(data_source_id=src.id, org_id=org["org"].id,
                        trigger="manual", status="running")
        done = SyncRun(data_source_id=src.id, org_id=org["org"].id,
                       trigger="manual", status="ok")
        db_session.add_all([stuck, done])
        await db_session.commit()

        assert await rs.reap_stuck_sync_runs(db_session) == 1
        await db_session.refresh(stuck)
        await db_session.refresh(done)
        assert stuck.status == "failed"
        assert "restart" in (stuck.error or "").lower()
        assert done.status == "ok"          # a finished run is left alone

    @pytest.mark.asyncio
    async def test_it_is_a_no_op_when_nothing_is_stuck(self, db_session, org):
        assert await rs.reap_stuck_sync_runs(db_session) == 0


@pytest.mark.asyncio
async def test_startup_reaps_failure_rows_whose_dataset_is_gone(db_session, two_orgs):
    from app.models.models import Dataset, ScheduleFailure
    from app.services.refresh_scheduler import reap_orphaned_failures, record_failure
    org = two_orgs["a"]["org"]
    live = Dataset(name="live", org_id=org.id, mode="import", filename=None)
    db_session.add(live)
    await db_session.flush()
    await record_failure(db_session, "dataset", live.id, "still here")
    await record_failure(db_session, "dataset", 999_999, "dataset deleted long ago")
    await record_failure(db_session, "schedule", 999_999, "not a dataset row; untouched")

    assert await reap_orphaned_failures(db_session) == 1
    rows = (await db_session.execute(select(ScheduleFailure))).scalars().all()
    assert {(r.kind, r.item_id) for r in rows} == {("dataset", live.id), ("schedule", 999_999)}
