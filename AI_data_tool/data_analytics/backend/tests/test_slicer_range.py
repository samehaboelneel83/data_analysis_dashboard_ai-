"""A number slicer as a from-to range (live check item 12).

A slicer over a price or an amount listed every distinct value -- over a
hundred check boxes nobody can use, and nobody wants "exactly 41.37". The
range mode returns the column's min and max instead, never the value list.
"""
import pandas as pd
import pytest

from app.services.widget_data import SLICER_RANGE_AUTO_DISTINCT, shape_slicer
from app.services.widget_roles import VOCABULARIES


@pytest.fixture
def orders():
    return pd.DataFrame({"amount": [round(10 + i * 1.37, 2) for i in range(150)],
                         "qty": [i % 4 for i in range(150)],
                         "units": list(range(150)),
                         "region": ["N", "S", "E"] * 50})


def test_range_mode_returns_bounds_not_values(orders):
    out = shape_slicer(orders, {"dimension": "amount", "slicer_mode": "range"})
    assert out["type"] == "slicer_range"
    assert out["rows"] == []
    assert (out["min"], out["max"]) == (10.0, orders["amount"].max())
    assert out["integer"] is False


def test_whole_numbers_stay_whole(orders):
    out = shape_slicer(orders, {"dimension": "units", "slicer_mode": "range"})
    assert (out["min"], out["max"], out["integer"]) == (0, 149, True)


def test_range_does_not_group_the_column(orders, monkeypatch):
    called = {"n": 0}
    real = pd.DataFrame.groupby
    monkeypatch.setattr(pd.DataFrame, "groupby", lambda self, *a, **kw: called.__setitem__("n", called["n"] + 1) or real(self, *a, **kw))
    shape_slicer(orders, {"dimension": "amount", "slicer_mode": "range"})
    assert called["n"] == 0


def test_auto_offers_a_range_for_a_many_valued_number(orders):
    assert orders["amount"].nunique() > SLICER_RANGE_AUTO_DISTINCT
    assert shape_slicer(orders, {"dimension": "amount"})["type"] == "slicer_range"


def test_auto_keeps_the_list_for_few_numbers_and_for_text(orders):
    assert shape_slicer(orders, {"dimension": "qty"})["rows"], "four values are a list"
    assert shape_slicer(orders, {"dimension": "region"})["rows"]


def test_a_chosen_list_mode_is_respected(orders):
    out = shape_slicer(orders, {"dimension": "amount", "slicer_mode": "search"})
    assert out["type"] != "slicer_range" and out["rows"]


def test_range_on_text_says_why(orders):
    out = shape_slicer(orders, {"dimension": "region", "slicer_mode": "range"})
    assert out["type"] == "slicer_range" and out["error"] == "not_numeric"


def test_range_is_a_known_mode():
    assert "range" in VOCABULARIES["slicer_mode"]
