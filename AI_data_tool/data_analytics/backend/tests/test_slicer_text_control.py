"""A text control for a column whose value list is useless.

A slicer over `Customer ID` is the case every list control gets wrong. With
748,000 distinct values the list is unusable — but the expensive part is not
the rendering, it is that the server groups the whole column to build a list
nobody can read. SAS offers a TEXT INPUT for exactly this: the reader types the
value they already know.

So the property that matters is not "a different widget appears". It is that
the text control asks the server for NOTHING, because computing the list is the
cost being avoided.
"""
import pandas as pd
import pytest

from app.services.widget_data import shape_slicer


@pytest.fixture
def customers():
    # Stands in for the high-cardinality case: every row a distinct value.
    return pd.DataFrame({"customer_id": [f"C{i}" for i in range(500)],
                         "spend": [1.0] * 500})


def test_a_text_control_returns_no_values(customers):
    out = shape_slicer(customers, {"dimension": "customer_id", "slicer_mode": "text"})

    assert out["type"] == "slicer_text"
    assert out["rows"] == []
    # The column is named so the control can say what it filters.
    assert out["column"] == "customer_id"


def test_a_text_control_does_not_group_the_column(customers, monkeypatch):
    """The point of the mode. Grouping 748k values to throw the result away
    would make the cheap control the expensive one."""
    called = {"n": 0}
    real_groupby = pd.DataFrame.groupby

    def _spy(self, *a, **kw):
        called["n"] += 1
        return real_groupby(self, *a, **kw)

    monkeypatch.setattr(pd.DataFrame, "groupby", _spy)
    shape_slicer(customers, {"dimension": "customer_id", "slicer_mode": "text"})
    assert called["n"] == 0


def test_every_other_mode_still_lists_values(customers):
    # The default slicer is unchanged: this is a new mode, not a new default.
    out = shape_slicer(customers.head(5), {"dimension": "customer_id"})
    assert out["rows"], "a list slicer still needs its values"


def test_auto_never_silently_becomes_text(customers):
    """`auto` picks buttons/list/search by size. It must not start choosing
    text: a reader who can see their options should be given them, and a
    control that silently stops listing looks broken."""
    out = shape_slicer(customers, {"dimension": "customer_id", "slicer_mode": "auto"})
    assert out["type"] != "slicer_text"
