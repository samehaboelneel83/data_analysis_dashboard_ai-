"""Closing the data-pipeline gaps (docs/pipeline/PLAN.md, 2026-10-10).

P1 rows deleted at the source leave an incremental dataset; P2 values must
exist in another dataset (referential integrity); P3 a schema change can
block; P4 runs record their speed and a far-slower run is flagged once; P5 a
column's lineage says where it comes from as well as what uses it. Sources are
real SQLite files, so the SQL the refresh writes really runs.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import (DataSource, Dataset, DatasetColumn, RefreshRun, SourceColumn,
                               SourceObject)
from app.services import data_checks
from app.services.dataset_refresh import build_incremental_query, drop_deleted, refresh_dataset


def _source(tmp_path, rows):
    path = tmp_path / "src.db"
    con = sqlite3.connect(path)
    con.execute("DROP TABLE IF EXISTS orders")
    con.execute("CREATE TABLE orders (id INTEGER, amount REAL, updated_at INTEGER)")
    con.executemany("INSERT INTO orders VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()
    return {"type": "sqlite", "filepath": str(path)}


class TestP1DeletesAtTheSource:
    def test_an_incremental_merge_removes_rows_deleted_at_the_source(self, tmp_path):
        cfg = _source(tmp_path, [(1, 10, 1), (2, 20, 2), (3, 30, 3)])
        file = tmp_path / "d.csv"
        first = refresh_dataset(cfg, str(file), "orders", None, "full", "updated_at", None)
        assert len(first["df"]) == 3
        # At the source: order 2 deleted, order 3 updated, order 4 added.
        _source(tmp_path, [(1, 10, 1), (3, 35, 4), (4, 40, 5)])
        out = refresh_dataset(cfg, str(file), "orders", None, "incremental", "updated_at", "3",
                              key_column="id", reconcile_deletes=True)
        assert out["mode"] == "incremental"
        assert sorted(out["df"]["id"]) == [1, 3, 4]
        assert out["rows_deleted"] == 1 and out["rows_updated"] == 1
        assert sorted(pd.read_csv(file)["id"]) == [1, 3, 4]

    def test_without_the_option_deleted_rows_stay(self, tmp_path):
        cfg = _source(tmp_path, [(1, 10, 1), (2, 20, 2)])
        file = tmp_path / "d.csv"
        refresh_dataset(cfg, str(file), "orders", None, "full", "updated_at", None)
        _source(tmp_path, [(1, 10, 1)])
        out = refresh_dataset(cfg, str(file), "orders", None, "incremental", "updated_at", "2", key_column="id")
        assert sorted(out["df"]["id"]) == [1, 2]

    def test_a_run_with_no_new_rows_leaves_the_numbers_alone(self, tmp_path):
        # Found while building P1: the empty fetch had untyped columns, and the
        # merged ids came back as 1970-01-01 00:00:00.000000001.
        cfg = _source(tmp_path, [(1, 10, 1), (2, 20, 2)])
        file = tmp_path / "d.csv"
        refresh_dataset(cfg, str(file), "orders", None, "full", "updated_at", None)
        for key in (None, "id"):
            out = refresh_dataset(cfg, str(file), "orders", None, "incremental", "updated_at", "2", key_column=key)
            assert out["df"]["id"].tolist() == [1, 2] and out["rows_added"] == 0
            assert pd.read_csv(file)["id"].tolist() == [1, 2]

    def test_a_key_stored_as_7_point_0_still_merges(self, tmp_path):
        # A key column with a gap is stored as decimals; the update was appended
        # as a duplicate because "7.0" != "7".
        file = tmp_path / "d.csv"
        pd.DataFrame({"id": [7.0, None], "amount": [1.0, 2.0], "updated_at": [1, 1]}).to_csv(file, index=False)
        cfg = _source(tmp_path, [(7, 99, 5)])
        out = refresh_dataset(cfg, str(file), "orders", None, "incremental", "updated_at", "1", key_column="id")
        assert out["rows_updated"] == 1 and len(out["df"]) == 2
        assert out["df"].loc[out["df"]["id"] == 7, "amount"].tolist() == [99]

    def test_an_empty_source_removes_nothing(self):
        df = pd.DataFrame({"id": [1, 2]})
        kept, removed, note = drop_deleted(df, "id", pd.Series([], dtype=object))
        assert len(kept) == 2 and removed == 0 and "no keys" in note

    def test_keys_compare_as_text(self):
        kept, removed, _ = drop_deleted(pd.DataFrame({"id": [1, 2, 3]}), "id", pd.Series(["1", "3"]))
        assert list(kept["id"]) == [1, 3] and removed == 1

    def test_the_watermark_column_is_quoted_for_the_source(self):
        # MySQL read "updated_at" as a text value, so the filter compared a constant.
        assert "`updated_at` > :cursor_val" in build_incremental_query("orders", None, "updated_at", "1",
                                                                       family="mysql")
        assert '"updated_at" > :cursor_val' in build_incremental_query("orders", None, "updated_at", "1")


class TestP2P3NewChecks:
    def test_references_counts_values_missing_from_the_other_dataset(self):
        check = {"kind": "references", "column": "customer_id", "severity": "block",
                 "params": {"dataset_id": 9, "column": "id"},
                 "_ref_values": {"1", "2"}, "_ref_name": "Customers.id"}
        df = pd.DataFrame({"customer_id": [1, 2, 7, 7, None]})
        r = data_checks.evaluate(df, [check])[0]
        assert r["passed"] is False and r["failing"] == 2
        assert "not found in Customers.id" in r["detail"] and "1 different" in r["detail"]
        assert data_checks.blocking_failures([r])

    def test_an_unreadable_reference_fails_visibly(self):
        r = data_checks.evaluate(pd.DataFrame({"c": [1]}), [{"kind": "references", "column": "c",
                                                              "severity": "warn", "params": {}}])[0]
        assert r["passed"] is False and "could not be read" in r["detail"]

    def test_same_columns_can_block_on_drift(self):
        known = {"id": "numeric", "price": "numeric"}
        df = pd.DataFrame({"id": [1, 2], "price": ["a", "b"], "extra": [1, 2]})
        check = {"kind": "same_columns", "severity": "block", "params": {"allow_new": True}}
        r = data_checks.evaluate(df, [check], known_types=known)[0]
        assert r["passed"] is False and "type changed: price" in r["detail"]
        strict = {**check, "params": {"allow_new": False}}
        assert "new: extra" in data_checks.evaluate(df, [strict], known_types=known)[0]["detail"]
        same = pd.DataFrame({"id": [1], "price": [2.5]})
        assert data_checks.evaluate(same, [check], known_types=known)[0]["passed"] is True

    @pytest.mark.parametrize("kind,params,msg", [
        ("references", {"column": "id"}, "Choose the dataset"),
        ("references", {"dataset_id": 3}, "Choose the column"),
    ])
    def test_new_kinds_are_validated(self, kind, params, msg):
        with pytest.raises(data_checks.InvalidCheck, match=msg):
            data_checks.validate_check(kind, "c", params, "warn")

    async def test_references_are_loaded_only_from_the_same_org(self, db_session, two_orgs, tmp_path):
        org_a, org_b = two_orgs["a"]["org"].id, two_orgs["b"]["org"].id
        f = tmp_path / "c.csv"
        pd.DataFrame({"id": [1, 2]}).to_csv(f, index=False)
        mine = Dataset(name="Customers", filename=str(f), org_id=org_a)
        theirs = Dataset(name="Theirs", filename=str(f), org_id=org_b)
        db_session.add_all([mine, theirs])
        await db_session.commit()
        checks = [{"kind": "references", "column": "c", "params": {"dataset_id": mine.id, "column": "id"}},
                  {"kind": "references", "column": "c", "params": {"dataset_id": theirs.id, "column": "id"}}]
        await data_checks._attach_references(db_session, checks, org_a)
        assert checks[0]["_ref_values"] == {"1", "2"} and checks[0]["_ref_name"] == "Customers.id"
        assert checks[1]["_ref_values"] is None

    async def test_the_api_refuses_a_dataset_of_another_org(self, client, db_session, two_orgs, auth_headers, tmp_path):
        org_a, org_b = two_orgs["a"]["org"].id, two_orgs["b"]["org"].id
        src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org_a)
        db_session.add(src)
        await db_session.commit()
        ds = Dataset(name="Orders", filename=str(tmp_path / "o.csv"), org_id=org_a, data_source_id=src.id)
        theirs = Dataset(name="Theirs", filename=str(tmp_path / "t.csv"), org_id=org_b)
        db_session.add_all([ds, theirs])
        await db_session.commit()
        r = await client.post(f"/api/v1/datasets/{ds.id}/checks", headers=auth_headers["a"], json={
            "kind": "references", "column": "customer_id", "severity": "block",
            "params": {"dataset_id": theirs.id, "column": "id"}})
        assert r.status_code == 400


class TestP4RunMetrics:
    async def _runs(self, db_session, org, durations_ms):
        from app.services.refresh_runs import finish_run, start_run
        ids = []
        for ms in durations_ms:
            rid = await start_run(db_session, "dataset", 4242, org, "manual")
            run = await db_session.get(RefreshRun, rid)
            run.started_at = datetime.utcnow() - timedelta(milliseconds=ms)
            await db_session.commit()
            await finish_run(db_session, rid, "ok", rows=1000)
            ids.append(rid)
        return [await db_session.get(RefreshRun, i) for i in ids]

    async def test_speed_is_recorded_and_a_far_slower_run_is_flagged_once(self, db_session, two_orgs, monkeypatch):
        told = []

        async def fake_slow(session, kind, item_id, run_id):
            told.append(run_id)
        monkeypatch.setattr("app.services.pipeline_alerts.on_slow_run", fake_slow)
        runs = await self._runs(db_session, two_orgs["a"]["org"].id, [10_000, 11_000, 9_000, 40_000, 45_000])
        for r in runs:
            await db_session.refresh(r)
        assert runs[0].metrics["rows_per_sec"] == pytest.approx(100, rel=0.2)
        assert "slow" not in (runs[2].metrics or {})
        assert runs[3].metrics["slow"]["times"] >= 3
        assert runs[4].metrics.get("slow")                 # still slow...
        assert told == [runs[3].id]                         # ...but told only once

    async def test_a_short_run_is_never_slow(self, db_session, two_orgs):
        runs = await self._runs(db_session, two_orgs["a"]["org"].id, [1_000, 1_000, 1_000, 9_000])
        await db_session.refresh(runs[-1])
        assert "slow" not in (runs[-1].metrics or {})


class TestP5ColumnLineage:
    async def test_origin_and_uses(self, client, db_session, two_orgs, auth_headers, tmp_path):
        org = two_orgs["a"]["org"].id
        src = DataSource(name="Cars DB", type="postgresql", config={}, org_id=org)
        db_session.add(src)
        await db_session.flush()
        obj = SourceObject(data_source_id=src.id, org_id=org, name="cars", schema_name="public", kind="table")
        db_session.add(obj)
        await db_session.flush()
        sc = SourceColumn(source_object_id=obj.id, name="price", position=0, dtype="numeric", native_type="numeric(12,2)")
        db_session.add(sc)
        await db_session.flush()
        ds = Dataset(name="Cars", org_id=org, data_source_id=src.id, filename=str(tmp_path / "c.csv"),
                     calculated_columns=[{"name": "price_k", "expression": "price / 1000"}],
                     measures=[{"name": "Avg price", "expression": "AVG(price)"}])
        db_session.add(ds)
        await db_session.flush()
        db_session.add_all([DatasetColumn(dataset_id=ds.id, name="price", dtype="numeric", source_column_id=sc.id),
                            DatasetColumn(dataset_id=ds.id, name="make", dtype="categorical")])
        await db_session.commit()

        body = (await client.get(f"/api/v1/datasets/{ds.id}/column-lineage", params={"name": "price"},
                                 headers=auth_headers["a"])).json()
        assert body["origin"] == {"kind": "source", "source": "Cars DB", "source_id": src.id,
                                  "table": "public.cars", "column": "price", "native_type": "numeric(12,2)"}
        assert {(u["kind"], u["label"]) for u in body["used_by"]} >= {("calculated_column", "price_k"),
                                                                      ("measure", "Avg price")}
        calc = (await client.get(f"/api/v1/datasets/{ds.id}/column-lineage", params={"name": "price_k"},
                                 headers=auth_headers["a"])).json()
        assert calc["origin"] == {"kind": "calculated", "expression": "price / 1000", "inputs": ["price"]}
        made = (await client.get(f"/api/v1/datasets/{ds.id}/column-lineage", params={"name": "make"},
                                 headers=auth_headers["a"])).json()
        assert made["origin"] == {"kind": "query"}

    async def test_another_org_cannot_read_it(self, client, db_session, two_orgs, auth_headers):
        ds = Dataset(name="Cars", org_id=two_orgs["a"]["org"].id)
        db_session.add(ds)
        await db_session.commit()
        r = await client.get(f"/api/v1/datasets/{ds.id}/column-lineage", params={"name": "x"},
                             headers=auth_headers["b"])
        assert r.status_code == 404


class TestP5WholeProcess:
    """"Make sure lineage shows all the process": source -> load (and the last
    run) -> transformation steps -> formula -> checks -> uses."""

    async def test_every_stage_in_order(self, client, db_session, two_orgs, auth_headers, tmp_path):
        from app.models.models import DataCheck, Watermark
        org = two_orgs["a"]["org"].id
        src = DataSource(name="Shop DB", type="postgresql", config={}, org_id=org)
        db_session.add(src)
        await db_session.flush()
        obj = SourceObject(data_source_id=src.id, org_id=org, name="orders", kind="table")
        db_session.add(obj)
        await db_session.flush()
        sc = SourceColumn(source_object_id=obj.id, name="amt", position=0, dtype="numeric")
        db_session.add(sc)
        regions = Dataset(name="Regions", org_id=org)
        db_session.add(regions)
        await db_session.flush()
        ds = Dataset(name="Orders", org_id=org, data_source_id=src.id, source_query="SELECT amt FROM orders",
                     filename=str(tmp_path / "o.csv"),
                     column_meta={"__prep_steps__": [
                         {"kind": "rename", "column": "amt", "to": "amount"},
                         {"kind": "join", "dataset_id": regions.id, "how": "left", "left_on": "r", "right_on": "r"},
                         {"kind": "trim", "columns": ["note"]}]},
                     calculated_columns=[{"name": "amount_k", "expression": "amount / 1000"}])
        db_session.add(ds)
        await db_session.flush()
        db_session.add_all([
            DatasetColumn(dataset_id=ds.id, name="amt", dtype="numeric", source_column_id=sc.id),
            Watermark(dataset_id=ds.id, strategy="incremental", cursor_column="updated_at", key_column="id",
                      reconcile_deletes=True),
            DataCheck(org_id=org, dataset_id=ds.id, kind="not_null", column="amount", params={}, severity="block"),
            RefreshRun(org_id=org, kind="dataset", item_id=ds.id, trigger="schedule", status="failed",
                       error="source unreachable\nstack...", started_at=datetime.utcnow())])
        await db_session.commit()

        body = (await client.get(f"/api/v1/datasets/{ds.id}/column-lineage", params={"name": "amount"},
                                 headers=auth_headers["a"])).json()
        stages = {s["stage"]: s for s in body["process"]}
        assert [s["stage"] for s in body["process"]] == ["source", "load", "steps", "checks"]
        # The renamed column is followed back to the source column it came from.
        assert stages["source"]["kind"] == "source" and stages["source"]["column"] == "amt"
        assert stages["source"]["arrives_as"] == "amt"
        load = stages["load"]
        assert (load["strategy"], load["key_column"], load["reconcile_deletes"]) == ("incremental", "id", True)
        assert load["last_run"]["status"] == "failed" and load["last_run"]["error"] == "source unreachable"
        assert load["query"] == "SELECT amt FROM orders"             # editors see the SQL
        steps = stages["steps"]["steps"]
        assert [(s["kind"], s["role"]) for s in steps] == [("rename", "makes"), ("join", "rows")]
        assert steps[1]["dataset"] == "Regions" and stages["steps"]["total_steps"] == 3
        assert stages["checks"]["checks"][0]["kind"] == "not_null"

        calc = (await client.get(f"/api/v1/datasets/{ds.id}/column-lineage", params={"name": "amount_k"},
                                 headers=auth_headers["a"])).json()
        cst = {s["stage"]: s for s in calc["process"]}
        assert cst["source"]["kind"] == "inputs"
        first = cst["source"]["inputs"][0]
        # The input is followed back through the rename to the source column.
        assert (first["name"], first["kind"], first["column"], first["arrives_as"]) == ("amount", "source", "amt", "amt")
        assert cst["formula"]["expression"] == "amount / 1000"
        assert any(u["label"] == "amount_k" for u in body["used_by"])

    async def test_a_reader_sees_the_journey_but_not_the_sql_or_raw_errors(self, db_session, two_orgs):
        # Who counts as an editor is the platform's own rule (require_dataset_write,
        # the same one that hides a watermark's value); here the reader side.
        from app.services.dependencies import column_process
        org = two_orgs["a"]["org"].id
        ds = Dataset(name="Orders", org_id=org, source_query="SELECT secret_col FROM t")
        db_session.add(ds)
        await db_session.flush()
        db_session.add(RefreshRun(org_id=org, kind="dataset", item_id=ds.id, trigger="schedule",
                                  status="failed", error="password authentication failed for db_admin"))
        await db_session.commit()
        load = next(s for s in await column_process(db_session, ds, "x", editor=False) if s["stage"] == "load")
        assert "query" not in load and load["has_query"] is True
        assert load["last_run"]["status"] == "failed" and load["last_run"]["error"] is None
        load = next(s for s in await column_process(db_session, ds, "x", editor=True) if s["stage"] == "load")
        assert load["query"].startswith("SELECT") and "password" in load["last_run"]["error"]


class TestScheduledRunsActAsTheirCreator:
    """Data-engineer tour (2026-10-10): every scheduled dataflow failed with
    "greenlet_spawn has not been called" -- the creator was loaded without
    their role, and the row-security lookup read `user.role` lazily. Tests
    missed it because the fixture user's role was already in the session."""

    async def test_a_scheduled_dataflow_runs_in_a_fresh_session(self, db_session, two_orgs, tmp_path):
        from app.models.models import Dataflow
        from app.services.prep import DERIVED_FROM_KEY
        from app.services.refresh_scheduler import refresh_dataflow
        org, user = two_orgs["a"]["org"].id, two_orgs["a"]["user"].id
        src_file, out_file = tmp_path / "src.csv", tmp_path / "out.csv"
        pd.DataFrame({"dept": ["a", "b"], "n": [1, 2]}).to_csv(src_file, index=False)
        pd.DataFrame({"dept": [], "n": []}).to_csv(out_file, index=False)
        src = Dataset(name="src", org_id=org, filename=str(src_file))
        db_session.add(src)
        await db_session.flush()
        flow = Dataflow(name="f", org_id=org, steps=[], source_dataset_id=src.id, created_by=user,
                        refresh_interval_minutes=60)
        db_session.add(flow)
        await db_session.flush()
        db_session.add(Dataset(name="out", org_id=org, filename=str(out_file),
                               column_meta={DERIVED_FROM_KEY: {"dataflow_id": flow.id}}))
        await db_session.commit()
        fid = flow.id
        db_session.expunge_all()            # a scheduler tick starts with nothing loaded
        flow = await db_session.get(Dataflow, fid)
        await refresh_dataflow(db_session, flow)
        await db_session.refresh(flow)
        assert flow.last_run_status == "ok", flow.last_run_error
        assert flow.last_run_rows == 2

    async def test_a_dataflow_with_no_outputs_is_recorded_once_not_every_hour(self, db_session, two_orgs):
        from app.models.models import Dataflow
        from app.services.refresh_scheduler import refresh_dataflow
        org = two_orgs["a"]["org"].id
        flow = Dataflow(name="idle", org_id=org, steps=[], created_by=two_orgs["a"]["user"].id,
                        refresh_interval_minutes=60)
        db_session.add(flow)
        await db_session.commit()
        for _ in range(3):
            await refresh_dataflow(db_session, flow)
        runs = (await db_session.execute(select(RefreshRun).where(
            RefreshRun.kind == "dataflow", RefreshRun.item_id == flow.id))).scalars().all()
        assert [r.status for r in runs] == ["skipped"]
        assert flow.last_run_status == "skipped"
