"""Auto-bin: a chart with too many values draws buckets, not thousands of marks.

Dashboard 213 (2026-09-29) drew a donut of 5,670 price slices and shipped up to
10,000 groups per chart; the browser was the bottleneck. These pin that:
  * the bucket count never exceeds the chart's target,
  * no row is lost -- the total over the buckets equals the total over the raw
    values, on every engine (DuckDB, pandas, a live SQL source),
  * a zoom window (`bin_range`) reads only its rows and picks a finer grain,
  * the author's own grain, and `auto_bin: false`, are left alone.
"""
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.models.models import DataSource, Dataset, DatasetColumn
from app.services import auto_bin
from app.services.auto_bin import BinPlan, Stats
from app.services.widget_data import clear_widget_data_cache, shape_series


@pytest.fixture(autouse=True)
def _clean():
    clear_widget_data_cache()
    auto_bin.clear_stats_cache()
    yield
    clear_widget_data_cache()
    auto_bin.clear_stats_cache()


# ── units ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,nice", [(47.3, 50), (0.13, 0.2), (2.2, 2.5), (1, 1), (7, 10), (472.5, 500)])
def test_nice_width(raw, nice):
    assert auto_bin.nice_width(raw) == pytest.approx(nice)


@pytest.mark.parametrize("days,target,grain", [
    (2, 150, "hour"), (100, 150, "day"), (730, 150, "week"), (730, 12, "quarter"), (3650, 12, "year"),
])
def test_choose_grain_is_the_finest_that_fits(days, target, grain):
    lo = datetime(2020, 1, 1)
    assert auto_bin.choose_grain(lo, lo + pd.Timedelta(days=days).to_pytimedelta(), target) == grain


def test_numbers_fit_the_target():
    p = auto_bin.plan_bins({"dimension": "price"}, "donut", "number", Stats(0.85, 6735.0, 5670))
    # 500 would need 14 ranges for 0..6735, so the next nice width is used.
    assert p.grouped and p.width == 1000 and p.origin == 0
    assert np.floor(6735 / p.width) - np.floor(0.85 / p.width) + 1 <= 12


def test_few_values_are_not_grouped():
    p = auto_bin.plan_bins({"dimension": "status"}, "bar", "number", Stats(1, 7, 7))
    assert not p.grouped


@pytest.mark.parametrize("cfg", [
    {"dimension": "d", "dimension_granularity": "month"},   # the author chose
    {"dimension": "d", "auto_bin": False},                  # switched off
    {"dimension": "d", "rank": {"mode": "top", "n": 5}},
    {"dimension": "d", "dimension2": "e"},
    {},
])
def test_authors_choice_is_never_rebinned(cfg):
    assert not auto_bin.wants_bins(cfg, "line")


def test_auto_granularity_counts_as_unset():
    assert auto_bin.wants_bins({"dimension": "d", "dimension_granularity": "auto"}, "line")
    assert "dimension_granularity" not in auto_bin.strip_keys({"dimension_granularity": "auto"})


@pytest.mark.parametrize("label,grain,start", [
    ("2024", "year", datetime(2024, 1, 1)), ("2024-Q3", "quarter", datetime(2024, 7, 1)),
    ("2024-05", "month", datetime(2024, 5, 1)), ("2026-W01", "week", datetime(2025, 12, 29)),
    ("2024-05-06", "day", datetime(2024, 5, 6)), ("2024-05-06 13:00", "hour", datetime(2024, 5, 6, 13)),
])
def test_labels_round_trip(label, grain, start):
    assert auto_bin.grain_start(label, grain) == start
    assert auto_bin.grain_label(start, grain) == label


def test_quarter_end_rolls_the_year():
    assert auto_bin.grain_end(datetime(2024, 10, 1), "quarter") == datetime(2025, 1, 1)


def test_bad_windows_are_ignored():
    assert auto_bin.parse_window({"bin_range": {"start": 5, "end": 1}}, "number") is None
    assert auto_bin.parse_window({"bin_range": {"start": "x", "end": "y"}}, "date") is None
    assert auto_bin.parse_window({"bin_range": {"start": 1, "end": 5}}, "number") == (1.0, 5.0)


def test_finish_labels_ranges_and_restores_the_column():
    plan = BinPlan(column="price", kind="number", target=12, distinct=99, width=500.0, origin=0.0)
    out = auto_bin.finish({"dimension": auto_bin.BIN_COL, "rows": [{"name": 500.0, "value": 3}]}, plan)
    assert out["dimension"] == "price"
    assert out["rows"] == [{"name": "500 – 1,000", "value": 3, "bin_start": 500.0, "bin_end": 1000.0}]
    assert out["binning"]["grouped"] and out["binning"]["width"] == 500.0


def test_shape_series_number_ranges_keep_every_row():
    df = pd.DataFrame({"price": np.arange(0, 1000, 0.5), "qty": 1})
    out = shape_series(df, {"dimension": "price", "measure": "qty", "aggregation": "sum",
                            "dimension_bin": {"width": 100, "origin": 0}})
    assert [r["name"] for r in out["rows"]] == [float(x) for x in range(0, 1000, 100)]
    assert sum(r["value"] for r in out["rows"]) == len(df)


# ── uploaded file, through the endpoint ────────────────────────────────────

@pytest.fixture
def ordersfile(tmp_path):
    rng = np.random.default_rng(7)
    n = 3000
    days = pd.date_range("2022-01-01", "2023-12-31", freq="D")
    df = pd.DataFrame({
        "d": rng.choice(days, n),
        "price": np.round(rng.uniform(0.5, 6000, n), 2),
        "status": rng.choice(["a", "b", "c"], n),
        "qty": rng.integers(1, 5, n),
    })
    p = tmp_path / "orders.csv"
    df.to_csv(p, index=False)
    return str(p), df


async def _import_ds(db, org, path):
    ds = Dataset(name="Orders", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c, t in (("d", "datetime"), ("price", "numeric"), ("status", "categorical"), ("qty", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _post(client, headers, ds_id, wt, cfg):
    r = await client.post(f"/api/v1/datasets/{ds_id}/widget-data", headers=headers["a"],
                          json={"widget_type": wt, "config": cfg})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(params=[True, False], ids=["duckdb-on", "duckdb-off"])
def engine(request, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", request.param)


class TestImport:
    async def test_donut_over_prices_draws_ranges_not_thousands(self, client, db_session, two_orgs, auth_headers, ordersfile, engine):
        path, df = ordersfile
        ds = await _import_ds(db_session, two_orgs["a"]["org"], path)
        out = await _post(client, auth_headers, ds.id, "donut",
                          {"dimension": "price", "measure": "qty", "aggregation": "sum"})
        assert 2 <= len(out["rows"]) <= 12
        assert out["binning"]["grouped"] and out["binning"]["distinct"] > 12
        assert sum(r["value"] for r in out["rows"]) == int(df["qty"].sum())
        assert all("–" in r["name"] and r["bin_end"] > r["bin_start"] for r in out["rows"])
        assert out["dimension"] == "price"

    async def test_line_over_two_years_of_days_is_weekly(self, client, db_session, two_orgs, auth_headers, ordersfile, engine):
        path, df = ordersfile
        ds = await _import_ds(db_session, two_orgs["a"]["org"], path)
        out = await _post(client, auth_headers, ds.id, "line",
                          {"dimension": "d", "measure": "qty", "aggregation": "sum"})
        assert out["binning"]["grain"] == "week"
        assert len(out["rows"]) <= 150
        assert sum(r["value"] for r in out["rows"]) == int(df["qty"].sum())
        names = [r["name"] for r in out["rows"]]
        assert names == sorted(names)            # time order

    async def test_zooming_in_reads_the_window_at_a_finer_grain(self, client, db_session, two_orgs, auth_headers, ordersfile, engine):
        path, df = ordersfile
        ds = await _import_ds(db_session, two_orgs["a"]["org"], path)
        out = await _post(client, auth_headers, ds.id, "line",
                          {"dimension": "d", "measure": "qty", "aggregation": "sum",
                           "bin_range": {"start": "2023-03-01", "end": "2023-04-01"}})
        in_window = df[(df["d"] >= "2023-03-01") & (df["d"] < "2023-04-01")]
        assert sum(r["value"] for r in out["rows"]) == int(in_window["qty"].sum())
        # 31 days fits a 150-point line: the raw days, no grouping needed.
        assert not out["binning"]["grouped"] and out["binning"]["finest"]
        assert out["binning"]["window"][0].startswith("2023-03-01")

    async def test_the_authors_grain_wins(self, client, db_session, two_orgs, auth_headers, ordersfile, engine):
        path, _ = ordersfile
        ds = await _import_ds(db_session, two_orgs["a"]["org"], path)
        out = await _post(client, auth_headers, ds.id, "line",
                          {"dimension": "d", "measure": "qty", "aggregation": "sum", "dimension_granularity": "month"})
        assert "binning" not in out and len(out["rows"]) == 24

    async def test_switched_off(self, client, db_session, two_orgs, auth_headers, ordersfile, engine):
        path, df = ordersfile
        ds = await _import_ds(db_session, two_orgs["a"]["org"], path)
        out = await _post(client, auth_headers, ds.id, "bar",
                          {"dimension": "price", "measure": "qty", "aggregation": "sum", "auto_bin": False})
        assert "binning" not in out and len(out["rows"]) == df["price"].nunique()


# ── live SQL source (SQLite) ───────────────────────────────────────────────

@pytest.fixture
def sqlite_orders(tmp_path, ordersfile):
    _, df = ordersfile
    db_path = tmp_path / "orders.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE orders (d TEXT, price REAL, status TEXT, qty INTEGER)")
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)",
                     [(r.d.strftime("%Y-%m-%d %H:%M:%S"), float(r.price), r.status, int(r.qty))
                      for r in df.itertuples()])
    conn.commit()
    conn.close()
    return str(db_path), df


async def _dq_ds(db, org, db_path):
    src = DataSource(name="Live", type="sqlite", config={"filepath": db_path}, org_id=org.id)
    db.add(src)
    await db.flush()
    ds = Dataset(name="Live orders", org_id=org.id, mode="directquery",
                 data_source_id=src.id, source_table="orders")
    db.add(ds)
    await db.flush()
    for c, t in (("d", "datetime"), ("price", "numeric"), ("status", "categorical"), ("qty", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


class TestLiveSource:
    @pytest.mark.parametrize("measure", [{"measure": "qty", "aggregation": "sum"}, {}], ids=["sum", "count"])
    async def test_prices_are_ranged_by_the_source(self, client, db_session, two_orgs, auth_headers, sqlite_orders, measure):
        db_path, df = sqlite_orders
        ds = await _dq_ds(db_session, two_orgs["a"]["org"], db_path)
        out = await _post(client, auth_headers, ds.id, "donut", {"dimension": "price", **measure})
        assert 2 <= len(out["rows"]) <= 12 and out["dimension"] == "price"
        expected = int(df["qty"].sum()) if measure else len(df)
        assert sum(r["value"] for r in out["rows"]) == expected

    @pytest.mark.parametrize("measure", [{"measure": "qty", "aggregation": "sum"}, {}], ids=["sum", "count"])
    async def test_dates_are_bucketed_by_the_source(self, client, db_session, two_orgs, auth_headers, sqlite_orders, measure):
        db_path, df = sqlite_orders
        ds = await _dq_ds(db_session, two_orgs["a"]["org"], db_path)
        out = await _post(client, auth_headers, ds.id, "line", {"dimension": "d", **measure})
        assert out["binning"]["grain"] == "week" and len(out["rows"]) <= 150
        expected = int(df["qty"].sum()) if measure else len(df)
        assert sum(r["value"] for r in out["rows"]) == expected
        # Same labels as an uploaded file draws.
        assert all(len(r["name"]) == 8 and "-W" in r["name"] for r in out["rows"])
        weeks = df["d"].dt.isocalendar()
        assert {r["name"] for r in out["rows"]} == {f"{y}-W{w:02d}" for y, w in zip(weeks["year"], weeks["week"])}

    async def test_zoom_on_a_live_source(self, client, db_session, two_orgs, auth_headers, sqlite_orders):
        db_path, df = sqlite_orders
        ds = await _dq_ds(db_session, two_orgs["a"]["org"], db_path)
        out = await _post(client, auth_headers, ds.id, "bar",
                          {"dimension": "price", "measure": "qty", "aggregation": "sum",
                           "bin_range": {"start": 1000, "end": 2000}})
        sel = df[(df["price"] >= 1000) & (df["price"] < 2000)]
        assert sum(r["value"] for r in out["rows"]) == int(sel["qty"].sum())
        assert all(1000 <= r["bin_start"] < 2000 for r in out["rows"])


class TestAuthorGrainOnLiveSource:
    """The author's own grain on a live table is grouped by the source, not by
    fetching every row -- same labels, same totals, and no auto-bin offered."""

    @pytest.mark.parametrize("measure", [{"measure": "qty", "aggregation": "sum"}, {}], ids=["sum", "count"])
    async def test_by_month_is_grouped_in_sql(self, client, db_session, two_orgs, auth_headers, sqlite_orders, measure, monkeypatch):
        from app.services import direct_query
        fetched = []
        real = direct_query._fetch_and_compute
        monkeypatch.setattr(direct_query, "_fetch_and_compute",
                            lambda *a, **k: fetched.append(1) or real(*a, **k))
        db_path, df = sqlite_orders
        ds = await _dq_ds(db_session, two_orgs["a"]["org"], db_path)
        out = await _post(client, auth_headers, ds.id, "line",
                          {"dimension": "d", "dimension_granularity": "month", **measure})
        assert not fetched                       # no row fetch: the GROUP BY ran at the source
        assert "binning" not in out and out["dimension"] == "d"
        assert [r["name"] for r in out["rows"]] == sorted(df["d"].dt.strftime("%Y-%m").unique())
        expected = int(df["qty"].sum()) if measure else len(df)
        assert sum(r["value"] for r in out["rows"]) == expected
