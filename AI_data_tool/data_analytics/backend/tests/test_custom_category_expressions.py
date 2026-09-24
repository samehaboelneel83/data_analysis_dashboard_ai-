"""Contract test between the frontend custom-category generator and this engine.

The generator in `frontend/src/lib/customCategories.ts` compiles grouping and binning
into calculated-column expressions. Nothing stops it emitting syntax this engine
rejects — that is exactly how the old expression palette ended up advertising
`.str.upper()` snippets that `_validate_expr_safety` refuses. These strings are
copied verbatim from that generator's own tests, so if either side drifts, one of
these fails.
"""
import pandas as pd
import pytest

from app.services.widget_data import _eval_expr, _validate_expr_safety


def test_grouping_expression_is_accepted_and_maps_values():
    df = pd.DataFrame({"region": ["US", "CA", "UK", "JP"]})
    expr = 'SWITCH(region, "US", "Americas", "CA", "Americas", "UK", "Europe", "Other")'

    _validate_expr_safety(expr)
    out = _eval_expr(expr, df)

    assert list(out) == ["Americas", "Americas", "Europe", "Other"]


def test_binning_expression_is_accepted_and_buckets_ascending():
    df = pd.DataFrame({"sales": [5, 10, 15, 20, 25]})
    expr = 'IF(sales < 10, "0-10", IF(sales < 20, "10-20", "20+"))'

    _validate_expr_safety(expr)
    out = _eval_expr(expr, df)

    # 10 is not < 10, so it lands in the next bucket up — half-open intervals.
    assert list(out) == ["0-10", "10-20", "10-20", "20+", "20+"]


def test_single_interval_binning_expression():
    df = pd.DataFrame({"sales": [10, 50, 90]})
    expr = 'IF(sales < 50, "0-50", "50+")'

    _validate_expr_safety(expr)

    assert list(_eval_expr(expr, df)) == ["0-50", "50+", "50+"]


def test_backtick_quoted_column_names_survive_validation_and_evaluation():
    df = pd.DataFrame({"Order Region": ["US", "UK"]})
    expr = 'SWITCH(`Order Region`, "US", "Americas", "Other")'

    _validate_expr_safety(expr)

    assert list(_eval_expr(expr, df)) == ["Americas", "Other"]


def test_an_escaped_quote_inside_a_value_still_parses():
    df = pd.DataFrame({"size": ['12" pipe', "small"]})
    expr = 'SWITCH(size, "12\\" pipe", "Big", "Other")'

    _validate_expr_safety(expr)

    assert list(_eval_expr(expr, df)) == ["Big", "Other"]


def test_grouped_result_is_usable_as_a_dimension_downstream():
    """The point of a custom category is grouping a chart by it, so the generated
    column has to survive being fed to a shaper as a calculated column."""
    from app.services.widget_data import apply_calculated_columns, get_widget_data_from_df

    df = pd.DataFrame({
        "region": ["US", "CA", "UK", "JP"],
        "sales": [10, 20, 30, 40],
    })
    calc = [{"name": "Continent",
             "expression": 'SWITCH(region, "US", "Americas", "CA", "Americas", "UK", "Europe", "Other")'}]

    df = apply_calculated_columns(df, calc)
    result = get_widget_data_from_df(
        df, {"dimension": "Continent", "measure": "sales", "aggregation": "sum"}, widget_type="bar",
    )

    by_name = {r["name"]: r["value"] for r in result["rows"]}
    assert by_name == {"Americas": 30, "Europe": 30, "Other": 40}


@pytest.mark.parametrize("expr", [
    'SWITCH(region, "US", "Americas", "Other")',
    'IF(sales < 10, "0-10", "10+")',
])
def test_generated_shapes_contain_no_attribute_access(expr):
    """The structural rule the old palette violated: no `x.y` anywhere."""
    assert "." not in expr.replace('"', "")
    _validate_expr_safety(expr)
