"""E06: one catalog -- what each dataset is and how current it is.

The Datasets list said "Live" for a live connection and nothing else. Now
every row says whether its rows were uploaded, copied from a connection
(and whether the refresh schedule is keeping up), built from other
datasets, or summarised from one -- naming only what the reader may see.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.models import DataSource, Dataset, DatasetShare
from app.services.catalog import catalog_entry, kind_of, origin_ids
from app.services.prep import DERIVED_FROM_KEY

from .test_prediction_models_api import _restricted_user

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def ds(**kw):
    base = dict(mode="import", aggregate_of_dataset_id=None, column_meta={}, data_source_id=None,
                source_table=None, source_query=None, query_model=None, refresh_interval_minutes=None,
                last_refreshed_at=None, created_at=NOW - timedelta(days=3))
    return SimpleNamespace(**{**base, **kw})


class TestKinds:
    def test_each_kind(self):
        assert kind_of(ds()) == "upload"
        assert kind_of(ds(data_source_id=1, source_table="sales")) == "connection"
        assert kind_of(ds(data_source_id=1, source_table="sales", mode="directquery")) == "live"
        assert kind_of(ds(column_meta={DERIVED_FROM_KEY: {"source_dataset_id": 4}})) == "derived"
        assert kind_of(ds(aggregate_of_dataset_id=4)) == "aggregate"

    def test_a_derived_dataset_names_what_it_was_built_from(self):
        assert origin_ids(ds(column_meta={DERIVED_FROM_KEY: {"source_dataset_id": 4, "join_dataset_ids": [7]}})) == [4, 7]
        assert origin_ids(ds(aggregate_of_dataset_id=9)) == [9]
        assert origin_ids(ds()) == []

    def test_scored_predictions_are_derived_from_the_dataset_scored(self):
        scored = ds(filename="scored.csv", column_meta={"__scored_by__": {"source_dataset_id": 12, "model_id": 3}})
        assert kind_of(scored) == "derived" and origin_ids(scored) == [12]


class TestFreshness:
    def conn(self, **kw):
        return ds(data_source_id=1, source_table="sales", **kw)

    def test_on_schedule_then_due_then_overdue(self):
        hourly = dict(refresh_interval_minutes=60)
        e = catalog_entry(self.conn(last_refreshed_at=NOW - timedelta(minutes=20), **hourly), now=NOW)
        assert e["freshness"] == "on_schedule" and e["next_due"] == "2026-09-26T12:40:00Z"
        assert e["as_of"] == "2026-09-26T11:40:00Z" and e["refresh_every_minutes"] == 60
        assert catalog_entry(self.conn(last_refreshed_at=NOW - timedelta(minutes=70), **hourly), now=NOW)["freshness"] == "due"
        assert catalog_entry(self.conn(last_refreshed_at=NOW - timedelta(hours=3), **hourly), now=NOW)["freshness"] == "overdue"

    def test_scheduled_but_never_refreshed_is_due(self):
        assert catalog_entry(self.conn(refresh_interval_minutes=60), now=NOW)["freshness"] == "due"

    def test_a_copy_without_a_schedule_is_manual_as_of_its_last_refresh(self):
        e = catalog_entry(self.conn(last_refreshed_at=NOW - timedelta(days=1)), now=NOW)
        assert e["freshness"] == "manual" and e["as_of"] == "2026-09-25T12:00:00Z" and e["next_due"] is None

    def test_live_is_always_current_and_has_no_as_of(self):
        e = catalog_entry(self.conn(mode="directquery", last_refreshed_at=NOW), now=NOW)
        assert e["freshness"] == "live" and e["as_of"] is None

    def test_an_upload_is_fixed_as_of_when_it_arrived(self):
        e = catalog_entry(ds(), now=NOW)
        assert e == {"kind": "upload", "freshness": "fixed", "as_of": "2026-09-23T12:00:00Z",
                     "next_due": None, "refresh_every_minutes": None}

    def test_naive_timestamps_are_utc(self):
        e = catalog_entry(self.conn(last_refreshed_at=datetime(2026, 9, 26, 11, 30), refresh_interval_minutes=60), now=NOW)
        assert e["freshness"] == "on_schedule"


class TestTheList:
    async def _list(self, client, headers):
        r = await client.get("/api/v1/datasets", headers=headers)
        assert r.status_code == 200, r.text
        return {d["name"]: d["catalog"] for d in r.json()}

    async def test_every_row_says_what_it_is(self, client, auth_headers, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        src = DataSource(name="Warehouse", type="postgresql", config={}, org_id=org.id)
        db_session.add(src)
        await db_session.flush()
        base = Dataset(name="Sales upload", filename="x.csv", org_id=org.id)
        db_session.add(base)
        await db_session.flush()
        db_session.add_all([
            Dataset(name="Orders copy", org_id=org.id, data_source_id=src.id, source_table="orders",
                    refresh_interval_minutes=60, last_refreshed_at=datetime.utcnow() - timedelta(minutes=5)),
            Dataset(name="Orders live", org_id=org.id, data_source_id=src.id, source_table="orders", mode="directquery"),
            Dataset(name="Sales by region", org_id=org.id, filename="y.csv",
                    column_meta={DERIVED_FROM_KEY: {"source_dataset_id": base.id, "steps": []}}),
        ])
        await db_session.commit()
        got = await self._list(client, auth_headers["a"])
        assert got["Sales upload"]["kind"] == "upload" and got["Sales upload"]["freshness"] == "fixed"
        assert got["Orders copy"] | {"as_of": None, "next_due": None} == {
            "kind": "connection", "freshness": "on_schedule", "source": "Warehouse", "refresh_every_minutes": 60,
            "as_of": None, "next_due": None}
        assert got["Orders live"]["kind"] == "live" and got["Orders live"]["source"] == "Warehouse"
        assert got["Sales by region"]["kind"] == "derived" and got["Sales by region"]["built_from"] == ["Sales upload"]

    async def test_a_source_the_reader_cannot_open_is_not_named(self, client, db_session, two_orgs):
        org, admin = two_orgs["a"]["org"], two_orgs["a"]["user"]
        secret = Dataset(name="Payroll 2026", filename="p.csv", org_id=org.id, created_by=admin.id)
        db_session.add(secret)
        await db_session.flush()
        derived = Dataset(name="Headcount", filename="h.csv", org_id=org.id, created_by=admin.id,
                          column_meta={DERIVED_FROM_KEY: {"source_dataset_id": secret.id, "steps": []}})
        db_session.add(derived)
        await db_session.commit()
        headers = await _restricted_user(db_session, org, derived, email="member-cat@example.com")
        from sqlalchemy import select
        from app.models.models import User
        member = (await db_session.execute(select(User).where(User.email == "member-cat@example.com"))).scalar_one()
        db_session.add(DatasetShare(dataset_id=derived.id, user_id=member.id))
        await db_session.commit()
        got = await self._list(client, headers)
        assert "Payroll 2026" not in got
        assert got["Headcount"]["built_from"] == ["another dataset"]
        assert "Payroll" not in str(got)
