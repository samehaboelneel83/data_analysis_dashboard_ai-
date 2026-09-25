"""Contract test between the frontend display-rule compiler and this engine.

The compiler in `frontend/src/lib/displayRules.ts` turns structured conditions into
expression strings. Nothing stops it emitting syntax the engine rejects — that is exactly
how the old expression palette ended up advertising `.str.upper()` snippets that
_validate_expr_safety refuses. These strings are copied verbatim from that compiler's own
tests, so if either side drifts, one of these fails.
"""
import pandas as pd
import pytest

from app.services.display_rules import evaluate_rules
from app.services.widget_data import _eval_expr, _validate_expr_safety


def test_gt_operator():
    """Comparison: greater than."""
    frame = pd.DataFrame([{"value": 1500}, {"value": 400}])
    expression = "value > 1000"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_gte_operator():
    """Comparison: greater than or equal."""
    frame = pd.DataFrame([{"value": 1500}, {"value": 400}])
    expression = "value >= 1000"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_lt_operator():
    """Comparison: less than."""
    frame = pd.DataFrame([{"value": 5}, {"value": 15}])
    expression = "value < 10"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_lte_operator():
    """Comparison: less than or equal."""
    frame = pd.DataFrame([{"value": 5}, {"value": 15}])
    expression = "value <= 10"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_eq_operator_numeric():
    """Comparison: equal with numeric value."""
    frame = pd.DataFrame([{"value": 10}, {"value": 15}])
    expression = "value == 10"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_ne_operator():
    """Comparison: not equal."""
    frame = pd.DataFrame([{"value": 10}, {"value": 15}])
    expression = "value != 10"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [False, True]


def test_eq_operator_string():
    """Comparison: equal with string value."""
    frame = pd.DataFrame([{"name": "US"}, {"name": "CA"}])
    expression = 'name == "US"'

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_between_operator():
    """Logical: between (inclusive on both ends) as (col >= min) and (col <= max)."""
    frame = pd.DataFrame([{"value": 5}, {"value": 15}])
    expression = "(value >= 10) and (value <= 20)"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [False, True]


def test_in_operator():
    """Membership: in list."""
    frame = pd.DataFrame([{"name": "US"}, {"name": "CA"}])
    expression = 'name in ["US", "CA"]'

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, True]


def test_isnull_true():
    """Null check: isnull(col) == True."""
    frame = pd.DataFrame([{"value": None}, {"value": 400}])
    expression = "isnull(value) == True"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_notnull():
    """Null check: notnull as isnull(col) == False."""
    frame = pd.DataFrame([{"value": 1500}, {"value": 400}])
    expression = "isnull(value) == False"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, True]


def test_escaped_quote_in_string_value():
    """String literal: embedded double quotes are escaped."""
    frame = pd.DataFrame([{"name": 'a"b'}, {"name": "other"}])
    expression = 'name == "a\\"b"'

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_eq_operator_boolean():
    """Comparison: equal with boolean value, compiled as Python's True/False (not JS's
    lowercase true/false, which would pass as a bare name and only fail later)."""
    frame = pd.DataFrame([{"active": True}, {"active": False}])
    expression = "active == True"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, False]


def test_backtick_quoted_column_name_in_direct_comparison():
    """Column name: non-bare identifiers are backtick-quoted."""
    frame = pd.DataFrame([{"net sales": 1500}, {"net sales": 400}])
    expression = "`net sales` > 1"

    _validate_expr_safety(expression)
    verdict = _eval_expr(expression, frame)

    assert [bool(v) for v in verdict] == [True, True]


def test_backtick_quoted_column_from_the_compiler_reaches_the_engine():
    """Integration: backtick-quoted column names survive through evaluate_rules."""
    result = {"type": "table", "columns": ["net sales"], "rows": [[1500], [400]], "total": 2}
    rules = [{"id": "r1", "kind": "expression", "target": "mark",
              "expression": "`net sales` > 1000", "style": {"fill": "#f87171"}}]

    styles = evaluate_rules(result, rules)

    assert styles["errors"] == []
    assert styles["rows"] == [{"fill": "#f87171"}, None]
