"""A series cut by `limit` says so (MASTER_PLAN Phase 0, constitution rule 4).

Found in the browser: the settings panel stamps `limit: 20` on every chart it
saves, so a bar over a 213-member dimension silently drew 20 bars and said
nothing. The numbers were right; the picture was a sample nobody was told about.
"""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df


def frame(n_groups: int):
    return pd.DataFrame({"city": [f"c{i:03d}" for i in range(n_groups) for _ in range(i % 5 + 1)], "id": 1})


def test_a_cut_series_reports_what_it_dropped():
    got = get_widget_data_from_df(frame(213), {"dimension": "city", "measure": "id",
                                               "aggregation": "count", "limit": 20})
    assert len(got["rows"]) == 20
    assert got["truncation"] == {"applied": True, "shown": 20, "of": 213, "limit": 20, "reason": "limit"}


def test_an_uncut_series_says_nothing_was_dropped():
    got = get_widget_data_from_df(frame(4), {"dimension": "city", "measure": "id",
                                             "aggregation": "count", "limit": 20})
    assert got["truncation"]["applied"] is False
    assert got["truncation"]["shown"] == got["truncation"]["of"] == 4


def test_a_raw_table_reports_its_cut_in_rows():
    df = pd.DataFrame({"a": range(120), "b": range(120)})
    got = get_widget_data_from_df(df, {"limit": 50})
    assert got["type"] == "table" and len(got["rows"]) == 50
    assert got["truncation"]["applied"] is True
    assert (got["truncation"]["shown"], got["truncation"]["of"], got["truncation"]["unit"]) == (50, 120, "rows")
