"""Boolean columns must not crash analysis.

pandas reports `is_numeric_dtype(bool_series)` as True, so `detect_types` files a
boolean column under "numeric" and `analyze_numeric` then calls `.quantile()` on
it. numpy refuses:

    TypeError: numpy boolean subtract, the `-` operator, is not supported

Which is a 500 on `POST /datasets/{id}/analysis`, and — because an unhandled
exception escapes past the CORS middleware — the browser reports it as a CORS
failure, sending anyone debugging it in entirely the wrong direction.

This is not hypothetical: a Postgres source with `boolean` columns
(`yolo_created_flag`, `have_general_situation`) reproduces it exactly.

Booleans are cast to 0/1 rather than dropped, because the statistics are then
genuinely useful — the mean of a 0/1 column is the proportion that are true.
"""
import pandas as pd
import pytest

from app.services.analytics import analyze_numeric, detect_types, run_full_analysis


@pytest.fixture
def frame():
    return pd.DataFrame({
        "amount": [10.0, 20.0, 30.0, 40.0],
        "is_active": [True, False, True, True],
        "label": ["a", "b", "c", "d"],
    })


class TestAnalyzeNumericWithBooleans:
    def test_a_boolean_column_does_not_raise(self, frame):
        """The regression itself."""
        result = analyze_numeric(frame, ["amount", "is_active"])
        assert "is_active" in result["columns"]

    def test_the_mean_is_the_proportion_true(self, frame):
        """3 of 4 rows are True. This is why booleans are cast rather than
        skipped — the number means something."""
        result = analyze_numeric(frame, ["is_active"])
        assert result["columns"]["is_active"]["mean"] == 0.75

    def test_quantiles_are_computed(self, frame):
        result = analyze_numeric(frame, ["is_active"])
        stats = result["columns"]["is_active"]
        assert stats["min"] == 0
        assert stats["max"] == 1

    def test_an_all_true_column_is_handled(self):
        df = pd.DataFrame({"flag": [True, True, True]})
        stats = analyze_numeric(df, ["flag"])["columns"]["flag"]
        assert stats["mean"] == 1.0
        assert stats["std"] == 0.0

    def test_a_nullable_boolean_column_is_handled(self):
        """Postgres booleans arrive as object dtype holding True/False/None."""
        df = pd.DataFrame({"flag": [True, None, False, True]})
        result = analyze_numeric(df, ["flag"])
        assert "flag" in result["columns"]

    def test_correlation_with_a_boolean_still_works(self, frame):
        """Two-column analysis adds a correlation matrix, which is a second
        place a boolean can break the maths."""
        result = analyze_numeric(frame, ["amount", "is_active"])
        assert "correlation" in result

    def test_ordinary_numeric_columns_are_unaffected(self, frame):
        stats = analyze_numeric(frame, ["amount"])["columns"]["amount"]
        assert stats["mean"] == 25.0
        assert stats["min"] == 10.0
        assert stats["max"] == 40.0


class TestFullAnalysis:
    def test_a_frame_with_a_boolean_completes(self, frame):
        """The end-to-end path the failing endpoint takes."""
        result = run_full_analysis(frame)
        assert result["overview"]["rows"] == 4
        assert "is_active" in result["numeric"]["columns"]

    def test_the_reported_type_is_still_numeric(self, frame):
        """Deliberately unchanged. Reclassifying booleans as categorical would
        move them between the measure and dimension buckets in the hierarchy,
        widget pickers and every saved report that already references them."""
        assert detect_types(frame)["is_active"] == "numeric"
