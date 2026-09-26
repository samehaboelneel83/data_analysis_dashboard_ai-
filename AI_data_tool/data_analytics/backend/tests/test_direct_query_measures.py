"""E04: named measures on DirectQuery.

The goldens in test_numeric_goldens.py prove the NUMBERS agree with import
mode. These pin HOW they are produced: which measures the source computes as
SQL and which fetch the rows, that row and column security still hold, and
what the translator writes.
"""
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services import direct_query as dq
from app.services import widget_data as wd
from app.services.measure_sql import MeasureNotTranslatable, measure_to_sql

COLS = ["region", "customer", "revenue", "profit", "units"]
ROWS = [
    ("North", "c1", 100.0, 20.0, 1.0),
    ("North", "c2", 200.0, 20.0, 3.0),
    ("South", "c1", 50.0, 5.0, 4.0),
    ("East", "c5", 0.0, 0.0, 2.0),
]
MEASURES = [
    {"name": "Margin", "expression": "SUM(profit) / SUM(revenue) * 100"},
    {"name": "Share", "expression": "SUM(revenue) / TOTAL(SUM(revenue)) * 100"},
]
KNOWN = set(COLS)


@pytest.fixture(autouse=True)
def _clean():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


@pytest.fixture
def src(tmp_path):
    db = tmp_path / "m.db"
    con = sqlite3.connect(db)
    pd.DataFrame(ROWS, columns=COLS).to_sql("sales", con, index=False)
    con.close()
    return ({"type": "sqlite", "filepath": str(db)},
            SimpleNamespace(source_table="sales", source_query=None,
                            columns=[SimpleNamespace(name=c, dtype="string") for c in COLS]))


def _values(result):
    return {r["name"]: r["value"] for r in result["rows"]}


# ── The translator ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr,sql", [
    ("SUM(profit) / SUM(revenue) * 100",
     '((1.0 * COALESCE(SUM("profit"), 0) / NULLIF(COALESCE(SUM("revenue"), 0), 0)) * 100)'),
    ("COUNTD(customer)", 'COUNT(DISTINCT "customer")'),
    ("AVG(revenue - profit)", 'AVG(1.0 * ("revenue" - "profit"))'),
    ("SUM(IF(region == \"It's\", revenue, 0))",
     """COALESCE(SUM((CASE WHEN ("region" = 'It''s') THEN "revenue" ELSE 0 END)), 0)"""),
    ("COUNT(revenue) - COUNT(profit)", '(COUNT("revenue") - COUNT("profit"))'),
    ("SUM(revenue) if False else 0", None),
])
def test_what_the_translator_writes(expr, sql):
    if sql is None:
        with pytest.raises(MeasureNotTranslatable):
            measure_to_sql(expr, KNOWN, "sqlite")
        return
    got, cols = measure_to_sql(expr, KNOWN, "sqlite")
    assert got == sql
    assert cols <= KNOWN


@pytest.mark.parametrize("expr", [
    "SUM(revenue) / TOTAL(SUM(revenue))",          # a context function
    "CALC(SUM(revenue), \"region == 'North'\")",
    "revenue",                                      # a column outside an aggregate
    "SUM(SUM(revenue))",                            # nested aggregates
    "SUM(nope)",                                    # not a column
    "SUM(revenue) % 7",                             # an operator SQL spells differently
    "MEDIAN(revenue)",                              # no MEDIAN on SQLite
    "SUM(revenue) ** 2",
])
def test_what_the_translator_refuses_rather_than_approximates(expr):
    with pytest.raises(MeasureNotTranslatable):
        measure_to_sql(expr, KNOWN, "sqlite")


def test_median_is_written_where_the_dialect_has_it():
    sql, _ = measure_to_sql("MEDIAN(revenue)", KNOWN, "postgresql")
    assert sql == 'PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY "revenue")'


def test_a_quote_in_a_string_literal_cannot_end_it():
    sql, _ = measure_to_sql("SUM(IF(region == \"x' OR 1=1 --\", revenue, 0))", KNOWN, "sqlite")
    assert "'x'' OR 1=1 --'" in sql


# ── Which path answers ───────────────────────────────────────────────────────

def test_a_translatable_measure_is_computed_by_the_source(src, monkeypatch):
    cfg, ds = src
    monkeypatch.setattr(dq, "_fetch_and_compute", lambda *a, **k: pytest.fail("rows were fetched"))
    r = dq.run_direct_query(cfg, ds, {"dimension": "region", "measure": "Margin", "show_totals": True},
                            widget_type="bar", cache_ttl_seconds=0, measures=MEASURES)
    assert _values(r) == {"North": pytest.approx(40 / 3), "South": pytest.approx(10), "East": None}
    assert r["totals"][1] == pytest.approx(45 / 350 * 100)


def test_a_kpi_of_a_measure_is_one_sql_value(src, monkeypatch):
    cfg, ds = src
    monkeypatch.setattr(dq, "_fetch_and_compute", lambda *a, **k: pytest.fail("rows were fetched"))
    r = dq.run_direct_query(cfg, ds, {"measure": "Margin"}, widget_type="kpi",
                            cache_ttl_seconds=0, measures=MEASURES)
    assert r["rows"][0]["value"] == pytest.approx(45 / 350 * 100)
    assert r["total"] == 4


def test_a_measure_sql_cannot_express_fetches_the_rows_and_says_how_many(src, monkeypatch):
    cfg, ds = src
    called = {}
    real = dq._fetch_and_compute

    def spy(*a, **k):
        called["yes"] = True
        return real(*a, **k)

    monkeypatch.setattr(dq, "_fetch_and_compute", spy)
    r = dq.run_direct_query(cfg, ds, {"dimension": "region", "measure": "Share"},
                            widget_type="bar", cache_ttl_seconds=0, measures=MEASURES)
    assert called and _values(r)["North"] == pytest.approx(300 / 350 * 100)
    assert r["sampled"] is False


def test_row_security_narrows_the_measure_query(src):
    cfg, ds = src
    r = dq.run_direct_query(cfg, ds, {"dimension": "region", "measure": "Margin", "show_totals": True},
                            widget_type="bar", cache_ttl_seconds=0, measures=MEASURES,
                            rls_filter_expr="region == 'North'")
    assert _values(r) == {"North": pytest.approx(40 / 3)}
    assert r["totals"][1] == pytest.approx(40 / 3)


def test_an_edited_measure_is_not_served_its_old_result(src):
    cfg, ds = src
    a = dq.run_direct_query(cfg, ds, {"measure": "Margin"}, widget_type="kpi",
                            cache_ttl_seconds=60, measures=MEASURES)
    edited = [{"name": "Margin", "expression": "SUM(profit)"}]
    b = dq.run_direct_query(cfg, ds, {"measure": "Margin"}, widget_type="kpi",
                            cache_ttl_seconds=60, measures=edited)
    assert a["rows"][0]["value"] != b["rows"][0]["value"] == pytest.approx(45)


# ── Column security through the route ────────────────────────────────────────

async def test_a_measure_over_a_denied_column_is_refused(client, db_session, two_orgs, tmp_path):
    from app.core.security import create_access_token, hash_password
    from app.models.models import (ColumnSecurityRule, DataSource, Dataset, DatasetColumn,
                                   DatasetShare, Role, User)
    org = two_orgs["a"]["org"].id
    db = tmp_path / "dq.db"
    con = sqlite3.connect(db)
    pd.DataFrame(ROWS, columns=COLS).to_sql("sales", con, index=False)
    con.close()
    src = DataSource(name="dq", type="sqlite", config={"filepath": str(db)}, org_id=org)
    role = Role(org_id=org, name="no-profit", is_org_admin=False)
    db_session.add_all([src, role])
    await db_session.flush()
    ds = Dataset(name="dq", org_id=org, mode="directquery", data_source_id=src.id,
                 source_table="sales", measures=MEASURES)
    user = User(org_id=org, role_id=role.id, email="np@example.com", password_hash=hash_password("pw"))
    db_session.add_all([ds, user])
    await db_session.flush()
    for c in COLS:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="string"))
    db_session.add_all([ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["profit"]),
                        DatasetShare(dataset_id=ds.id, user_id=user.id)])
    await db_session.commit()
    h = {"Authorization": f"Bearer {create_access_token(user.id, org)}"}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "kpi", "config": {"measure": "Margin"}}, headers=h)
    assert r.status_code == 403, r.text
    ok = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                           json={"widget_type": "kpi", "config": {"measure": "Share"}}, headers=h)
    assert ok.status_code == 200, ok.text
