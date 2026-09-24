"""Text functions for the calculated-column engine.

The engine had none: `str()` for coercion and nothing else. This closes the gap
against SAS's 13 and Power BI's DAX text family.

The hard constraint is that `_validate_expr_safety` structurally forbids attribute
access, so none of these can be implemented as a user-facing `.str.*` accessor —
they have to be real functions in the namespace taking a Series. That is exactly why
the old expression palette shipped broken, so every function here is tested through
`_eval_expr` rather than called directly.
"""
import pandas as pd
import pytest

from app.services.widget_data import _eval_expr


def _s(values):
    return pd.DataFrame({"t": values})


def test_upper_and_lower():
    assert list(_eval_expr("UPPER(t)", _s(["ab", "Cd"]))) == ["AB", "CD"]
    assert list(_eval_expr("LOWER(t)", _s(["Ab", "CD"]))) == ["ab", "cd"]


def test_trim_removes_surrounding_whitespace_only():
    assert list(_eval_expr("TRIM(t)", _s(["  a b  "]))) == ["a b"]


def test_len_counts_characters():
    assert list(_eval_expr("LEN(t)", _s(["abc", ""]))) == [3, 0]


def test_substring_is_one_based_to_match_sas_and_dax():
    """SAS's Substring and DAX's MID both start at 1. Zero-based here would silently
    shift every result by one character."""
    assert list(_eval_expr("SUBSTRING(t, 3, 4)", _s(["USBURLIN0101"]))) == ["BURL"]


def test_substring_past_the_end_yields_what_exists_rather_than_erroring():
    assert list(_eval_expr("SUBSTRING(t, 2, 99)", _s(["abc"]))) == ["bc"]


def test_left_and_right():
    assert list(_eval_expr("LEFT(t, 2)", _s(["abcd"]))) == ["ab"]
    assert list(_eval_expr("RIGHT(t, 2)", _s(["abcd"]))) == ["cd"]


def test_concat_joins_two_values():
    df = pd.DataFrame({"a": ["US"], "b": ["BUR"]})
    assert list(_eval_expr("CONCAT(a, b)", df)) == ["USBUR"]


def test_concat_coerces_a_number_so_mixed_types_do_not_raise():
    df = pd.DataFrame({"a": ["x"], "n": [7]})
    assert list(_eval_expr("CONCAT(a, n)", df)) == ["x7"]


def test_replace_substitutes_every_occurrence():
    assert list(_eval_expr('REPLACE(t, "_", "-")', _s(["a_b_c"]))) == ["a-b-c"]


def test_find_is_one_based_and_returns_zero_when_absent():
    """Zero for "not found" matches SAS's Findchar, and keeps the result usable as a
    boolean-ish test without a separate CONTAINS."""
    assert list(_eval_expr('FIND(t, "b")', _s(["abc"]))) == [2]
    assert list(_eval_expr('FIND(t, "z")', _s(["abc"]))) == [0]


def test_contains_returns_a_boolean_usable_in_if():
    assert list(_eval_expr('CONTAINS(t, "b")', _s(["abc", "xyz"]))) == [True, False]
    assert list(_eval_expr('IF(CONTAINS(t, "b"), "yes", "no")', _s(["abc", "xyz"]))) == ["yes", "no"]


def test_startswith_and_endswith():
    assert list(_eval_expr('STARTSWITH(t, "ab")', _s(["abc", "bbc"]))) == [True, False]
    assert list(_eval_expr('ENDSWITH(t, "bc")', _s(["abc", "abd"]))) == [True, False]


def test_reverse():
    assert list(_eval_expr("REVERSE(t)", _s(["abc"]))) == ["cba"]


def test_split_takes_the_nth_part_one_based():
    assert list(_eval_expr('SPLIT(t, "-", 2)', _s(["a-b-c"]))) == ["b"]


def test_split_out_of_range_yields_empty_rather_than_raising():
    assert list(_eval_expr('SPLIT(t, "-", 9)', _s(["a-b"]))) == [""]


def test_padding_helpers():
    assert list(_eval_expr('LPAD(t, 5, "0")', _s(["42"]))) == ["00042"]
    assert list(_eval_expr('RPAD(t, 4, ".")', _s(["ab"]))) == ["ab.."]


def test_nulls_become_empty_strings_rather_than_the_literal_nan():
    """Left alone, pandas renders a missing value as the string 'nan' once coerced,
    which then shows up in a chart axis as real data."""
    assert list(_eval_expr("UPPER(t)", _s(["a", None]))) == ["A", ""]
    assert list(_eval_expr("LEN(t)", _s(["abc", None]))) == [3, 0]


def test_numeric_input_is_coerced_so_a_code_column_can_be_sliced():
    df = pd.DataFrame({"code": [90210, 10001]})
    assert list(_eval_expr("LEFT(code, 3)", df)) == ["902", "100"]


def test_text_functions_compose_with_each_other():
    assert list(_eval_expr('UPPER(LEFT(TRIM(t), 2))', _s(["  abcd "]))) == ["AB"]


@pytest.mark.parametrize("expr", [
    "UPPER(t)", "LOWER(t)", "TRIM(t)", "LEN(t)", "REVERSE(t)",
    'REPLACE(t, "a", "b")', 'FIND(t, "a")', 'CONTAINS(t, "a")',
    "SUBSTRING(t, 1, 2)", "LEFT(t, 1)", "RIGHT(t, 1)",
])
def test_every_text_function_passes_the_safety_validator(expr):
    """The structural point: these are real functions, so no expression using them
    needs the attribute access the validator forbids."""
    from app.services.widget_data import _validate_expr_safety
    _validate_expr_safety(expr)


def test_a_text_function_result_works_as_a_chart_dimension():
    from app.services.widget_data import apply_calculated_columns, get_widget_data_from_df

    df = pd.DataFrame({"sku": ["US-1", "US-2", "UK-1"], "qty": [1, 2, 3]})
    df = apply_calculated_columns(df, [{"name": "Country", "expression": 'SPLIT(sku, "-", 1)'}])

    result = get_widget_data_from_df(
        df, {"dimension": "Country", "measure": "qty", "aggregation": "sum"}, widget_type="bar",
    )

    assert {r["name"]: r["value"] for r in result["rows"]} == {"US": 3, "UK": 3}
