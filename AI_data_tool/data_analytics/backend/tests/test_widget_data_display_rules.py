import pandas as pd

from app.services.widget_data import get_widget_data_from_df


def _df():
    return pd.DataFrame({"region": ["US", "CA"], "sales": [1500, 400]})


def test_result_carries_rule_styles_when_rules_are_configured():
    config = {
        "dimension": "region", "measure": "sales", "aggregation": "sum",
        "display_rules": [{"id": "r1", "kind": "expression", "target": "mark",
                           "expression": "value > 1000", "style": {"fill": "#f87171"}}],
    }

    result = get_widget_data_from_df(_df(), config, "bar")

    assert result["rule_styles"]["rows"] == [{"fill": "#f87171"}, None]
    assert result["rule_errors"] == []


def test_result_is_untouched_when_no_rules_are_configured():
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    result = get_widget_data_from_df(_df(), config, "bar")

    assert "rule_styles" not in result
    assert "rule_errors" not in result


def test_a_broken_rule_never_costs_the_widget_its_data():
    config = {
        "dimension": "region", "measure": "sales", "aggregation": "sum",
        "display_rules": [{"id": "bad", "kind": "expression", "target": "mark",
                           "expression": "nope >", "style": {"fill": "#000"}}],
    }

    result = get_widget_data_from_df(_df(), config, "bar")

    assert len(result["rows"]) == 2
    assert len(result["rule_errors"]) == 1


def test_rules_do_not_run_on_an_error_result():
    config = {"measure": "missing_measure", "display_rules": [
        {"id": "r1", "kind": "expression", "target": "mark",
         "expression": "value > 1", "style": {"fill": "#000"}}]}

    result = get_widget_data_from_df(_df(), config, "bar")

    assert "rule_styles" not in result or result["rule_styles"]["rows"] == []
