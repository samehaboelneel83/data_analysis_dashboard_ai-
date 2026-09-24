"""Characterization tests for the value_map and interval rule paths.

Written against the ORIGINAL per-row implementation and confirmed green BEFORE those
paths were vectorized, so they are a true before/after fixture rather than a
restatement of whatever the rewrite happens to do. That ordering matters more here
than usual: display rules fail OPEN (see the module docstring of
app.services.display_rules), so a vectorized path that quietly stops matching, or
quietly stops raising, produces no visible symptom at all -- no exception, no blank
widget, just marks that silently render unstyled. These tests are the only thing
standing between that and a shipped regression.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.display_rules import _rule_row_styles, evaluate_rules


def _styles(rule, frame):
    return _rule_row_styles(rule, frame)


def _interval(bands, column="value", **extra):
    return {"id": "r1", "kind": "interval", "target": "mark", "column": column,
            "bands": bands, **extra}


def _value_map(mappings, **extra):
    return {"id": "r1", "kind": "value_map", "target": "mark",
            "mappings": mappings, **extra}


_BANDS = [
    {"min": 0, "max": 50, "color": "#f87171"},
    {"min": 50, "max": 100, "color": "#34d399"},
]


# --------------------------------------------------------------------------
# interval: missing / non-numeric cells
# --------------------------------------------------------------------------

def test_interval_nan_and_none_cells_mixed_with_valid_ones_are_unstyled():
    frame = pd.DataFrame({"value": [10.0, np.nan, 60.0, None]})

    assert _styles(_interval(_BANDS), frame) == [
        {"fill": "#f87171"}, None, {"fill": "#34d399"}, None,
    ]


def test_interval_column_that_is_entirely_nan_is_all_unstyled_and_does_not_raise():
    frame = pd.DataFrame({"value": [np.nan, np.nan, np.nan]})

    assert _styles(_interval(_BANDS), frame) == [None, None, None]


def test_interval_on_an_object_column_of_none_is_unstyled_not_an_error():
    frame = pd.DataFrame({"value": pd.Series([None, None], dtype=object)})

    assert _styles(_interval(_BANDS), frame) == [None, None]


def test_interval_on_a_non_numeric_column_still_raises():
    """The raise is how an author discovers the rule is pointed at a text column.
    A vectorized path that coerced with errors="coerce" would turn every row into a
    silent no-match -- fail-open means that regression is completely invisible."""
    frame = pd.DataFrame({"value": ["alpha", "beta"]})

    with pytest.raises(ValueError):
        _styles(_interval(_BANDS), frame)


def test_interval_on_a_mixed_numeric_and_text_column_still_raises():
    frame = pd.DataFrame({"value": pd.Series([10, "not a number", 60], dtype=object)})

    with pytest.raises(ValueError):
        _styles(_interval(_BANDS), frame)


def test_interval_reads_numeric_strings_the_way_float_does():
    frame = pd.DataFrame({"value": ["10", "60"]})

    assert _styles(_interval(_BANDS), frame) == [{"fill": "#f87171"}, {"fill": "#34d399"}]


def test_interval_naming_an_absent_column_raises_for_a_non_empty_frame():
    frame = pd.DataFrame({"value": [1.0]})

    with pytest.raises(ValueError, match="not in the result"):
        _styles(_interval(_BANDS, column="nope"), frame)


def test_interval_with_a_falsy_column_falls_back_to_the_value_column():
    frame = pd.DataFrame({"value": [10.0]})

    assert _styles(_interval(_BANDS, column=""), frame) == [{"fill": "#f87171"}]


# --------------------------------------------------------------------------
# interval: zero rows
# --------------------------------------------------------------------------

def test_interval_on_an_empty_frame_returns_no_styles():
    frame = pd.DataFrame({"value": pd.Series([], dtype=float)})

    assert _styles(_interval(_BANDS), frame) == []


def test_interval_on_an_empty_frame_does_not_raise_for_an_absent_column():
    """Nothing checks the column until a row asks for it, so a zero-row result is
    silent rather than erroring. Vectorizing hoists work out of the per-row loop and
    it would be easy to hoist this check with it, inventing an error that the
    author never used to see."""
    frame = pd.DataFrame({"value": pd.Series([], dtype=float)})

    assert _styles(_interval(_BANDS, column="absent"), frame) == []


def test_interval_on_an_empty_frame_does_not_raise_for_a_malformed_band():
    frame = pd.DataFrame({"value": pd.Series([], dtype=float)})

    assert _styles(_interval([{"min": None, "max": 5, "color": "#f00"}]), frame) == []


# --------------------------------------------------------------------------
# interval: band boundaries and ordering
# --------------------------------------------------------------------------

def test_interval_bands_are_lower_inclusive_and_upper_exclusive():
    frame = pd.DataFrame({"value": [0.0, 49.999, 50.0]})

    assert _styles(_interval(_BANDS), frame) == [
        {"fill": "#f87171"}, {"fill": "#f87171"}, {"fill": "#34d399"},
    ]


def test_interval_last_band_upper_bound_is_inclusive():
    frame = pd.DataFrame({"value": [100.0]})

    assert _styles(_interval(_BANDS), frame) == [{"fill": "#34d399"}]


def test_interval_a_non_final_band_upper_bound_stays_exclusive():
    """Only the LAST band closes its top. The first band's max must keep falling
    through to the next band, or every boundary value would land one band too low."""
    frame = pd.DataFrame({"value": [50.0]})

    assert _styles(_interval(_BANDS), frame) == [{"fill": "#34d399"}]


def test_interval_value_above_every_band_is_unstyled():
    frame = pd.DataFrame({"value": [100.01, -1.0]})

    assert _styles(_interval(_BANDS), frame) == [None, None]


def test_interval_overlapping_bands_resolve_to_the_first_match():
    bands = [
        {"min": 0, "max": 100, "color": "#first"},
        {"min": 0, "max": 100, "color": "#second"},
    ]
    frame = pd.DataFrame({"value": [10.0, 20.0]})

    assert _styles(_interval(bands), frame) == [{"fill": "#first"}, {"fill": "#first"}]


def test_interval_first_match_wins_even_when_a_later_band_closes_its_top():
    """A value equal to an overlapping later band's max must still take the earlier
    band, so the inclusive-top rule can never reorder first-match-wins."""
    bands = [
        {"min": 0, "max": 100, "color": "#first"},
        {"min": 40, "max": 50, "color": "#second"},
    ]
    frame = pd.DataFrame({"value": [50.0]})

    assert _styles(_interval(bands), frame) == [{"fill": "#first"}]


def test_interval_with_no_bands_leaves_everything_unstyled():
    frame = pd.DataFrame({"value": [1.0, 2.0]})

    assert _styles(_interval([]), frame) == [None, None]


def test_interval_band_bounds_are_only_coerced_when_a_row_reaches_them():
    """Band bounds are read inside the per-row scan, so a malformed band that every
    row matches before reaching is never coerced and never raises. Coercing all the
    bands up front would turn a working rule into a recorded error."""
    bands = [
        {"min": 0, "max": 100, "color": "#ok"},
        {"min": None, "max": 200, "color": "#broken"},
    ]
    frame = pd.DataFrame({"value": [10.0, 20.0]})

    assert _styles(_interval(bands), frame) == [{"fill": "#ok"}, {"fill": "#ok"}]


def test_interval_a_malformed_band_that_a_row_does_reach_raises():
    bands = [
        {"min": 0, "max": 100, "color": "#ok"},
        {"min": None, "max": 200, "color": "#broken"},
    ]
    frame = pd.DataFrame({"value": [10.0, 150.0]})

    with pytest.raises(TypeError):
        _styles(_interval(bands), frame)


def test_interval_nan_rows_never_reach_a_malformed_band():
    bands = [{"min": None, "max": 200, "color": "#broken"}]
    frame = pd.DataFrame({"value": [np.nan]})

    assert _styles(_interval(bands), frame) == [None]


def test_interval_band_colour_may_be_absent_and_still_resolves_a_style():
    frame = pd.DataFrame({"value": [10.0]})

    assert _styles(_interval([{"min": 0, "max": 50}]), frame) == [{"fill": None}]


def test_interval_band_icon_is_carried_into_the_resolved_style():
    """Power-BI-style icon sets: a band may carry an icon glyph alongside its
    colour. Only added to the style dict when the band actually has one --
    every existing interval test above asserts an exact `{"fill": ...}` dict
    with no `icon` key, and an unconditional `icon: None` would have broken
    every one of them for a feature they never opted into."""
    bands = [{"min": 0, "max": 50, "color": "#f87171", "icon": "⚠️"}]
    frame = pd.DataFrame({"value": [10.0]})

    assert _styles(_interval(bands), frame) == [{"fill": "#f87171", "icon": "⚠️"}]


def test_interval_band_with_no_icon_omits_the_icon_key():
    """The negative case for the test above: a band with no icon must not gain
    one, so an unstyled/no-icon widget renders exactly as it always has."""
    bands = [{"min": 0, "max": 50, "color": "#f87171"}]
    frame = pd.DataFrame({"value": [10.0]})

    assert _styles(_interval(bands), frame) == [{"fill": "#f87171"}]


# --------------------------------------------------------------------------
# value_map
# --------------------------------------------------------------------------

def test_value_map_stringifies_both_operands():
    """A numeric cell matches a string mapping and vice versa -- the editor stores
    mapping values as whatever the category picker produced."""
    frame = pd.DataFrame({"name": ["x"], "code": [1]})

    assert _styles(_value_map([{"value": "1", "color": "#hit"}], column="code"),
                   frame) == [{"fill": "#hit"}]


def test_value_map_matches_a_string_cell_against_a_numeric_mapping_value():
    frame = pd.DataFrame({"code": ["1"], "name": ["x"]})

    assert _styles(_value_map([{"value": 1, "color": "#hit"}], column="code"),
                   frame) == [{"fill": "#hit"}]


def test_value_map_matching_does_not_depend_on_columns_the_rule_never_names():
    """This assertion was INVERTED when it was written, and pinned a bug on purpose.

    The per-row form read a cell as frame.iloc[i][column]. That row lookup builds a
    Series across every column, so an all-numeric frame upcast an int64 column to
    float and stringified it "1.0" -- which did not match a mapping value of 1. Put
    the same column next to a text column and the common dtype became object, the int
    survived, and the identical rule matched. Whether a colour rule worked therefore
    depended on the dtypes of columns it never mentioned.

    The vectorized rewrite reproduced that deliberately, so a performance change could
    not quietly alter which results match. This is the separate, visible change that
    fixes it: the comparison now reads the named column and nothing else, so both
    frames below behave the same way."""
    all_numeric = pd.DataFrame({"code": [1], "amount": [1.5]})
    beside_text = pd.DataFrame({"code": [1], "name": ["x"]})

    for frame in (all_numeric, beside_text):
        assert _styles(_value_map([{"value": 1, "color": "#hit"}], column="code"),
                       frame) == [{"fill": "#hit"}]

    # And the string the upcast used to produce no longer matches an int column,
    # which is the other half of the behaviour change.
    assert _styles(_value_map([{"value": "1.0", "color": "#hit"}], column="code"),
                   all_numeric) == [None]


def test_value_map_leaves_unmapped_cells_unstyled():
    frame = pd.DataFrame({"name": ["US", "CA"]})

    assert _styles(_value_map([{"value": "US", "color": "#hit"}], column="name"), frame) == [
        {"fill": "#hit"}, None,
    ]


def test_value_map_first_matching_mapping_wins():
    frame = pd.DataFrame({"name": ["US"]})
    mappings = [{"value": "US", "color": "#first"}, {"value": "US", "color": "#second"}]

    assert _styles(_value_map(mappings, column="name"), frame) == [{"fill": "#first"}]


def test_value_map_nan_cells_do_not_match_a_real_mapping():
    frame = pd.DataFrame({"name": pd.Series(["US", None, np.nan], dtype=object)})

    assert _styles(_value_map([{"value": "US", "color": "#hit"}], column="name"),
                   frame) == [{"fill": "#hit"}, None, None]


def test_value_map_stringifies_missing_cells_rather_than_skipping_them():
    """value_map has no isna guard: the cell is stringified like any other, so a
    mapping authored against the literal text "None" matches an empty cell. Odd, but
    it is what ships, and a vectorized path that added an isna guard would change it."""
    frame = pd.DataFrame({"name": pd.Series([None], dtype=object)})

    assert _styles(_value_map([{"value": "None", "color": "#hit"}], column="name"),
                   frame) == [{"fill": "#hit"}]


def test_value_map_mapping_colour_may_be_absent_and_still_resolves_a_style():
    frame = pd.DataFrame({"name": ["US"]})

    assert _styles(_value_map([{"value": "US"}], column="name"), frame) == [{"fill": None}]


def test_value_map_with_no_mappings_leaves_everything_unstyled():
    frame = pd.DataFrame({"name": ["US", "CA"]})

    assert _styles(_value_map([], column="name"), frame) == [None, None]


def test_value_map_on_an_empty_frame_returns_no_styles():
    frame = pd.DataFrame({"name": pd.Series([], dtype=object)})

    assert _styles(_value_map([{"value": "US", "color": "#hit"}], column="name"), frame) == []


def test_value_map_on_an_empty_frame_does_not_raise_for_an_absent_column():
    frame = pd.DataFrame({"name": pd.Series([], dtype=object)})

    assert _styles(_value_map([{"value": "US"}], column="absent"), frame) == []


def test_value_map_on_an_empty_frame_does_not_raise_for_a_missing_column_key():
    frame = pd.DataFrame({"name": pd.Series([], dtype=object)})

    assert _styles(_value_map([{"value": "US"}]), frame) == []


def test_value_map_naming_an_absent_column_raises_for_a_non_empty_frame():
    frame = pd.DataFrame({"name": ["US"]})

    with pytest.raises(ValueError, match="not in the result"):
        _styles(_value_map([{"value": "US"}], column="absent"), frame)


def test_value_map_with_no_column_selected_raises_for_a_non_empty_frame():
    frame = pd.DataFrame({"name": ["US"]})

    with pytest.raises(ValueError, match="no column selected"):
        _styles(_value_map([{"value": "US"}]), frame)


# --------------------------------------------------------------------------
# value_map: any_category
# --------------------------------------------------------------------------

def test_any_category_matches_across_every_column_except_value():
    frame = pd.DataFrame({"region": ["US", "CA"], "channel": ["web", "US"],
                          "value": [1, 2]})
    rule = _value_map([{"value": "US", "color": "#hit"}], any_category=True)

    assert _styles(rule, frame) == [{"fill": "#hit"}, {"fill": "#hit"}]


def test_any_category_never_reads_the_value_column():
    """`value` is the measure, not a category, so a mapping must not match against
    it however the number stringifies."""
    frame = pd.DataFrame({"region": ["US"], "value": ["US"]})
    rule = _value_map([{"value": "US", "color": "#miss"}], any_category=True)

    assert _styles(rule, frame) == [{"fill": "#miss"}]

    frame_only_value = pd.DataFrame({"value": ["US"]})

    assert _styles(rule, frame_only_value) == [None]


def test_any_category_column_order_outranks_mapping_order():
    """The scan is columns-outer, mappings-inner: a match in an earlier column beats
    an earlier mapping that only matches a later column. Vectorizing per mapping
    instead of per column would silently invert this."""
    frame = pd.DataFrame({"first": ["a"], "second": ["b"]})
    mappings = [{"value": "b", "color": "#by-mapping-order"},
                {"value": "a", "color": "#by-column-order"}]
    rule = _value_map(mappings, any_category=True)

    assert _styles(rule, frame) == [{"fill": "#by-column-order"}]


def test_any_category_ignores_a_column_key_entirely():
    """any_category never reads `column`, so naming an absent one must not raise."""
    frame = pd.DataFrame({"region": ["US"]})
    rule = _value_map([{"value": "US", "color": "#hit"}], any_category=True,
                      column="not-a-real-column")

    assert _styles(rule, frame) == [{"fill": "#hit"}]


# --------------------------------------------------------------------------
# data_bar: Power-BI-style in-cell proportional bars
# --------------------------------------------------------------------------

def _data_bar(column="value", **extra):
    return {"id": "r1", "kind": "data_bar", "target": "mark", "column": column, **extra}


def test_data_bar_scales_to_the_columns_own_min_and_max_by_default():
    """With no explicit min/max, the bar is scaled to the COLUMN's own observed
    range -- the same "auto" default Excel/Power BI data bars use."""
    frame = pd.DataFrame({"value": [0.0, 50.0, 100.0]})

    assert _styles(_data_bar(), frame) == [
        {"bar": 0.0}, {"bar": 0.5}, {"bar": 1.0},
    ]


def test_data_bar_honours_an_explicit_min_and_max():
    frame = pd.DataFrame({"value": [10.0, 20.0]})

    assert _styles(_data_bar(min=0, max=40), frame) == [
        {"bar": 0.25}, {"bar": 0.5},
    ]


def test_data_bar_clamps_a_value_outside_an_explicit_range():
    """An explicit range is an author's deliberate scale, not a re-observed one --
    a value past either end still paints a full or empty bar rather than a bar
    over 100% or a negative width, either of which would be invalid CSS."""
    frame = pd.DataFrame({"value": [-5.0, 999.0]})

    assert _styles(_data_bar(min=0, max=100), frame) == [
        {"bar": 0.0}, {"bar": 1.0},
    ]


def test_data_bar_carries_its_colour_when_set():
    frame = pd.DataFrame({"value": [0.0, 100.0]})

    assert _styles(_data_bar(min=0, max=100, color="#60a5fa"), frame) == [
        {"bar": 0.0, "fill": "#60a5fa"}, {"bar": 1.0, "fill": "#60a5fa"},
    ]


def test_data_bar_with_no_colour_omits_the_fill_key():
    frame = pd.DataFrame({"value": [0.0]})

    assert _styles(_data_bar(min=0, max=10), frame) == [{"bar": 0.0}]


def test_data_bar_on_a_column_with_a_single_distinct_value_paints_a_full_bar():
    """Auto min==max would divide by zero. A flat column -- every row equal to the
    column's own only value -- has nothing to compare against, so every row reads
    as "at the maximum" (a full bar) rather than raising or leaving it unstyled."""
    frame = pd.DataFrame({"value": [7.0, 7.0]})

    assert _styles(_data_bar(), frame) == [{"bar": 1.0}, {"bar": 1.0}]


def test_data_bar_leaves_a_nan_cell_unstyled():
    frame = pd.DataFrame({"value": [10.0, np.nan, 20.0]})

    assert _styles(_data_bar(), frame) == [{"bar": 0.0}, None, {"bar": 1.0}]


def test_data_bar_on_a_non_numeric_column_raises():
    """Matches interval's contract exactly: a rule pointed at a text column is an
    authoring mistake that must surface in rule_errors, not fail silently."""
    frame = pd.DataFrame({"value": ["a", "b"]})

    with pytest.raises((ValueError, TypeError)):
        _styles(_data_bar(), frame)


def test_data_bar_naming_an_absent_column_raises_for_a_non_empty_frame():
    frame = pd.DataFrame({"value": [1.0]})

    with pytest.raises(ValueError, match="not in the result"):
        _styles(_data_bar(column="nope"), frame)


def test_data_bar_on_an_empty_frame_returns_no_styles():
    frame = pd.DataFrame({"value": pd.Series([], dtype=float)})

    assert _styles(_data_bar(), frame) == []


# --------------------------------------------------------------------------
# end-to-end through evaluate_rules: the fail-open contract around all of the above
# --------------------------------------------------------------------------

def _numeric_table():
    return {"type": "table", "columns": ["region", "sales"],
            "rows": [["US", 10.0], ["CA", None], ["MX", 90.0]], "total": 3}


def test_evaluate_rules_records_a_non_numeric_interval_column_as_an_error():
    rules = [_interval(_BANDS, column="region")]

    styles = evaluate_rules(_numeric_table(), rules)

    assert styles["rows"] == [None, None, None]
    assert len(styles["errors"]) == 1


def test_evaluate_rules_keeps_other_rules_when_an_interval_rule_breaks():
    rules = [
        _interval(_BANDS, column="region"),
        {"id": "ok", "kind": "interval", "target": "mark", "column": "sales",
         "bands": _BANDS},
    ]

    styles = evaluate_rules(_numeric_table(), rules)

    assert styles["cells"]["0"]["sales"] == {"fill": "#f87171"}
    assert styles["cells"]["2"]["sales"] == {"fill": "#34d399"}
    assert "1" not in styles["cells"]
    assert len(styles["errors"]) == 1


def test_evaluate_rules_paints_interval_cells_on_a_table_result():
    rules = [_interval(_BANDS, column="sales")]

    styles = evaluate_rules(_numeric_table(), rules)

    assert styles["cells"] == {"0": {"sales": {"fill": "#f87171"}},
                               "2": {"sales": {"fill": "#34d399"}}}
    assert styles["rows"] == [None, None, None]


def test_evaluate_rules_widget_target_matches_when_any_row_lands_in_a_band():
    rules = [dict(_interval(_BANDS, column="sales"), target="visibility")]

    styles = evaluate_rules(_numeric_table(), rules)

    assert styles["widget"]["hidden"] is True


def test_evaluate_rules_widget_target_stays_visible_when_no_row_matches():
    rules = [dict(_interval([{"min": 1000, "max": 2000, "color": "#f00"}], column="sales"),
                  target="visibility")]

    styles = evaluate_rules(_numeric_table(), rules)

    assert styles["widget"]["hidden"] is False
