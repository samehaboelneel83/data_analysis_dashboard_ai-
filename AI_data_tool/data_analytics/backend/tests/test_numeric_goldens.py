"""Golden numbers: hand-computed answers, checked on every engine (E04 slice 1).

The engine-parity suites (test_duck_agg.py, the DirectQuery execution tests)
compare one engine against ANOTHER -- they pass if both are wrong together.
Here every expected value is worked out by hand in the comment beside it, from
the seven rows below, and each engine must produce it or refuse explicitly:

    pandas       get_widget_data with DuckDB pushdown off
    duckdb       the same call with pushdown on (it takes only grain-safe
                 aggregations; the rest fall back to pandas by design, so for
                 count/countd this row re-checks pandas and says so)
    directquery  run_direct_query against the same rows in SQLite

A silently different number fails; an explicit refusal (DirectQueryUnsupported)
is acceptable and asserted as such. The cases are the non-additive traps the
gap analysis names in section 9B: totals that must be recomputed, distinct
counts across overlapping groups, ratios, weighted averages, percent-of-total
after a filter, nulls, and a zero denominator.
"""
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.core.config import settings
from app.services import widget_data as wd
from app.services.direct_query import DirectQueryUnsupported, run_direct_query

COLS = ["region", "customer", "revenue", "profit", "units"]
ROWS = [
    ("North", "c1", 100.0, 20.0, 1.0),
    ("North", "c2", 200.0, 20.0, 3.0),
    ("North", "c1", 300.0, 90.0, 2.0),
    ("South", "c1", 50.0, 5.0, 4.0),     # c1 again: customers overlap regions
    ("South", "c3", 150.0, None, 1.0),   # profit missing
    ("South", "c4", None, 10.0, 1.0),    # revenue missing
    ("East", "c5", 0.0, 0.0, 2.0),       # a zero denominator for ratios
]

MEASURES = [
    {"name": "Margin", "expression": "SUM(profit) / SUM(revenue) * 100"},
    {"name": "WAvg", "expression": "SUM(revenue * units) / SUM(units)"},
    {"name": "Share", "expression": "SUM(revenue) / TOTAL(SUM(revenue)) * 100"},
]

ENGINES = ("pandas", "duckdb", "directquery")


@pytest.fixture(autouse=True)
def _clean():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


@pytest.fixture
def data(tmp_path):
    frame = pd.DataFrame(ROWS, columns=COLS)
    csv = tmp_path / "golden.csv"
    frame.to_csv(csv, index=False)
    db = tmp_path / "golden.db"
    con = sqlite3.connect(db)
    frame.to_sql("sales", con, index=False)
    con.close()
    return {"csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)},
            "dataset": SimpleNamespace(source_table="sales", source_query=None,
                                       columns=[SimpleNamespace(name=c) for c in COLS])}


def run(engine, data, config, widget_type="bar", monkeypatch=None, measures=None):
    if engine == "directquery":
        return run_direct_query(data["source"], data["dataset"], dict(config),
                                widget_type=widget_type, cache_ttl_seconds=0)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", engine == "duckdb")
    wd.clear_widget_data_cache()
    return wd.get_widget_data(data["csv"], dict(config), widget_type=widget_type,
                              use_cache=False, measures=measures)


def values(result):
    return {r["name"]: r["value"] for r in result["rows"]}


def assert_values(result, expected, total=None):
    got = values(result)
    assert set(got) == set(expected), got
    for k, v in expected.items():
        assert got[k] == (None if v is None else pytest.approx(v, rel=1e-9)), (k, got[k])
    if total is not None:
        assert result["totals"][1] == pytest.approx(total, rel=1e-9)


@pytest.mark.parametrize("engine", ENGINES)
class TestPlainAggregations:
    def test_sum_ignores_a_missing_value(self, engine, data, monkeypatch):
        # North 100+200+300; South 50+150 (the missing revenue adds nothing); East 0.
        r = run(engine, data, {"dimension": "region", "measure": "revenue",
                               "aggregation": "sum", "show_totals": True}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 600, "South": 200, "East": 0}, total=800)

    def test_the_average_total_is_over_rows_not_over_group_averages(self, engine, data, monkeypatch):
        # South (50+150)/2 = 100. Total: 800 over the 6 non-missing rows = 133.33,
        # not (200+100+0)/3 = 100, the average of the averages.
        r = run(engine, data, {"dimension": "region", "measure": "revenue",
                               "aggregation": "avg", "show_totals": True}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 200, "South": 100, "East": 0}, total=800 / 6)

    def test_distinct_customers_are_not_added_across_regions(self, engine, data, monkeypatch):
        # North {c1,c2}=2, South {c1,c3,c4}=3, East {c5}=1. Total {c1..c5} = 5,
        # not 2+3+1 = 6: c1 bought in both North and South.
        r = run(engine, data, {"dimension": "region", "measure": "customer",
                               "aggregation": "countd", "show_totals": True}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 2, "South": 3, "East": 1}, total=5)

    def test_count_excludes_missing_values(self, engine, data, monkeypatch):
        r = run(engine, data, {"dimension": "region", "measure": "revenue",
                               "aggregation": "count"}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 3, "South": 2, "East": 1})

    def test_a_filter_narrows_before_aggregation(self, engine, data, monkeypatch):
        r = run(engine, data, {"dimension": "region", "measure": "revenue", "aggregation": "sum",
                               "filters": [{"column": "region", "op": "neq", "value": "East"}]},
                monkeypatch=monkeypatch)
        assert_values(r, {"North": 600, "South": 200})

    def test_the_median_total_is_the_median_of_every_row(self, engine, data, monkeypatch):
        # median(0, 50, 100, 150, 200, 300) = 125 -- not 200+100+0, not their median.
        config = {"dimension": "region", "measure": "revenue", "aggregation": "median",
                  "show_totals": True}
        if engine == "directquery":
            # SQLite has no MEDIAN: refused by name, never approximated.
            with pytest.raises(DirectQueryUnsupported, match="median"):
                run(engine, data, config)
            return
        assert_values(run(engine, data, config, monkeypatch=monkeypatch),
                      {"North": 200, "South": 100, "East": 0}, total=125)


@pytest.mark.parametrize("engine", ["pandas", "duckdb"])
class TestPostAggregationMeasures:
    """Named measures run after aggregation. DirectQuery cannot run them; its
    widget route refuses a config that names one, pinned separately below."""

    def test_margin_total_is_recomputed_not_averaged(self, engine, data, monkeypatch):
        # North 130/600 = 21.67%; South 15/200 = 7.5%; East 0/0 = blank, never inf.
        # Total 145/800 = 18.125% -- not the mean of the group margins (14.58%).
        r = run(engine, data, {"dimension": "region", "measure": "Margin", "show_totals": True},
                monkeypatch=monkeypatch, measures=MEASURES)
        assert_values(r, {"North": 130 / 6, "South": 7.5, "East": None}, total=18.125)

    def test_a_kpi_of_the_margin_is_the_same_recomputed_ratio(self, engine, data, monkeypatch):
        r = run(engine, data, {"measure": "Margin"}, widget_type="kpi",
                monkeypatch=monkeypatch, measures=MEASURES)
        assert r["rows"][0]["value"] == pytest.approx(18.125)

    def test_weighted_average_weights_every_row(self, engine, data, monkeypatch):
        # North (100*1+200*3+300*2)/6 = 216.67; South (50*4+150*1)/6 = 58.33 (the
        # row with no revenue adds weight but no value: the formula as written);
        # East 0. Total 1650/14 = 117.86.
        r = run(engine, data, {"dimension": "region", "measure": "WAvg", "show_totals": True},
                monkeypatch=monkeypatch, measures=MEASURES)
        assert_values(r, {"North": 1300 / 6, "South": 350 / 6, "East": 0}, total=1650 / 14)

    def test_percent_of_total_rebases_to_the_filtered_rows(self, engine, data, monkeypatch):
        r = run(engine, data, {"dimension": "region", "measure": "Share",
                               "filters": [{"column": "region", "op": "neq", "value": "East"}]},
                monkeypatch=monkeypatch, measures=MEASURES)
        assert_values(r, {"North": 75, "South": 25})


@pytest.mark.parametrize("engine", ENGINES)
class TestRanking:
    """Top/bottom N with an "All Other" bucket. The bucket is the aggregation
    over the excluded categories' RAW rows, ties at the boundary are kept, and
    a display `limit` must not cut categories before the rank sees them.
    DirectQuery got all three wrong by ranking the pushed-down, SQL-limited
    page as if it were raw rows (avg of avgs 14.17 for 17.0; no All Other at
    all on the count path; All Other 60 for 85 under limit 3)."""

    @pytest.fixture
    def ranked(self, data, tmp_path):
        rows = ROWS + [("West", "c7", 30.0, 3.0, 1.0), ("West", "c8", 30.0, 3.0, 1.0),
                       ("Mid", "c9", 20.0, 2.0, 1.0), ("Mid", "c9", 5.0, 1.0, 1.0)]
        # sums: North 600, South 200, West 60, Mid 25, East 0
        frame = pd.DataFrame(rows, columns=COLS)
        csv = tmp_path / "ranked.csv"
        frame.to_csv(csv, index=False)
        db = tmp_path / "ranked.db"
        con = sqlite3.connect(db)
        frame.to_sql("sales", con, index=False)
        con.close()
        return {**data, "csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)}}

    def test_all_other_sums_the_excluded_categories(self, engine, ranked, monkeypatch):
        r = run(engine, ranked, {"dimension": "region", "measure": "revenue", "aggregation": "sum",
                                 "rank": {"mode": "top", "n": 2, "other": True}}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 600, "South": 200, "All Other": 85})   # 60 + 25 + 0

    def test_all_other_averages_the_excluded_rows_not_their_averages(self, engine, ranked, monkeypatch):
        # Excluded rows: West 30, 30; Mid 20, 5; East 0 -> 85 / 5 = 17.
        # The average of the three group averages would be (30 + 12.5 + 0) / 3.
        r = run(engine, ranked, {"dimension": "region", "measure": "revenue", "aggregation": "avg",
                                 "rank": {"mode": "top", "n": 2, "other": True}}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 200, "South": 100, "All Other": 17})

    def test_the_count_path_ranks_too(self, engine, ranked, monkeypatch):
        # Counts: North 3, South 3, West 2, Mid 2, East 1. Top 1 keeps the tie.
        r = run(engine, ranked, {"dimension": "region", "aggregation": "count",
                                 "rank": {"mode": "top", "n": 1, "other": True}}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 3, "South": 3, "All Other": 5})

    def test_a_display_limit_does_not_shrink_all_other(self, engine, ranked, monkeypatch):
        r = run(engine, ranked, {"dimension": "region", "measure": "revenue", "aggregation": "sum",
                                 "limit": 3, "rank": {"mode": "top", "n": 2, "other": True}},
                monkeypatch=monkeypatch)
        assert_values(r, {"North": 600, "South": 200, "All Other": 85})

    def test_bottom_n(self, engine, ranked, monkeypatch):
        r = run(engine, ranked, {"dimension": "region", "measure": "revenue", "aggregation": "sum",
                                 "rank": {"mode": "bottom", "n": 2}}, monkeypatch=monkeypatch)
        assert_values(r, {"Mid": 25, "East": 0})


@pytest.mark.parametrize("engine", ENGINES)
class TestDateBuckets:
    """Calendar semantics, hand-checked: ISO weeks keep the last days of
    December with the week they belong to, quarters and months are exact, and
    a missing date is dropped from every bucket and the total. Year labels are
    whole numbers, never `2024.0`: the row builder's iterrows() upcast an int
    name beside a float value on every engine, and a NaT floated the whole
    year column besides."""

    DATES = [("2024-12-30", 1.0), ("2024-12-31", 2.0), ("2025-01-01", 4.0), ("2025-01-05", 8.0),
             ("2025-03-31", 16.0), ("2025-04-01", 32.0), ("2025-12-31", 64.0), (None, 128.0)]

    @pytest.fixture
    def dated(self, tmp_path):
        frame = pd.DataFrame(self.DATES, columns=["day", "amount"])
        frame["day"] = pd.to_datetime(frame["day"])
        csv = tmp_path / "dates.csv"
        frame.to_csv(csv, index=False)
        db = tmp_path / "dates.db"
        con = sqlite3.connect(db)
        frame.to_sql("t", con, index=False)
        con.close()
        return {"csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)},
                "dataset": SimpleNamespace(source_table="t", source_query=None, columns=[
                    SimpleNamespace(name="day", dtype="datetime"),
                    SimpleNamespace(name="amount", dtype="number")])}

    def _bucket(self, engine, dated, granularity, monkeypatch):
        r = run(engine, dated, {"dimension": "day", "measure": "amount", "aggregation": "sum",
                                "dimension_granularity": granularity, "show_totals": True},
                monkeypatch=monkeypatch)
        assert r["totals"][1] == pytest.approx(127)          # the blank date's 128 is out
        assert r["missing_category"] == {"rows": 1}
        return values(r)

    def test_years_are_whole_numbers_even_with_a_blank_date(self, engine, dated, monkeypatch):
        got = self._bucket(engine, dated, "year", monkeypatch)
        assert got == {2024: 3, 2025: 124}
        assert all(isinstance(k, int) for k in got), list(got)

    def test_iso_weeks_cross_the_year_boundary(self, engine, dated, monkeypatch):
        # 30-31 Dec 2024 and 1-5 Jan 2025 are one ISO week; 31 Dec 2025 is 2026-W01.
        assert self._bucket(engine, dated, "week", monkeypatch) == {
            "2025-W01": 15, "2025-W14": 48, "2026-W01": 64}

    def test_quarters_and_months_are_exact(self, engine, dated, monkeypatch):
        assert self._bucket(engine, dated, "quarter", monkeypatch) == {
            "2024-Q4": 3, "2025-Q1": 28, "2025-Q2": 32, "2025-Q4": 64}
        assert self._bucket(engine, dated, "month", monkeypatch) == {
            "2024-12": 3, "2025-01": 12, "2025-03": 16, "2025-04": 32, "2025-12": 64}


PIVOT_COLS = ["region", "quarter", "customer", "revenue", "profit"]
PIVOT_ROWS = [
    ("N", "Q1", "c1", 100.0, 20.0), ("N", "Q1", "c2", 200.0, 20.0), ("N", "Q2", "c1", 300.0, 90.0),
    ("S", "Q1", "c1", 50.0, 5.0), ("S", "Q2", "c3", 150.0, None), ("S", "Q2", "c4", None, 10.0),
    ("E", "Q1", "c5", 0.0, 0.0),
]   # row sums: N 600, S 200, E 0


@pytest.fixture
def pivot_data(tmp_path):
    frame = pd.DataFrame(PIVOT_ROWS, columns=PIVOT_COLS)
    csv = tmp_path / "pivot.csv"
    frame.to_csv(csv, index=False)
    db = tmp_path / "pivot.db"
    con = sqlite3.connect(db)
    frame.to_sql("t", con, index=False)
    con.close()
    return {"csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)},
            "dataset": SimpleNamespace(source_table="t", source_query=None,
                                       columns=[SimpleNamespace(name=c) for c in PIVOT_COLS])}


def grid(result):
    """{row label: {column: value}} plus the totals row under 'TOTAL'."""
    cols = result["columns"]
    out = {r[0]: dict(zip(cols[1:], r[1:])) for r in result["rows"]}
    if result.get("totals") is not None:
        out["TOTAL"] = dict(zip(cols[1:], result["totals"][1:]))
    return out


def approx_row(row, expected):
    assert set(row) == set(expected), row
    for k, v in expected.items():
        assert row[k] == (None if v is None else pytest.approx(v, rel=1e-9)), (k, row[k], v)


class TestCrosstabRanking:
    """Journey B, the regional pivot: Top/Bottom N on a crosstab's rows. The
    panel offered it on crosstabs and matrices while the crosstab branch had no
    ranking at all -- a control that saved and did nothing, on every engine
    (DuckDB and DirectQuery both decline dimension2 and run this branch)."""

    BASE = {"dimension": "region", "dimension2": "quarter", "measure": "revenue",
            "aggregation": "sum", "show_totals": True, "show_subtotals": True}

    @pytest.mark.parametrize("engine", ENGINES)
    def test_top_1_with_all_other_sums_the_rest(self, engine, pivot_data, monkeypatch):
        g = grid(run(engine, pivot_data, {**self.BASE, "rank": {"mode": "top", "n": 1, "other": True}},
                     widget_type="crosstab", monkeypatch=monkeypatch))
        assert list(g) == ["N", "All Other", "TOTAL"]
        approx_row(g["N"], {"Q1": 300, "Q2": 300, "__total__": 600})
        approx_row(g["All Other"], {"Q1": 50, "Q2": 150, "__total__": 200})   # S + E
        approx_row(g["TOTAL"], {"Q1": 350, "Q2": 450, "__total__": 800})

    @pytest.mark.parametrize("engine", ENGINES)
    def test_all_other_averages_the_excluded_rows_per_column(self, engine, pivot_data, monkeypatch):
        # Excluded raw rows: S/Q1 50, S/Q2 150, E/Q1 0 -> Q1 avg(50, 0) = 25,
        # Q2 150, subtotal avg(50, 150, 0) = 66.67. Not the mean of S's and E's means.
        g = grid(run(engine, pivot_data, {**self.BASE, "aggregation": "avg",
                                          "rank": {"mode": "top", "n": 1, "other": True}},
                     widget_type="crosstab", monkeypatch=monkeypatch))
        approx_row(g["N"], {"Q1": 150, "Q2": 300, "__total__": 200})
        approx_row(g["All Other"], {"Q1": 25, "Q2": 150, "__total__": 200 / 3})
        approx_row(g["TOTAL"], {"Q1": 87.5, "Q2": 225, "__total__": 800 / 6})

    @pytest.mark.parametrize("engine", ENGINES)
    def test_all_other_distinct_counts_are_not_added(self, engine, pivot_data, monkeypatch):
        # Ranked by the row's OWN distinct count: S {c1, c3, c4} = 3 beats N's 2,
        # so S is the top row. Excluded N {c1, c2} and E {c5}: Q1 {c1, c2, c5} = 3,
        # Q2 {c1} = 1, subtotal {c1, c2, c5} = 3 (not 3 + 1, not N's 2 + E's 1).
        g = grid(run(engine, pivot_data, {**self.BASE, "measure": "customer", "aggregation": "countd",
                                          "rank": {"mode": "top", "n": 1, "other": True}},
                     widget_type="crosstab", monkeypatch=monkeypatch))
        assert list(g) == ["S", "All Other", "TOTAL"]
        approx_row(g["S"], {"Q1": 1, "Q2": 2, "__total__": 3})
        approx_row(g["All Other"], {"Q1": 3, "Q2": 1, "__total__": 3})
        approx_row(g["TOTAL"], {"Q1": 3, "Q2": 3, "__total__": 5})

    @pytest.mark.parametrize("engine", ["pandas", "duckdb"])
    def test_all_other_re_evaluates_a_ratio_measure(self, engine, pivot_data, monkeypatch):
        # Margin over the excluded rows: Q1 (5 + 0) / (50 + 0) = 10%; Q2 10 / 150
        # = 6.67% (S's blanks count as nothing); subtotal 15 / 200 = 7.5%.
        g = grid(run(engine, pivot_data, {**self.BASE, "measure": "Margin",
                                          "rank": {"mode": "top", "n": 1, "other": True}},
                     widget_type="crosstab", monkeypatch=monkeypatch, measures=MEASURES))
        approx_row(g["N"], {"Q1": 40 / 3, "Q2": 30, "__total__": 130 / 6})
        approx_row(g["All Other"], {"Q1": 10, "Q2": 20 / 3, "__total__": 7.5})
        approx_row(g["TOTAL"], {"Q1": 90 / 7, "Q2": 200 / 9, "__total__": 18.125})

    @pytest.mark.parametrize("engine", ENGINES)
    def test_hidden_rows_without_a_bucket_are_disclosed(self, engine, pivot_data, monkeypatch):
        r = run(engine, pivot_data, {**self.BASE, "rank": {"mode": "bottom", "n": 2}},
                widget_type="crosstab", monkeypatch=monkeypatch)
        g = grid(r)
        assert list(g) == ["E", "S", "TOTAL"]
        approx_row(g["TOTAL"], {"Q1": 350, "Q2": 450, "__total__": 800})   # every source row
        # ...and what the two visible rows add up to, since N is not on the grid.
        assert r["totals_shown"][1:] == [50, 150, 200]
        assert r["totals_basis"] == {"unit": "groups", "shown": 2, "of": 3,
                                     "truncated": True, "suppressed_excluded": False}

    @pytest.mark.parametrize("engine", ENGINES)
    def test_no_rank_is_untouched(self, engine, pivot_data, monkeypatch):
        r = run(engine, pivot_data, self.BASE, widget_type="crosstab", monkeypatch=monkeypatch)
        assert list(grid(r)) == ["E", "N", "S", "TOTAL"]
        assert "totals_shown" not in r
        assert r["totals_basis"]["truncated"] is False and r["totals_basis"]["of"] == 3


async def test_directquery_refuses_a_named_measure_at_the_route(client, db_session, two_orgs, tmp_path):
    """run_direct_query itself answers a KPI on a measure name with an EMPTY
    result; the widget route is what turns that into a refusal. Pinned here so
    the refusal cannot quietly become a blank tile."""
    from app.models.models import DataSource, Dataset, DatasetColumn
    org = two_orgs["a"]["org"].id
    db = tmp_path / "dq.db"
    con = sqlite3.connect(db)
    pd.DataFrame(ROWS, columns=COLS).to_sql("sales", con, index=False)
    con.close()
    src = DataSource(name="dq", type="sqlite", config={"filepath": str(db)}, org_id=org)
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="dq", org_id=org, mode="directquery", data_source_id=src.id,
                 source_table="sales", measures=MEASURES)
    db_session.add(ds)
    await db_session.flush()
    for c in COLS:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="string"))
    await db_session.commit()
    from app.core.security import create_access_token
    from app.models.models import User
    admin = await db_session.get(User, two_orgs["a"]["user"].id)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data",
                          json={"widget_type": "kpi", "config": {"measure": "Margin"}},
                          headers={"Authorization": f"Bearer {create_access_token(admin.id, org)}"})
    assert r.status_code == 400 and "Measures are not yet supported" in r.text


@pytest.mark.parametrize("engine", ENGINES)
class TestRowsWithNoCategoryAreDisclosed:
    """A row whose category is missing is dropped from a chart AND its Total
    (every engine, on purpose), while a KPI of the same measure counts it: 800
    beside 840 on one dashboard. The drop stays -- reversing it is a semantics
    change across three engines -- but it is no longer silent: the result says
    how many rows it left out, the way `truncation` says what a limit cut."""

    @pytest.fixture
    def with_null_row(self, data, tmp_path):
        rows = ROWS + [(None, "c6", 40.0, 4.0, 1.0)]
        frame = pd.DataFrame(rows, columns=COLS)
        csv = tmp_path / "nullcat.csv"
        frame.to_csv(csv, index=False)
        db = tmp_path / "nullcat.db"
        con = sqlite3.connect(db)
        frame.to_sql("sales", con, index=False)
        con.close()
        return {**data, "csv": str(csv), "source": {"type": "sqlite", "filepath": str(db)}}

    def test_the_chart_says_what_the_kpi_counts_that_it_does_not(
            self, engine, with_null_row, monkeypatch):
        chart = run(engine, with_null_row, {"dimension": "region", "measure": "revenue",
                                            "aggregation": "sum", "show_totals": True},
                    monkeypatch=monkeypatch)
        kpi = run(engine, with_null_row, {"measure": "revenue", "aggregation": "sum"},
                  widget_type="kpi", monkeypatch=monkeypatch)
        assert chart["totals"][1] == pytest.approx(800)
        assert kpi["rows"][0]["value"] == pytest.approx(840)
        assert chart["missing_category"] == {"rows": 1}

    def test_the_no_measure_count_path_discloses_it_too(self, engine, with_null_row, monkeypatch):
        # DirectQuery answers a count-per-category from SQL without the shaper,
        # so it builds this field itself; it has to agree with the others.
        r = run(engine, with_null_row, {"dimension": "region"}, monkeypatch=monkeypatch)
        assert_values(r, {"North": 3, "South": 3, "East": 1})
        assert r["missing_category"] == {"rows": 1}

    def test_a_filter_that_removes_the_row_removes_it_from_the_count(
            self, engine, with_null_row, monkeypatch):
        r = run(engine, with_null_row, {"dimension": "region", "measure": "revenue",
                                        "aggregation": "sum",
                                        "filters": [{"column": "customer", "op": "neq", "value": "c6"}]},
                monkeypatch=monkeypatch)
        assert r["missing_category"] == {"rows": 0}

    def test_zero_when_every_row_has_a_category(self, engine, data, monkeypatch):
        r = run(engine, data, {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
                monkeypatch=monkeypatch)
        assert r["missing_category"] == {"rows": 0}


class TestAnUnknownFieldIsAnErrorNotACount:
    """A widget naming a field that is neither a column nor a defined measure
    fell through to the no-measure branch and drew a ROW COUNT under the
    measure's name (live: "Margin % by region" read 517, 514, 509, 460 after
    its measure was renamed). Now an explicit error the frontend draws as a
    tile -- on every engine. DuckDB declines an unknown column and DirectQuery
    refuses it by name, so they reach the same error or refuse outright."""

    @pytest.mark.parametrize("engine", ENGINES)
    @pytest.mark.parametrize("widget_type,config,field", [
        ("bar", {"dimension": "region", "measure": "Gone"}, "measure"),
        ("bar", {"dimension": "region", "measure": "Gone", "aggregation": "avg"}, "measure"),
        ("line", {"dimension": "region", "measure": "Gone"}, "measure"),
        ("pie", {"dimension": "region", "measure": "Gone"}, "measure"),
        ("bar", {"dimension": "Nowhere", "measure": "revenue"}, "dimension"),
    ])
    def test_never_a_count(self, engine, data, monkeypatch, widget_type, config, field):
        try:
            r = run(engine, data, config, widget_type=widget_type, monkeypatch=monkeypatch)
        except DirectQueryUnsupported as e:
            assert "unknown column" in str(e)          # refused by name, never drawn
            return
        assert r["type"] == "error" and r["code"] == "unknown_field", r
        assert r["field"] == field and r["rows"] == []

    @pytest.mark.parametrize("engine", ["pandas", "duckdb"])
    def test_kpi_and_crosstab_too(self, engine, data, monkeypatch):
        for wt, cfg in (("kpi", {"measure": "Gone"}),
                        ("crosstab", {"dimension": "region", "dimension2": "customer", "measure": "Gone"})):
            r = run(engine, data, cfg, widget_type=wt, monkeypatch=monkeypatch)
            assert r["code"] == "unknown_field", (wt, r)

    @pytest.mark.parametrize("engine", ["pandas", "duckdb"])
    def test_a_defined_measure_still_resolves(self, engine, data, monkeypatch):
        r = run(engine, data, {"dimension": "region", "measure": "Margin"},
                monkeypatch=monkeypatch, measures=MEASURES)
        assert r["type"] == "series"
