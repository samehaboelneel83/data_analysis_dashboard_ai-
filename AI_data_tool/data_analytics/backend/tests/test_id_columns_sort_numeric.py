"""Id-like columns are categories for aggregation, but NUMERIC for sorting.

The user-facing rule has two halves. Elsewhere (measure dropdowns, bubble
color) an id column is treated as a category; these tests pin the other
half: sorting by an id column must use its numeric order (2 before 10),
never the lexicographic order ("10" before "2") that string-typed category
handling would produce.
"""
import pandas as pd

from app.services.widget_data import shape_series


def df():
    # state_id values chosen so numeric and lexicographic order disagree:
    # numeric 2 < 10 < 30, lexicographic "10" < "2" < "30".
    return pd.DataFrame({
        "state_id": [10, 2, 30, 2, 10],
        "amount": [1.0, 1.0, 1.0, 1.0, 1.0],
    })


def test_sort_by_name_on_id_dimension_is_numeric():
    out = shape_series(df(), {
        "dimension": "state_id", "measure": "amount", "aggregation": "sum",
        "sort_by": "name", "sort": "asc",
    })
    assert [r["name"] for r in out["rows"]] == [2, 10, 30]


def test_sort_col_pointing_at_id_column_is_numeric():
    frame = pd.DataFrame({
        "region": ["a", "b", "c"],
        "state_id": [10, 2, 30],
        "amount": [1.0, 1.0, 1.0],
    })
    out = shape_series(frame, {
        "dimension": "region", "measure": "amount", "aggregation": "sum",
        "sort_col": "state_id", "sort": "asc",
    })
    assert [r["name"] for r in out["rows"]] == ["b", "a", "c"]
