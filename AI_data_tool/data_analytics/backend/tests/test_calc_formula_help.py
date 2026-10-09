"""Calculated columns made easier (2026-10-10): formulas that failed for no
good reason now work, a broken formula is explained in plain terms, and Test
says what the WHOLE column looks like, not six sample values."""
import pandas as pd
import pytest

from app.services.expr_explain import explain, summarize
from app.services.widget_data import _eval_expr, preview_expression

DF = pd.DataFrame({"revenue": [100.0, 2500.0, 0.0, None], "units": [2, 0, 1, 3], "cost": [1, 2, 3, 4],
                   "region": ["East", "West", "East", None], "product": ["A", "B", "C", "D"]})


class TestFormulasThatFailedBefore:
    def test_and_or_not_work_on_columns(self):
        # "The truth value of a Series is ambiguous" -- while the palette offered and/or/not.
        assert list(_eval_expr("IF(region == 'East' and revenue > 50, 'yes', 'no')", DF)) == ["yes", "no", "no", "no"]
        assert list(_eval_expr("IF(region == 'East' or units > 2, 'yes', 'no')", DF)) == ["yes", "no", "yes", "yes"]
        assert list(_eval_expr("IF(not isnull(region), region, '?')", DF)) == ["East", "West", "East", "?"]

    def test_concat_takes_any_number_of_values(self):
        assert list(_eval_expr("CONCAT(region, ' - ', product)", DF))[:2] == ["East - A", "West - B"]

    def test_single_values_keep_python_meaning(self):
        assert _eval_expr("IF(1 > 0 and 2 > 1, 'a', 'b')", DF) == "a"

    def test_the_logic_helpers_cannot_be_typed(self):
        with pytest.raises(ValueError):
            _eval_expr("_AND_(revenue, units)", DF)


class TestPlainProblems:
    @pytest.mark.parametrize("expr,expected", [
        ("revenue - cot", {"code": "unknown_name", "name": "cot", "suggest": "cost"}),
        ("Round(revenue, 1)", {"code": "unknown_name", "name": "Round", "suggest": "round"}),
        ("revenue -", {"code": "ends_with_operator", "operator": "-"}),
        ("IF(revenue > 5, 'a', 'b'", {"code": "brackets", "open": 1, "close": 0}),
        ("region = 'East'", {"code": "single_equals"}),
        ("'abc", {"code": "open_quote"}),
        ("region - 1", {"code": "text_math", "operator": "-"}),
        ("LEFT(region)", {"code": "missing_value", "function": "LEFT", "missing": 1}),
    ])
    def test_the_test_button_explains(self, tmp_path, expr, expected):
        path = tmp_path / "d.parquet"
        DF.to_parquet(path)
        out = preview_expression(str(path), expr)
        assert out["ok"] is False and out["problem"] == expected
        assert out["error"]          # the raw text stays, for "Show details"

    def test_an_unknown_error_says_so(self):
        assert explain("something odd", "x", ["x"]) == {"code": "other"}


class TestSummary:
    def test_labels_are_counted(self):
        s = summarize(_eval_expr("IF(revenue >= 1000, 'Big', IF(revenue >= 50, 'Mid', 'Small'))", DF))
        assert s == {"kind": "labels", "rows": 4, "empty": 0, "distinct": 3,
                     "top": [["Small", 2], ["Mid", 1], ["Big", 1]]}

    def test_numbers_show_range_empty_and_infinite(self):
        s = summarize(_eval_expr("revenue / units", DF))
        assert s["kind"] == "number" and s["infinite"] == 1 and s["empty"] == 1 and s["max"] == 50.0

    def test_numbers_with_gaps_are_still_numbers(self):
        s = summarize(_eval_expr("IF(units == 0, None, revenue / units)", DF))
        assert s["kind"] == "number" and s["infinite"] == 0 and s["empty"] == 2


class TestTemplateFormulas:
    """The exact formulas the frontend's "What do you want to make?" forms write
    (frontend/src/lib/calcTemplates.test.ts), run by the real evaluator."""
    CARS = pd.DataFrame({
        "price": [250000.0, 900000.0, 2000000.0, None], "cost": [1.0, 2.0, 3.0, 4.0], "units": [1, 0, 2, 3],
        "target": [100.0, 0.0, 50.0, 10.0], "revenue": [110.0, 5.0, 40.0, 10.0],
        "condition": ["Used", "Used", "New", "Used"], "make": ["Kia", "MG", "BMW", "Fiat"],
        "model": ["Rio", "5", "X5", "500"], "city": [" Cairo ", "Giza", "it's", None],
        "listed_at": pd.to_datetime(["2024-01-05", "2024-02-10", "2025-03-15", None]),
    })

    @pytest.mark.parametrize("expr,expected", [
        ("revenue - cost", [109.0, 3.0, 37.0, 6.0]),
        ("IF(units == 0, None, revenue / units)", [110.0, None, 20.0, pytest.approx(10 / 3)]),
        ("IF(target == 0, None, (revenue - target) / target * 100)", [pytest.approx(10.0), None, pytest.approx(-20.0), 0.0]),
        ("IF(price < 500000, 'Budget', IF(price < 1500000, 'Mid', 'Luxury'))", ["Budget", "Mid", "Luxury", "Luxury"]),
        ("IF(isnull(price), 'Unknown', IF(price < 500000, 'Budget', IF(price < 1500000, 'Mid', 'Luxury')))",
         ["Budget", "Mid", "Luxury", "Unknown"]),
        ("IF(condition == 'Used' and (make == 'Kia' or (make == 'Hyundai' or make == 'MG')), 'Hot', "
         "IF(price < 300000, 'Cheap', 'Normal'))", ["Hot", "Hot", "Normal", "Normal"]),
        ("CONCAT(make, ' ', model)", ["Kia Rio", "MG 5", "BMW X5", "Fiat 500"]),
        ("MONTHNAME(listed_at)", ["January", "February", "March", None]),
        ("TRIM(city)", ["Cairo", "Giza", "it's", ""]),
        ("REPLACE(city, '\\'', '')", [" Cairo ", "Giza", "its", ""]),
    ])
    def test_each_form_formula_runs(self, expr, expected):
        got = [None if (isinstance(v, float) and v != v) else v for v in list(_eval_expr(expr, self.CARS))]
        assert got == expected


class TestDatePartsAreWholeNumbers:
    """YEAR(listed_at) read "2024.0" in every table, legend and export."""
    DATES = pd.DataFrame({"d": pd.to_datetime(["2024-01-05", None, "2023-02-02"]),
                          "e": pd.to_datetime(["2025-03-01", "2025-01-01", "2023-02-03"])})

    @pytest.mark.parametrize("expr,expected", [
        ("YEAR(d)", [2024, None, 2023]), ("QUARTER(d)", [1, None, 1]), ("MONTH(d)", [1, None, 2]),
        ("DAY(d)", [5, None, 2]), ("WEEKDAY(d)", [5, None, 4]), ("DAYOFYEAR(d)", [5, None, 33]),
        ("DATEDIFF(d, e, 'day')", [421, None, 1]), ("DATEDIFF(d, e, 'month')", [14, None, 0]),
    ])
    def test_whole_numbers_with_real_gaps(self, expr, expected):
        r = _eval_expr(expr, self.DATES)
        assert str(r.dtype) == "Int64"
        assert [None if pd.isna(v) else int(v) for v in r] == expected

    def test_a_gap_never_breaks_a_condition(self):
        # A comparison on an empty value is unknown; IF / SWITCH / filters read it as "no".
        assert list(_eval_expr("IF(YEAR(d) >= 2024, 'new', 'old')", self.DATES)) == ["new", "old", "old"]
        assert list(_eval_expr("SWITCH(YEAR(d), 2024, 'a', 'b')", self.DATES)) == ["a", "b", "b"]
        from app.services.widget_data import apply_filter_expr
        assert len(apply_filter_expr(self.DATES, "YEAR(d) == 2024")) == 1

    def test_the_test_summary_reads_them(self):
        s = summarize(_eval_expr("YEAR(d)", self.DATES))
        assert (s["min"], s["max"], s["empty"]) == (2023, 2024, 1)


class TestMeasures:
    """Measures had the same `and`/`not` failure, no Lowest/Highest, and raw errors;
    the measure forms' formulas (frontend/src/lib/measureTemplates.test.ts) run here."""
    SALES = pd.DataFrame({"region": ["E", "E", "W", "W"], "channel": ["On", "Off", "On", "Off"],
                          "revenue": [100.0, 50.0, 0.0, 30.0], "cost": [40.0, 0.0, 0.0, 0.0],
                          "target": [80.0, 80.0, 0.0, 0.0]})

    def ev(self, expr, by=None):
        from app.services.measure_eval import evaluate_measure
        r = evaluate_measure(expr, self.SALES, [by] if by else [])
        return {k: (None if v != v else v) for k, v in r.to_dict().items()} if hasattr(r, "to_dict") else r

    @pytest.mark.parametrize("expr,whole,by_region", [
        ("MAX(revenue)", 100.0, {"E": 100.0, "W": 30.0}),
        ("MIN(revenue)", 0.0, {"E": 50.0, "W": 0.0}),
        ("IF(SUM(cost) == 0, None, SUM(revenue) / SUM(cost))", 4.5, {"E": 3.75, "W": None}),
        ("IF(SUM(target) == 0, None, (SUM(revenue) - SUM(target)) / SUM(target) * 100)",
         pytest.approx(12.5), {"E": pytest.approx(-6.25), "W": None}),
        ("IF(TOTAL(SUM(revenue)) == 0, None, SUM(revenue) / TOTAL(SUM(revenue)) * 100)",
         100.0, {"E": pytest.approx(83.333, rel=1e-3), "W": pytest.approx(16.667, rel=1e-3)}),
        ("SUM(IF(channel == 'On', revenue, 0))", 100.0, {"E": 100.0, "W": 0.0}),
        ("AVG(IF(channel == 'On', revenue, None))", 50.0, {"E": 100.0, "W": 0.0}),
        ("SUM(IF(channel == 'On', 1, 0))", 2, {"E": 1, "W": 1}),
        ("SUM(IF(channel == 'On' and revenue > 10, revenue, 0))", 100.0, {"E": 100.0, "W": 0.0}),
        ("SUM(IF(not channel == 'On', revenue, 0))", 80.0, {"E": 50.0, "W": 30.0}),
    ])
    def test_measure_formulas(self, expr, whole, by_region):
        assert self.ev(expr) == whole
        assert self.ev(expr, "region") == by_region

    def test_a_broken_measure_is_explained(self):
        from app.services.measure_eval import preview_measure
        out = preview_measure("Sum(revenu)", self.SALES)
        assert out["ok"] is False and out["problem"]["code"] == "unknown_name"
