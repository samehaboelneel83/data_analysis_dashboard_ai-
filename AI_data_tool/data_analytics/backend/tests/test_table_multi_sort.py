"""Multi-column sort for the raw table / list widget (gap row 362)."""
import pandas as pd

from app.services.widget_data import shape_series


def _df():
    # region repeats so the secondary key actually decides order within a region.
    return pd.DataFrame({
        "region": ["US", "US", "CA", "CA", "US"],
        "city":   ["NY", "LA", "TO", "VA", "SF"],
        "sales":  [100, 300, 200, 200, 100],
    })


def _rows(result):
    return result["rows"]


def test_sorts_by_first_key_then_breaks_ties_with_the_second():
    result = shape_series(_df(), {
        "columns": ["region", "city", "sales"],
        "sort_keys": [{"col": "region", "dir": "asc"}, {"col": "sales", "dir": "desc"}],
    })
    # region ascending (CA before US); within each region, sales descending.
    assert [r[0] for r in _rows(result)] == ["CA", "CA", "US", "US", "US"]
    us = [r for r in _rows(result) if r[0] == "US"]
    assert [r[2] for r in us] == [300, 100, 100]


def test_ties_on_every_key_keep_source_order_stable():
    # CA rows tie on region and sales (both 200): source order TO before VA must hold.
    result = shape_series(_df(), {
        "columns": ["region", "city", "sales"],
        "sort_keys": [{"col": "region", "dir": "asc"}, {"col": "sales", "dir": "asc"}],
    })
    ca = [r[1] for r in _rows(result) if r[0] == "CA"]
    assert ca == ["TO", "VA"]


def test_sort_keys_supersede_the_single_sort_col():
    result = shape_series(_df(), {
        "columns": ["region", "sales"],
        "sort_col": "sales", "sort": "asc",           # would put 100s first
        "sort_keys": [{"col": "sales", "dir": "desc"}],  # wins: 300 first
    })
    assert [r[1] for r in _rows(result)] == [300, 200, 200, 100, 100]


def test_unknown_sort_column_is_ignored_not_fatal():
    # A column since removed from the dataset must not raise; it is simply skipped.
    result = shape_series(_df(), {
        "columns": ["region", "sales"],
        "sort_keys": [{"col": "gone", "dir": "asc"}, {"col": "sales", "dir": "desc"}],
    })
    assert [r[1] for r in _rows(result)] == [300, 200, 200, 100, 100]


def test_no_sort_keys_leaves_the_single_col_path_untouched():
    result = shape_series(_df(), {"columns": ["region", "sales"], "sort_col": "sales", "sort": "asc"})
    assert [r[1] for r in _rows(result)] == [100, 100, 200, 200, 300]
