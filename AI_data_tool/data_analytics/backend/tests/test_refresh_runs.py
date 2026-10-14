"""Pipeline plan, phase 1: every refresh is recorded, and a failure never looks fresh.

Live finding (2026-10-03): a scheduled refresh of an ordinary dataset that
failed was only logged -- no `ScheduleFailure`, no backoff -- and its
`last_refreshed_at` still advanced, so a dataset whose source had been down
for a week read as refreshed a minute ago. Each test below pins one half of
the fix: the failure is recorded (backoff + a failed `RefreshRun`), the stamp
and the file stay as they were, and success writes an `ok` run with its rows.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from app.models.models import DataSource, Dataflow, Dataset, RefreshRun, ScheduleFailure


async def _dataset(db_session, org_id, tmp_path, name="ds"):
    path = tmp_path / f"{name}.csv"
    pd.DataFrame([{"id": 1, "v": 10}]).to_csv(path, index=False)
    src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    ds = Dataset(name=name, filename=str(path), org_id=org_id, row_count=1, col_count=2,
                 data_source_id=src.id, source_table="t", refresh_interval_minutes=60)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _runs(db_session, kind, item_id):
    return (await db_session.execute(select(RefreshRun).where(
        RefreshRun.kind == kind, RefreshRun.item_id == item_id
    ).order_by(RefreshRun.id))).scalars().all()


def _broken(*_a, **_k):
    raise ConnectionError("the source is unreachable")


class TestAScheduledFailureIsRecorded:
    async def test_the_failure_is_recorded_and_backs_off(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import in_backoff, refresh_one
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        monkeypatch.setattr("app.services.connections.import_to_dataframe", _broken)

        assert await refresh_one(db_session, ds) is True

        failure = (await db_session.execute(select(ScheduleFailure).where(
            ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == ds.id))).scalar_one()
        assert "unreachable" in failure.last_error
        assert await in_backoff(db_session, "dataset", ds.id, datetime.utcnow())

    async def test_it_does_not_look_fresh(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import refresh_one
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        week_ago = datetime.utcnow() - timedelta(days=7)
        ds.last_refreshed_at = week_ago
        await db_session.commit()
        before = open(ds.filename, encoding="utf-8").read()
        monkeypatch.setattr("app.services.connections.import_to_dataframe", _broken)

        await refresh_one(db_session, ds)
        await db_session.refresh(ds)

        assert ds.last_refreshed_at.replace(tzinfo=None) == week_ago
        assert open(ds.filename, encoding="utf-8").read() == before

    async def test_a_failed_run_is_kept_with_its_error(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import refresh_one
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        monkeypatch.setattr("app.services.connections.import_to_dataframe", _broken)

        await refresh_one(db_session, ds)

        [run] = await _runs(db_session, "dataset", ds.id)
        assert (run.status, run.trigger, run.error_code) == ("failed", "schedule", "refresh_failed")
        assert "unreachable" in run.error
        assert run.finished_at is not None and run.duration_ms is not None


class TestAScheduledSuccess:
    async def test_it_records_rows_and_clears_the_failure(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import refresh_one
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        monkeypatch.setattr("app.services.connections.import_to_dataframe", _broken)
        await refresh_one(db_session, ds)
        fresh = pd.DataFrame([{"id": i, "v": i} for i in range(5)])
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: fresh)

        await refresh_one(db_session, ds)
        await db_session.refresh(ds)

        runs = await _runs(db_session, "dataset", ds.id)
        assert [r.status for r in runs] == ["failed", "ok"]
        assert runs[-1].rows == 5
        assert ds.row_count == 5 and ds.last_refreshed_at is not None
        assert (await db_session.execute(select(ScheduleFailure).where(
            ScheduleFailure.item_id == ds.id))).scalar_one_or_none() is None


class TestADataflowFailure:
    async def test_it_is_recorded_and_backs_off(self, db_session, two_orgs, tmp_path):
        from app.services.prep import DERIVED_FROM_KEY
        from app.services.refresh_scheduler import in_backoff, refresh_dataflow
        org_id = two_orgs["a"]["org"].id
        flow = Dataflow(name="f", org_id=org_id, steps=[], source_dataset_id=None,
                        created_by=two_orgs["a"]["user"].id, refresh_interval_minutes=60)
        db_session.add(flow)
        await db_session.commit()
        out = tmp_path / "out.csv"
        pd.DataFrame({"k": [1]}).to_csv(out, index=False)
        db_session.add(Dataset(name="out", filename=str(out), org_id=org_id,
                               column_meta={DERIVED_FROM_KEY: {"dataflow_id": flow.id}}))
        await db_session.commit()

        await refresh_dataflow(db_session, flow)

        [run] = await _runs(db_session, "dataflow", flow.id)
        assert run.status == "failed" and run.error_code == "source_gone"
        assert await in_backoff(db_session, "dataflow", flow.id, datetime.utcnow())


class TestAManualRefresh:
    async def test_it_is_recorded_as_manual(self, client, db_session, two_orgs, auth_headers,
                                            tmp_path, monkeypatch):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        fresh = pd.DataFrame([{"id": 1, "v": 1}, {"id": 2, "v": 2}])
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: fresh)

        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full"},
                              headers=auth_headers["a"])
        assert r.status_code == 200, r.text

        [run] = await _runs(db_session, "dataset", ds.id)
        assert (run.status, run.trigger, run.rows) == ("ok", "manual", 2)

    async def test_a_manual_failure_is_recorded(self, client, db_session, two_orgs, auth_headers,
                                                tmp_path, monkeypatch):
        ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
        monkeypatch.setattr("app.services.connections.import_to_dataframe", _broken)

        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full"},
                              headers=auth_headers["a"])
        assert r.status_code >= 400

        [run] = await _runs(db_session, "dataset", ds.id)
        assert (run.status, run.trigger) == ("failed", "manual")
        assert "unreachable" in run.error


class TestHousekeeping:
    async def test_a_restart_closes_runs_left_running(self, db_session):
        from app.services.refresh_runs import reap_running
        db_session.add(RefreshRun(kind="dataset", item_id=1, trigger="schedule", status="running"))
        await db_session.commit()

        assert await reap_running(db_session) == 1

        run = (await db_session.execute(select(RefreshRun))).scalar_one()
        assert run.status == "failed" and run.error_code == "interrupted"

    async def test_history_is_trimmed_per_item(self, db_session, monkeypatch):
        from app.services import refresh_runs
        monkeypatch.setattr(refresh_runs, "KEEP_PER_ITEM", 3)
        for _ in range(5):
            rid = await refresh_runs.start_run(db_session, "dataset", 7, None)
            await refresh_runs.finish_run(db_session, rid, "ok", rows=1)

        assert len(await _runs(db_session, "dataset", 7)) == 3
