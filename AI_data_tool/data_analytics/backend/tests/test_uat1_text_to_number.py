"""UAT-1 (16 Oct 2026): text -> number in calculated columns never guesses.

`TONUMBER(RIGHT(order_id, 6))` on ids like "SO-100199" read the digits as a
date ("100199" -> 1999-10-01 -> 10,865 epoch days, most ids -> empty), so a
count distinct of 4,200 ids came out 3,100 with no warning; and
`REPLACE(order_id, "SO-", "") * 1` stayed TEXT (Python's str * int is
repetition), so `* 2` would have read "100199100199".

Chosen behaviour:
- TONUMBER(date column) -> epoch days, as before (round-trips with TODATE).
- TONUMBER / VALUE on number-like text ("100199", "1,234.5", " 42 ", Arabic
  digits) -> those numbers. Empty text -> empty (NA).
- TONUMBER on text that is entirely ISO dates ("2024-03-01") -> epoch days, as
  before. VALUE never reads a date.
- Any other text -> a clear error naming an offending value. Never a date guess.
- Arithmetic (+ - * / % // **) with text on either side -> a readable error
  pointing at VALUE(); text + text stays concatenation.
- DirectQuery: TONUMBER/VALUE refuse with the reason; arithmetic with a text
  literal refuses with the same VALUE() hint. (A text COLUMN is left to the
  source: live column types come from a probe that reads NUMERIC as text.)
"""
import pandas as pd
import pytest

from app.services.sql_expr import ExpressionTranslationError, calc_column_to_sql
from app.services.widget_data import _eval_expr, apply_calculated_columns, preview_expression


def _ids(n=4200):
    return pd.DataFrame({"order_id": [f"SO-{100000 + i}" for i in range(n)],
                         "amount": [float(i % 7) for i in range(n)]})


class TestUatCase:
    def test_tonumber_of_order_id_digits_counts_every_id(self):
        df = apply_calculated_columns(_ids(), [{"name": "order_num", "expression": "TONUMBER(RIGHT(order_id, 6))"}])
        assert df["order_num"].nunique() == 4200
        assert df["order_num"].notna().all()
        assert df["order_num"].iloc[199] == 100199          # not 10,865 (1999-10-01 in epoch days)
        assert df["order_num"].min() == 100000 and df["order_num"].max() == 104199

    def test_value_of_replace_is_a_real_number(self):
        df = apply_calculated_columns(_ids(), [{"name": "order_key", "expression": 'VALUE(REPLACE(order_id, "SO-", "")) * 2'}])
        assert df["order_key"].iloc[199] == 200398
        assert pd.api.types.is_numeric_dtype(df["order_key"])
        assert df["order_key"].nunique() == 4200


class TestTonumber:
    def test_datetime_column_still_epoch_days_and_round_trips(self):
        df = pd.DataFrame({"d": pd.to_datetime(["2024-01-15", None])})
        out = _eval_expr("TONUMBER(d)", df)
        assert out.iloc[0] == (pd.Timestamp("2024-01-15") - pd.Timestamp("1970-01-01")).days
        assert pd.isna(out.iloc[1])
        back = _eval_expr("TODATE(TONUMBER(d))", df)
        assert back.iloc[0] == pd.Timestamp("2024-01-15")

    def test_number_like_text_reads_as_numbers(self):
        df = pd.DataFrame({"t": ["100199", "1,234.5", " 42 ", "-7", "", None, "١٢٣"]})
        out = _eval_expr("TONUMBER(t)", df)
        assert out.iloc[:4].tolist() == [100199, 1234.5, 42, -7]
        assert out.iloc[4:6].isna().all()                 # genuinely empty -> empty
        assert out.iloc[6] == 123                          # Arabic-Indic digits

    def test_iso_date_text_keeps_epoch_days(self):
        df = pd.DataFrame({"t": ["2024-03-01", "2024-03-02 10:00"]})
        assert _eval_expr("TONUMBER(t)", df).tolist() == [19783, 19784]

    def test_text_that_is_neither_raises_instead_of_guessing(self):
        df = pd.DataFrame({"t": ["SO-100199", "SO-100200"]})
        with pytest.raises(ValueError, match="SO-100199"):
            _eval_expr("TONUMBER(t)", df)

    def test_digits_are_never_read_as_a_date(self):
        df = pd.DataFrame({"t": ["100199", "20240301"]})
        assert _eval_expr("TONUMBER(t)", df).tolist() == [100199, 20240301]

    def test_numeric_column_passes_through(self):
        df = pd.DataFrame({"n": [1.5, 2.0]})
        assert _eval_expr("TONUMBER(n)", df).tolist() == [1.5, 2.0]


class TestValue:
    def test_value_rejects_dates_and_words(self):
        with pytest.raises(ValueError, match="VALUE"):
            _eval_expr("VALUE(t)", pd.DataFrame({"t": ["2024-03-01"]}))
        with pytest.raises(ValueError, match="abc"):
            _eval_expr("VALUE(t)", pd.DataFrame({"t": ["12", "abc"]}))

    def test_value_of_a_literal(self):
        assert _eval_expr('VALUE("1,250") + 1', pd.DataFrame({"a": [1]})) == 1251


class TestTextArithmetic:
    @pytest.mark.parametrize("expr", ['REPLACE(order_id, "SO-", "") * 1', "order_id * 1",
                                      "RIGHT(order_id, 6) + 1", "order_id / 2", "order_id - 1"])
    def test_number_like_text_times_number_raises_pointing_to_value(self, expr):
        df = pd.DataFrame({"order_id": ["SO-100199", "SO-100200"]})
        with pytest.raises(ValueError, match=r"VALUE\("):
            _eval_expr(expr, df)

    def test_digits_text_times_one_raises_and_value_fixes_it(self):
        df = pd.DataFrame({"t": ["100199"]})
        with pytest.raises(ValueError, match=r"VALUE\("):
            _eval_expr("t * 1", df)
        assert _eval_expr("VALUE(t) * 2", df).tolist() == [200398]

    def test_word_text_times_one_raises(self):
        df = pd.DataFrame({"t": ["abc"]})
        with pytest.raises(ValueError, match=r"VALUE\("):
            _eval_expr("t * 1", df)
        with pytest.raises(ValueError, match=r"VALUE\("):
            _eval_expr('"abc" * 1', df)

    def test_text_concatenation_and_number_maths_unchanged(self):
        df = pd.DataFrame({"a": ["x", "y"], "n": [1, 2], "d": pd.to_datetime(["2024-01-02", "2024-01-05"])})
        assert _eval_expr('a + "-" + a', df).tolist() == ["x-x", "y-y"]
        assert _eval_expr("n * 2 + 1", df).tolist() == [3, 5]
        assert _eval_expr("LEN(a) * 2", df).tolist() == [2, 2]
        assert (_eval_expr("d - d", df) == pd.Timedelta(0)).all()

    def test_preview_explains_text_math(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.csv")
            pd.DataFrame({"order_id": ["SO-100199"]}).to_csv(path, index=False)
            out = preview_expression(path, 'REPLACE(order_id, "SO-", "") * 1')
        assert out["ok"] is False
        assert "VALUE(" in out["error"]
        assert out["problem"]["code"] == "text_math"


class TestDirectQuery:
    def test_tonumber_and_value_refuse_clearly(self):
        for expr in ("TONUMBER(order_id)", "VALUE(order_id)"):
            with pytest.raises(ExpressionTranslationError, match="no SQL translation"):
                calc_column_to_sql(expr, {"order_id"}, "postgresql")

    def test_arithmetic_on_a_text_literal_refuses_with_value_hint(self):
        with pytest.raises(ExpressionTranslationError, match=r"VALUE\("):
            calc_column_to_sql('"abc" * 1', {"order_id"}, "sqlite")
        with pytest.raises(ExpressionTranslationError, match=r"VALUE\("):
            calc_column_to_sql('amount + "100199"', {"amount"}, "postgresql")
        sql, used = calc_column_to_sql("amount * 2", {"order_id", "amount"}, "sqlite")
        assert used == ["amount"]
