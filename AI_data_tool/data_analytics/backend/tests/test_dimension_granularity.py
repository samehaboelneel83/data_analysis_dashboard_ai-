import pandas as pd
import pytest
from app.services.widget_data import _dimension_granularity_label, shape_series, _apply_filters


def test_dimension_granularity_label_year():
    s = pd.Series(pd.to_datetime(["2024-01-15", "2024-06-01", "2023-12-31"]))
    result = _dimension_granularity_label(s, "year")
    assert list(result) == [2024, 2024, 2023]


def test_dimension_granularity_label_quarter():
    s = pd.Series(pd.to_datetime(["2024-01-15", "2024-06-01", "2024-11-01"]))
    result = _dimension_granularity_label(s, "quarter")
    assert list(result) == ["2024-Q1", "2024-Q2", "2024-Q4"]


def test_dimension_granularity_label_month():
    s = pd.Series(pd.to_datetime(["2024-01-15", "2024-06-01"]))
    result = _dimension_granularity_label(s, "month")
    assert list(result) == ["2024-01", "2024-06"]


def test_shape_series_groups_by_year_when_dimension_granularity_set():
    df = pd.DataFrame({
        "order_date": pd.to_datetime(["2023-01-01", "2023-06-01", "2024-01-01"]),
        "sales": [10, 20, 30],
    })
    config = {"dimension": "order_date", "dimension_granularity": "year", "measure": "sales", "aggregation": "sum"}
    result = shape_series(df, config)
    rows = {r["name"]: r["value"] for r in result["rows"]}
    assert rows == {2023: 30, 2024: 30}


def test_apply_filters_eq_with_granularity_matches_truncated_value():
    df = pd.DataFrame({
        "order_date": pd.to_datetime(["2023-01-01", "2023-06-01", "2024-01-01"]),
        "sales": [10, 20, 30],
    })
    filtered = _apply_filters(df, [{"column": "order_date", "op": "eq", "value": 2023, "granularity": "year"}])
    assert list(filtered["sales"]) == [10, 20]

class TestNullDates:
    """A null date has no bucket. Month and day (strftime) already agreed;
    quarter and week were built by string concatenation over nullable ints,
    so a null became the LABEL "<NA>-Q<NA>" -- a garbage bar on every chart
    with one missing date, and the reason the no-dates-here guard in
    _bucket_dimension could never fire for those two granularities."""

    @pytest.mark.parametrize("gran", ["year", "quarter", "month", "week", "day"])
    def test_a_null_date_labels_as_missing_not_as_text(self, gran):
        from app.services.widget_data import _dimension_granularity_label
        out = _dimension_granularity_label(pd.Series(["2024-02-01", None]), gran)
        assert pd.isna(out.iloc[1]), repr(out.iloc[1])
        assert "<NA>" not in str(out.iloc[1])

    def test_a_text_column_with_quarter_granularity_is_handed_back_untouched(self):
        from app.services.widget_data import _bucket_dimension
        s = pd.Series(["ops", "hr", "sales"])
        assert list(_bucket_dimension(s, "quarter")) == ["ops", "hr", "sales"]
        assert list(_bucket_dimension(s, "week")) == ["ops", "hr", "sales"]
