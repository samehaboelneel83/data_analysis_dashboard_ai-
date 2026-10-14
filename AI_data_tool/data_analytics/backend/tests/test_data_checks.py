"""Pipeline plan, phase 3: saved checks stop bad data before it is published.

Each check is evaluated on the NEW frame before the file is swapped. A failing
`block` check keeps yesterday's data live and records the run as blocked; a
`warn` check is recorded and the data published. An editor can publish a
blocked refresh anyway. Schema notes (gone / new / retyped columns) ride along.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.models.models import (DataCheck, DataSource, Dataset, DatasetColumn, Notification,
                               RefreshRun)
from app.services import pipeline_alerts
from app.services.data_checks import (ChecksBlocked, InvalidCheck, evaluate, make_validator,
                                      schema_notes, validate_check)


@pytest.fixture(autouse=True)
def _no_brief_cache():
    pipeline_alerts._BRIEF_CACHE.clear()
    yield


FRAME = pd.DataFrame({"id": [1, 2, 3, 3], "status": ["open", "closed", "weird", None],
                      "amount": [10, 20, -5, 7]})


def _c(kind, column=None, severity="block", **params):
    return {"id": 1, "kind": kind, "column": column, "params": params, "severity": severity,
            "enabled": True}


class TestEachKind:
    def test_not_null(self):
        [r] = evaluate(FRAME, [_c("not_null", "status")])
        assert not r["passed"] and r["failing"] == 1 and "no status" in r["detail"]
        [r] = evaluate(FRAME, [_c("not_null", "id")])
        assert r["passed"]

    def test_unique(self):
        [r] = evaluate(FRAME, [_c("unique", "id")])
        assert not r["passed"] and r["failing"] == 1 and "1 distinct" in r["detail"]

    def test_accepted_values(self):
        [r] = evaluate(FRAME, [_c("accepted_values", "status", values=["open", "closed"])])
        assert not r["passed"] and r["failing"] == 1

    def test_no_message_carries_a_value_from_the_data(self):
        """Checks run over every row, before row rules: a sample value would
        show a limited editor a row they may not see."""
        results = evaluate(FRAME, [_c("unique", "id"), _c("accepted_values", "status", values=["open"])])
        text = " ".join(r["detail"] or "" for r in results)
        assert "weird" not in text and "closed" not in text and "3]" not in text

    def test_row_count(self):
        assert not evaluate(FRAME, [_c("row_count", min=10)])[0]["passed"]
        assert not evaluate(FRAME, [_c("row_count", max=3)])[0]["passed"]
        assert evaluate(FRAME, [_c("row_count", min=1, max=10)])[0]["passed"]

    def test_row_drop_compares_with_the_last_load(self):
        [r] = evaluate(FRAME, [_c("row_drop", max_drop_pct=50)], previous_rows=10)
        assert not r["passed"] and "60%" in r["detail"]
        assert evaluate(FRAME, [_c("row_drop", max_drop_pct=50)], previous_rows=6)[0]["passed"]
        assert evaluate(FRAME, [_c("row_drop", max_drop_pct=50)], previous_rows=None)[0]["passed"]

    def test_rule(self):
        [r] = evaluate(FRAME, [_c("rule", expression="amount >= 0")])
        assert not r["passed"] and r["failing"] == 1

    def test_a_missing_column_fails_visibly(self):
        [r] = evaluate(FRAME, [_c("not_null", "gone")])
        assert not r["passed"] and "no column 'gone'" in r["detail"]

    def test_disabled_checks_do_not_run(self):
        assert evaluate(FRAME, [{**_c("not_null", "status"), "enabled": False}]) == []


def test_schema_notes():
    notes = schema_notes(FRAME, {"id": "numeric", "status": "categorical", "old": "numeric",
                                 "amount": "categorical"})
    text = " | ".join(n["detail"] for n in notes)
    assert "no longer in the data: old" in text
    assert "type changed: amount" in text
    assert all(n["severity"] == "warn" for n in notes)


@pytest.mark.parametrize("kind,column,params", [
    ("bogus", None, {}), ("not_null", None, {}), ("accepted_values", "s", {"values": []}),
    ("row_count", None, {}), ("row_count", None, {"min": 5, "max": 2}),
    ("row_drop", None, {"max_drop_pct": 0}), ("rule", None, {"expression": "__import__('os')"}),
])
def test_unusable_checks_are_refused(kind, column, params):
    with pytest.raises(InvalidCheck):
        validate_check(kind, column, params, "block")


def test_the_validator_blocks_unless_forced():
    holder = {}
    v = make_validator([_c("unique", "id")], None, {}, holder)
    with pytest.raises(ChecksBlocked):
        v(FRAME)
    assert holder["checks"][0]["passed"] is False
    make_validator([_c("unique", "id")], None, {}, holder, force=True)(FRAME)


# ── through the refresh paths ────────────────────────────────────────────────

async def _dataset(db_session, two_orgs, tmp_path, rows=10):
    org = two_orgs["a"]["org"]
    path = tmp_path / "orders.csv"
    pd.DataFrame({"id": range(rows), "status": ["open"] * rows}).to_csv(path, index=False)
    src = DataSource(name="db", type="sqlite", config={"filepath": "x.db"}, org_id=org.id)
    db_session.add(src)
    await db_session.commit()
    ds = Dataset(name="Orders", filename=str(path), org_id=org.id, row_count=rows, col_count=2,
                 data_source_id=src.id, source_table="t", refresh_interval_minutes=60,
                 created_by=two_orgs["a"]["user"].id,
                 last_refreshed_at=datetime.utcnow() - timedelta(days=1))
    db_session.add(ds)
    await db_session.commit()
    db_session.add_all([DatasetColumn(dataset_id=ds.id, name="id", dtype="numeric", stats={}),
                        DatasetColumn(dataset_id=ds.id, name="status", dtype="categorical", stats={})])
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


def _source(monkeypatch, frame):
    monkeypatch.setattr("app.services.connections.import_to_dataframe",
                        lambda cfg, table, query, params=None: frame)


async def _runs(db_session, ds):
    return (await db_session.execute(select(RefreshRun).where(
        RefreshRun.item_id == ds.id).order_by(RefreshRun.id))).scalars().all()


class TestTheScheduler:
    async def test_a_blocking_check_keeps_yesterdays_data(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import in_backoff, refresh_one
        ds = await _dataset(db_session, two_orgs, tmp_path)
        db_session.add(DataCheck(dataset_id=ds.id, org_id=ds.org_id, kind="row_drop",
                                 params={"max_drop_pct": 50}, severity="block", enabled=True))
        await db_session.commit()
        before, stamp = open(ds.filename).read(), ds.last_refreshed_at
        _source(monkeypatch, pd.DataFrame({"id": range(3), "status": ["open"] * 3}))   # 10 -> 3 rows

        await refresh_one(db_session, ds)
        await db_session.refresh(ds)

        assert open(ds.filename).read() == before
        assert ds.last_refreshed_at == stamp and ds.row_count == 10
        [run] = await _runs(db_session, ds)
        assert run.status == "blocked" and run.error_code == "checks_blocked"
        assert "70%" in run.error
        assert any(c["kind"] == "row_drop" and not c["passed"] for c in run.checks)
        assert await in_backoff(db_session, "dataset", ds.id, datetime.utcnow())
        [n] = (await db_session.execute(select(Notification))).scalars().all()
        assert "not published" in n.text and "previous data" in n.text

    async def test_a_warning_is_recorded_and_the_data_published(self, db_session, two_orgs, tmp_path, monkeypatch):
        from app.services.refresh_scheduler import refresh_one
        ds = await _dataset(db_session, two_orgs, tmp_path)
        db_session.add(DataCheck(dataset_id=ds.id, org_id=ds.org_id, kind="accepted_values",
                                 column="status", params={"values": ["open"]}, severity="warn",
                                 enabled=True))
        await db_session.commit()
        _source(monkeypatch, pd.DataFrame({"id": range(12), "status": ["open"] * 11 + ["lost"],
                                           "region": ["N"] * 12}))

        await refresh_one(db_session, ds)
        await db_session.refresh(ds)

        assert ds.row_count == 12
        [run] = await _runs(db_session, ds)
        assert run.status == "ok"
        details = " | ".join(c["detail"] or "" for c in run.checks)
        assert "outside the list" in details and "new in the data: region" in details


class TestAManualRefresh:
    async def test_blocked_then_published_anyway(self, client, db_session, two_orgs, auth_headers,
                                                 tmp_path, monkeypatch):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        db_session.add(DataCheck(dataset_id=ds.id, org_id=ds.org_id, kind="not_null",
                                 column="status", params={}, severity="block", enabled=True))
        await db_session.commit()
        before = open(ds.filename).read()
        _source(monkeypatch, pd.DataFrame({"id": range(10), "status": ["open"] * 9 + [None]}))

        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh", json={"mode": "full"},
                              headers=auth_headers["a"])
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["code"] == "checks_blocked" and "no status" in body["detail"]
        assert body["checks"][0]["passed"] is False
        assert open(ds.filename).read() == before

        r = await client.post(f"/api/v1/datasets/{ds.id}/refresh",
                              json={"mode": "full", "publish_anyway": True}, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert open(ds.filename).read() != before
        statuses = [x.status for x in await _runs(db_session, ds)]
        assert statuses == ["blocked", "ok"]

    async def test_an_incremental_append_is_checked_as_a_whole(self, tmp_path, monkeypatch):
        from app.services.dataset_refresh import refresh_dataset
        path = tmp_path / "d.csv"
        pd.DataFrame({"id": [1, 2], "ts": [1, 2]}).to_csv(path, index=False)
        monkeypatch.setattr("app.services.connections.import_to_dataframe",
                            lambda cfg, table, query, params=None: pd.DataFrame({"id": [2], "ts": [3]}))
        holder = {}
        validate = make_validator([_c("unique", "id")], 2, {}, holder)
        with pytest.raises(ChecksBlocked):
            refresh_dataset({"type": "sqlite"}, str(path), "t", None, "incremental", "ts", "2",
                            validate=validate)
        assert list(pd.read_csv(path)["id"]) == [1, 2]       # untouched


class TestTheApi:
    async def test_crud_try_and_history(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        h = auth_headers["a"]
        r = await client.post(f"/api/v1/datasets/{ds.id}/checks",
                              json={"kind": "unique", "column": "id", "severity": "block"}, headers=h)
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        r = await client.post(f"/api/v1/datasets/{ds.id}/checks",
                              json={"kind": "row_count", "params": {"min": 100}}, headers=h)
        assert r.status_code == 201

        listed = (await client.get(f"/api/v1/datasets/{ds.id}/checks", headers=h)).json()
        assert [c["kind"] for c in listed] == ["unique", "row_count"]

        tried = (await client.post(f"/api/v1/datasets/{ds.id}/checks/try", headers=h)).json()
        assert tried["rows"] == 10
        assert [x["passed"] for x in tried["results"]] == [True, False]

        r = await client.patch(f"/api/v1/datasets/{ds.id}/checks/{cid}",
                               json={"kind": "unique", "column": "id", "severity": "warn"}, headers=h)
        assert r.json()["severity"] == "warn"
        assert (await client.delete(f"/api/v1/datasets/{ds.id}/checks/{cid}", headers=h)).status_code == 204
        assert (await client.get(f"/api/v1/datasets/{ds.id}/refresh-runs", headers=h)).status_code == 200

    async def test_a_bad_check_is_refused(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        r = await client.post(f"/api/v1/datasets/{ds.id}/checks",
                              json={"kind": "not_null", "severity": "block"}, headers=auth_headers["a"])
        assert r.status_code == 400 and "column" in r.json()["detail"]

    async def test_another_org_cannot_reach_them(self, client, db_session, two_orgs, auth_headers, tmp_path):
        ds = await _dataset(db_session, two_orgs, tmp_path)
        assert (await client.get(f"/api/v1/datasets/{ds.id}/checks",
                                 headers=auth_headers["b"])).status_code == 404
        assert (await client.post(f"/api/v1/datasets/{ds.id}/checks", json={"kind": "row_count",
                "params": {"min": 1}}, headers=auth_headers["b"])).status_code == 404
