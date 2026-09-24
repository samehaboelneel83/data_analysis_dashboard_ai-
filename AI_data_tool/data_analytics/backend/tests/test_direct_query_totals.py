"""`show_totals` on a DirectQuery dataset.

The branch's central claim is that a table total is computed over the whole table,
before `limit` truncates anything. On DirectQuery that claim has to survive two
truncations the import path does not have:

  * `_run_row_capped` fetches at most DEFAULT_ROW_CAP rows and RANDOMLY SAMPLES when
    the table is bigger, then hands that frame to the same shaper. Totalling it would
    put a sample's sum, labelled "Total", directly beneath a truthful "Showing 10,000
    of 4,000,000".
  * the aggregate path pushes `plan.limit` into SQL, so the shaper only ever sees the
    top-N groups.

Every test here runs against a real SQLite file through the public `run_direct_query`
entry point, so it fails if the totals are computed from the truncated frame.
"""
import sqlite3
from types import SimpleNamespace

import pytest

from app.services.direct_query import run_direct_query
from app.services.widget_data import clear_widget_data_cache

# 20 rows. Sales are deliberately all-positive and distinct, so ANY strict subset of
# them sums to strictly less than the true total -- a sampled total can never
# coincidentally equal the right answer.
REGIONS = ["US", "CA", "UK", "JP", "DE"]
ROWS = [(REGIONS[i % 5], (i + 1) * 10, i + 1) for i in range(20)]
TRUE_SALES_TOTAL = sum(r[1] for r in ROWS)   # 2100
TRUE_UNITS_TOTAL = sum(r[2] for r in ROWS)   # 210


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


@pytest.fixture
def sales_sqlite_source(tmp_path):
    db_path = tmp_path / "totals_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, sales REAL, units INTEGER)")
    conn.executemany("INSERT INTO sales (region, sales, units) VALUES (?, ?, ?)", ROWS)
    conn.commit()
    conn.close()
    return {"type": "sqlite", "filepath": str(db_path)}


def _dataset():
    return SimpleNamespace(
        source_table="sales", source_query=None,
        columns=[SimpleNamespace(name=c) for c in ("region", "sales", "units")],
    )


# ── row-capped raw table ──────────────────────────────────────────────────────

def test_raw_table_total_is_the_tables_total_not_the_samples(sales_sqlite_source):
    """row_cap=5 over 20 rows: the shaper sees a random 5-row sample whose sales sum
    is necessarily below 2100. The displayed total must still be 2100."""
    config = {"columns": ["region", "sales", "units"], "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="table", row_cap=5, cache_ttl_seconds=0,
    )

    assert result["sampled"] is True
    assert len(result["rows"]) == 5
    assert result["totals"] == [None, TRUE_SALES_TOTAL, TRUE_UNITS_TOTAL]
    # ...sitting under a truthful "Showing 5 of 20", which is the pairing that made a
    # sampled total actively misleading rather than merely approximate.
    assert result["total"] == 20


def test_raw_table_total_under_the_cap_is_computed_locally_and_is_identical(sales_sqlite_source):
    """Below the cap the fetched frame IS every matching row, so the shaper's own sums
    are already true and no second query is needed."""
    config = {"columns": ["region", "sales"], "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="table", cache_ttl_seconds=0,
    )

    assert result["sampled"] is False
    assert result["totals"] == [None, TRUE_SALES_TOTAL]


def test_raw_table_totals_respect_the_widgets_filter(sales_sqlite_source):
    """The totals query must carry the same WHERE the fetch did, or the total would
    describe rows the table is not showing."""
    config = {
        "columns": ["region", "sales"], "show_totals": True,
        "filters": [{"column": "region", "op": "eq", "value": "US"}],
    }

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="table", row_cap=2, cache_ttl_seconds=0,
    )

    us_total = sum(r[1] for r in ROWS if r[0] == "US")
    assert result["totals"] == [None, us_total]


def test_raw_table_without_show_totals_runs_no_totals_query(sales_sqlite_source):
    config = {"columns": ["region", "sales"]}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="table", row_cap=5, cache_ttl_seconds=0,
    )

    assert "totals" not in result
    assert "totals_unavailable" not in result


def test_sampled_grouped_table_suppresses_the_totals_row_and_says_so(sales_sqlite_source):
    """A table configured the way the Fields pane requires (Dimension set) shapes as a
    grouped series, and `_run_row_capped` plans no aggregation it could push down --
    so there is no true total available on this path. The row is DROPPED rather than
    shown wrong, and the client is told why so the author does not read a missing row
    as a checkbox that did nothing."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum", "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="table", row_cap=5, cache_ttl_seconds=0,
    )

    assert result["sampled"] is True
    assert "totals" not in result
    assert result["totals_unavailable"] == "sampled"


def test_unsampled_grouped_table_keeps_its_true_total(sales_sqlite_source):
    """Below the cap the same configuration has nothing to hide: every row was
    fetched, so the grouped total is the real one and no suppression note appears."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum", "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="table", cache_ttl_seconds=0,
    )

    assert result["sampled"] is False
    assert "totals_unavailable" not in result
    assert result["totals"] == [None, TRUE_SALES_TOTAL]


# ── aggregate pushdown (SQL LIMIT) ────────────────────────────────────────────

def test_pushed_down_grand_total_covers_groups_the_sql_limit_excluded(sales_sqlite_source):
    """build_sql pushes limit=2 into SQL, so the shaper only ever sees the top 2 of
    the 5 regions. The grand total must still describe all five."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 2, "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert len(result["rows"]) == 2
    assert sum(r["value"] for r in result["rows"]) < TRUE_SALES_TOTAL
    assert result["totals"] == [None, TRUE_SALES_TOTAL]


def test_pushed_down_grand_total_matches_the_unlimited_result(sales_sqlite_source):
    """The same query with no meaningful limit must produce the same total -- the
    total is a property of the table, not of how much of it is on screen."""
    base = {"dimension": "region", "measure": "sales", "aggregation": "sum", "show_totals": True}

    limited = run_direct_query(sales_sqlite_source, _dataset(), {**base, "limit": 2},
                               widget_type="crosstab", cache_ttl_seconds=0)
    full = run_direct_query(sales_sqlite_source, _dataset(), {**base, "limit": 50},
                            widget_type="crosstab", cache_ttl_seconds=0)

    assert limited["totals"] == full["totals"]


def test_pushed_down_grand_total_uses_the_configured_aggregation(sales_sqlite_source):
    """An avg total is the average of every ROW, aggregated in SQL at no grain.

    This test used to assert the opposite -- the SUM of the five per-region
    averages -- which is a number no reader means by "Total" and one that only
    agrees with the row-level answer for SUM and COUNT."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "avg",
              "limit": 2, "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert result["totals"][1] == pytest.approx(TRUE_SALES_TOTAL / len(ROWS))


def test_pushed_down_avg_total_on_uneven_groups_matches_import_mode(nullable_sqlite_source):
    """Uneven groups are where avg-of-avgs and avg-of-rows part: US has two rows,
    UK one. Both engines must give the row-level average of the non-null rows."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    config = {"dimension": "region", "measure": "sales", "aggregation": "avg",
              "limit": 50, "show_totals": True}

    direct = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )
    imported = get_widget_data_from_df(
        pd.DataFrame(NULL_ROWS, columns=["region", "sales"]), config, "crosstab",
    )

    non_null = [s for r, s in NULL_ROWS if r is not None]
    assert direct["totals"][1] == pytest.approx(sum(non_null) / len(non_null))
    assert direct["totals"][1] == pytest.approx(imported["totals"][1])


def test_pushed_down_total_reports_its_basis_and_the_shown_rows_total(sales_sqlite_source):
    """limit=2 of five regions: `totals` covers every row, `totals_shown` the rows of
    the two regions on screen -- aggregated from those rows, not from their cells."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "avg",
              "limit": 2, "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    shown = {r["name"] for r in result["rows"]}
    shown_sales = [s for reg, s, _ in ROWS if reg in shown]
    assert result["totals_shown"][1] == pytest.approx(sum(shown_sales) / len(shown_sales))
    assert result["totals_basis"] == {"unit": "groups", "shown": 2, "of": 5,
                                      "truncated": True, "suppressed_excluded": False}


def test_pushed_down_total_has_no_shown_total_when_every_group_is_shown(sales_sqlite_source):
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 50, "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert "totals_shown" not in result
    assert result["totals_basis"]["truncated"] is False
    assert result["totals_basis"]["of"] == 5


def test_count_series_reports_the_shown_rows_total(sales_sqlite_source):
    config = {"dimension": "region", "limit": 2, "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert result["totals"] == [None, len(ROWS)]
    assert result["totals_shown"] == [None, sum(r["value"] for r in result["rows"])]
    assert result["totals_basis"]["of"] == 5


def test_suppression_withholds_the_pushed_down_total(sales_sqlite_source):
    """The SQL total would include the suppressed groups' rows, so a reader could
    recover them as (total - visible cells). Withheld, with the reason."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 50, "show_totals": True, "suppress_below": 5}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert "totals" not in result
    assert result["totals_unavailable"] == "suppressed"


def test_pushed_down_count_series_total_covers_every_group(sales_sqlite_source):
    """The no-measure case takes its own COUNT(*)-per-group path, which also LIMITs
    in SQL and never went through the shaper at all."""
    config = {"dimension": "region", "limit": 2, "show_totals": True}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert len(result["rows"]) == 2
    assert result["totals"] == [None, len(ROWS)]


def test_aggregate_path_without_show_totals_emits_no_totals(sales_sqlite_source):
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum", "limit": 2}

    result = run_direct_query(
        sales_sqlite_source, _dataset(), config, widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert "totals" not in result


# ── NULL dimension values ─────────────────────────────────────────────────────
# SQL makes NULL a group of its own; pandas' groupby drops those rows. DirectQuery
# standardises on the pandas answer, because on the aggregate path the rendered rows
# are literally produced by pandas -- the pushed-down frame goes back through
# shape_series, which drops the NULL group before the widget sees it. A SQL total
# that counted it would describe rows the table does not show.

NULL_ROWS = [("US", 10.0), ("US", 20.0), ("CA", 30.0), ("UK", 90.0),
             (None, 60.0), (None, 70.0), ("CA", 0.0)]
NULL_FREE_TOTAL = sum(s for r, s in NULL_ROWS if r is not None)   # 150, not 280


@pytest.fixture
def nullable_sqlite_source(tmp_path):
    db_path = tmp_path / "nullable_totals.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, sales REAL)")
    conn.executemany("INSERT INTO sales (region, sales) VALUES (?, ?)", NULL_ROWS)
    conn.commit()
    conn.close()
    return {"type": "sqlite", "filepath": str(db_path)}


def _nullable_dataset():
    return SimpleNamespace(
        source_table="sales", source_query=None,
        columns=[SimpleNamespace(name=c) for c in ("region", "sales")],
    )


def test_aggregate_total_matches_the_rows_that_are_actually_rendered(nullable_sqlite_source):
    """limit=50, so nothing is truncated: the totals row must equal the sum of the
    rows on screen exactly. It used to read 280 under three rows summing to 150."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 50, "show_totals": True}

    result = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert [r["name"] for r in result["rows"]] == ["UK", "CA", "US"]
    assert result["totals"] == [None, sum(r["value"] for r in result["rows"])]
    assert result["totals"] == [None, NULL_FREE_TOTAL]


def test_count_series_neither_renders_nor_totals_a_null_group(nullable_sqlite_source):
    """The no-measure path builds its rows itself instead of routing them through
    shape_series, so it used to RENDER a nameless NULL group that import mode never
    shows. Both pushdown paths now agree that NULL is not a group."""
    config = {"dimension": "region", "limit": 50, "show_totals": True}

    result = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert None not in [r["name"] for r in result["rows"]]
    assert result["totals"] == [None, sum(r["value"] for r in result["rows"])]
    assert result["totals"] == [None, 5]


@pytest.mark.parametrize("config", [
    {"dimension": "region", "measure": "sales", "aggregation": "sum", "limit": 50, "show_totals": True},
    {"dimension": "region", "limit": 50, "show_totals": True},
])
def test_both_pushdown_paths_agree_with_import_mode_on_null_dimensions(nullable_sqlite_source, config):
    """The equivalence guarantee, stated over the one case the two engines disagreed
    about: same rendered group set, same total, whichever engine ran the query."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    direct = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )
    imported = get_widget_data_from_df(
        pd.DataFrame(NULL_ROWS, columns=["region", "sales"]), config, "crosstab",
    )

    # Compared row for row, NOT sorted. The sorted() this replaces hid a real
    # divergence: NULL_ROWS contains a 30-vs-30 tie between US and CA, and the two
    # engines ordered it differently until both were given the same tiebreak.
    assert [r["name"] for r in direct["rows"]] == [r["name"] for r in imported["rows"]]
    assert direct["totals"] == imported["totals"]


def test_a_widget_filter_still_narrows_a_null_excluding_total(nullable_sqlite_source):
    """The IS NOT NULL clause must sit alongside the widget's own WHERE, not replace it."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 50, "show_totals": True,
              "filters": [{"column": "region", "op": "eq", "value": "US"}]}

    result = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )

    assert result["totals"] == [None, 30.0]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_a_null_group_never_consumes_a_top_n_slot(nullable_sqlite_source, limit):
    """build_sql pushes `limit` into SQL. While NULL was still a SQL group it took a
    slot in the top-N and was then dropped by shape_series' pandas groupby, so the
    slot simply vanished: limit=2 rendered one row where import rendered two, and
    limit=1 rendered an EMPTY table beneath a non-zero total.

    NULL sums to 130 here, outranking every real group, so it claims the FIRST slot at
    every limit below -- without the fix limit=1 returns no rows at all, and each
    higher limit is short by exactly one.

    Row count and the unambiguous top group are asserted; the second and third places
    are a genuine 30-vs-30 tie between US and CA, whose ordering is a separate known
    issue, so pinning it here would make this test fail for an unrelated reason."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": limit, "show_totals": True}

    result = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )
    names = [r["name"] for r in result["rows"]]

    assert len(names) == limit
    assert names[0] == "UK"                       # 90, the only untied top group
    assert None not in names
    assert set(names) <= {"UK", "CA", "US"}


def test_a_limited_directquery_renders_the_same_rows_as_import_mode(nullable_sqlite_source):
    """The equivalence guarantee, restated where it used to break: once the limit
    bites. limit=1 avoids the US/CA tie, so any difference here is the vanished slot
    and nothing else."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 1, "show_totals": True}

    direct = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )
    imported = get_widget_data_from_df(
        pd.DataFrame(NULL_ROWS, columns=["region", "sales"]), config, "crosstab",
    )

    assert [r["name"] for r in direct["rows"]] == [r["name"] for r in imported["rows"]] == ["UK"]
    assert [r["value"] for r in direct["rows"]] == [r["value"] for r in imported["rows"]]


@pytest.mark.parametrize("config", [
    {"dimension": "region", "measure": "sales", "aggregation": "sum", "limit": 50, "show_totals": True},
    {"dimension": "region", "limit": 50, "show_totals": True},
])
def test_tied_groups_come_back_in_the_same_order_from_both_engines(nullable_sqlite_source, config):
    """US and CA both sum to 30 here. SQL leaves the order among equal values
    unspecified and pandas' default sort is quicksort, so neither side was
    deterministic and the two disagreed for identical data. Both now break ties on the
    dimension ascending, which is why CA precedes US.

    Asserted as an exact sequence on BOTH pushdown paths: a set or a sorted() comparison
    passes whatever the order is, which is precisely how this went unnoticed."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    direct = run_direct_query(
        nullable_sqlite_source, _nullable_dataset(), config,
        widget_type="crosstab", cache_ttl_seconds=0,
    )
    imported = get_widget_data_from_df(
        pd.DataFrame(NULL_ROWS, columns=["region", "sales"]), config, "crosstab",
    )

    assert [r["name"] for r in direct["rows"]] == [r["name"] for r in imported["rows"]]
    # The tie itself: CA before US, not merely "both present".
    names = [r["name"] for r in direct["rows"]]
    assert names.index("CA") < names.index("US")


def test_the_tie_order_is_stable_across_repeated_queries(nullable_sqlite_source):
    """Determinism is the actual claim -- a single run can agree by luck."""
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum",
              "limit": 50, "show_totals": True}
    seen = {
        tuple(r["name"] for r in run_direct_query(
            nullable_sqlite_source, _nullable_dataset(), config,
            widget_type="crosstab", cache_ttl_seconds=0,
        )["rows"])
        for _ in range(5)
    }
    assert len(seen) == 1, f"tie order varied between runs: {seen}"
