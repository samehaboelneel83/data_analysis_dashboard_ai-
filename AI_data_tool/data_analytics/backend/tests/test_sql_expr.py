import pytest

from app.services.sql_expr import ExpressionTranslationError, translate_filter_expr

COLUMNS = {"region", "revenue", "status", "col name"}


def test_translate_simple_equality():
    sql, params = translate_filter_expr("region == 'east'", COLUMNS)
    assert sql == '"region" = :r0'
    assert params == {"r0": "east"}


def test_translate_numeric_comparison():
    sql, params = translate_filter_expr("revenue > 100", COLUMNS)
    assert sql == '"revenue" > :r0'
    assert params == {"r0": 100}


@pytest.mark.parametrize("py_op,sql_op", [
    ("==", "="), ("!=", "!="), ("<", "<"), ("<=", "<="), (">", ">"), (">=", ">="),
])
def test_translate_all_comparison_operators(py_op, sql_op):
    sql, params = translate_filter_expr(f"revenue {py_op} 100", COLUMNS)
    assert sql == f'"revenue" {sql_op} :r0'


def test_translate_and():
    sql, params = translate_filter_expr("region == 'east' and revenue > 100", COLUMNS)
    assert sql == '("region" = :r0) AND ("revenue" > :r1)'
    assert params == {"r0": "east", "r1": 100}


def test_translate_or():
    sql, params = translate_filter_expr("region == 'east' or region == 'west'", COLUMNS)
    assert sql == '("region" = :r0) OR ("region" = :r1)'


def test_translate_not():
    sql, params = translate_filter_expr("not (status == 'archived')", COLUMNS)
    assert sql == 'NOT ("status" = :r0)'
    assert params == {"r0": "archived"}


def test_translate_case_insensitive_and_or_not_keywords():
    sql, params = translate_filter_expr("region == 'east' AND revenue > 100", COLUMNS)
    assert sql == '("region" = :r0) AND ("revenue" > :r1)'


def test_translate_in_list():
    sql, params = translate_filter_expr("region in ('east', 'west')", COLUMNS)
    assert sql == '"region" IN (:r0, :r1)'
    assert params == {"r0": "east", "r1": "west"}


def test_translate_not_in_list():
    sql, params = translate_filter_expr("region not in ('east', 'west')", COLUMNS)
    assert sql == '"region" NOT IN (:r0, :r1)'


def test_translate_arithmetic():
    sql, params = translate_filter_expr("revenue - 10 > 0", COLUMNS)
    assert sql == '("revenue" - :r0) > :r1'
    assert params == {"r0": 10, "r1": 0}


def test_translate_backtick_quoted_column_name():
    sql, params = translate_filter_expr("`col name` == 'x'", COLUMNS)
    assert sql == '"col name" = :r0'


def test_translate_empty_expression_returns_empty():
    sql, params = translate_filter_expr("", COLUMNS)
    assert sql == ""
    assert params == {}


def test_translate_rejects_unknown_column():
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("does_not_exist == 'x'", COLUMNS)


def test_translate_rejects_function_calls():
    """Row-filter expressions may reference aggregation/date functions (SUM, YEAR, ...)
    when evaluated in pandas, but those have no meaningful SQL WHERE-clause pushdown for
    a per-row predicate -- reject rather than silently drop or mistranslate."""
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("YEAR(signup_date) == 2024", COLUMNS)


def test_translate_rejects_chained_comparisons():
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("0 < revenue < 100", COLUMNS)


def test_translate_rejects_power_operator():
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("revenue ** 2 > 100", COLUMNS)


def test_translate_rejects_in_with_non_literal_list():
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("region in other_column", COLUMNS)


def test_translate_rejects_dangerous_underscore_identifiers():
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("__class__ == 'x'", COLUMNS)


def test_translate_rejects_syntactically_invalid_expression():
    with pytest.raises(ExpressionTranslationError):
        translate_filter_expr("region ==", COLUMNS)
