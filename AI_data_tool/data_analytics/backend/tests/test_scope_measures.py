"""Phase 6.5: SCOPE() / ISINSCOPE() -- one measure, a different formula per grain."""
import pandas as pd
import pytest

from app.services.measure_eval import evaluate_measure, preview_measure, resolve_scope
from app.services.widget_data import get_widget_data_from_df


@pytest.fixture
def df():
    return pd.DataFrame({
        "region": ["N", "N", "S", "S", "S"],
        "product": ["a", "b", "a", "b", "b"],
        "sales": [10.0, 30.0, 20.0, 20.0, 20.0],
    })


SHARE_OR_COUNT = 'SCOPE(SUM(sales), "product", SUM(sales) / TOTAL(SUM(sales)), "", COUNT(sales))'


def test_each_grain_gets_its_own_branch(df):
    by_product = evaluate_measure(SHARE_OR_COUNT, df, ["product"])
    assert by_product["a"] == pytest.approx(0.3) and by_product["b"] == pytest.approx(0.7)
    assert evaluate_measure(SHARE_OR_COUNT, df, []) == 5            # grand total branch
    by_region = evaluate_measure(SHARE_OR_COUNT, df, ["region"])     # no branch -> default
    assert by_region["N"] == 40 and by_region["S"] == 60


def test_multi_column_levels_match_as_a_set(df):
    expr = 'SCOPE(0, "product, region", SUM(sales), "region", AVG(sales))'
    both = evaluate_measure(expr, df, ["region", "product"])
    assert both[("S", "b")] == 40
    assert evaluate_measure(expr, df, ["region"])["S"] == 20


def test_untaken_branches_never_run(df):
    # BYGROUP cannot evaluate without a grain; SCOPE must not try it at the total.
    expr = 'SCOPE(SUM(sales), "product", SUM(sales) / BYGROUP(SUM(sales), "region"))'
    assert evaluate_measure(expr, df, []) == 100


def test_isinscope_is_a_constant_for_if(df):
    expr = 'IF(ISINSCOPE("product"), 1, 2) * SUM(sales)'
    assert evaluate_measure(expr, df, ["product"])["a"] == 30
    assert evaluate_measure(expr, df, []) == 200


@pytest.mark.parametrize("bad,msg", [
    ('SCOPE(SUM(sales), "product")', "pairs"),
    ('SCOPE(SUM(sales), region, SUM(sales))', "quoted"),
    ('SCOPE(1, "a", 2, "a", 3)', "twice"),
    ('TOTAL(SCOPE(SUM(sales), "", 1))', "cannot contain"),
    ('ISINSCOPE(region)', "quoted"),
])
def test_malformed_scope_is_refused_with_a_reason(df, bad, msg):
    with pytest.raises(ValueError) as e:
        evaluate_measure(bad, df, ["product"])
    assert msg in str(e.value)


def test_unused_scope_leaves_the_expression_untouched():
    assert resolve_scope("SUM(sales) / TOTAL(SUM(sales))", ["x"]) == "SUM(sales) / TOTAL(SUM(sales))"


def test_crosstab_subtotals_evaluate_their_own_branch(df):
    measures = [{"name": "m", "expression": 'SCOPE(SUM(sales), "", COUNT(sales), "region", AVG(sales))'}]
    res = get_widget_data_from_df(df, {"dimension": "region", "dimension2": "product", "measure": "m",
                                       "show_totals": True}, "crosstab", measures=measures)
    # cells: SUM per region x product; row totals: AVG per region; grand total: COUNT
    assert res["rows"] == [["N", 10.0, 30.0, 20.0], ["S", 20.0, 40.0, 20.0]]
    assert res["totals"][-1] == 5


def test_preview_reports_the_branch_at_the_preview_grain(df):
    got = preview_measure(SHARE_OR_COUNT, df, group_by="product")
    assert got["ok"] and got["sample"][0]["value"] == pytest.approx(0.3)
