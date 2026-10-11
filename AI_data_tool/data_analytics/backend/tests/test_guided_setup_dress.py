"""Options, interactivity and navigation added to designed pages by plain code
(services/guided_setup/dress.py). Names here are deliberately of no field."""
import asyncio
from types import SimpleNamespace

from app.services.guided_setup import answer, dress


def bar(dim="group", measure="amount", agg="sum", **cfg):
    return {"widget_type": "bar", "title": f"{measure} by {dim}", "question": "q1",
            "config": {"dimension": dim, "measure": measure, "aggregation": agg, **cfg}}


def rows(*values):
    return {"type": "series", "rows": [{"name": f"g{i}", "value": v} for i, v in enumerate(values)]}


class TestTheRuleOnAComparison:
    def test_groups_above_the_average_are_marked_in_a_neutral_colour_when_nothing_says_which_way_is_good(self):
        rule = dress.above_average_rule(bar(), rows(10, 30, 50), "en", None)
        assert rule["expression"] == "value > AVG(value)" and rule["style"] == {"fill": dress.COLOUR_NEUTRAL}
        assert rule["label"] == "Above the average"
        assert dress.above_average_rule(bar(), rows(10, 30, 50), "ar", None)["label"] == "أعلى من المتوسط"

    def test_a_stored_direction_decides_good_or_bad_and_a_share_takes_its_flags(self):
        better = dress.above_average_rule(bar(), rows(1, 2, 3), "en", {"amount": {"direction": "higher_better"}})
        worse = dress.above_average_rule(bar(), rows(1, 2, 3), "en", {"amount": {"direction": "higher_worse"}})
        assert (better["style"]["fill"], worse["style"]["fill"]) == (dress.COLOUR_GOOD, dress.COLOUR_BAD)
        share = dress.above_average_rule(bar(measure="flag_pct", agg="avg"), rows(1, 2, 3), "en",
                                         {"flag": {"direction": "higher_worse"}}, {"flag_pct": "flag"})
        assert share["style"]["fill"] == dress.COLOUR_BAD

    def test_no_rule_where_it_would_say_nothing(self):
        assert dress.above_average_rule(bar(), rows(10, 30), "en", None) is None               # two groups
        assert dress.above_average_rule(bar(), rows(7, 7, 7), "en", None) is None              # all level
        assert dress.above_average_rule({**bar(), "widget_type": "line"}, rows(1, 2, 3), "en", None) is None
        own = bar(display_rules=[{"id": "theirs"}])
        assert dress.above_average_rule(own, rows(1, 2, 3), "en", None) is None                # never over someone's own


def test_a_few_carrying_most_is_a_pareto_and_an_even_split_is_not():
    assert dress.is_pareto([500, 300, 40, 30, 20, 10, 5, 5])
    assert not dress.is_pareto([100, 100, 100, 100, 100, 100, 100, 100])
    assert not dress.is_pareto([900, 50, 30])                                                   # too few groups


def test_clicking_a_group_filters_the_other_charts_of_the_page_and_nothing_else():
    widgets = [{"widget_type": "text"}, {"widget_type": "button"}, {"widget_type": "slicer"},
               {"widget_type": "kpi", "config": {"measure": "amount"}}, bar(), bar("kind"),
               {"widget_type": "line", "config": {"dimension": "day", "measure": "amount"}}]
    rel = dress.relations(widgets, {"day"})
    assert {r["from"] for r in rel} == {4, 5} and all(r["mode"] == "filter" for r in rel)
    assert {r["to"] for r in rel if r["from"] == 4} == {3, 5, 6}                                # never text, button, slicer, itself
    assert dress.relations([{"widget_type": "kpi", "config": {}}], set()) == []


def test_navigation_names_each_other_page_and_carries_the_selections():
    nav = dress.navigation(["Overview", "By group", "Over time"], 0, "en")
    assert [b["config"]["actionPageTitle"] for b in nav] == ["By group", "Over time"]
    assert all(b["widget_type"] == "button" and b["config"]["action"] == "navigate" and b["config"]["carry_filters"]
               for b in nav)
    assert dress.navigation(["Only page"], 0, "en") == []


class Gate:
    """Stands in for the designer's gate: draws from a table of results."""
    richness, percent, dates, flag_of = "balanced", set(), {"day"}, {}

    def __init__(self, results):
        self.results, self.drawn = results, []

    async def _draw(self, widget):
        self.drawn.append(widget)
        cfg = widget["config"]
        key = (widget["widget_type"], cfg.get("dimension"), bool(cfg.get("sparkline_date")), bool(cfg.get("pareto")))
        return self.results.get(key, {"rows": []}), ""


INPUTS = SimpleNamespace(
    column_meta={}, ineligible=lambda: set(),
    df=SimpleNamespace(columns=["day", "group", "kind", "amount"]),
    profile={"columns": [{"name": "group", "role": "categorical", "distinct": 5, "is_identifier": False, "is_personal": False},
                         {"name": "kind", "role": "categorical", "distinct": 3, "is_identifier": False, "is_personal": False},
                         {"name": "day", "role": "datetime"}, {"name": "amount", "role": "numeric"}]})


def page(title, *widgets):
    return {"title": title, "scope_filters": [],
            "widgets": [{"widget_type": "text", "title": title, "config": {"content": "the answer"}}, *widgets]}


def test_a_page_gains_its_options_its_filters_its_clicks_and_its_buttons():
    series = [{"period": f"2025-{m:02d}", "value": m} for m in range(1, 9)]
    gate = Gate({("bar", "group", False, False): rows(10, 30, 50, 20, 15),
                 ("kpi", None, False, False): {"rows": [{"name": "amount", "value": 125}]},
                 ("kpi", None, True, False): {"rows": [{"name": "amount", "value": 125}], "trend": {"series": series}}})
    pages = [page("Overview", {"widget_type": "kpi", "title": "Total", "question": "q1",
                               "config": {"measure": "amount", "aggregation": "sum"}}, bar()),
             page("By kind", bar("kind"))]
    asyncio.run(dress.apply(pages, gate, INPUTS, "en"))
    first = pages[0]["widgets"]
    assert [w["widget_type"] for w in first] == ["text", "button", "slicer", "kpi", "bar"]      # answer, links, filters, charts
    assert first[1]["config"]["actionPageTitle"] == "By kind"
    assert first[3]["config"]["sparkline_date"] == "day"                                       # the number has its history
    assert first[4]["config"]["display_rules"][0]["expression"] == "value > AVG(value)"
    assert pages[0]["relations"] == [{"from": 4, "to": 3, "mode": "filter"}]
    # The second page's bar drew nothing in this stand-in: it keeps its plain form.
    assert "display_rules" not in pages[1]["widgets"][-1]["config"]


def test_basic_adds_nothing_at_all():
    gate = Gate({})
    gate.richness = "basic"
    pages = [page("Overview", bar()), page("More", bar("kind"))]
    before = [list(p["widgets"]) for p in pages]
    asyncio.run(dress.apply(pages, gate, INPUTS, "en"))
    assert [p["widgets"] for p in pages] == before and gate.drawn == [] and "relations" not in pages[0]


def test_an_option_the_engine_refuses_is_dropped_and_the_chart_stays():
    refused = {**rows(10, 30, 50), "rule_errors": [{"id": "setup-above-average", "message": "no"}]}

    class Refusing(Gate):
        async def _draw(self, widget):
            return (refused if widget["config"].get("display_rules") else rows(10, 30, 50)), ""
    pages = [page("Only", bar())]
    asyncio.run(dress.apply(pages, Refusing({}), INPUTS, "en"))
    assert "display_rules" not in pages[0]["widgets"][-1]["config"]


def test_the_menu_widens_with_the_setting_and_basic_is_as_it_was():
    profile = {"structure": {"date_range": ["2024-01-01", "2025-12-31"]}, "columns": [
        {"name": "group", "role": "categorical", "distinct": 9, "is_identifier": False, "is_personal": False},
        {"name": "kind", "role": "categorical", "distinct": 3, "is_identifier": False, "is_personal": False},
        {"name": "day", "role": "datetime", "is_identifier": False, "is_personal": False},
        {"name": "amount", "role": "numeric", "is_identifier": False, "is_personal": False},
        {"name": "level", "role": "numeric", "is_identifier": False, "is_personal": False}]}
    basic, basic_text = answer.menu(profile, "basic")
    balanced, text = answer.menu(profile, "balanced")
    assert "SIMPLE CHARTS -- use these for almost everything" in basic_text and "treemap" not in basic
    assert set(basic) < set(balanced) and {"treemap", "area"} <= set(balanced)
    assert "at most 2 per page" in text and "take the kind the dashboard does not have yet" in text
    assert answer.ADVANCED_PER_PAGE == {"basic": 1, "balanced": 2, "rich": 3}
    assert answer.richness_now() == "balanced" and answer.richness_now("rich") == "rich"


class TestDrillThrough:
    def pages(self):
        kpi = {"widget_type": "kpi", "title": "Total", "question": "q1", "config": {"measure": "amount", "aggregation": "sum"}}
        line = {"widget_type": "line", "title": "By month", "config": {"dimension": "day", "measure": "amount", "aggregation": "sum"}}
        table = {"widget_type": "table", "title": "Records", "config": {"columns": ["group", "amount"]}}
        return [page("Overview", kpi, bar(), line), page("By group", bar(), bar("kind")), page("Records", table)]

    def test_the_most_used_category_gets_a_page_for_one_value_and_its_charts_open_it(self):
        pages = self.pages()
        drill = dress.drill_page(pages, INPUTS.profile, {"day"}, set(), "en")
        assert (drill["page_type"], drill["prompt_column"], drill["prompt_label"]) == ("drillthrough", "group", "Group")
        assert drill["title"] == "One group"
        # For one value: the number, the trend, the records -- never the split by the value itself.
        assert [w["widget_type"] for w in drill["widgets"]] == ["kpi", "line", "table"]
        marked = [(p["title"], w["title"]) for p in pages for w in p["widgets"] if w.get("drill_to") == "drill"]
        assert marked == [("Overview", "amount by group"), ("By group", "amount by group")]
        assert all("drill_to" not in w for w in drill["widgets"])

    def test_no_page_when_nothing_is_split_or_the_category_is_the_scope(self):
        only_numbers = [page("Overview", {"widget_type": "kpi", "title": "Total", "config": {"measure": "amount"}})]
        assert dress.drill_page(only_numbers, INPUTS.profile, {"day"}, set(), "en") is None
        pages = self.pages()
        got = dress.drill_page(pages, INPUTS.profile, {"day"}, {"group"}, "en")
        assert got["prompt_column"] == "kind"                               # the scope is one value already
        two = {**INPUTS.profile, "columns": [dict(c, distinct=2) if c["name"] in ("group", "kind") else c
                                              for c in INPUTS.profile["columns"]]}
        assert dress.drill_page(self.pages(), two, {"day"}, set(), "en") is None   # two values: nothing to pick among

    def test_it_is_added_last_with_a_way_back_and_no_button_leads_to_it(self):
        gate = Gate({("bar", "group", False, False): rows(10, 30, 50, 20, 15)})
        pages = self.pages()
        asyncio.run(dress.apply(pages, gate, INPUTS, "ar"))
        assert [p.get("page_type") for p in pages] == [None, None, None, "drillthrough"]
        drill = pages[-1]
        assert drill["widgets"][0]["widget_type"] == "button" and drill["widgets"][0]["config"]["actionPageTitle"] == "Overview"
        targets = {w["config"].get("actionPageTitle") for p in pages[:-1] for w in p["widgets"] if w["widget_type"] == "button"}
        assert drill["title"] not in targets and targets == {"Overview", "By group", "Records"}
        assert drill["title"].startswith("تفاصيل")


class TestBarAfterBar:
    def test_a_bar_could_be_what_its_shape_calls_for(self):
        assert dress.another_kind(bar(agg="sum"), 4, set(), set()) == "donut"            # a few parts of a whole
        assert dress.another_kind(bar(agg="count"), 9, set(), set()) == "treemap"         # many parts
        assert dress.another_kind(bar(agg="avg"), 5, set(), set()) == "dot_plot"          # a handful of averages
        assert dress.another_kind(bar(measure="flag_pct", agg="sum"), 5, {"flag_pct"}, set()) == "dot_plot"  # a rate is no part of a whole
        assert dress.another_kind(bar(agg="avg"), 40, set(), set()) is None               # too many to compare precisely
        assert dress.another_kind(bar("day"), 6, set(), {"day"}) is None                  # over time stays as it is
        assert dress.another_kind({**bar(), "widget_type": "line"}, 6, set(), set()) is None

    def test_the_first_comparisons_stay_bars_and_the_later_ones_change_once_each(self):
        many = rows(10, 30, 50, 20, 15, 12, 9, 7)

        class Drawing(Gate):
            async def _draw(self, widget):
                return many, ""
        pages = [page("Only", bar("a", agg="sum"), bar("b", agg="sum"), bar("c", agg="sum"), bar("d", agg="sum"),
                      bar("e", agg="avg"))]
        asyncio.run(dress.apply(pages, Drawing({}), INPUTS, "en"))
        kinds = [w["widget_type"] for w in pages[0]["widgets"] if w["widget_type"] != "text"]
        # two bars kept; the third becomes a treemap; the fourth would be a second treemap, so it stays; the averages a dot plot
        assert kinds == ["bar", "bar", "treemap", "bar", "dot_plot"]
