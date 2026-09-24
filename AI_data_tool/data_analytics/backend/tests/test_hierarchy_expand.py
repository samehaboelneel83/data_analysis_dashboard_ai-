"""Hierarchy expand: multi-level grouping with path labels, composing with the
whole downstream pipeline."""
import pandas as pd

from app.services.widget_data import shape_series

SEP = " › "


def df():
    return pd.DataFrame({
        "region": ["EU", "EU", "EU", "US"],
        "country": ["FR", "FR", "DE", "US"],
        "v": [1.0, 2.0, 4.0, 8.0],
    })


def test_expand_groups_by_every_level_with_path_labels():
    r = shape_series(df(), {"dimension_levels": ["region", "country"],
                            "measure": "v", "aggregation": "sum"})
    assert {x["name"]: x["value"] for x in r["rows"]} == {
        f"US{SEP}US": 8.0, f"EU{SEP}DE": 4.0, f"EU{SEP}FR": 3.0}


def test_expand_composes_with_having_and_rank():
    r = shape_series(df(), {"dimension_levels": ["region", "country"],
                            "measure": "v", "aggregation": "sum",
                            "having": [{"op": "gt", "value": 3}],
                            "rank": {"mode": "top", "n": 1}})
    assert [x["name"] for x in r["rows"]] == [f"US{SEP}US"]


def test_single_or_invalid_levels_fall_back_to_plain_dimension():
    # one level is not an expand; an unknown level column must not blank the widget
    r = shape_series(df(), {"dimension_levels": ["region"], "dimension": "region",
                            "measure": "v", "aggregation": "sum"})
    assert {x["name"] for x in r["rows"]} == {"EU", "US"}
    r = shape_series(df(), {"dimension_levels": ["region", "ghost"], "dimension": "region",
                            "measure": "v", "aggregation": "sum"})
    assert {x["name"] for x in r["rows"]} == {"EU", "US"}
