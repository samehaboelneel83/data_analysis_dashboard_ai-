"""`dimension_granularity` must reach the matrix shapers too.

Third time for this bug. `shape_series` honoured "group by month" from the
first; `shape_dual_series` was found ignoring it and fixed, with a comment
saying "offered and ignored is the same failure as a control wired to nothing";
`shape_heatmap` — which serves BOTH the heatmap and the ribbon — still ignored
it.

The config panel writes `dimension_granularity` for whatever widget is
selected, so this was not a hypothetical. A ribbon of triage mix "by quarter"
grouped by raw arrival minute instead: 120,000 columns, a 2.4 MB response for
one tile, and a chart no reader could interpret. Silent, because every layer
did what it was told and only the shaper knew the instruction had been dropped.
"""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

BASE = {"dimension": "arrived_at", "dimension2": "triage", "measure": "cost",
        "aggregation": "sum", "dimension_granularity": "month"}


def frame():
    """Two months, minute-level stamps — so honouring the granularity collapses
    six rows to two, and ignoring it leaves six."""
    stamps = ["2025-01-05 08:15", "2025-01-19 22:40", "2025-01-27 03:05",
              "2025-02-02 11:00", "2025-02-14 16:30", "2025-02-28 23:59"]
    return pd.DataFrame({"arrived_at": pd.to_datetime(stamps),
                         "triage": ["red", "green"] * 3,
                         "cost": [10, 20, 30, 40, 50, 60]})


class TestTheMatrixShapers:
    def test_the_heatmap_buckets_its_rows(self):
        got = get_widget_data_from_df(frame(), BASE, "heatmap")
        assert got["rows_axis"] == ["2025-01", "2025-02"], got["rows_axis"]

    def test_the_ribbon_buckets_its_periods(self):
        """Same shaper, and the widget that exposed it."""
        got = get_widget_data_from_df(frame(), BASE, "ribbon")
        assert got["rows_axis"] == ["2025-01", "2025-02"], got["rows_axis"]

    def test_the_cells_are_aggregated_within_the_bucket(self):
        """Bucketing the label without re-aggregating would keep six rows under
        two names — the numbers must actually combine."""
        got = get_widget_data_from_df(frame(), BASE, "heatmap")
        j = got["cols_axis"].index("red")
        assert got["cells"][0][j] == 40, got["cells"]      # 10 + 30, both January
        assert got["cells"][1][j] == 50, got["cells"]      # 50 alone, February

    def test_a_quarter_bucket_works_too(self):
        got = get_widget_data_from_df(frame(), dict(BASE, dimension_granularity="quarter"),
                                      "heatmap")
        assert got["rows_axis"] == ["2025-Q1"], got["rows_axis"]


class TestNothingElseMoves:
    def test_no_granularity_leaves_the_column_alone(self):
        cfg = {k: v for k, v in BASE.items() if k != "dimension_granularity"}
        got = get_widget_data_from_df(frame(), cfg, "heatmap")
        assert len(got["rows_axis"]) == 6, got["rows_axis"]

    def test_a_categorical_row_axis_is_untouched(self):
        df = frame().assign(dept=["A", "A", "B", "B", "C", "C"])
        got = get_widget_data_from_df(df, dict(BASE, dimension="dept"), "heatmap")
        assert got["rows_axis"] == ["A", "B", "C"], got["rows_axis"]
