"""Integration tests: measures resolved through the full get_widget_data pipeline.

These use the file-based style of test_get_widget_data_rls.py so they exercise the
real load -> RLS -> filter -> calc-columns -> shaper path without async fixtures.
"""
import pandas as pd

from app.services.widget_data import get_widget_data, get_widget_data_from_df

MEASURES = [
    {"name": "Sales % of Total", "expression": "SUM(sales) / TOTAL(SUM(sales)) * 100"},
    {"name": "Profit Margin", "expression": "SUM(profit) / SUM(sales) * 100"},
]


def _csv(tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def _rows(tmp_path):
    return _csv(tmp_path, [
        {"region": "East", "sales": 100, "profit": 10},
        {"region": "East", "sales": 50, "profit": 5},
        {"region": "West", "sales": 200, "profit": 50},
        {"region": "West", "sales": 100, "profit": 10},
    ])


def test_bar_chart_measure_gives_percent_of_total_across_categories(tmp_path):
    result = get_widget_data(
        _rows(tmp_path),
        {"dimension": "region", "measure": "Sales % of Total"},
        widget_type="bar", measures=MEASURES, use_cache=False,
    )

    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert round(by_name["East"], 2) == 33.33     # 150 / 450
    assert round(by_name["West"], 2) == 66.67     # 300 / 450
    assert round(sum(by_name.values()), 1) == 100.0


def test_measure_recomputes_against_a_narrowed_filter_context(tmp_path):
    """The defining property of a post-aggregation measure: narrowing the filter
    context changes the denominator, so shares re-base to the visible rows."""
    result = get_widget_data(
        _rows(tmp_path),
        {
            "dimension": "region", "measure": "Sales % of Total",
            "filters": [{"column": "region", "op": "eq", "value": "West"}],
        },
        widget_type="bar", measures=MEASURES, use_cache=False,
    )

    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert list(by_name) == ["West"]
    assert round(by_name["West"], 2) == 100.0     # re-based to the filtered total


def test_ratio_measure_varies_by_group(tmp_path):
    result = get_widget_data(
        _rows(tmp_path),
        {"dimension": "region", "measure": "Profit Margin"},
        widget_type="bar", measures=MEASURES, use_cache=False,
    )

    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert round(by_name["East"], 2) == 10.0      # 15 / 150
    assert round(by_name["West"], 2) == 20.0      # 60 / 300


def test_kpi_measure_returns_a_single_scalar_with_no_dimension(tmp_path):
    result = get_widget_data(
        _rows(tmp_path),
        {"measure": "Profit Margin"},
        widget_type="kpi", measures=MEASURES, use_cache=False,
    )

    assert result["type"] == "scalar"
    assert round(result["rows"][0]["value"], 2) == 16.67   # 75 profit / 450 sales


def test_measure_is_applied_after_rls_so_it_cannot_leak_restricted_rows(tmp_path):
    """A measure must never see rows the caller's RLS rule excludes — the denominator
    has to come from the restricted row set only."""
    result = get_widget_data(
        _rows(tmp_path),
        {"dimension": "region", "measure": "Sales % of Total"},
        widget_type="bar", measures=MEASURES,
        rls_filter_expr="region == 'East'", use_cache=False,
    )

    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert list(by_name) == ["East"]
    assert round(by_name["East"], 2) == 100.0


def test_plain_column_measure_still_uses_the_existing_aggregation_path(tmp_path):
    """No regression: a measure role naming a real column behaves exactly as before."""
    result = get_widget_data(
        _rows(tmp_path),
        {"dimension": "region", "measure": "sales", "aggregation": "sum"},
        widget_type="bar", measures=MEASURES, use_cache=False,
    )

    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert by_name == {"West": 300, "East": 150}


def test_a_column_named_like_nothing_and_no_measures_is_unchanged(tmp_path):
    """Passing measures=None must not alter existing behaviour at all."""
    result = get_widget_data(
        _rows(tmp_path),
        {"dimension": "region", "measure": "sales", "aggregation": "sum"},
        widget_type="bar", use_cache=False,
    )

    assert {r["name"] for r in result["rows"]} == {"East", "West"}


def test_broken_measure_expression_surfaces_an_error_not_a_wrong_number(tmp_path):
    result = get_widget_data(
        _rows(tmp_path),
        {"dimension": "region", "measure": "Bad"},
        widget_type="bar",
        measures=[{"name": "Bad", "expression": "SUM(nonexistent_column)"}],
        use_cache=False,
    )

    assert result["type"] == "error"
    assert "nonexistent_column" in result["message"]


def test_cache_key_separates_two_different_expressions_under_one_measure_name(tmp_path):
    """Editing a measure's expression must invalidate the cached result, otherwise a
    stale value would be served under the same measure name."""
    path = _rows(tmp_path)
    cfg = {"dimension": "region", "measure": "M"}

    first = get_widget_data(path, cfg, widget_type="bar",
                            measures=[{"name": "M", "expression": "SUM(sales)"}])
    second = get_widget_data(path, cfg, widget_type="bar",
                             measures=[{"name": "M", "expression": "SUM(profit)"}])

    assert {r["name"]: r["value"] for r in first["rows"]} == {"West": 300, "East": 150}
    assert {r["name"]: r["value"] for r in second["rows"]} == {"West": 60, "East": 15}


# ── Measures on crosstab intersections and the multi-measure card ────────────

def _mdf():
    return pd.DataFrame({
        "region": ["N", "N", "S", "S"],
        "chan": ["web", "store", "web", "store"],
        "sales": [10.0, 30.0, 20.0, 40.0],
        "cost": [5.0, 10.0, 5.0, 20.0],
    })


MARGIN = [{"name": "margin_pct", "expression": "(SUM(sales) - SUM(cost)) / SUM(sales) * 100"}]


def test_crosstab_evaluates_a_measure_per_intersection():
    r = get_widget_data_from_df(_mdf(), {
        "dimension": "region", "dimension2": "chan", "measure": "margin_pct",
        "show_subtotals": True, "show_totals": True,
    }, "crosstab", measures=MARGIN)
    assert r["type"] == "crosstab"
    cols = r["columns"]
    rows = {row[0]: dict(zip(cols[1:], row[1:])) for row in r["rows"]}
    # N/web: (10-5)/10 = 50%; N/store: (30-10)/30 = 66.67; S/web: 75; S/store: 50
    assert abs(rows["N"]["web"] - 50) < 0.01
    assert abs(rows["S"]["web"] - 75) < 0.01
    # Row subtotal is the measure RE-EVALUATED at the row grain, not a cell sum:
    # N: (40-15)/40 = 62.5 — the sum of cells (116.67) would be nonsense.
    assert abs(rows["N"]["__total__"] - 62.5) < 0.01
    # Column totals at the column grain; grand total at no grain.
    totals = dict(zip(cols, r["totals"]))
    assert abs(totals["web"] - ((30 - 10) / 30 * 100)) < 0.01
    assert abs(totals["__total__"] - ((100 - 40) / 100 * 100)) < 0.01


def test_card_mixes_columns_and_measures():
    r = get_widget_data_from_df(_mdf(), {
        "roles": {"measures": ["sales", "margin_pct"]},
    }, "card", measures=MARGIN)
    rows = {x["name"]: x["value"] for x in r["rows"]}
    assert rows["sales"] == 100
    assert abs(rows["margin_pct"] - 60) < 0.01  # (100-40)/100


def test_a_measure_that_names_the_grouping_column_still_charts(tmp_path):
    """`% of rows by region` grouped BY region.

    The natural quick calculation for a category refers to that same column:
    `COUNT(region) / TOTAL(COUNT(region)) * 100`. Evaluated at the region grain
    pandas names the resulting Series after the column, and `reset_index()` then
    tries to insert an index column called `region` beside a value column
    already called `region` -- "cannot insert region, already exists". The
    widget returned an error, or silently no rows at all when no aggregation was
    set. Found by charting one on the running server.
    """
    path = _csv(tmp_path, [
        {"region": "N", "sales": 1.0}, {"region": "N", "sales": 2.0},
        {"region": "S", "sales": 3.0}, {"region": "E", "sales": 4.0},
    ])
    measures = [{"name": "Share of rows",
                 "expression": "COUNT(region) / TOTAL(COUNT(region)) * 100"}]
    result = get_widget_data(path, {"dimension": "region", "measure": "Share of rows"},
                             widget_type="bar", measures=measures, use_cache=False)

    assert result.get("type") != "error", result
    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert by_name == {"N": 50.0, "S": 25.0, "E": 25.0}
    assert round(sum(by_name.values()), 6) == 100.0


def test_a_measure_named_value_does_not_collide_either(tmp_path):
    # The same defect wearing the other hat: the shaper's own output column is
    # called "value", so a dimension of that name must not clash with it.
    path = _csv(tmp_path, [{"value": "N", "sales": 1.0}, {"value": "S", "sales": 3.0}])
    measures = [{"name": "Total sales", "expression": "SUM(sales)"}]
    result = get_widget_data(path, {"dimension": "value", "measure": "Total sales"},
                             widget_type="bar", measures=measures, use_cache=False)
    assert result.get("type") != "error", result
    assert {r["name"]: r["value"] for r in result["rows"]} == {"N": 1.0, "S": 3.0}


def test_a_plain_dimension_named_value_charts_too(tmp_path):
    """Not a measure problem at all, as it turned out.

    `value` is the ordinary name of the value column in long-format data, and
    every aggregation refused it -- sum, count, everything -- because the
    shaper's own output column has that name and `reset_index` will not insert
    a second one. The dimension now travels under an internal name inside the
    shaper and is emitted under its real one.
    """
    path = _csv(tmp_path, [{"value": "N", "sales": 1.0}, {"value": "S", "sales": 3.0},
                           {"value": "N", "sales": 5.0}])
    summed = get_widget_data(path, {"dimension": "value", "measure": "sales",
                                    "aggregation": "sum"},
                             widget_type="bar", use_cache=False)
    assert summed.get("type") != "error", summed
    assert {r["name"]: r["value"] for r in summed["rows"]} == {"N": 6.0, "S": 3.0}

    counted = get_widget_data(path, {"dimension": "value", "aggregation": "count"},
                              widget_type="bar", use_cache=False)
    assert {r["name"]: r["value"] for r in counted["rows"]} == {"N": 2.0, "S": 1.0}
