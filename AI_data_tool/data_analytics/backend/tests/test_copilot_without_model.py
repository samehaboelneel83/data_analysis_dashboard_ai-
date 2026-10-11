"""The page copilot without a model: plain words about what can be done, and
the charts the platform already built for the columns named (§AW)."""
from app.services import copilot_without_model as cw

COLUMNS = {"deliveries": {"region": "VARCHAR", "fee": "DOUBLE", "created_at": "TIMESTAMP"}}
CARDS = [
    {"title": "Fee by region", "sentence": "North is highest.",
     "action": {"kind": "add_widget", "widget_type": "bar", "config": {"dimension": "region", "measure": "fee"}}},
    {"title": "Rows by month", "sentence": "",
     "action": {"kind": "add_widget", "widget_type": "line", "config": {"dimension": "created_at"}}},
    {"title": "An analysis", "action": {"kind": "run_analysis"}},
]


def test_it_names_the_columns_and_offers_only_charts_about_them():
    got = cw.answer("show the fee for each region", COLUMNS, CARDS, "AI is switched off")
    assert "AI is switched off" in got["reply"] and "not changed" in got["reply"]
    assert "region" in got["reply"] and "fee" in got["reply"]
    assert [s["title"] for s in got["suggestions"]] == ["Fee by region"]
    assert got["suggestions"][0]["config"] == {"dimension": "region", "measure": "fee"}
    assert "- Fee by region: North is highest." in got["reply"]


def test_words_that_match_nothing_still_get_the_ready_charts():
    got = cw.answer("make it nicer", COLUMNS, CARDS)
    assert "None of your words matched" in got["reply"]
    assert [s["title"] for s in got["suggestions"]] == ["Fee by region", "Rows by month"]


def test_with_no_cards_it_points_at_the_builder():
    got = cw.answer("fee", COLUMNS, None)
    assert got["suggestions"] == [] and "Fields" in got["reply"]


def test_a_message_in_arabic_is_answered_in_arabic():
    got = cw.answer("أضف مخططًا عن fee لكل region", COLUMNS, CARDS, "AI is switched off for the data this dashboard reads")
    assert got["language"] == "ar"
    assert "فلم تتغيّر الصفحة" in got["reply"] and "الذكاء الاصطناعي موقوف" in got["reply"]
    assert "I could not" not in got["reply"] and "Columns your words" not in got["reply"]
    assert [s["title"] for s in got["suggestions"]] == ["Fee by region"]       # the chart's own words stay the engine's
