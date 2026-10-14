"""Top N + "All Other": a chart over a text column with thousands of values
draws its largest N and one slice for the rest -- not up to 10,000 marks.

The residual is the chart's own aggregation over the hidden values' RAW rows
(an average of averages would be a different number), on every engine; on a
live source it is computed in SQL, not by fetching every row.
"""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.models.models import DataSource, Dataset, DatasetColumn
from app.services import auto_bin
from app.services.auto_bin import Stats
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clean():
    clear_widget_data_cache(); auto_bin.clear_stats_cache()
    yield
    clear_widget_data_cache(); auto_bin.clear_stats_cache()


def test_plan_only_when_the_rest_is_more_than_one_value():
    assert auto_bin.plan_bins({"dimension": "p"}, "donut", "text", Stats(None, None, 11)).top_n is None
    assert auto_bin.plan_bins({"dimension": "p"}, "donut", "text", Stats(None, None, 12)).top_n == 10
    assert auto_bin.plan_bins({"dimension": "p", "top_n": 50}, "donut", "text", Stats(None, None, 900)).top_n == 50
    assert auto_bin.plan_bins({"dimension": "p", "top_n": 7}, "bar", "text", Stats(None, None, 900)).top_n == 20


def test_text_is_not_ranked_on_a_line():
    assert not auto_bin.wants_bins({"dimension": "p"}, "line", "text")
    assert auto_bin.wants_bins({"dimension": "p"}, "donut", "text")


@pytest.fixture
def sales(tmp_path):
    rng = np.random.default_rng(11)
    n = 5000
    products = [f"p{i:04d}" for i in range(400)]
    weights = np.linspace(40, 1, 400); weights /= weights.sum()
    df = pd.DataFrame({"product": rng.choice(products, n, p=weights),
                       "amount": np.round(rng.uniform(1, 100, n), 2)})
    csv = tmp_path / "s.csv"; df.to_csv(csv, index=False)
    db = tmp_path / "s.db"; c = sqlite3.connect(str(db)); df.to_sql("sales", c, index=False); c.close()
    return df, str(csv), str(db)


COLS = (("product", "categorical"), ("amount", "numeric"))


async def _ds(db, org, mode, path):
    if mode == "live":
        src = DataSource(name="live", type="sqlite", config={"filepath": path}, org_id=org.id)
        db.add(src); await db.flush()
        ds = Dataset(name="s", org_id=org.id, mode="directquery", data_source_id=src.id, source_table="sales")
    else:
        ds = Dataset(name="s", filename=path, org_id=org.id, mode="import")
    db.add(ds); await db.flush()
    for c, t in COLS:
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _post(client, headers, ds_id, wt, cfg):
    r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", headers=headers["a"],
                          json={"widget_type": wt, "config": cfg})
    assert r.status_code == 200, r.text
    return r.json()


def _expected(df, agg, n):
    g = df.groupby("product")["amount"]
    vals = {"sum": g.sum(), "avg": g.mean(), "max": g.max(), "count": g.size()}[agg]
    top = vals.sort_values(ascending=False).head(n)
    rest = df[~df["product"].isin(top.index)]["amount"]
    other = {"sum": rest.sum(), "avg": rest.mean(), "max": rest.max(), "count": len(rest)}[agg]
    return top, other


@pytest.mark.parametrize("mode", ["import", "live"])
@pytest.mark.parametrize("agg", ["sum", "avg", "max", "count"])
async def test_donut_shows_top_ten_and_the_true_rest(client, db_session, two_orgs, auth_headers, sales, mode, agg, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    df, csv, db = sales
    ds = await _ds(db_session, two_orgs["a"]["org"], mode, db if mode == "live" else csv)
    cfg = {"dimension": "product", **({"measure": "amount", "aggregation": agg} if agg != "count" else {})}
    out = await _post(client, auth_headers, ds.id, "donut", cfg)
    top, other = _expected(df, agg, 10)
    rows = out["rows"]
    assert rows[-1]["name"] == "All Other" and rows[-1].get("other") is True
    assert {r["name"] for r in rows[:-1]} >= set(top.index[:9])        # ties at the boundary may add one
    assert rows[-1]["value"] == pytest.approx(other if len(rows) == 11 else rows[-1]["value"], rel=1e-9)
    assert out["binning"]["top_n"] == 10 and out["binning"]["distinct"] == df["product"].nunique()
    if agg in ("sum", "count"):
        assert sum(r["value"] for r in rows) == pytest.approx(df["amount"].sum() if agg == "sum" else len(df))


@pytest.mark.parametrize("mode", ["import", "live"])
async def test_the_reader_can_ask_for_fifty(client, db_session, two_orgs, auth_headers, sales, mode):
    df, csv, db = sales
    ds = await _ds(db_session, two_orgs["a"]["org"], mode, db if mode == "live" else csv)
    out = await _post(client, auth_headers, ds.id, "bar",
                      {"dimension": "product", "measure": "amount", "aggregation": "sum", "top_n": 50})
    assert 51 <= len(out["rows"]) <= 52 and out["rows"][-1]["name"] == "All Other"


async def test_a_live_top_n_never_fetches_the_rows(client, db_session, two_orgs, auth_headers, sales, monkeypatch):
    from app.services import direct_query
    fetched = []
    real = direct_query._fetch_and_compute
    monkeypatch.setattr(direct_query, "_fetch_and_compute", lambda *a, **k: fetched.append(1) or real(*a, **k))
    df, _, db = sales
    ds = await _ds(db_session, two_orgs["a"]["org"], "live", db)
    await _post(client, auth_headers, ds.id, "donut", {"dimension": "product", "measure": "amount", "aggregation": "sum"})
    assert not fetched


@pytest.mark.parametrize("mode", ["import", "live"])
async def test_few_values_are_left_alone(client, db_session, two_orgs, auth_headers, tmp_path, mode):
    df = pd.DataFrame({"product": list("abcde") * 20, "amount": 1.0})
    csv = tmp_path / "f.csv"; df.to_csv(csv, index=False)
    db = tmp_path / "f.db"; c = sqlite3.connect(str(db)); df.to_sql("sales", c, index=False); c.close()
    ds = await _ds(db_session, two_orgs["a"]["org"], mode, str(db) if mode == "live" else str(csv))
    out = await _post(client, auth_headers, ds.id, "donut", {"dimension": "product", "measure": "amount"})
    assert len(out["rows"]) == 5 and not out["binning"]["grouped"]
