"""C-24 step 2 (round 2): a numeric series over more rows than it draws shows
the WHOLE x range by default -- evenly thinned -- instead of the first 500
rows by x (one sliver at the left edge). The cap is still disclosed."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DF = pd.DataFrame({"x": range(2000), "y": [v * 2.0 for v in range(2000)]})


def test_the_whole_range_is_drawn_when_thinned():
    r = get_widget_data_from_df(DF, {"measure": "x", "measure2": "y"}, "numeric_series")
    xs = [row["x"] for row in r["rows"]]
    assert len(xs) == 500
    assert xs[0] == 0 and xs[-1] == 1999
    assert xs == sorted(xs)
    assert r["truncation"]["applied"] is True


def test_an_authors_limit_still_takes_the_first_rows():
    r = get_widget_data_from_df(DF, {"measure": "x", "measure2": "y", "limit": 100}, "numeric_series")
    xs = [row["x"] for row in r["rows"]]
    assert xs == list(range(100))


def test_a_short_series_is_drawn_whole():
    r = get_widget_data_from_df(DF.head(50), {"measure": "x", "measure2": "y"}, "numeric_series")
    assert len(r["rows"]) == 50
