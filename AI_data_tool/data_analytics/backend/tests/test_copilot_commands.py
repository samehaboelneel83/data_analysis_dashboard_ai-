"""Plain instructions the page copilot carries out with no model
(services/copilot_commands.py): rules, not guesses."""
from app.services.copilot_commands import parse

COLS = {"data": {"group": "object", "kind": "object", "day": "datetime64[ns]", "amount": "float64",
                 "unit price": "float64", "price": "float64"}}
PAGE = [{"id": 1, "widget_type": "text", "title": "About"},
        {"id": 2, "widget_type": "bar", "title": "Amount by group"},
        {"id": 3, "widget_type": "line", "title": "Amount over time"}]


def act(message, widgets=PAGE, selected=None):
    got = parse(message, widgets, COLS, selected)
    return got and got["actions"][0]


class TestAdding:
    def test_a_number_by_a_category_is_a_bar_and_by_a_date_a_line(self):
        a = act("add amount by group")
        assert (a["op"], a["widget_type"]) == ("create", "bar")
        assert a["config"] == {"aggregation": "sum", "measure": "amount", "dimension": "group"}
        b = act("show the average amount by day")
        assert b["widget_type"] == "line" and b["config"]["aggregation"] == "avg"
        assert b["config"]["dimension_granularity"] == "month"

    def test_the_kind_asked_for_is_the_kind_made(self):
        assert act("add a donut chart of amount by kind")["widget_type"] == "donut"
        assert act("create a table of group, kind and amount")["config"] == {"columns": "group,kind,amount"}

    def test_a_number_alone_is_a_headline_number_and_a_category_alone_is_counted(self):
        assert act("add total amount")["widget_type"] == "kpi"
        c = act("add a bar chart of kind")
        assert c["config"] == {"aggregation": "count", "dimension": "kind"}

    def test_a_column_counts_only_when_its_whole_name_is_said(self):
        assert act("add unit price by group")["config"]["measure"] == "unit price"
        assert act("add price by group")["config"]["measure"] == "price"
        assert parse("add revenue by region", PAGE, COLS) is None       # neither is a column here

    def test_arabic_is_read_the_same_way(self):
        a = act("أضف متوسط amount حسب group")
        assert a["widget_type"] == "bar" and a["config"]["aggregation"] == "avg"
        assert "متوسط" in a["title"]


class TestChangingWhatIsThere:
    def test_a_chart_is_named_by_its_whole_title_or_is_the_selected_one(self):
        assert act("remove Amount over time") == {"op": "delete", "widget_id": 3}
        assert act("delete it", selected=2) == {"op": "delete", "widget_id": 2}
        # Two charts, none named, none selected: nothing is guessed.
        assert parse("remove the chart", PAGE, COLS) is None
        assert act("remove the chart", widgets=PAGE[:2]) == {"op": "delete", "widget_id": 2}

    def test_rename_takes_the_quoted_title(self):
        assert act('rename Amount by group to "Where the amount is"') == {
            "op": "update", "widget_id": 2, "title": "Where the amount is"}
        assert parse("rename it to something better", PAGE, COLS, 2) is None

    def test_kind_top_and_sort(self):
        assert act("make it a line chart", selected=2) == {"op": "update", "widget_id": 2, "widget_type": "line"}
        assert parse("make it a bar chart", PAGE, COLS, 2) is None      # it already is
        assert act("top 5", selected=2)["config"] == {"limit": 5, "sort": "desc"}
        assert act("sort ascending", selected=2)["config"] == {"sort": "asc"}
        assert act("حوّل Amount by group إلى دائري")["widget_type"] == "donut"


def test_anything_else_is_left_to_the_caller():
    for message in ("why did amount fall last month?", "make this page look better", "", "x" * 400,
                    "add something interesting"):
        assert parse(message, PAGE, COLS, 2) is None


def test_the_answer_has_the_shape_of_a_models_and_its_language():
    got = parse("أضف amount حسب group", PAGE, COLS)
    assert got["data_question"] is None and got["language"] == "ar" and "ذكاء" in got["reply"]
