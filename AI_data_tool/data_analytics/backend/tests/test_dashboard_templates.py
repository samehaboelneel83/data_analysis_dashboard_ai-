"""Dashboard templates: a dashboard as a reusable specification
(services/dashboard_templates). Pure rules -- no database."""
import pytest

from app.services.dashboard_templates import builtin, mapping, resolve as res, spec
from app.services.widget_roles import InvalidWidget, validate_widget_payload

COLUMNS = [
    {"name": "id", "kind": "number", "number": "code", "distinct": 5000, "ordered": False, "geo": None, "identifier": True, "label": "id"},
    {"name": "day", "kind": "date", "number": None, "distinct": 900, "ordered": False, "geo": None, "identifier": False, "label": "day"},
    {"name": "amount", "kind": "number", "number": "amount", "distinct": 4000, "ordered": False, "geo": None, "identifier": False, "label": "Amount"},
    {"name": "planned", "kind": "number", "number": "amount", "distinct": 300, "ordered": False, "geo": None, "identifier": False, "label": "planned"},
    {"name": "score", "kind": "number", "number": "score", "distinct": 5, "ordered": False, "geo": None, "identifier": False, "label": "score"},
    {"name": "group", "kind": "category", "number": None, "distinct": 12, "ordered": False, "geo": None, "identifier": False, "label": "group"},
    {"name": "step", "kind": "category", "number": None, "distinct": 5, "ordered": True, "geo": None, "identifier": False, "label": "step"},
    {"name": "area", "kind": "category", "number": None, "distinct": 16, "ordered": False, "geo": "region", "identifier": False, "label": "area"},
    {"name": "note", "kind": "text", "number": None, "distinct": 4800, "ordered": False, "geo": None, "identifier": False, "label": "note"},
    {"name": "done", "kind": "flag", "number": None, "distinct": 2, "ordered": False, "geo": None, "identifier": False, "label": "done"},
]
NAMES = {c["name"] for c in COLUMNS}


@pytest.mark.parametrize("key", sorted(builtin.BUILTIN))
def test_every_builtin_is_valid_and_resolves_into_widgets_the_engine_accepts(key):
    tpl = builtin.BUILTIN[key]
    assert spec.problems(tpl) == []
    fit = mapping.fit(tpl, COLUMNS)
    assert fit["usable"], (key, fit)
    out = res.resolve(tpl, fit["mapping"], {c["name"]: c["label"] for c in COLUMNS})
    assert out["pages"] and out["pages"][0]["widgets"]
    for page in out["pages"]:
        for w in page["widgets"]:
            # No reference is left behind, and every named column is a real one.
            assert spec.refs_in(w["config"]) == (set(), set()), w
            assert "{" not in w["title"], w["title"]
            try:
                validate_widget_payload(w["widget_type"], w["config"])
            except InvalidWidget as e:                         # pragma: no cover - the message is the point
                pytest.fail(f"{key}: '{w['title']}' is refused: {e}")
            for k in ("dimension", "dimension2", "measure", "measure2", "sparkline_date"):
                v = w["config"].get(k)
                assert v is None or v in NAMES or v in {m["name"] for m in out["measures"]}, (k, v)


def test_builtins_are_named_for_what_they_show_and_cover_every_category():
    assert {t["category"] for t in builtin.listing()} == set(spec.CATEGORIES)
    assert len({t["name"] for t in builtin.listing()}) == len(builtin.BUILTIN)


class TestMapping:
    tpl = builtin.BUILTIN["target"]

    def test_slots_are_filled_from_what_the_columns_are_never_twice_with_one_column(self):
        got = mapping.suggest(self.tpl, COLUMNS)
        assert got["actual"] != got["target"] and {got["actual"][0], got["target"][0]} == {"amount", "planned"}
        assert got["date"] == ["day"] and "id" not in sum(got.values(), [])

    def test_an_identifier_a_text_and_a_date_are_never_a_number(self):
        slot = {"id": "v", "kind": "measure"}
        assert mapping.candidates(slot, COLUMNS) == ["amount", "planned", "score"]

    def test_an_ordered_column_is_the_first_choice_for_a_stage_and_a_place_for_a_map(self):
        assert mapping.candidates({"id": "s", "kind": "stage"}, COLUMNS)[0] == "step"
        assert mapping.candidates({"id": "p", "kind": "geography"}, COLUMNS) == ["area"]

    def test_a_place_prefers_a_country_and_a_split_does_not_take_the_place_column(self):
        """F-13: Executive summary suggested `region` for both "the main way to
        split it" and "the place of each row". A label-like column fills one
        slot only, the place is chosen before the split, and a named level
        (country) beats a generic region."""
        # Demo -- Sales: region (5 sales regions, tagged geo "region") and country (14).
        places = [
            {"name": "region", "kind": "category", "number": None, "distinct": 5, "ordered": False, "geo": "region",
             "identifier": False, "label": "region"},
            {"name": "country", "kind": "category", "number": None, "distinct": 14, "ordered": False, "geo": "country",
             "identifier": False, "label": "country"},
        ]
        base = [c for c in COLUMNS if c["name"] in ("id", "day", "amount")]
        got = mapping.suggest(builtin.BUILTIN["executive"], base + places)
        assert got["place"] == ["country"]
        assert got["group"] == ["region"]
        # With many label columns, still no column in two slots.
        got = mapping.suggest(builtin.BUILTIN["executive"], [c for c in COLUMNS if c["name"] != "area"] + places)
        used = sum(got.values(), [])
        assert got["place"] == ["country"] and len(used) == len(set(used)), got

    def test_a_label_column_is_offered_once_across_label_slots(self):
        """F-13 (Low): the same column was suggested in two label slots of
        different kinds (a flag and a category)."""
        tpl = {"slots": [{"id": "f", "kind": "flag", "required": True},
                         {"id": "c", "kind": "category", "required": True}]}
        cols = [{"name": "topic", "kind": "category", "number": None, "distinct": 2, "ordered": False, "geo": None,
                 "identifier": False, "label": "topic"}]
        got = mapping.suggest(tpl, cols)
        assert sum(got.values(), []) == ["topic"]

    def test_a_mapping_is_checked_before_anything_is_made(self):
        bad = mapping.validate(self.tpl, {"actual": "amount", "target": "note", "date": "nope"}, COLUMNS)
        assert not bad["ok"]
        assert {(p["slot"], p["code"]) for p in bad["problems"]} == {
            ("target", "wrong_kind"), ("target", "required_missing"), ("date", "unknown_column")}
        ok = mapping.validate(self.tpl, {"actual": "amount", "target": "planned"}, COLUMNS)
        assert ok["ok"] and ok["missing"] == ["date", "group"]
        assert 0 < ok["widgets"]["kept"] < ok["widgets"]["total"] and ok["dropped"]

    def test_data_without_what_a_template_needs_is_not_offered_it(self):
        only_text = [c for c in COLUMNS if c["kind"] in ("text", "category")]
        fit = mapping.fit(self.tpl, only_text)
        assert not fit["usable"] and fit["score"] == 0.0 and "actual" in fit["missing"]


class TestResolving:
    tpl = builtin.BUILTIN["target"]

    def test_metrics_become_measures_named_in_the_columns_own_words(self):
        out = res.resolve(self.tpl, {"actual": "amount", "target": "planned", "group": "group"},
                          {"amount": "Amount"})
        reached = next(m for m in out["measures"] if "%" in m["name"])
        assert reached == {"name": "Amount as % of planned", "expression": "SUM(amount) / SUM(planned) * 100",
                           "format": {"type": "number", "decimals": 1, "suffix": "%"}}
        gauge = next(w for p in out["pages"] for w in p["widgets"] if w["widget_type"] == "gauge")
        assert gauge["config"]["measure"] == "Amount as % of planned"

    def test_a_chart_whose_slot_is_empty_is_left_out_and_named(self):
        out = res.resolve(self.tpl, {"actual": "amount", "target": "planned"})
        kinds = [w["widget_type"] for w in out["pages"][0]["widgets"]]
        assert "dual_axis_line" not in kinds and "gauge" in kinds
        assert {"date", "group"} >= {n for d in out["dropped"] for n in d["needs"]} and out["dropped"]
        assert out["filters"] == []

    def test_a_required_slot_left_empty_is_refused(self):
        with pytest.raises(spec.TemplateError, match="What was expected"):
            res.resolve(self.tpl, {"actual": "amount"})

    def test_a_measure_name_already_on_the_dataset_is_not_overwritten(self):
        out = res.resolve(self.tpl, {"actual": "amount", "target": "planned"},
                          existing_measures={"amount as % of planned"})
        assert out["measures"][0]["name"] == "amount as % of planned (2)"

    def test_a_column_that_cannot_be_written_into_a_formula_drops_its_metric_and_says_so(self):
        cols = COLUMNS + [{**COLUMNS[2], "name": "net amount"}]
        out = res.resolve(self.tpl, {"actual": "net amount", "target": "planned"})
        assert out["measures"] == [] and {s["why"] for s in out["skipped_metrics"]} == {"column_name"}
        assert all(w["widget_type"] != "gauge" for w in out["pages"][0]["widgets"]) and cols

    def test_click_to_filter_follows_the_charts_that_stayed(self):
        tpl = builtin.BUILTIN["overview"]
        out = res.resolve(tpl, {"value": "amount", "group": "group"})
        page = out["pages"][0]
        for r in page["relations"]:
            assert 0 <= r["from"] < len(page["widgets"]) and 0 <= r["to"] < len(page["widgets"])
        assert all(page["widgets"][r["from"]]["widget_type"] in ("bar", "donut") for r in page["relations"])

    def test_a_many_slot_fills_a_table_with_all_its_columns(self):
        out = res.resolve(builtin.BUILTIN["detail"], {"columns": ["day", "group", "amount"]})
        table = next(w for w in out["pages"][0]["widgets"] if w["widget_type"] == "table")
        assert table["config"]["columns"] == ["day", "group", "amount"] and table["config"]["dimension"] == "day"


class TestTheSpecification:
    def test_what_is_wrong_is_named(self):
        bad = {"schema": spec.SCHEMA, "name": "x", "category": "overview",
               "slots": [{"id": "a", "kind": "measure"}, {"id": "a", "kind": "colour"}],
               "metrics": [{"id": "m1", "expression": "SUM({zz})"}],
               "pages": [{"widgets": [{"widget_type": "kpi", "config": {"measure": "$nope", "x": "$m:none"}}],
                          "relations": [{"from": 0, "to": 4}]}]}
        said = " | ".join(spec.problems(bad))
        for part in ("declared twice", "kind must be", "names slot 'zz'", "uses slot 'nope'", "uses metric 'none'",
                     "points outside"):
            assert part in said, (part, said)

    def test_a_style_keeps_only_what_a_look_may_hold(self):
        got = spec.clean_style({"font_family": "serif", "font_size": 13, "border_style": "dashed", "radius": 999,
                                "card_background": "red", "page_background": "#fff", "onclick": "x", "shadow": "soft"})
        assert got == {"font_family": "serif", "font_size": 13, "border_style": "dashed", "page_background": "#fff",
                       "shadow": "soft"}

    def test_the_preview_is_the_first_page_as_boxes(self):
        boxes = spec.schematic(builtin.BUILTIN["overview"])
        assert boxes[0] == {"x": 0, "y": 0, "w": 3, "h": 3, "kind": "kpi"} and len(boxes) == 8


class TestSavingADashboardAsATemplate:
    from app.services.dashboard_templates import capture as _capture
    PAGES = [{"name": "Main", "page_type": "normal", "page_size": "16:9", "widgets": [
        {"id": 11, "widget_type": "kpi", "title": "Total Amount",
         "config": {"measure": "amount", "aggregation": "sum", "sparkline_date": "day", "dataset_id": 7,
                    "__export": "x", "filters": [{"column": "group", "op": "eq", "value": "a"}]},
         "layout": {"x": 0, "y": 0, "w": 3, "h": 3}},
        {"id": 12, "widget_type": "bar", "title": "amount by group",
         "config": {"dimension": "group", "measure": "amount", "aggregation": "sum",
                    "interaction": {"actions": [{"targetId": 13, "mode": "filter"}]},
                    "display_rules": [{"kind": "expression", "expression": "value > AVG(value)"},
                                      {"kind": "value_map", "map": {"a": "#f00"}}]},
         "layout": {"x": 3, "y": 0, "w": 9, "h": 6}},
        {"id": 13, "widget_type": "gauge", "title": "Reached", "config": {"measure": "Reached %"},
         "layout": {"x": 0, "y": 3, "w": 3, "h": 3}},
        {"id": 14, "widget_type": "bar", "title": "gone", "config": {"dimension": "no_such_column"}}]}]
    MEASURES = [{"name": "Reached %", "expression": "SUM(amount) / SUM(planned) * 100"}]

    def _made(self):
        return self._capture.from_report(self.PAGES, COLUMNS, self.MEASURES, name="Mine", category="target",
                                         style={"font_family": "serif", "bogus": 1})

    def test_columns_become_slots_and_measures_become_metrics(self):
        tpl, _left = self._made()
        assert spec.problems(tpl) == []
        kinds = {s["id"]: s["kind"] for s in tpl["slots"]}
        assert kinds == {"amount": "measure", "day": "date", "group": "category", "planned": "measure"}
        assert tpl["metrics"] == [{"id": "m1", "label": "Reached %", "expression": "SUM({amount}) / SUM({planned}) * 100"}]
        assert next(s for s in tpl["slots"] if s["id"] == "amount")["required"]
        assert tpl["style"] == {"font_family": "serif"}

    def test_what_belongs_to_this_data_is_taken_out_and_counted(self):
        tpl, left = self._made()
        kpi, bar, gauge = tpl["pages"][0]["widgets"]
        assert kpi["config"] == {"measure": "$amount", "aggregation": "sum", "sparkline_date": "$day", "filters": []}
        assert kpi["title"] == "Total {amount}" and bar["title"] == "{amount} by {group}"
        assert [r["kind"] for r in bar["config"]["display_rules"]] == ["expression"]
        assert "interaction" not in bar["config"] and gauge["config"]["measure"] == "$m:m1"
        assert tpl["pages"][0]["relations"] == [{"from": 1, "to": 2, "mode": "filter"}]
        assert left == {"filters": 1, "rules": 1, "unknown": ["no_such_column"]}

    def test_a_saved_template_draws_on_other_data(self):
        tpl, _ = self._made()
        other = [{**c, "name": n, "label": n} for c, n in zip(
            [COLUMNS[1], COLUMNS[2], COLUMNS[3], COLUMNS[5]], ["when", "cost", "budget", "team"])]
        fit = mapping.fit(tpl, other)
        assert fit["usable"] and fit["widgets"]["kept"] == fit["widgets"]["total"]
        out = res.resolve(tpl, fit["mapping"])
        titles = [w["title"] for w in out["pages"][0]["widgets"]]
        assert titles[1] in ("cost by team", "budget by team") and out["measures"][0]["expression"].startswith("SUM(")


class TestHowWellATemplateSuits:
    def _cols(self, **units):
        return [{**c, "unit": units.get(c["name"])} for c in COLUMNS]

    def test_a_target_in_the_same_unit_is_chosen_and_scores_higher_than_one_in_another(self):
        tpl = builtin.BUILTIN["target"]
        same = mapping.fit(tpl, self._cols(amount="kg", planned="kg", score="pts"))
        assert {same["mapping"]["actual"][0], same["mapping"]["target"][0]} == {"amount", "planned"}
        other = mapping.fit(tpl, self._cols(amount="kg", planned="days", score="pts"))
        unknown = mapping.fit(tpl, self._cols())
        assert same["score"] > unknown["score"] > other["score"] and other["usable"]

    def test_an_ordered_column_makes_the_stages_template_a_surer_match(self):
        tpl = builtin.BUILTIN["stages"]
        plain = [{**c, "ordered": False} for c in COLUMNS]
        assert mapping.fit(tpl, COLUMNS)["match"] > mapping.fit(tpl, plain)["match"]

    def test_only_a_metric_some_chart_shows_is_defined(self):
        tpl = {**builtin.BUILTIN["target"],
               "metrics": [*builtin.BUILTIN["target"]["metrics"],
                           {"id": "unused", "label": "nobody shows this", "expression": "SUM({actual})"}]}
        out = res.resolve(tpl, {"actual": "amount", "target": "planned"})
        assert "nobody shows this" not in [m["name"] for m in out["measures"]]


def test_a_gauge_can_show_a_defined_measure():
    import pandas as pd
    from app.services.widget_data import shape_gauge
    df = pd.DataFrame({"done": [30.0, 20.0], "planned": [50.0, 50.0]})
    got = shape_gauge(df, {"measure": "Reached", "target_value": 100,
                           "measure_defs": [{"name": "Reached", "expression": "SUM(done) / SUM(planned) * 100"}]})
    assert got["type"] == "gauge" and got["value"] == 50.0 and got["target"] == 100.0
    assert shape_gauge(df, {"measure": "nothing here"})["type"] == "empty"


class TestATemplatesOwnSampleData:
    """Every template can be looked at on rows made from its own slots."""

    @pytest.mark.parametrize("key", sorted(builtin.BUILTIN))
    def test_every_builtin_draws_every_chart_on_its_sample(self, key):
        from app.services.dashboard_templates import sample
        got = sample.preview(builtin.BUILTIN[key])
        total = sum(len(p["widgets"]) for p in builtin.BUILTIN[key]["pages"])
        widgets = [w for p in got["pages"] for w in p["widgets"]]
        assert len(widgets) == total and got["rows"] > 0
        for w in widgets:
            d = w["data"]
            assert d.get("type") not in ("error", "empty"), (key, w["title"], d.get("message"))
            assert "{" not in w["title"]

    def test_the_sample_is_placeholders_made_from_the_slots_and_the_same_every_time(self):
        from app.services.dashboard_templates import sample
        tpl = builtin.BUILTIN["target"]
        df, mapping_ = sample.frame(tpl)
        assert set(mapping_) == {s["id"] for s in tpl["slots"]}
        assert set(df["group"].unique()) <= {f"Group {c}" for c in "ABCDEF"}
        # What is measured against another number sits near it.
        assert 0.8 < df["target"].sum() / df["actual"].sum() < 1.4
        assert sample.frame(tpl)[0].equals(df)

    def test_a_saved_template_has_a_sample_too(self):
        from app.services.dashboard_templates import capture, sample
        tpl, _ = capture.from_report(TestSavingADashboardAsATemplate.PAGES, COLUMNS,
                                     TestSavingADashboardAsATemplate.MEASURES, name="Mine")
        got = sample.preview(tpl)
        assert [w["data"].get("type") for w in got["pages"][0]["widgets"]].count("error") == 0


def test_a_measure_the_dataset_already_defines_the_same_way_is_used_not_defined_again():
    tpl = builtin.BUILTIN["target"]
    first = res.resolve(tpl, {"actual": "amount", "target": "planned"})
    again = res.resolve(tpl, {"actual": "amount", "target": "planned"},
                        existing_measures={m["name"]: m["expression"] for m in first["measures"]})
    assert again["measures"] == []
    assert [w["config"].get("measure") for w in again["pages"][0]["widgets"] if w["widget_type"] == "gauge"] == [
        "amount as % of planned"]


class TestWhatATemplateWritesIsInTheReadersLanguage:
    def test_every_word_a_builtin_writes_has_its_arabic(self):
        from app.services.dashboard_templates import words
        said = set()
        for t in builtin.listing():
            said |= {s["label"] for s in t["slots"]} | {m["label"] for m in t.get("metrics") or []}
            for p in t["pages"]:
                said.add(p["name"])
                said |= {w["title"] for w in p["widgets"] if spec.named_in(w["title"]) != {w["title"].strip("{}")}
                         or not w["title"].startswith("{")}
        missing = sorted(x for x in said if x not in words.AR and not (x.startswith("{") and x.endswith("}") and x.count("{") == 1))
        assert missing == []
        # A translation keeps exactly the slots of its English.
        for en, ar in words.AR.items():
            assert spec.named_in(en) == spec.named_in(ar), en

    def test_an_arabic_reader_gets_arabic_titles_pages_and_measures(self):
        from app.services.dashboard_templates import words
        tpl = words.localise(builtin.BUILTIN["target"], "ar")
        out = res.resolve(tpl, {"actual": "amount", "target": "planned", "group": "group"})
        assert out["pages"][0]["name"] == "المستهدف"
        assert "amount كنسبة من planned" in [m["name"] for m in out["measures"]]
        assert "الفرق حسب group" in [w["title"] for w in out["pages"][0]["widgets"]]
        # English, an unknown language and a saved template are left as they are.
        assert words.localise(builtin.BUILTIN["target"], "en") is builtin.BUILTIN["target"]
        mine = {**builtin.BUILTIN["target"], "key": None}
        assert words.localise(mine, "ar") is mine


class TestTheRoomOfWhatIsLeftOut:
    def test_a_row_that_lost_a_chart_is_shared_by_the_ones_that_stayed(self):
        # Four numbers across; the fourth is left out: three share the twelve columns.
        row = [{"x": 0, "y": 0, "w": 3, "h": 3}, {"x": 3, "y": 0, "w": 3, "h": 3},
               {"x": 6, "y": 0, "w": 3, "h": 3}, {"x": 9, "y": 0, "w": 3, "h": 3}]
        got = res.reflow(row, [0, 1, 2])
        assert [(got[i]["x"], got[i]["w"]) for i in (0, 1, 2)] == [(0, 4), (4, 4), (8, 4)]

    def test_a_row_that_lost_everything_closes(self):
        page = [{"x": 0, "y": 0, "w": 12, "h": 3}, {"x": 0, "y": 3, "w": 12, "h": 6}, {"x": 0, "y": 9, "w": 12, "h": 5}]
        got = res.reflow(page, [0, 2])
        assert got[2]["y"] == 3 and got[0]["y"] == 0

    def test_nothing_moves_on_a_page_that_kept_everything(self):
        page = [{"x": 2, "y": 4, "w": 5, "h": 3}, {"x": 7, "y": 4, "w": 5, "h": 3}]
        assert res.reflow(page, [0, 1]) == {0: page[0], 1: page[1]}

    def test_a_template_with_optional_parts_left_empty_has_no_holes(self):
        out = res.resolve(builtin.BUILTIN["overview"], {"value": "amount"})
        boxes = [w["layout"] for w in out["pages"][0]["widgets"]]
        # No two charts overlap, the first row is full, and the page starts at the top.
        assert min(b["y"] for b in boxes) == 0
        assert sum(b["w"] for b in boxes if b["y"] == 0) == 12
        for a in boxes:
            for b in boxes:
                if a is not b:
                    assert not (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                                and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]), (a, b)


class TestLinksBetweenPages:
    from app.services.dashboard_templates import capture as _capture
    PAGES = [
        {"id": 1, "name": "Main", "widgets": [
            {"id": 11, "widget_type": "bar", "title": "amount by group",
             "config": {"dimension": "group", "measure": "amount", "aggregation": "sum", "drillthroughPageId": 2},
             "layout": {"x": 0, "y": 0, "w": 8, "h": 5}},
            {"id": 12, "widget_type": "button", "title": "Details",
             "config": {"label": "Details", "action": "navigate", "actionPageId": 2},
             "layout": {"x": 8, "y": 0, "w": 4, "h": 2}}]},
        {"id": 2, "name": "One group", "page_type": "drillthrough", "prompt_column": "group", "prompt_label": "Group",
         "widgets": [{"id": 21, "widget_type": "line", "title": "amount over time",
                      "config": {"dimension": "day", "measure": "amount", "aggregation": "sum"},
                      "layout": {"x": 0, "y": 0, "w": 12, "h": 6}}]}]

    def _tpl(self):
        return self._capture.from_report(self.PAGES, COLUMNS, [], name="Linked")[0]

    def test_a_button_and_a_drill_through_are_kept_by_the_pages_name(self):
        tpl = self._tpl()
        assert spec.problems(tpl) == []
        bar, button = tpl["pages"][0]["widgets"]
        assert bar["config"]["drill_page"] == "One group" and "drillthroughPageId" not in bar["config"]
        assert button["config"]["actionPageTitle"] == "One group" and "actionPageId" not in button["config"]
        assert tpl["pages"][1]["prompt_column"] == "$group" and tpl["pages"][1]["page_type"] == "drillthrough"

    def test_on_other_data_the_page_opens_for_the_mapped_column(self):
        out = res.resolve(self._tpl(), {"group": "step", "amount": "planned", "day": "day"})
        assert out["pages"][1]["prompt_column"] == "step" and out["pages"][1]["page_type"] == "drillthrough"
        assert out["pages"][0]["widgets"][0]["config"]["drill_page"] == "One group"

    def test_a_link_to_a_page_that_was_left_out_goes_with_it(self):
        out = res.resolve(self._tpl(), {"group": "step", "amount": "planned"})
        assert [p["name"] for p in out["pages"]] == ["Main"]
        configs = [w["config"] for w in out["pages"][0]["widgets"]]
        assert all("drill_page" not in c and "actionPageTitle" not in c for c in configs)


def test_an_optional_setting_is_left_off_and_the_chart_stays():
    # No date mapped: the headline numbers keep their figure and lose only their history.
    out = res.resolve(builtin.BUILTIN["overview"], {"value": "amount"})
    numbers = [w for w in out["pages"][0]["widgets"] if w["widget_type"] == "kpi"]
    assert [w["title"] for w in numbers] == ["Total amount", "Rows", "Average amount"]
    assert all("sparkline_date" not in w["config"] for w in numbers)
    with_date = res.resolve(builtin.BUILTIN["overview"], {"value": "amount", "date": "day"})
    assert next(w for w in with_date["pages"][0]["widgets"] if w["widget_type"] == "kpi")["config"]["sparkline_date"] == "day"
    # An optional reference to a slot nobody declared is still an error.
    bad = {**builtin.BUILTIN["overview"], "pages": [{"name": "p", "widgets": [
        {"widget_type": "kpi", "title": "x", "config": {"measure": "$value", "sparkline_date": "$?nope"}}]}]}
    assert any("nope" in x for x in spec.problems(bad))


class TestReflowBesideATallChart:
    def test_room_beside_and_under_a_chart_is_taken_up(self):
        # A tall chart on the right, two rows on the left; the lower-left chart is left out.
        page = [{"x": 0, "y": 0, "w": 8, "h": 3}, {"x": 0, "y": 3, "w": 8, "h": 3}, {"x": 8, "y": 0, "w": 4, "h": 6},
                {"x": 0, "y": 6, "w": 12, "h": 5}]
        got = res.reflow(page, [0, 2, 3])
        # The upper-left chart grows down to meet the chart below; nothing overlaps; no hole is left.
        assert got[0] == {"x": 0, "y": 0, "w": 8, "h": 6} and got[2]["h"] == 6 and got[3]["y"] == 6
        area = sum(b["w"] * b["h"] for b in got.values())
        assert area == 12 * (got[3]["y"] + got[3]["h"])

    def test_a_chart_is_never_stretched_to_more_than_twice_its_height_or_over_another(self):
        page = [{"x": 0, "y": 0, "w": 6, "h": 2}, {"x": 6, "y": 0, "w": 6, "h": 9}, {"x": 0, "y": 2, "w": 6, "h": 7}]
        got = res.reflow(page, [0, 1])
        assert got[0]["h"] <= 4
        boxes = list(got.values())
        for a in boxes:
            for b in boxes:
                if a is not b:
                    assert not (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                                and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def test_charts_of_an_additional_dataset_are_counted_apart_from_the_fit():
    tpl = {**builtin.BUILTIN["overview"], "datasets": [{"key": "d2", "label": "costs"}],
           "slots": [*builtin.BUILTIN["overview"]["slots"], {"id": "cost", "label": "cost", "kind": "measure",
                                                              "required": True, "dataset": "d2"}],
           "pages": [{"name": "Overview", "widgets": [
               *builtin.BUILTIN["overview"]["pages"][0]["widgets"],
               {"widget_type": "kpi", "title": "cost", "dataset": "d2", "config": {"measure": "$cost", "aggregation": "sum"},
                "layout": {"x": 0, "y": 15, "w": 3, "h": 3}}]}]}
    fit = mapping.fit(tpl, COLUMNS)
    assert fit["usable"] and fit["widgets"] == {"kept": 8, "total": 8}
    assert fit["elsewhere"] == {"widgets": 1, "datasets": ["costs"]} and "cost" not in fit["missing"]
    assert mapping.fit(builtin.BUILTIN["overview"], COLUMNS)["elsewhere"] is None


def test_an_optional_column_in_a_list_is_left_out_and_the_chart_keeps_the_rest():
    tpl = builtin.BUILTIN["correlation"]
    out = res.resolve(tpl, {"value": ["x"], "other": ["y"]})
    grid = next(w for w in out["pages"][0]["widgets"] if w["widget_type"] == "correlation_matrix")
    assert grid["config"]["measures"] == ["x", "y"]
    out = res.resolve(tpl, {"value": ["x"], "other": ["y"], "d": ["z"]})
    assert next(w for w in out["pages"][0]["widgets"] if w["widget_type"] == "correlation_matrix")["config"]["measures"] == ["x", "y", "z"]


def test_a_network_draws_when_some_rows_have_no_other_end():
    import pandas as pd
    from app.services.widget_data import shape_network
    df = pd.DataFrame({"a": ["p", "q", None, "p", "r"], "b": ["x", None, "y", "x", "y"], "n": [1, 2, 3, 4, 5]})
    got = shape_network(df, {"dimension": "a", "dimension2": "b", "measure": "n", "aggregation": "sum"})
    assert got.get("type") != "error" and got.get("edges") or got.get("links") or got.get("rows")


def test_two_numbers_as_points_are_a_sample_of_the_whole_range_not_the_left_edge():
    import numpy as np
    import pandas as pd
    from app.services.widget_data import shape_xy_numeric
    df = pd.DataFrame({"x": np.arange(10_000.0), "y": np.arange(10_000.0) * 2})
    first = shape_xy_numeric(df, {"measure": "x", "measure2": "y", "limit": 100})
    cloud = shape_xy_numeric(df, {"measure": "x", "measure2": "y", "limit": 100, "points": True})
    assert max(r["x"] for r in first["rows"]) == 99                 # as before: the hundred smallest
    assert len(cloud["rows"]) == 100 and max(r["x"] for r in cloud["rows"]) > 9000 and cloud["truncation"]
    assert cloud["rows"] == shape_xy_numeric(df, {"measure": "x", "measure2": "y", "limit": 100, "points": True})["rows"]
