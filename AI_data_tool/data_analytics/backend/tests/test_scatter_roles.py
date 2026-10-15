"""C-07 (round 2): Scatter's roles are an X measure (`measure2`) and a Y
measure (`measure`), both required, with an optional Label (`dimension`).

Old scatters -- a dimension on X and a measure -- keep rendering exactly as
before: they still satisfy the old rule, and the builder's migrated form of
one (X = that same dimension) is recognised as the legacy chart."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df
from app.services.widget_roles import REQUIRED_ROLES, missing_roles

DF = pd.DataFrame({"height": [150, 150, 160, 170, 170, 170], "weight": [50.0, 54, 60, 70, 72, 74],
                   "units": [1, 2, 3, 4, 5, 6], "product": ["a", "a", "b", "b", "c", "c"]})


def test_x_and_y_are_the_required_roles():
    assert set(REQUIRED_ROLES["scatter"]) == {"measure", "measure2"}


def test_a_new_scatter_needs_both_measures():
    assert missing_roles("scatter", {"measure": "weight"}) == ["measure2"]
    assert missing_roles("scatter", {"measure2": "units"}) == ["measure"]
    assert missing_roles("scatter", {"measure": "weight", "measure2": "units"}) == []


def test_an_old_scatter_still_counts_as_complete():
    assert missing_roles("scatter", {"dimension": "height", "measure": "weight"}) == []
    assert missing_roles("scatter", {"dimension": "height"}) == []          # a count per value, as before
    # the builder's migrated form: X is the same dimension
    assert missing_roles("scatter", {"dimension": "height", "measure2": "height", "measure": "weight"}) == []


def test_the_migrated_old_scatter_draws_exactly_what_it_drew():
    old = get_widget_data_from_df(DF, {"dimension": "height", "measure": "weight", "aggregation": "avg"}, "scatter")
    new = get_widget_data_from_df(DF, {"dimension": "height", "measure2": "height", "measure": "weight",
                                       "aggregation": "avg"}, "scatter")
    assert new == old


def test_x_against_y_without_a_label_plots_the_rows():
    r = get_widget_data_from_df(DF, {"measure2": "units", "measure": "weight"}, "scatter")
    assert len(r["rows"]) == 6


def test_x_against_y_by_label_is_one_point_per_label():
    r = get_widget_data_from_df(DF, {"dimension": "product", "measure2": "units", "measure": "weight",
                                     "aggregation": "avg", "aggregation2": "sum"}, "scatter")
    assert {row["name"]: (row["x"], row["y"]) for row in r["rows"]} == {
        "a": (3, 52.0), "b": (7, 65.0), "c": (11, 73.0)}
