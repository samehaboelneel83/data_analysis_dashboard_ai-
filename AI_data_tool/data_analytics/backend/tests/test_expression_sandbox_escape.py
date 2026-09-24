import pytest
from app.services.widget_data import _eval_expr, apply_filter_expr, preview_expression
import pandas as pd


def test_dunder_globals_access_is_rejected():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(Exception):
        _eval_expr("a.sum.__globals__", df)


def test_dunder_expression_rejected_via_apply_filter_expr(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3]})
    # silent=False so the rejection surfaces rather than degrading silently
    with pytest.raises(Exception):
        apply_filter_expr(df, "SUM.__globals__", silent=False)


def test_dunder_expression_rejected_via_preview_expression(tmp_path):
    csv_path = tmp_path / "d.csv"
    df = pd.DataFrame({"a": [1, 2, 3]})
    df.to_csv(csv_path, index=False)

    result = preview_expression(str(csv_path), "SUM.__globals__")

    assert result["ok"] is False


def test_attribute_access_without_dunder_is_rejected():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(Exception):
        _eval_expr("a.sum()", df)  # a legitimate-looking pandas method call, no dunder at all


def test_unicode_lookalike_dunder_is_rejected():
    df = pd.DataFrame({"a": [1, 2, 3]})
    # Any attribute-access syntax must be rejected structurally (AST), regardless of
    # what the attribute name looks like — this doesn't even need a real lookalike
    # character to prove the point, since ALL `x.y` syntax is blocked now.
    with pytest.raises(Exception):
        _eval_expr("a.mean", df)


def test_backtick_quoted_attribute_chain_is_rejected():
    # Regression test for a bypass found during fix verification: pandas' own
    # df.eval() natively resolves attribute chains on backtick-quoted column names
    # (confirmed directly: df.eval("`a`.sum.__globals__") returns the real globals
    # dict). A naive AST check that calls ast.parse() on the raw expression would hit
    # SyntaxError on the backticks (they aren't valid Python syntax) and skip
    # validation entirely, letting this reach df.eval() unchecked. The validator must
    # normalize backtick-quoted segments before parsing so this is still caught.
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(Exception):
        _eval_expr("`a`.sum.__globals__", df)


def test_pandas_at_local_reference_is_rejected():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(Exception):
        _eval_expr("@df.to_csv('should_not_be_written.csv')", df)
    assert not __import__("os").path.exists("should_not_be_written.csv")


def test_pandas_at_local_reference_rejected_via_apply_filter_expr():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(Exception):
        apply_filter_expr(df, "@df.to_csv('should_not_be_written2.csv')", silent=False)
    assert not __import__("os").path.exists("should_not_be_written2.csv")
