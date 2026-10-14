"""Pipeline plan, phase 4: load less, run in order.

* An incremental load MERGES on a key: an updated row appears once, with its
  new values. A look-back re-reads late updates behind a date cursor.
* The scheduler follows the watermark, with a full reload every N days.
* A dataflow, or a dataset rebuilt from another, can run when its source
  refreshes; a loop is refused when it is set up.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import (DataSource, Dataflow, Dataset, DatasetColumn, PipelineWatch,
                               RefreshRun, Watermark)
from app.services.dataset_refresh import lookback_cursor, refresh_dataset
from app.services.prep import DERIVED_FROM_KEY


class TestLookback:
    @pytest.mark.parametrize("cursor,hours,expected", [
        ("2026-10-03", 48, "2026-10-01"),
        ("2026-10-03 12:00:00", 6, "2026-10-03 06:00:00"),
        ("1042", 6, "1042"),            # a number: no such thing as six hours before it
        (None, 6, None),
        ("2026-10-03", None, "2026-10-03"),
    ])
    def test_it_moves_only_a_date_cursor(self, cursor, hours, expected):
        assert lookback_cursor(cursor, hours) == expected


class TestTheMerge:
    def _run(self, tmp_path, monkeypatch, existing, incoming, key="id", lookback=None):
        path = tmp_path / "d.csv"
        existing.to_csv(path, index=False)
        seen = {}

        def fake(cfg, table, query, params=None):
            seen["params"] = params
            return incoming
        monkeypatch.setattr("app.services.connections.import_to_dataframe", fake)
        out = refresh_dataset({"type": "sqlite"}, str(path), "t", None, "incremental", "ts", "2",
                              key_column=key, lookback_hours=lookback)
        return out, pd.read_csv(path), seen

    def test_an_updated_row_replaces_the_old_one(self, tmp_path, monkeypatch):
        out, on_disk, _ = self._run(
            tmp_path, monkeypatch,
            pd.DataFrame({"id": [1, 2], "status": ["open", "open"], "ts": [1, 2]}),
            pd.DataFrame({"id": [2, 3], "status": ["closed", "open"], "ts": [3, 3]}))
        assert sorted(on_disk["id"]) == [1, 2, 3]
        assert on_disk.set_index("id").loc[2, "status"] == "closed"
        assert (out["rows_added"], out["rows_updated"]) == (1, 1)

    def test_without_a_key_it_appends_as_before(self, tmp_path, monkeypatch):
        _, on_disk, _ = self._run(
            tmp_path, monkeypatch,
            pd.DataFrame({"id": [1, 2], "ts": [1, 2]}), pd.DataFrame({"id": [2], "ts": [3]}), key=None)
        assert list(on_disk["id"]) == [1, 2, 2]

    def test_a_key_the_file_lacks_appends_and_says_so(self, tmp_path, monkeypatch):
        out, on_disk, _ = self._run(
            tmp_path, monkeypatch,
            pd.DataFrame({"id": [1], "ts": [1]}), pd.DataFrame({"id": [2], "ts": [3]}), key="order_no")
        assert "not found" in out["warning"] and len(on_disk) == 2

    def test_the_look_back_fetches_further_but_keeps_the_watermark(self, tmp_path, monkeypatch):
        path = tmp_path / "d.csv"
        pd.DataFrame({"id": [1], "ts": ["2026-10-02"]}).to_csv(path, index=False)
        seen = {}
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, t, q, params=None: seen.update(p=params) or
                            pd.DataFrame({"id": [1], "ts": ["2026-10-02"]}))
        out = refresh_dataset({"type": "sqlite"}, str(path), "t", None, "incremental", "ts",
                              "2026-10-02", key_column="id", lookback_hours=24)
        assert seen["p"] == {"cursor_val": "2026-10-01"}
        assert len(pd.read_csv(path)) == 1                  # re-read, replaced, not duplicated
        assert str(out["cursor_value"]).startswith("2026-10-02")


# ── the scheduler and the API ────────────────────────────────────────────────

async def _dataset(db_session, two_orgs, tmp_path, name="Orders"):
    org = two_orgs["a"]["org"]
    path = tmp_path / f"{name}.csv"
    pd.DataFrame({"id": [1, 2], "status": ["open", "open"], "ts": [1, 2]}).to_csv(path, index=False)
    src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org.id)
    db_session.add(src)
    await db_session.commit()
    ds = Dataset(name=name, filename=str(path), org_id=org.id, row_count=2, col_count=3,
                 data_source_id=src.id, source_table="t", refresh_interval_minutes=60,
                 created_by=two_orgs["a"]["user"].id)
    db_session.add(ds)
    await db_session.commit()
    for c, t in (("id", "numeric"), ("status", "categorical"), ("ts", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t, stats={}))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


class TestTheScheduler:
    async def test_it_follows_an_incremental_watermark(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import refresh_one
        ds = await _dataset(db_session, two_orgs, tmp_path)
        db_session.add(Watermark(dataset_id=ds.id, strategy="incremental", cursor_column="ts",
                                 cursor_value="2", key_column="id",
                                 last_full_at=datetime.utcnow()))
        await db_session.commit()
        calls = []
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, t, q, params=None: calls.append(params) or
                            pd.DataFrame({"id": [2, 3], "status": ["closed", "open"], "ts": [3, 4]}))

        await refresh_one(db_session, ds)

        assert calls == [{"cursor_val": "2"}]               # only past the cursor
        on_disk = pd.read_csv(ds.filename)
        assert sorted(on_disk["id"]) == [1, 2, 3]
        wm = (await db_session.execute(select(Watermark))).scalar_one()
        await db_session.refresh(wm)
        assert str(wm.cursor_value) == "4"
        run = (await db_session.execute(select(RefreshRun))).scalar_one()
        assert run.status == "ok" and run.rows == 3

    async def test_a_full_reload_comes_round(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import refresh_one
        ds = await _dataset(db_session, two_orgs, tmp_path)
        db_session.add(Watermark(dataset_id=ds.id, strategy="incremental", cursor_column="ts",
                                 cursor_value="2", key_column="id", full_reload_days=7,
                                 last_full_at=datetime.utcnow() - timedelta(days=8)))
        await db_session.commit()
        calls = []
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, t, q, params=None: calls.append(params) or
                            pd.DataFrame({"id": [5], "status": ["open"], "ts": [9]}))

        await refresh_one(db_session, ds)

        assert calls == [None]                               # the whole table
        assert list(pd.read_csv(ds.filename)["id"]) == [5]
        wm = (await db_session.execute(select(Watermark))).scalar_one()
        await db_session.refresh(wm)
        assert wm.last_full_at is not None and datetime.utcnow() - wm.last_full_at.replace(tzinfo=None) < timedelta(minutes=1)


class TestSettings:
    async def test_round_trip(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        body = {"strategy": "incremental", "cursor_column": "ts", "key_column": "id",
                "lookback_hours": 24, "full_reload_days": 7}
        r = await client.put(f"/api/v1/datasets/{ds.id}/incremental", json=body, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        got = (await client.get(f"/api/v1/datasets/{ds.id}/incremental", headers=auth_headers["a"])).json()
        assert {k: got[k] for k in body} == body

    @pytest.mark.parametrize("body", [
        {"strategy": "incremental"},
        {"strategy": "incremental", "cursor_column": "nope"},
        {"strategy": "incremental", "cursor_column": "ts", "lookback_hours": 6},      # no key
        {"strategy": "incremental", "cursor_column": "ts", "key_column": "id", "full_reload_days": 0},
        {"strategy": "sometimes"},
    ])
    async def test_bad_settings_are_refused(self, client, db_session, two_orgs, auth_headers, tmp_path, body):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        r = await client.put(f"/api/v1/datasets/{ds.id}/incremental", json=body, headers=auth_headers["a"])
        assert r.status_code == 400

    async def test_another_org_cannot_reach_them(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        assert (await client.get(f"/api/v1/datasets/{ds.id}/incremental",
                                 headers=auth_headers["b"])).status_code == 404


# ── run after the source ─────────────────────────────────────────────────────

async def _flow_world(db_session, two_orgs, tmp_path):
    """Source S -> dataflow F -> output O."""
    s = await _dataset(db_session, two_orgs, tmp_path, "S")
    org_id = s.org_id
    flow = Dataflow(name="F", org_id=org_id, steps=[], source_dataset_id=s.id,
                    created_by=two_orgs["a"]["user"].id, refresh_interval_minutes=60)
    db_session.add(flow)
    await db_session.commit()
    o_path = tmp_path / "O.csv"
    pd.DataFrame({"id": [1]}).to_csv(o_path, index=False)
    o = Dataset(name="O", filename=str(o_path), org_id=org_id,
                column_meta={DERIVED_FROM_KEY: {"dataflow_id": flow.id, "source_dataset_id": s.id}})
    db_session.add(o)
    await db_session.commit()
    return s, flow, o


class TestRunAfterSource:
    async def test_a_dataflow_follows_its_source(self, client, db_session, two_orgs, auth_headers, tmp_path):
        from app.services.pipeline_deps import pending_items
        from app.services.refresh_runs import finish_run, start_run
        s, flow, _o = await _flow_world(db_session, two_orgs, tmp_path)

        r = await client.put(f"/api/v1/dataflows/{flow.id}", json={"run_after_source": True},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["run_after_source"] is True
        assert r.json()["refresh_interval_minutes"] is None          # one trigger, not two

        rid = await start_run(db_session, "dataset", s.id, s.org_id)
        await finish_run(db_session, rid, "ok", rows=2)
        assert await pending_items(db_session) == [("dataflow", flow.id)]

    async def test_a_failed_source_refresh_triggers_nothing(self, client, db_session, two_orgs,
                                                            auth_headers, tmp_path):
        from app.services.pipeline_deps import pending_items
        from app.services.refresh_runs import finish_run, start_run
        s, flow, _o = await _flow_world(db_session, two_orgs, tmp_path)
        await client.put(f"/api/v1/dataflows/{flow.id}", json={"run_after_source": True},
                           headers=auth_headers["a"])
        rid = await start_run(db_session, "dataset", s.id, s.org_id)
        await finish_run(db_session, rid, "failed", error="boom")
        assert await pending_items(db_session) == []

    async def test_a_loop_is_refused(self, client, db_session, two_orgs, auth_headers, tmp_path):
        s, flow, o = await _flow_world(db_session, two_orgs, tmp_path)
        # S is itself rebuilt from O: S -> F -> O -> S.
        s.column_meta = {DERIVED_FROM_KEY: {"source_dataset_id": o.id}}
        await db_session.commit()
        r = await client.put(f"/api/v1/dataflows/{flow.id}", json={"run_after_source": True},
                               headers=auth_headers["a"])
        assert r.status_code == 400 and "never stop" in r.json()["detail"]

    async def test_a_rebuilt_dataset_follows_its_source(self, client, db_session, two_orgs,
                                                        auth_headers, tmp_path):
        from app.services.pipeline_deps import pending_items
        from app.services.refresh_runs import finish_run, start_run
        s = await _dataset(db_session, two_orgs, tmp_path, "S")
        d_path = tmp_path / "D.csv"
        pd.DataFrame({"id": [1]}).to_csv(d_path, index=False)
        d = Dataset(name="D", filename=str(d_path), org_id=s.org_id, refresh_interval_minutes=60,
                    column_meta={DERIVED_FROM_KEY: {"source_dataset_id": s.id, "steps": []}})
        db_session.add(d)
        await db_session.commit()

        r = await client.patch(f"/api/v1/datasets/{d.id}/refresh-schedule", json={"after_source": True},
                               headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert r.json()["refresh_interval_minutes"] is None

        rid = await start_run(db_session, "dataset", s.id, s.org_id)
        await finish_run(db_session, rid, "ok", rows=2)
        assert await pending_items(db_session) == [("dataset", d.id)]
        w = (await db_session.execute(select(PipelineWatch).where(PipelineWatch.item_id == d.id))).scalar_one()
        assert w.run_after_source and w.trigger_pending

    async def test_choosing_a_timer_stops_following(self, client, db_session, two_orgs, auth_headers, tmp_path):
        _s, flow, _o = await _flow_world(db_session, two_orgs, tmp_path)
        await client.put(f"/api/v1/dataflows/{flow.id}", json={"run_after_source": True},
                           headers=auth_headers["a"])
        r = await client.put(f"/api/v1/dataflows/{flow.id}", json={"refresh_interval_minutes": 60},
                               headers=auth_headers["a"])
        assert r.json()["run_after_source"] is False and r.json()["refresh_interval_minutes"] == 60
