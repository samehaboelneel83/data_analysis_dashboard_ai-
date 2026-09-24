import pytest

from app.services.display_rules import MAX_EXPRESSION_LENGTH, MAX_RULES, evaluate_rules, result_frame


def _series_result():
    return {
        "type": "series", "dimension": "region", "measure": "sales",
        "rows": [{"name": "US", "value": 1500}, {"name": "CA", "value": 400}],
        "total": 2,
    }


def test_result_frame_lifts_series_rows_to_name_and_value_columns():
    frame = result_frame(_series_result())

    assert list(frame.columns) == ["name", "value"]
    assert list(frame["value"]) == [1500, 400]


def _waterfall_result():
    # shape_waterfall (backend/app/services/widget_data.py) keys its per-bar data as
    # "bars", not "rows" -- result_frame's generic "rows and isinstance(rows[0], dict)"
    # fallback branch never sees it, so a mark rule on a waterfall widget always fell
    # through as if 0 rows existed. WaterfallChartRenderer's <Cell> was already wired
    # for ruleStyles.rows (see fill={ruleStyles?.rows?.[i]?.fill ?? ...}) but that
    # wiring was inert until result_frame recognises this shape too.
    return {
        "type": "waterfall", "category": "region", "measure": "sales",
        "bars": [
            {"name": "US", "start": 0, "delta": 1500, "end": 1500},
            {"name": "CA", "start": 1500, "delta": -400, "end": 1100},
        ],
        "grand_total": 1100, "total": 2,
    }


def test_result_frame_lifts_waterfall_bars_to_a_frame():
    frame = result_frame(_waterfall_result())

    assert list(frame.columns) == ["name", "start", "delta", "end"]
    assert list(frame["delta"]) == [1500, -400]


def test_result_frame_returns_none_for_a_waterfall_result_with_no_bars():
    assert result_frame({"type": "waterfall", "bars": []}) is None


def test_expression_rule_styles_a_waterfall_bar_by_its_delta():
    rules = [{
        "id": "r1", "kind": "expression", "target": "mark",
        "expression": "delta < 0", "style": {"fill": "#f87171"},
    }]

    styles = evaluate_rules(_waterfall_result(), rules)

    assert styles["rows"] == [None, {"fill": "#f87171"}]
    assert styles["errors"] == []


def test_expression_rule_styles_only_the_matching_mark():
    rules = [{
        "id": "r1", "kind": "expression", "target": "mark",
        "expression": "value > 1000", "style": {"fill": "#f87171"},
    }]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert styles["errors"] == []


def test_later_rule_wins_for_the_same_mark():
    rules = [
        {"id": "report", "kind": "expression", "target": "mark",
         "expression": "value > 100", "style": {"fill": "#aaa"}},
        {"id": "widget", "kind": "expression", "target": "mark",
         "expression": "value > 1000", "style": {"fill": "#f87171"}},
    ]

    styles = evaluate_rules(_series_result(), rules)

    # Report rules are sent first, so a widget rule overriding one is just list order.
    assert styles["rows"] == [{"fill": "#f87171"}, {"fill": "#aaa"}]


def test_no_rules_produces_no_styles():
    styles = evaluate_rules(_series_result(), [])

    assert styles["rows"] == [None, None]
    assert styles["widget"] == {}


def test_rule_naming_a_missing_column_is_reported_and_others_still_apply():
    rules = [
        {"id": "broken", "kind": "expression", "target": "mark",
         "expression": "revneue > 1", "style": {"fill": "#000"}},
        {"id": "good", "kind": "expression", "target": "mark",
         "expression": "value > 1000", "style": {"fill": "#f87171"}},
    ]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert [e["id"] for e in styles["errors"]] == ["broken"]


def test_malformed_rule_leaves_the_widget_data_intact():
    """The assertion that separates display rules from RLS: a broken cosmetic rule must
    NOT blank the widget. apply_rls_filter fails closed to zero rows; this fails open."""
    result = _series_result()
    rules = [{"id": "bad", "kind": "expression", "target": "mark",
              "expression": "value >>> ", "style": {"fill": "#000"}}]

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [None, None]
    assert len(styles["errors"]) == 1
    assert result["rows"] == [{"name": "US", "value": 1500}, {"name": "CA", "value": 400}]


@pytest.mark.parametrize("expression", [
    "value.__globals__",
    "`value`.to_csv('/tmp/x')",
    "@value",
])
def test_injection_attempts_are_rejected_through_the_rule_path(expression):
    rules = [{"id": "evil", "kind": "expression", "target": "mark",
              "expression": expression, "style": {"fill": "#000"}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, None]
    assert len(styles["errors"]) == 1


def test_value_map_colours_marks_by_category_value():
    rules = [{
        "id": "r1", "kind": "value_map", "target": "mark", "column": "name",
        "mappings": [{"value": "US", "color": "#6c8fff"}, {"value": "CA", "color": "#34d399"}],
    }]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#6c8fff"}, {"fill": "#34d399"}]


def test_value_map_leaves_unmapped_values_unstyled():
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "column": "name",
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#6c8fff"}, None]


def test_any_category_mode_matches_without_naming_a_column():
    """SAS's Any Category: one mapping applies across every category column in the
    result, so a region colour stays the same colour wherever region appears."""
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "any_category": True,
              "mappings": [{"value": "CA", "color": "#34d399"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, {"fill": "#34d399"}]


def test_value_map_needs_no_expression_and_never_errors_on_one():
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "column": "name",
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["errors"] == []


def test_matching_rule_with_no_style_leaves_the_mark_unstyled():
    """A rule that matches but carries nothing to paint resolves to None, not {}.
    None means "no style resolved for this mark" — the distinction is deliberate, so
    do not restore the older behaviour of merging an empty style onto the row."""
    rules = [{"id": "r1", "kind": "expression", "target": "mark",
              "expression": "value > 1000", "style": {}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, None]
    assert styles["errors"] == []


def _gauge_result():
    return {"type": "gauge", "measure": "attainment", "value": 72, "target": 100, "total": 5}


def test_interval_rule_picks_the_band_containing_the_gauge_value():
    rules = [{"id": "r1", "kind": "interval", "target": "mark", "column": "value", "bands": [
        {"min": 0,  "max": 60,  "color": "#f87171"},
        {"min": 60, "max": 85,  "color": "#fbbf24"},
        {"min": 85, "max": 100, "color": "#34d399"},
    ]}]

    styles = evaluate_rules(_gauge_result(), rules)

    assert styles["rows"] == [{"fill": "#fbbf24"}]


def test_bands_are_lower_inclusive_and_upper_exclusive():
    rules = [{"id": "r1", "kind": "interval", "column": "value", "target": "mark", "bands": [
        {"min": 0,  "max": 60, "color": "#f87171"},
        {"min": 60, "max": 85, "color": "#fbbf24"},
    ]}]
    result = {"type": "gauge", "measure": "m", "value": 60, "target": 100, "total": 1}

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [{"fill": "#fbbf24"}]


def test_top_of_range_lands_in_the_last_band_rather_than_falling_through():
    """The final band's upper bound is inclusive, so a value equal to the maximum is
    coloured instead of rendering unstyled — the same closed-top-interval choice the
    numeric binning generator already makes."""
    rules = [{"id": "r1", "kind": "interval", "column": "value", "target": "mark", "bands": [
        {"min": 0,  "max": 60,  "color": "#f87171"},
        {"min": 60, "max": 100, "color": "#34d399"},
    ]}]
    result = {"type": "gauge", "measure": "m", "value": 100, "target": 100, "total": 1}

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [{"fill": "#34d399"}]


def test_value_outside_every_band_is_unstyled():
    rules = [{"id": "r1", "kind": "interval", "column": "value", "target": "mark",
              "bands": [{"min": 0, "max": 50, "color": "#f87171"}]}]
    result = {"type": "gauge", "measure": "m", "value": 90, "target": 100, "total": 1}

    styles = evaluate_rules(result, rules)

    assert styles["rows"] == [None]


def _table_result():
    return {
        "type": "table",
        "columns": ["region", "sales", "margin"],
        "rows": [["US", 1500, 0.4], ["CA", 400, 0.1]],
        "total": 2,
    }


def test_rule_with_a_column_styles_that_cell_only():
    rules = [{"id": "r1", "kind": "expression", "target": "mark", "column": "sales",
              "expression": "sales > 1000", "style": {"fill": "#f87171"}}]

    styles = evaluate_rules(_table_result(), rules)

    assert styles["cells"] == {"0": {"sales": {"fill": "#f87171"}}}
    assert styles["rows"] == [None, None]


def test_rule_without_a_column_styles_the_whole_row():
    rules = [{"id": "r1", "kind": "expression", "target": "mark",
              "expression": "sales > 1000", "style": {"fill": "#f87171"}}]

    styles = evaluate_rules(_table_result(), rules)

    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert styles["cells"] == {}


def test_crosstab_columns_are_addressable_by_name():
    result = {"type": "crosstab", "columns": ["region", "Q1", "Q2", "__total__"],
              "rows": [["US", 10, 90, 100], ["CA", 5, 5, 10]], "total": 2}
    rules = [{"id": "r1", "kind": "expression", "target": "mark", "column": "Q2",
              "expression": "Q2 > 50", "style": {"fill": "#34d399"}}]

    styles = evaluate_rules(result, rules)

    assert styles["cells"] == {"0": {"Q2": {"fill": "#34d399"}}}


def test_background_target_sets_a_widget_level_style_not_a_row_style():
    rules = [{"id": "r1", "kind": "expression", "target": "background",
              "expression": "value > 1000", "style": {"background": "#fee2e2"}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["widget"] == {"background": "#fee2e2"}
    assert styles["rows"] == [None, None]


def test_visibility_target_hides_the_widget_when_the_rule_matches():
    rules = [{"id": "r1", "kind": "expression", "target": "visibility",
              "expression": "value > 1000", "style": {}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["widget"]["hidden"] is True


def test_visibility_rule_that_matches_nothing_leaves_the_widget_visible():
    rules = [{"id": "r1", "kind": "expression", "target": "visibility",
              "expression": "value > 99999", "style": {}}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["widget"].get("hidden", False) is False


def test_widget_level_rules_use_any_row_matching():
    """A widget-level rule is a statement about the widget, so one qualifying mark is
    enough. Scalar and gauge results have exactly one row, making this a no-op there."""
    result = {"type": "series", "rows": [{"name": "A", "value": 1}, {"name": "B", "value": 5000}],
              "total": 2}
    rules = [{"id": "r1", "kind": "expression", "target": "background",
              "expression": "value > 1000", "style": {"background": "#fee2e2"}}]

    styles = evaluate_rules(result, rules)

    assert styles["widget"] == {"background": "#fee2e2"}


# ── hardening: rules are attacker-choosable client input ───────────────────────

def test_rule_list_beyond_the_cap_is_truncated_and_recorded_as_an_error():
    rules = [
        {"id": f"r{i}", "kind": "expression", "target": "mark",
         "expression": "value > 0", "style": {"fill": "#f87171"}}
        for i in range(MAX_RULES + 5)
    ]

    styles = evaluate_rules(_series_result(), rules)

    # Every row still matches the (truncated) rule set -- the cap is not a blank, it's
    # fail-open consistent with every other error path in this module.
    assert styles["rows"] == [{"fill": "#f87171"}, {"fill": "#f87171"}]
    assert any("5 rule(s)" in e["message"] for e in styles["errors"])


def test_rule_list_at_exactly_the_cap_is_not_flagged():
    rules = [
        {"id": f"r{i}", "kind": "expression", "target": "mark",
         "expression": "value > 0", "style": {"fill": "#f87171"}}
        for i in range(MAX_RULES)
    ]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["errors"] == []


def test_oversized_expression_is_rejected_as_a_per_rule_error_not_evaluated():
    rules = [
        {"id": "huge", "kind": "expression", "target": "mark",
         "expression": "value > 0 or " * (MAX_EXPRESSION_LENGTH // 12), "style": {"fill": "#000"}},
        {"id": "good", "kind": "expression", "target": "mark",
         "expression": "value > 1000", "style": {"fill": "#f87171"}},
    ]

    styles = evaluate_rules(_series_result(), rules)

    # The oversized rule fails open (no style, an error recorded) without blocking the
    # well-formed rule after it in the list.
    assert styles["rows"] == [{"fill": "#f87171"}, None]
    assert [e["id"] for e in styles["errors"]] == ["huge"]


def test_value_map_naming_a_column_the_result_lacks_records_an_error():
    """Every other rule kind raises when it names a missing column, so the failure
    lands in `errors` and the author can act on it. value_map used to be the one kind
    that returned None for every row instead: a rule that had silently stopped
    applying (row subtotals turned off, a column dropped from a raw table) looked
    exactly like one that matched nothing. Fail-open is unchanged -- the rule is
    recorded, not raised."""
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "column": "region",
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, None]
    assert [e["id"] for e in styles["errors"]] == ["r1"]
    assert "region" in styles["errors"][0]["message"]


def test_a_broken_value_map_rule_still_lets_every_other_rule_apply():
    """The fail-open contract, now that value_map can fail at all."""
    rules = [
        {"id": "broken", "kind": "value_map", "target": "mark", "column": "nope",
         "mappings": [{"value": "US", "color": "#000000"}]},
        {"id": "ok", "kind": "value_map", "target": "mark", "column": "name",
         "mappings": [{"value": "US", "color": "#6c8fff"}]},
    ]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [{"fill": "#6c8fff"}, None]
    assert [e["id"] for e in styles["errors"]] == ["broken"]


def test_value_map_with_no_column_selected_records_an_error():
    rules = [{"id": "r1", "kind": "value_map", "target": "mark",
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert len(styles["errors"]) == 1


def test_any_category_mode_is_unaffected_by_the_missing_column_check():
    """any_category never reads `column`, so it must not have gained a failure mode."""
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "any_category": True,
              "column": "not_in_the_result",
              "mappings": [{"value": "CA", "color": "#34d399"}]}]

    styles = evaluate_rules(_series_result(), rules)

    assert styles["rows"] == [None, {"fill": "#34d399"}]
    assert styles["errors"] == []
