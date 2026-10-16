"""C-07: a scatter can plot an X MEASURE against a Y measure, one point per
category -- 'product x units' drew bare axes because x was the product name."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DF = pd.DataFrame({"product": ["A", "A", "B", "B", "C"],
                   "units": [1, 3, 2, 2, 10], "revenue": [10.0, 30.0, 25.0, 25.0, 5.0]})


def test_one_point_per_category_at_its_x_and_y_measures():
    r = get_widget_data_from_df(DF, {"dimension": "product", "measure": "revenue", "measure2": "units",
                                     "aggregation": "sum"}, "scatter")
    pts = {row["name"]: (row["x"], row["y"]) for row in r["rows"]}
    assert pts == {"A": (4, 40.0), "B": (4, 50.0), "C": (10, 5.0)}


def test_the_x_measure_has_its_own_aggregation():
    r = get_widget_data_from_df(DF, {"dimension": "product", "measure": "revenue", "measure2": "units",
                                     "aggregation": "sum", "aggregation2": "avg"}, "scatter")
    assert {row["name"]: row["x"] for row in r["rows"]} == {"A": 2, "B": 2, "C": 10}


def test_a_legacy_scatter_is_unchanged():
    df = pd.DataFrame({"height": [160, 170, 170], "weight": [55.0, 65.0, 75.0]})
    r = get_widget_data_from_df(df, {"dimension": "height", "measure": "weight", "aggregation": "avg"}, "scatter")
    assert {row["name"]: row["value"] for row in r["rows"]} == {160: 55.0, 170: 70.0}
