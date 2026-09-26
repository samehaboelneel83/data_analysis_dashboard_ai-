"""E08: the pivot fixture suite.

A crosstab puts one dimension down the side and one across the top. Every
number below was worked out by hand from the twelve rows in ROWS, not read
back from the engine, and each case runs on the import engine, on DuckDB
(which hands a crosstab back to the import shaper) and on DirectQuery (which
fetches the rows and does the same). The grid follows
docs/EVALUATION_ORDER.md; what it adds is written in `_shape_grid`.

Before E08 the crosstab branch was a separate, older path. It ignored every
control in the panel's "Sort & limit" group, so the cases for suppression,
HAVING, sort, custom order, quick calculations and the row limit all failed
there; it counted rows with no region or no quarter in its totals, drew an
average over no rows as 0, summed a "Percentage" instead of dividing it, and
evaluated TOTAL() in the All Other row over the excluded rows alone.

The fixture (region down, quarter across, revenue and cost):

    region  quarter  customer  revenue  cost
    North   Q1       a         100      60
    North   Q1       b          50      20
    North   Q2       a          30      10
    South   Q1       c         200     150
    South   Q2       c          40      30
    South   Q2       d          60      30
    South   Q2       d        (none)     5
    East    Q2       e          10       2
    West    Q1       f          20      10
    West    Q1       f          30      20
    West    Q2       g          25       5
    (none)  Q1       h         999       1     <- no region: in no cell, no total
    North   (none)   a         888       1     <- no quarter: likewise
"""
import io
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.core.config import settings
from app.services import widget_data as wd
from app.services.direct_query import run_direct_query

ROWS = [
    ("North", "Q1", "a", 100.0, 60.0),
    ("North", "Q1", "b", 50.0, 20.0),
    ("North", "Q2", "a", 30.0, 10.0),
    ("South", "Q1", "c", 200.0, 150.0),
    ("South", "Q2", "c", 40.0, 30.0),
    ("South", "Q2", "d", 60.0, 30.0),
    ("South", "Q2", "d", None, 5.0),
    ("East", "Q2", "e", 10.0, 2.0),
    ("West", "Q1", "f", 20.0, 10.0),
    ("West", "Q1", "f", 30.0, 20.0),
    ("West", "Q2", "g", 25.0, 5.0),
    (None, "Q1", "h", 999.0, 1.0),
    ("North", None, "a", 888.0, 1.0),
]
COLS = ["region", "quarter", "customer", "revenue", "cost"]
MEASURES = [
    {"name": "Margin", "expression": "(SUM(revenue) - SUM(cost)) / SUM(revenue) * 100"},
    {"name": "Share", "expression": "SUM(revenue) / TOTAL(SUM(revenue)) * 100"},
]
ENGINES = ["pandas", "duckdb", "directquery"]
BASE = {"dimension": "region", "dimension2": "quarter", "measure": "revenue", "aggregation": "sum"}


@pytest.fixture(autouse=True)
def _clean():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


@pytest.fixture
def data(tmp_path):
    frame = pd.DataFrame(ROWS, columns=COLS)
    csv = tmp_path / "pivot.csv"
    frame.to_csv(csv, index=False)
    db = tmp_path / "pivot.db"
    con = sqlite3.connect(db)
    frame.to_sql("t", con, index=False)
    con.close()
    types = {"region": "string", "quarter": "string", "customer": "string",
             "revenue": "number", "cost": "number"}
    return {"csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)},
            "dataset": SimpleNamespace(source_table="t", source_query=None,
                                       columns=[SimpleNamespace(name=c, dtype=t) for c, t in types.items()])}


def run(engine, data, config, monkeypatch, widget_type="crosstab"):
    config = {**config}
    if engine == "directquery":
        return run_direct_query(data["source"], data["dataset"], config, widget_type=widget_type,
                                cache_ttl_seconds=0, measures=MEASURES)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", engine == "duckdb")
    wd.clear_widget_data_cache()
    return wd.get_widget_data(data["csv"], config, widget_type=widget_type, use_cache=False,
                              measures=MEASURES)


def grid(result, places=2):
    """The grid as {row label: [cells...]}, numbers rounded."""
    def r(v):
        return round(v, places) if isinstance(v, float) else v
    return {row[0]: [r(v) for v in row[1:]] for row in result["rows"]}


def order(result):
    return [row[0] for row in result["rows"]]


def totals(result, key="totals", places=2):
    return [round(v, places) if isinstance(v, float) else v for v in result[key]]


@pytest.fixture(params=ENGINES)
def engine(request):
    return request.param


# --------------------------------------------------------------------------
# Aggregations: cells, row subtotals, column totals, all from the rows
# --------------------------------------------------------------------------

class TestAggregations:
    def test_sum(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "show_totals": True}, monkeypatch)
        assert res["columns"] == ["region", "Q1", "Q2", "__total__"]
        # East has no Q1 rows: a sum of nothing is 0.
        assert grid(res) == {"East": [0, 10, 10], "North": [150, 30, 180],
                             "South": [200, 100, 300], "West": [50, 25, 75]}
        # 999 (no region) and 888 (no quarter) are in no total.
        assert totals(res) == [None, 400, 165, 565]
        assert res["missing_category"]["rows"] == 2

    def test_average_over_no_rows_is_blank_and_totals_average_the_rows(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "aggregation": "avg", "show_totals": True}, monkeypatch)
        # East Q1 has no rows: blank, not 0. Row subtotals average the ROWS
        # (North: 180 / 3 = 60), not the cells ((75 + 30) / 2 = 52.5).
        assert grid(res) == {"East": [None, 10, 10], "North": [75, 30, 60],
                             "South": [200, 50, 100], "West": [25, 25, 25]}
        assert totals(res) == [None, 80, 33, 56.5]

    def test_distinct_count_is_not_additive(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "measure": "customer", "aggregation": "countd",
                                 "show_totals": True}, monkeypatch)
        assert grid(res) == {"East": [0, 1, 1], "North": [2, 1, 2],
                             "South": [1, 2, 2], "West": [1, 1, 2]}
        # 4 + 5 = 9 cells' worth, but only 7 different customers.
        assert totals(res) == [None, 4, 5, 7]

    def test_row_count_without_a_measure(self, engine, data, monkeypatch):
        res = run(engine, data, {"dimension": "region", "dimension2": "quarter", "show_totals": True},
                  monkeypatch)
        # South Q2 counts the row whose revenue is missing.
        assert grid(res) == {"East": [0, 1, 1], "North": [2, 1, 3],
                             "South": [1, 3, 4], "West": [2, 1, 3]}
        assert totals(res) == [None, 5, 6, 11]

    def test_percentage_aggregation_is_a_share_of_the_whole(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "aggregation": "pct", "show_totals": True}, monkeypatch)
        # Each cell over 565. Before E08 "Percentage" drew the sums.
        assert grid(res) == {"East": [0, 1.77, 1.77], "North": [26.55, 5.31, 31.86],
                             "South": [35.4, 17.7, 53.1], "West": [8.85, 4.42, 13.27]}
        assert totals(res) == [None, 70.8, 29.2, 100]


class TestMeasures:
    def test_a_ratio_is_evaluated_per_cell_row_and_column(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "measure": "Margin", "show_totals": True}, monkeypatch)
        # (revenue - cost) / revenue, each at its own grain. The missing
        # revenue row still adds its cost (5) to South Q2: 100 - 65.
        assert grid(res) == {"East": [None, 80, 80], "North": [46.67, 66.67, 50],
                             "South": [25, 35, 28.33], "West": [40, 80, 53.33]}
        assert totals(res) == [None, 35, 50.3, 39.47]

    def test_total_means_the_rows_that_have_a_cell(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "measure": "Share", "show_totals": True}, monkeypatch)
        # TOTAL(SUM(revenue)) is 565: not 2,452 with the rows that have no
        # region or no quarter.
        assert grid(res)["North"] == [26.55, 5.31, 31.86]
        assert totals(res)[-1] == 100

    def test_all_other_of_a_share_is_a_share_of_the_whole(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "measure": "Share", "rank": {"n": 2, "other": True}},
                  monkeypatch)
        # East and West as one row: 50 and 35 of 565. Before E08, TOTAL()
        # there was the excluded rows alone, so the row read 58.8 and 41.2.
        assert order(res) == ["North", "South", "All Other"]
        assert grid(res)["All Other"] == [8.85, 6.19, 15.04]


# --------------------------------------------------------------------------
# After aggregation: HAVING, suppression, ranking, sort, quick calcs, limit
# --------------------------------------------------------------------------

class TestRanking:
    def test_top_two_rows_by_their_subtotal_with_all_other(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "rank": {"n": 2, "other": True}, "show_totals": True},
                  monkeypatch)
        assert order(res) == ["North", "South", "All Other"]
        assert grid(res)["All Other"] == [50, 35, 85]
        # With the Other row every row is on the grid: one total.
        assert totals(res) == [None, 400, 165, 565]
        assert "totals_shown" not in res

    def test_all_other_of_an_average_is_the_average_of_its_rows(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "aggregation": "avg", "rank": {"n": 2, "other": True}},
                  monkeypatch)
        # Ranked by row average: South (100) and North (60) are the top two;
        # East (10) and West (25) are the rest.
        assert order(res) == ["North", "South", "All Other"]
        # avg(20, 30) and avg(10, 25), and avg(10, 20, 30, 25) for the row.
        assert grid(res)["All Other"] == [25, 17.5, 21.25]

    def test_without_all_other_the_hidden_rows_are_said(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "rank": {"n": 2}, "show_totals": True}, monkeypatch)
        assert order(res) == ["North", "South"]
        assert totals(res) == [None, 400, 165, 565]
        assert totals(res, "totals_shown") == [None, 350, 130, 480]
        assert res["totals_basis"]["truncated"] is True


class TestHavingAndSort:
    def test_having_keeps_rows_whose_subtotal_passes(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "having": [{"op": "gt", "value": 100}], "show_totals": True},
                  monkeypatch)
        assert order(res) == ["North", "South"]
        # "all" keeps every row, as the series does; "shown" is the grid's.
        assert totals(res) == [None, 400, 165, 565]
        assert totals(res, "totals_shown") == [None, 350, 130, 480]

    def test_sort_by_value(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "sort_by": "value", "sort": "desc"}, monkeypatch)
        assert order(res) == ["South", "North", "West", "East"]
        res = run(engine, data, {**BASE, "sort_by": "value", "sort": "asc"}, monkeypatch)
        assert order(res) == ["East", "West", "North", "South"]

    def test_sort_by_name_descending(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "sort_by": "name", "sort": "desc"}, monkeypatch)
        assert order(res) == ["West", "South", "North", "East"]

    def test_unstated_sort_keeps_label_order(self, engine, data, monkeypatch):
        # The panel stamps sort: desc on every widget; without sort_by the
        # grid keeps the label order every crosstab has always had.
        res = run(engine, data, {**BASE, "sort": "desc"}, monkeypatch)
        assert order(res) == ["East", "North", "South", "West"]

    def test_custom_order_puts_the_named_rows_first(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "sort_custom": ["West", "East"]}, monkeypatch)
        assert order(res) == ["West", "East", "North", "South"]


class TestSuppression:
    def test_small_cells_are_blank_and_out_of_every_total(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "suppress_below": 2, "show_totals": True}, monkeypatch)
        # One-row cells: North Q2, South Q1, East Q2, West Q2. East has no
        # cell left, so it has no row. Totals leave the hidden rows out, so
        # no total minus the visible cells gives a hidden one back.
        assert grid(res) == {"North": [150, None, 150], "South": [None, 100, 100],
                             "West": [50, None, 50]}
        assert totals(res) == [None, 200, 100, 300]
        assert res["suppressed_cells"] == 4
        assert res["totals_basis"]["suppressed_excluded"] is True

    def test_nothing_reads_a_suppressed_cell(self, engine, data, monkeypatch):
        # Ranked after suppression: North's subtotal is 150 without the
        # hidden 30, so South (100) and West (50) come after it.
        res = run(engine, data, {**BASE, "suppress_below": 2, "sort_by": "value", "sort": "desc"},
                  monkeypatch)
        assert order(res) == ["North", "South", "West"]
        res = run(engine, data, {**BASE, "measure": "Share", "suppress_below": 2}, monkeypatch)
        # TOTAL() is the 300 left on the grid.
        assert grid(res) == {"North": [50, None, 50], "South": [None, 33.33, 33.33],
                             "West": [16.67, None, 16.67]}


def test_complementary_suppression_leaves_no_row_or_column_with_one_hidden_cell():
    # A 3 x 3 grid of three rows per cell, except A/X with one row.
    rows = []
    for r in "ABC":
        for c in "XYZ":
            rows += [(r, c, 1.0)] * (1 if (r, c) == ("A", "X") else 3)
    df = pd.DataFrame(rows, columns=["r", "c", "v"])
    res = wd.shape_series(df, {"dimension": "r", "dimension2": "c", "measure": "v",
                               "aggregation": "sum", "suppress_below": 2, "suppress_complement": True})
    cells = grid(res)
    hidden = {(r, c) for r, vals in cells.items() for c, v in zip("XYZ", vals) if v is None}
    # A/X alone would come back as (row A's total - A/Y - A/Z) from any other
    # object on the page; each row and column now hides none or two or more.
    assert ("A", "X") in hidden
    for axis in (0, 1):
        for key in "ABC" if axis == 0 else "XYZ":
            n = sum(1 for h in hidden if h[axis] == key)
            assert n != 1, f"{key} has exactly one hidden cell"
    assert res["suppressed_cells"] == len(hidden) == 4


class TestQuickCalcsAndLimit:
    def test_percent_of_total(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "quick_calc": "percent_of_total", "show_totals": True},
                  monkeypatch)
        assert grid(res)["South"] == [35.4, 17.7, 53.1]
        assert totals(res) == [None, 70.8, 29.2, 100]

    def test_difference_runs_down_each_column(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "quick_calc": "difference", "show_totals": True}, monkeypatch)
        assert grid(res) == {"East": [None, None, None], "North": [150, 20, 170],
                             "South": [50, 70, 120], "West": [-150, -75, -225]}
        # Differences have no total in the measure's units.
        assert res["totals_unavailable"] == "quick_calc"

    def test_rank_within_each_column(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "quick_calc": "rank"}, monkeypatch)
        assert grid(res) == {"East": [4, 4, 4], "North": [2, 2, 2],
                             "South": [1, 1, 1], "West": [3, 3, 3]}

    def test_row_limit_cuts_rows_and_says_so(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "limit": 2, "show_totals": True}, monkeypatch)
        assert order(res) == ["East", "North"]
        assert res["truncation"] == {"applied": True, "shown": 2, "of": 4, "limit": 2,
                                     "reason": "limit", "unit": "groups"}
        assert totals(res) == [None, 400, 165, 565]
        assert totals(res, "totals_shown") == [None, 150, 40, 190]


class TestFilters:
    def test_a_row_filter_applies_before_the_grid(self, engine, data, monkeypatch):
        res = run(engine, data, {**BASE, "filters": [{"column": "customer", "op": "neq", "value": "a"}],
                                 "show_totals": True}, monkeypatch)
        assert grid(res) == {"East": [0, 10, 10], "North": [50, 0, 50],
                             "South": [200, 100, 300], "West": [50, 25, 75]}
        # Only the row with no region is left out now (888 was customer a).
        assert res["missing_category"]["rows"] == 1


def test_matrix_and_a_two_dimension_bar_are_the_same_grid(data, monkeypatch):
    base = run("pandas", data, BASE, monkeypatch)
    for widget_type in ("matrix", "bar"):
        assert run("pandas", data, BASE, monkeypatch, widget_type=widget_type)["rows"] == base["rows"]


# --------------------------------------------------------------------------
# Export: the file is the table the reader sees
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_carries_the_total_column_and_row(client, auth_headers, db_session, two_orgs, tmp_path):
    from app.models.models import Dataset, DatasetColumn
    path = tmp_path / "pivot.csv"
    pd.DataFrame(ROWS, columns=COLS).to_csv(path, index=False)
    ds = Dataset(name="Pivot", filename=str(path), org_id=two_orgs["a"]["org"].id, mode="import")
    db_session.add(ds)
    await db_session.flush()
    for name, dtype in (("region", "categorical"), ("quarter", "categorical"), ("customer", "categorical"),
                        ("revenue", "numeric"), ("cost", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=name, dtype=dtype))
    await db_session.commit()
    body = {"widget_type": "crosstab", "config": {**BASE, "show_totals": True}}

    shown = (await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body,
                               headers=auth_headers["a"])).json()
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv", json=body,
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    exported = pd.read_csv(io.BytesIO(r.content))
    assert list(exported.columns) == ["region", "Q1", "Q2", "Total"]
    assert exported.shape[0] == len(shown["rows"]) + 1
    assert list(exported.iloc[-1]) == ["Total", 400, 165, 565]
    assert list(exported["region"][:-1]) == [row[0] for row in shown["rows"]]

    # The "shown" scope exports the page's own totals.
    body["config"] = {**BASE, "show_totals": True, "rank": {"n": 2}, "totals_scope": "shown"}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv", json=body,
                          headers=auth_headers["a"])
    assert list(pd.read_csv(io.BytesIO(r.content)).iloc[-1]) == ["Total", 350, 130, 480]
