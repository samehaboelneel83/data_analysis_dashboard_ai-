"""A suggested page's filters are the control that suits the column -- buttons
for a few values, a list for a dozen, a dropdown beyond -- with a period
control beside them when the data has a date (analyst_panel.slicers_for)."""
from app.services import analyst_panel as ap


def profile(days=800):
    return {"columns": [
        {"name": "kind", "role": "categorical", "distinct": 3},
        {"name": "team", "role": "categorical", "distinct": 9},
        {"name": "place", "role": "categorical", "distinct": 40},
        {"name": "code", "role": "categorical", "distinct": 900},
        {"name": "when", "role": "datetime"}, {"name": "amount", "role": "numeric"}],
        "structure": {"date_range": {"column": "when", "days": days}}}


def widgets(*dims):
    return [{"widget_type": "bar", "config": {"dimension": d, "measure": "amount"}} for d in dims]


def test_the_control_follows_how_many_values_there_are_to_choose_from():
    assert [ap.control_for(n) for n in (2, 5, 6, 12, 13, 50)] == ["buttons", "buttons", "list", "list", "dropdown", "dropdown"]
    got = ap.slicers_for(widgets("kind", "team", "place", "kind", "team", "kind"), profile(), limit=3)
    assert [(s["config"]["dimension"], s["config"]["slicer_mode"]) for s in got] == \
        [("kind", "buttons"), ("team", "list"), ("place", "dropdown")]
    # A column with too many values to choose among is never a filter.
    assert "code" not in {s["config"]["dimension"] for s in ap.slicers_for(widgets("code", "kind"), profile())}


def test_a_from_to_date_control_sits_beside_them_on_the_date_the_rows_happened(monkeypatch):
    prof = profile()
    prof["columns"] += [{"name": "due", "role": "datetime", "min": "2020-01-01", "max": "2026-01-01"}]
    prof["columns"][4].update(min="2023-01-01", max="2025-03-01")
    prof["structure"]["date_range"] = {"column": "due", "days": 2192}          # the WIDEST date is not the event's
    got = ap.slicers_for(widgets("kind"), prof, with_date=True, date="when")
    assert [(s["config"]["dimension"], s["config"]["slicer_mode"]) for s in got] == [("kind", "buttons"), ("when", "range")]
    # With no event date named, the date the history is measured on.
    assert ap.slicers_for(widgets("kind"), prof, with_date=True)[-1]["config"]["dimension"] == "due"
    # A date covering a few weeks is not a filter; asked for without one, only the categories.
    short = profile(days=20)
    assert len(ap.slicers_for(widgets("kind"), short, with_date=True)) == 1
    assert len(ap.slicers_for(widgets("kind"), profile())) == 1


def test_the_range_control_answers_for_a_date_with_its_first_and_last_day_and_the_filter_keeps_both_ends():
    import pandas as pd
    from app.services.widget_data import _apply_filters, shape_slicer
    df = pd.DataFrame({"when": pd.date_range("2024-01-01", periods=100, freq="D"), "amount": range(100)})
    got = shape_slicer(df, {"dimension": "when", "slicer_mode": "range"})
    assert got["type"] == "slicer_range" and got["kind"] == "date" and (got["min"], got["max"]) == ("2024-01-01", "2024-04-09")
    # Dates stored as text are read the same way; text that is not dates is refused in words.
    assert shape_slicer(df.assign(when=df["when"].dt.strftime("%Y-%m-%d")), {"dimension": "when", "slicer_mode": "range"})["kind"] == "date"
    assert shape_slicer(pd.DataFrame({"k": ["a", "b"] * 30}), {"dimension": "k", "slicer_mode": "range"})["error"] == "not_numeric"
    # What the browser sends for "10 Jan to 12 Jan": the day after the last one, so both ends are kept.
    kept = _apply_filters(df, [{"column": "when", "op": "date_range", "value": ["2024-01-10", "2024-01-13"]}])
    assert kept["when"].dt.strftime("%m-%d").tolist() == ["01-10", "01-11", "01-12"]
    # An open end.
    assert len(_apply_filters(df, [{"column": "when", "op": "date_range", "value": ["1700-01-01", "2024-01-03"]}])) == 2
    assert len(_apply_filters(df, [{"column": "when", "op": "date_range", "value": ["2024-04-08", "2200-01-01"]}])) == 2


def test_every_suggested_control_is_one_the_product_would_save():
    from app.services.widget_roles import validate_widget_payload
    for s in ap.slicers_for(widgets("kind", "team", "place"), profile(), limit=3, with_date=True):
        validate_widget_payload("slicer", s["config"])
