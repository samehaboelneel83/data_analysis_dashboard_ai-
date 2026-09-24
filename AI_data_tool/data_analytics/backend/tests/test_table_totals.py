import pandas as pd
import pytest

from app.services.widget_data import shape_series


def _df():
    return pd.DataFrame({
        "region": ["US", "CA", "UK", "JP", "DE"],
        "sales":  [100, 200, 300, 400, 500],
        "units":  [1, 2, 3, 4, 5],
    })


def test_no_totals_key_when_not_requested():
    result = shape_series(_df(), {"columns": ["region", "sales"]})

    assert "totals" not in result


def test_grand_total_sums_numeric_columns_and_blanks_text_ones():
    result = shape_series(_df(), {"columns": ["region", "sales"], "show_totals": True})

    assert result["columns"] == ["region", "sales"]
    assert result["totals"] == [None, 1500]


def test_grand_total_is_computed_before_the_row_limit_truncates():
    """The whole reason totals are server-side. With limit=2 the client only ever
    sees two rows, but the total must describe all five."""
    result = shape_series(_df(), {"columns": ["region", "sales"], "show_totals": True, "limit": 2})

    assert len(result["rows"]) == 2
    assert result["totals"] == [None, 1500]


def test_totals_cover_every_numeric_column():
    result = shape_series(_df(), {"columns": ["region", "sales", "units"], "show_totals": True})

    assert result["totals"] == [None, 1500, 15]


def _crosstab_df():
    return pd.DataFrame({
        "region":  ["US", "US", "CA", "CA"],
        "quarter": ["Q1", "Q2", "Q1", "Q2"],
        "sales":   [10, 20, 30, 40],
    })


def _cfg(**over):
    base = {"dimension": "region", "dimension2": "quarter", "measure": "sales", "aggregation": "sum"}
    base.update(over)
    return base


def test_row_subtotal_column_ships_by_default_so_existing_widgets_keep_it():
    result = shape_series(_crosstab_df(), _cfg())

    assert "__total__" in result["columns"]


def test_row_subtotal_column_can_be_turned_off():
    result = shape_series(_crosstab_df(), _cfg(show_subtotals=False))

    assert "__total__" not in result["columns"]


def test_no_grand_total_row_unless_requested():
    result = shape_series(_crosstab_df(), _cfg())

    assert "totals" not in result


def test_grand_total_row_sums_each_numeric_column():
    result = shape_series(_crosstab_df(), _cfg(show_totals=True))

    cols = result["columns"]
    totals = dict(zip(cols, result["totals"]))
    assert totals[cols[0]] is None          # the dimension column has no total
    assert totals["Q1"] == 40               # 10 + 30
    assert totals["Q2"] == 60               # 20 + 40
    assert totals["__total__"] == 100


# ── Totals in the configuration the Fields pane actually produces ──────────────
# ROLE_SPECS (frontend/src/types/report.ts) marks `category` REQUIRED for table,
# crosstab and matrix, and WidgetConfigPanel writes that role out as the legacy
# `dimension` key. So the moment an author fills the pane in the way it demands,
# shape_series takes its grouped-series branch -- not the raw-table branch. The
# tests above only ever exercised the raw-table branch, which is exactly why
# "Show totals" could be dead in the panel's own required configuration and still
# ship green. Every test below drives the panel's output shape.

def _panel_table_config(**over):
    """What WidgetConfigPanel.buildConfig emits for a table with the required
    Dimension (and optional Measure) filled in."""
    base = {"aggregation": "sum", "limit": 20, "sort": "desc", "sort_by": "value",
            "rtl": False, "dimension": "region", "measure": "sales"}
    base.update(over)
    return base


def test_show_totals_is_live_for_a_table_configured_with_the_required_dimension():
    result = shape_series(_df(), _panel_table_config(show_totals=True))

    assert result["type"] == "series"
    assert result["totals"] == [None, 1500]


def test_dimensioned_table_writes_no_totals_key_unless_asked():
    result = shape_series(_df(), _panel_table_config())

    assert "totals" not in result


def test_dimensioned_table_total_covers_groups_the_row_limit_hides():
    """Five regions, a limit of two: the visible page sums to 900, the table to 1500.
    A total describing only the page is worse than no total."""
    result = shape_series(_df(), _panel_table_config(show_totals=True, limit=2))

    assert [r["value"] for r in result["rows"]] == [500, 400]
    assert result["totals"] == [None, 1500]


def test_dimensioned_table_totals_align_with_the_renderer_columns():
    """WidgetRenderer builds a grouped table's columns from `Object.keys(rows[0])`,
    so `totals` has to be positionally aligned with those keys, and the dimension
    position must carry no number."""
    result = shape_series(_df(), _panel_table_config(show_totals=True))

    keys = list(result["rows"][0].keys())
    assert len(result["totals"]) == len(keys)
    assert result["totals"][keys.index("name")] is None
    assert result["totals"][keys.index("value")] == 1500


def test_dimensioned_table_with_no_measure_totals_the_row_counts():
    result = shape_series(_df(), _panel_table_config(show_totals=True, measure=None))

    assert result["totals"] == [None, 5]


def test_running_column_gets_no_total_of_its_own():
    """A running_sum is derived from the visible page only, so there is no honest
    grand total for that column -- it stays blank rather than repeating the value
    total under a different heading."""
    result = shape_series(_df(), _panel_table_config(show_totals=True, running="sum"))

    keys = list(result["rows"][0].keys())
    assert result["totals"][keys.index("running_sum")] is None
    assert result["totals"][keys.index("value")] == 1500


def test_crosstab_with_only_the_required_dimension_still_honours_show_totals():
    """A crosstab whose optional Column Pivot is left empty shapes as a series, not
    a pivot -- the branch where both totals keys used to be unreachable."""
    result = shape_series(_crosstab_df(), _cfg(dimension2=None, show_totals=True))

    assert result["type"] == "series"
    assert result["totals"] == [None, 100]


# ── Totals are aggregated from the ROWS, at their own grain ─────────────────────
# For sum and count, a total derived from the displayed cells and one aggregated
# from the rows agree -- which is why every test above, all on sum, could not tell
# the two apart. The fixture below is built so they DISAGREE: groups of unequal
# size (so the average of averages is not the average) and a customer that
# appears in both regions (so summed per-group distinct counts double-count it).

def _uneven_df():
    return pd.DataFrame({
        "region":   ["A", "A", "A", "B"],
        "quarter":  ["Q1", "Q1", "Q2", "Q1"],
        "sales":    [10.0, 20.0, 60.0, 100.0],
        "customer": ["c1", "c2", "c1", "c1"],
    })


def _grouped(**over):
    base = {"dimension": "region", "measure": "sales", "aggregation": "avg", "show_totals": True}
    base.update(over)
    return base


def test_avg_grand_total_is_the_average_of_every_row_not_of_the_group_averages():
    result = shape_series(_uneven_df(), _grouped())

    assert {r["name"]: r["value"] for r in result["rows"]} == {"A": 30.0, "B": 100.0}
    assert result["totals"] == [None, 47.5]     # (10+20+60+100)/4, not 130 or 65


def test_median_grand_total_is_the_median_of_every_row():
    result = shape_series(_uneven_df(), _grouped(aggregation="median"))

    assert result["totals"] == [None, 40.0]     # median(10,20,60,100), not 20+100


def test_distinct_count_grand_total_is_the_true_distinct_count():
    result = shape_series(_uneven_df(), _grouped(measure="customer", aggregation="countd"))

    assert {r["name"]: r["value"] for r in result["rows"]} == {"A": 2, "B": 1}
    assert result["totals"] == [None, 2]        # c1 and c2 -- not 2 + 1


def test_min_grand_total_is_the_smallest_row_not_the_sum_of_group_minimums():
    result = shape_series(_uneven_df(), _grouped(aggregation="min"))

    assert result["totals"] == [None, 10.0]


def test_crosstab_row_subtotal_is_that_rows_aggregate_not_the_sum_of_its_cells():
    result = shape_series(_uneven_df(), {"dimension": "region", "dimension2": "quarter",
                                         "measure": "sales", "aggregation": "avg"})

    rows = {r[0]: dict(zip(result["columns"], r)) for r in result["rows"]}
    assert rows["A"]["Q1"] == 15.0 and rows["A"]["Q2"] == 60.0
    assert rows["A"]["__total__"] == 30.0       # avg(10,20,60), not 15+60
    assert rows["B"]["__total__"] == 100.0


def test_crosstab_column_and_grand_totals_are_aggregated_from_the_rows():
    result = shape_series(_uneven_df(), {"dimension": "region", "dimension2": "quarter",
                                         "measure": "sales", "aggregation": "avg",
                                         "show_totals": True})

    totals = dict(zip(result["columns"], result["totals"]))
    assert totals["region"] is None
    assert totals["Q1"] == pytest.approx(130 / 3)   # avg(10,20,100), not 15+100
    assert totals["Q2"] == 60.0
    assert totals["__total__"] == 47.5              # every row -- not the sum of subtotals


def test_crosstab_distinct_count_totals_do_not_double_count():
    result = shape_series(_uneven_df(), {"dimension": "region", "dimension2": "quarter",
                                         "measure": "customer", "aggregation": "countd",
                                         "show_totals": True})

    rows = {r[0]: dict(zip(result["columns"], r)) for r in result["rows"]}
    totals = dict(zip(result["columns"], result["totals"]))
    assert rows["A"]["__total__"] == 2          # c1 is in both A's quarters
    assert totals["Q1"] == 2                    # c1 is in both regions' Q1
    assert totals["__total__"] == 2


def test_sum_totals_are_unchanged_by_aggregating_from_rows():
    """Sum is the case where both methods agree: guard that nothing moved."""
    result = shape_series(_crosstab_df(), _cfg(show_totals=True))

    totals = dict(zip(result["columns"], result["totals"]))
    assert (totals["Q1"], totals["Q2"], totals["__total__"]) == (40, 60, 100)


# ── What a total covers when the page shows only some groups ────────────────────

def test_total_declares_it_covers_all_rows_when_the_limit_hides_groups():
    result = shape_series(_df(), _panel_table_config(show_totals=True, limit=2,
                                                      aggregation="avg"))

    assert [r["name"] for r in result["rows"]] == ["DE", "JP"]
    assert result["totals"] == [None, 300.0]         # avg of all five rows
    assert result["totals_shown"] == [None, 450.0]   # avg of DE and JP's rows
    assert result["totals_basis"] == {"unit": "groups", "shown": 2, "of": 5,
                                      "truncated": True, "suppressed_excluded": False}


def test_no_shown_total_when_every_group_is_on_the_page():
    result = shape_series(_df(), _panel_table_config(show_totals=True))

    assert "totals_shown" not in result
    assert result["totals_basis"]["truncated"] is False


def test_rank_shown_total_is_aggregated_from_the_ranked_groups_rows():
    result = shape_series(_uneven_df(), _grouped(rank={"n": 1}))

    assert [r["name"] for r in result["rows"]] == ["B"]
    assert result["totals"] == [None, 47.5]
    assert result["totals_shown"] == [None, 100.0]


def test_all_other_bucket_counts_as_shown():
    """The Other row stands for the groups rank excluded, so a page showing it
    shows every row: the two totals are the same and nothing is truncated."""
    result = shape_series(_uneven_df(), _grouped(rank={"n": 1, "other": True}))

    assert [r["name"] for r in result["rows"]] == ["B", "All Other"]
    assert result["totals"] == [None, 47.5]
    assert result["totals_basis"]["truncated"] is False


def test_suppressed_groups_rows_are_left_out_of_the_total():
    """An all-rows total over a suppressed group would give its value back as
    (total - visible cells). B has one row, below the threshold of two."""
    result = shape_series(_uneven_df(), _grouped(aggregation="sum", suppress_below=2))

    assert [r["name"] for r in result["rows"]] == ["A"]
    assert result["totals"] == [None, 90.0]          # A's rows only, not 190
    assert result["totals_basis"]["suppressed_excluded"] is True


def test_quick_calcs_outside_the_measures_units_withhold_the_total():
    for qc in ("difference", "percent_change", "rank"):
        result = shape_series(_uneven_df(), _grouped(quick_calc=qc))

        assert "totals" not in result, qc
        assert result["totals_unavailable"] == "quick_calc", qc


def test_percent_of_total_quick_calc_totals_one_hundred():
    result = shape_series(_uneven_df(), _grouped(aggregation="sum", quick_calc="percent_of_total"))

    assert result["totals"] == [None, 100.0]


def test_measure_grand_total_is_re_evaluated_over_every_row():
    """A saved measure at no grain -- the crosstab already did this; the grouped
    table summed the per-group values instead."""
    df = pd.DataFrame({"region": ["A", "A", "B"], "rev": [30.0, 10.0, 60.0], "cost": [10.0, 10.0, 20.0]})
    measure = {"name": "margin", "expression": "(SUM(rev) - SUM(cost)) / SUM(rev) * 100"}

    result = shape_series(df, {"dimension": "region", "measure": "margin", "show_totals": True,
                               "measure_defs": [measure]})

    assert result["totals"][1] == pytest.approx((100 - 40) / 100 * 100)


# ── Creation-time defaults: new tables only ─────────────────────────────────────
# New tables are created with subtotals OFF and totals drawn BEFORE their data.
# Stamped at creation rather than applied at read time, so a table saved before
# this change keeps rendering exactly as it did (subtotals on, totals after).

async def _new_widget(client, headers, wtype, config):
    rep = (await client.post("/api/v1/reports", json={"name": "Totals"}, headers=headers)).json()
    r = await client.post(
        f"/api/v1/reports/{rep['id']}/pages/{rep['pages'][0]['id']}/widgets",
        json={"widget_type": wtype, "title": "t", "config": config,
              "layout": {"x": 0, "y": 0, "w": 6, "h": 4}},
        headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("wtype", ["table", "crosstab", "matrix"])
async def test_new_tables_are_created_with_the_current_totals_defaults(client, auth_headers, wtype):
    w = await _new_widget(client, auth_headers["a"], wtype, {"dimension": "region"})

    assert w["config"]["show_subtotals"] is False
    assert w["config"]["totals_position"] == "before"
    assert w["config"]["dimension"] == "region"


async def test_explicit_totals_settings_on_creation_win(client, auth_headers):
    """A duplicate of an older table sends its own values; they must survive."""
    w = await _new_widget(client, auth_headers["a"], "crosstab",
                          {"show_subtotals": True, "totals_position": "after"})

    assert w["config"]["show_subtotals"] is True
    assert w["config"]["totals_position"] == "after"


async def test_non_table_widgets_are_created_without_totals_keys(client, auth_headers):
    w = await _new_widget(client, auth_headers["a"], "bar", {"dimension": "region"})

    assert "show_subtotals" not in w["config"]
    assert "totals_position" not in w["config"]
