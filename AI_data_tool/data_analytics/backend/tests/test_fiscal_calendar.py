"""E10 calendar choices: charts grouped by fiscal year and fiscal quarter.

An org whose year runs July to June reads FY2025/26, not half of 2025 and half
of 2026. The start month is the org's (Admin -> Calendar); a widget may name
its own. The labels sort as text; a clicked bucket filters the page to it.
"""
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.models import AuditLogEntry, Dataset, DatasetColumn, Organization
from app.services.fiscal import fiscal_label, with_fiscal_start
from app.services.widget_roles import VOCABULARIES

from .test_prediction_models_api import _restricted_user

DATES = ["2024-06-30", "2024-07-01", "2024-12-31", "2025-01-15", "2025-06-30", "2025-07-01", None]


class TestLabels:
    def test_a_july_year_is_named_by_both_calendar_years(self):
        s = pd.Series(pd.to_datetime(DATES))
        assert list(fiscal_label(s, "fiscal_year", 7).fillna("-")) == [
            "FY2023/24", "FY2024/25", "FY2024/25", "FY2024/25", "FY2024/25", "FY2025/26", "-"]

    def test_quarters_count_from_the_first_month(self):
        s = pd.Series(pd.to_datetime(["2024-07-01", "2024-09-30", "2024-10-01", "2025-01-01", "2025-06-30"]))
        assert list(fiscal_label(s, "fiscal_quarter", 7)) == [
            "FY2024/25-Q1", "FY2024/25-Q1", "FY2024/25-Q2", "FY2024/25-Q3", "FY2024/25-Q4"]

    def test_an_october_year(self):
        s = pd.Series(pd.to_datetime(["2025-09-30", "2025-10-01", "2025-12-31"]))
        assert list(fiscal_label(s, "fiscal_quarter", 10)) == ["FY2024/25-Q4", "FY2025/26-Q1", "FY2025/26-Q1"]

    def test_a_january_year_is_the_calendar_year(self):
        s = pd.Series(pd.to_datetime(["2024-12-31", "2025-01-01", "2025-04-01"]))
        assert list(fiscal_label(s, "fiscal_year", 1)) == ["FY2024", "FY2025", "FY2025"]
        assert list(fiscal_label(s, "fiscal_quarter", 1)) == ["FY2024-Q4", "FY2025-Q1", "FY2025-Q2"]

    def test_the_century_turns(self):
        s = pd.Series(pd.to_datetime(["2099-08-01"]))
        assert list(fiscal_label(s, "fiscal_year", 7)) == ["FY2099/00"]

    def test_labels_sort_in_time_order(self):
        s = pd.Series(pd.date_range("2023-01-01", "2026-12-31", freq="MS"))
        labels = list(dict.fromkeys(fiscal_label(s, "fiscal_quarter", 4)))
        assert labels == sorted(labels)


class TestCarryingTheStartMonth:
    def test_the_widget_s_own_month_wins_over_the_org_s(self):
        out = with_fiscal_start({"dimension_granularity": "fiscal_year", "fiscal_start_month": 4}, 7)
        assert out["dimension_granularity"] == "fiscal_year@4"

    def test_the_org_month_otherwise_and_on_drill_filters_too(self):
        cfg = {"dimension_granularity": "fiscal_quarter",
               "filters": [{"column": "d", "value": "FY2024/25-Q1", "granularity": "fiscal_quarter"},
                           {"column": "r", "value": "x"}]}
        out = with_fiscal_start(cfg, 7)
        assert out["dimension_granularity"] == "fiscal_quarter@7"
        assert out["filters"][0]["granularity"] == "fiscal_quarter@7"
        assert out["filters"][1] == {"column": "r", "value": "x"}
        assert cfg["dimension_granularity"] == "fiscal_quarter"          # not mutated

    def test_nothing_fiscal_is_returned_as_it_came(self):
        cfg = {"dimension_granularity": "month", "filters": []}
        assert with_fiscal_start(cfg, 7) is cfg


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"date": ["2024-06-30", "2024-07-01", "2024-12-31", "2025-01-15", "2025-06-30", "2025-07-01"],
                  "region": ["N", "N", "S", "S", "N", "S"],
                  "sales": [1, 10, 100, 1000, 10000, 100000]}).to_csv(p, index=False)
    return str(p)


async def _ds(db, org, path):
    ds = Dataset(name="Sales", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("date", "datetime"), ("region", "categorical"), ("sales", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _bars(client, headers, ds_id, **cfg):
    r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", headers=headers, json={
        "widget_type": "bar", "config": {"dimension": "date", "measure": "sales", "aggregation": "sum", **cfg}})
    assert r.status_code == 200, r.text
    return {row["name"]: row["value"] for row in r.json()["rows"]}


class TestTheSetting:
    async def test_january_until_an_admin_says_otherwise(self, client, auth_headers):
        r = await client.get("/api/v1/calendar-settings", headers=auth_headers["a"])
        assert r.status_code == 200 and r.json() == {"fiscal_year_start_month": 1}

    async def test_an_admin_sets_it_and_it_is_audited(self, client, auth_headers, db_session, two_orgs):
        r = await client.put("/api/v1/calendar-settings", headers=auth_headers["a"],
                             json={"fiscal_year_start_month": 7})
        assert r.status_code == 200 and r.json() == {"fiscal_year_start_month": 7}
        entry = (await db_session.execute(select(AuditLogEntry).where(
            AuditLogEntry.action == "calendar.fiscal_year"))).scalar_one()
        assert "month 7 (was 1)" in entry.detail
        # The other org is untouched.
        r = await client.get("/api/v1/calendar-settings", headers=auth_headers["b"])
        assert r.json() == {"fiscal_year_start_month": 1}

    @pytest.mark.parametrize("bad", [0, 13, "7", 7.5, True, None])
    async def test_only_a_month_number(self, client, auth_headers, bad):
        r = await client.put("/api/v1/calendar-settings", headers=auth_headers["a"],
                             json={"fiscal_year_start_month": bad})
        assert r.status_code == 400

    async def test_a_member_reads_it_but_cannot_set_it(self, client, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        headers = await _restricted_user(db_session, two_orgs["a"]["org"], ds, email="member@example.com")
        assert (await client.get("/api/v1/calendar-settings", headers=headers)).status_code == 200
        r = await client.put("/api/v1/calendar-settings", headers=headers, json={"fiscal_year_start_month": 4})
        assert r.status_code == 403


class TestCharts:
    @pytest.fixture(params=[True, False], ids=["duckdb-on", "duckdb-off"])
    def engine(self, request, monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param)
        return request.param

    async def test_bars_by_the_org_s_fiscal_year(self, client, auth_headers, db_session, two_orgs, salesfile, engine):
        org = two_orgs["a"]["org"]
        org.fiscal_year_start_month = 7
        await db_session.commit()
        ds = await _ds(db_session, org, salesfile)
        assert await _bars(client, auth_headers["a"], ds.id, dimension_granularity="fiscal_year") == {
            "FY2023/24": 1, "FY2024/25": 11110, "FY2025/26": 100000}
        assert await _bars(client, auth_headers["a"], ds.id, dimension_granularity="fiscal_quarter") == {
            "FY2023/24-Q4": 1, "FY2024/25-Q1": 10, "FY2024/25-Q2": 100, "FY2024/25-Q3": 1000,
            "FY2024/25-Q4": 10000, "FY2025/26-Q1": 100000}

    async def test_a_widget_may_name_its_own_start(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        assert await _bars(client, auth_headers["a"], ds.id, dimension_granularity="fiscal_year",
                           fiscal_start_month=1) == {"FY2024": 111, "FY2025": 111000}

    async def test_a_clicked_bucket_filters_to_its_rows(self, client, auth_headers, db_session, two_orgs, salesfile):
        org = two_orgs["a"]["org"]
        org.fiscal_year_start_month = 7
        await db_session.commit()
        ds = await _ds(db_session, org, salesfile)
        got = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", headers=auth_headers["a"], json={
            "widget_type": "bar", "config": {
                "dimension": "region", "measure": "sales", "aggregation": "sum",
                "filters": [{"column": "date", "op": "eq", "value": "FY2024/25",
                             "granularity": "fiscal_year"}]}})
        assert got.status_code == 200, got.text
        assert {r["name"]: r["value"] for r in got.json()["rows"]} == {"N": 10010, "S": 1100}

    async def test_changing_the_org_setting_moves_the_chart(self, client, auth_headers, db_session, two_orgs, salesfile):
        ds = await _ds(db_session, two_orgs["a"]["org"], salesfile)
        before = await _bars(client, auth_headers["a"], ds.id, dimension_granularity="fiscal_year")
        assert before == {"FY2024": 111, "FY2025": 111000}
        await client.put("/api/v1/calendar-settings", headers=auth_headers["a"], json={"fiscal_year_start_month": 7})
        # The start month rides on the granularity, so the cached result of
        # the January chart is not served for the July one.
        after = await _bars(client, auth_headers["a"], ds.id, dimension_granularity="fiscal_year")
        assert after == {"FY2023/24": 1, "FY2024/25": 11110, "FY2025/26": 100000}

    def test_the_saved_config_vocabulary_knows_the_new_values(self):
        assert {"fiscal_year", "fiscal_quarter"} <= VOCABULARIES["dimension_granularity"]


async def test_a_live_connection_groups_by_fiscal_year_too(client, auth_headers, db_session, two_orgs, tmp_path):
    """DirectQuery: a date grouping fetches the rows and buckets them like an
    import, so the org's fiscal year reaches a live source as well."""
    import sqlite3
    from app.models.models import DataSource
    from app.services.widget_data import clear_widget_data_cache
    clear_widget_data_cache()
    path = tmp_path / "live.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE sales (date TEXT, sales REAL)")
    conn.executemany("INSERT INTO sales VALUES (?, ?)",
                     [("2024-06-30", 1), ("2024-07-01", 10), ("2025-06-30", 100), ("2025-07-01", 1000)])
    conn.commit()
    conn.close()
    org = two_orgs["a"]["org"]
    org.fiscal_year_start_month = 7
    src = DataSource(name="Live", type="sqlite", config={"filepath": str(path)}, org_id=org.id)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="Live sales", org_id=org.id, mode="directquery", data_source_id=src.id, source_table="sales")
    db_session.add(ds)
    await db_session.flush()
    for c in ("date", "sales"):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="string"))
    await db_session.commit()
    assert await _bars(client, auth_headers["a"], ds.id, dimension_granularity="fiscal_year") == {
        "FY2023/24": 1, "FY2024/25": 110, "FY2025/26": 1000}
    clear_widget_data_cache()
