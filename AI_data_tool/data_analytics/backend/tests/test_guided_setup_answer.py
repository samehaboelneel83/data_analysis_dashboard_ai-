"""Guided setup v2: charts are kept for what they show, and answers use only their numbers."""
from app.services.guided_setup import answer

DATES = {"month"}


def series(*pairs):
    return {"type": "series", "rows": [{"name": n, "value": v} for n, v in pairs]}


def w(wt, **config):
    return {"widget_type": wt, "title": "t", "config": config}


class TestWorth:
    def test_a_real_difference_is_kept(self):
        assert answer.worth(w("bar", dimension="city", measure="fee", aggregation="avg"),
                            series(("Cairo", 80), ("Aswan", 140)), DATES) is None

    def test_the_same_value_everywhere_says_nothing(self):
        assert answer.worth(w("bar", dimension="city", measure="fee", aggregation="median"),
                            series(("Cairo", 100), ("Giza", 100.2), ("Aswan", 100.1)), DATES) == "flat"

    def test_one_group_is_not_a_comparison(self):
        assert answer.worth(w("donut", dimension="kind"), series(("Express", 900)), DATES) == "single"

    def test_a_headline_of_zero(self):
        assert answer.worth(w("kpi", measure="change_pct", aggregation="median"), series(("x", 0)), DATES) == "zero"
        assert answer.worth(w("kpi", measure="id", aggregation="count"), series(("x", 0)), DATES) is None

    def test_a_top_list_whose_values_tie(self):
        assert answer.worth(w("bar", dimension="stock", measure="chg", aggregation="max", limit=10),
                            series(("A", 5), ("B", 5), ("C", 5), ("D", 5.2), ("E", 5)), DATES) is None
        assert answer.worth(w("bar", dimension="stock", measure="n", aggregation="count", limit=3),
                            series(("A", 7), ("B", 3), ("C", 7), ("D", 7)), DATES) == "tied"

    def test_mostly_unknown(self):
        assert answer.worth(w("bar", dimension="reason", aggregation="count"),
                            series(("Unknown", 900), ("Refused", 60), ("Damaged", 40)), DATES) == "unknown"

    def test_a_line_over_time_needs_more_than_one_period_and_some_movement(self):
        line = w("line", dimension="month", measure="fee", aggregation="sum")
        assert answer.worth(line, series(("2024-01", 5)), DATES) == "single"
        assert answer.worth(line, series(("2024-01", 5), ("2024-02", 9)), DATES) is None


class TestFinding:
    def test_groups_time_and_one_number(self):
        bar = w("bar", dimension="city", measure="fee", aggregation="avg")
        assert answer.finding(bar, series(("Cairo", 80), ("Aswan", 140.5)), DATES, "en") == \
            "Highest: Aswan (140.50); lowest: Cairo (80)"
        line = w("line", dimension="month", measure="n", aggregation="count")
        assert answer.finding(line, series(("2024-01-01T00:00:00", 1000), ("2025-01-01T00:00:00", 1500)),
                              DATES, "en") == "2024: 1,000 → 2025: 1,500 (+50%)"
        assert answer.finding(w("kpi", measure="fee"), series(("fee", 1234.5)), DATES, "en") == "1,234"


class TestHonestText:
    ALLOWED = [17427.0, 17.4, 3032.0, 31.6]

    def test_numbers_from_the_charts_stay_rounded_or_not(self):
        text = "Of 17,427 Express parcels, about 17% arrived late. That is 3,032 parcels."
        assert answer.honest_text(text, self.ALLOWED) == text

    def test_a_sentence_with_an_invented_number_is_dropped(self):
        text = "17.4% of Express parcels were late. This costs the company 250,000 EGP a month."
        assert answer.honest_text(text, self.ALLOWED) == "17.4% of Express parcels were late."

    def test_a_bare_number_is_not_excused_as_a_scaled_one(self):
        assert answer.honest_text("The top customer paid 1,299.", [1299400.0]) == ""
        assert answer.honest_text("The top customer paid 1.3M.", [1299400.0]) == "The top customer paid 1.3M."

    def test_scaled_and_arabic_numbers(self):
        assert answer.honest_text("About 17.4K parcels.", self.ALLOWED) == "About 17.4K parcels."
        assert answer.honest_text("تأخر ١٧٫٤٪ من الشحنات.", self.ALLOWED) == "تأخر ١٧٫٤٪ من الشحنات."

    def test_small_counts_and_years_are_not_figures_to_check(self):
        assert answer.honest_text("The top 3 cities since 2024.", [9.0]) == "The top 3 cities since 2024."


class TestScope:
    def test_the_scope_goes_in_front_and_wins_on_its_column(self):
        scope = [{"column": "kind", "op": "in", "value": ["Express"]}]
        got = answer.with_scope({"measure": "fee", "filters": [{"column": "kind", "op": "eq", "value": "Standard"},
                                                               {"column": "status", "op": "eq", "value": "Late"}]},
                                scope)
        assert got["filters"] == [{"column": "kind", "op": "in", "value": ["Express"]},
                                  {"column": "status", "op": "eq", "value": "Late"}]
        assert answer.with_scope({"measure": "fee"}, []) == {"measure": "fee"}

    def test_the_same_numbers_in_another_shape_are_one_reading(self):
        bar = w("bar", dimension="city", measure="fee", aggregation="avg")
        table = w("table", dimension="city", measure="fee", aggregation="avg", columns=["city", "fee"])
        assert answer._reading(bar) == answer._reading(table)
        assert answer._reading(w("table", columns=["a"])) != answer._reading(w("table", columns=["b"]))


# ── retry-2 (2026-10-11): what the third round of the seven requests exposed ──
class TestRowsStillOnTheirWay:
    """A share of an outcome leaves out the rows whose outcome is not known yet."""

    def gate(self, df):
        from types import SimpleNamespace
        return SimpleNamespace(inputs=SimpleNamespace(df=df), dates={"began"}, _open={}, open_notes={}, made=[])

    def frame(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(0)
        began = pd.date_range("2025-01-01", periods=12, freq="MS").repeat(200)
        state = rng.choice(["done", "back"], len(began), p=[0.9, 0.1]).astype(object)
        newest = began >= pd.Timestamp("2025-12-01")
        state[newest & (rng.random(len(began)) < 0.3)] = "moving"       # only rows begun last month are still moving
        return pd.DataFrame({"began": began, "state": state, "n": 1})

    def test_a_value_held_only_by_the_newest_rows_is_still_open(self):
        from app.services.guided_setup.answer import Gate
        df = self.frame()
        assert Gate.open_values(self.gate(df), "state") == ["moving"]
        assert Gate.open_values(self.gate(df), "nothing") == []

    def test_a_value_spread_over_the_whole_history_is_an_outcome(self):
        from app.services.guided_setup.answer import Gate
        df = self.frame()
        df.loc[df["state"] == "moving", "state"] = "done"
        assert Gate.open_values(self.gate(df), "state") == []

    def test_the_share_gets_the_filter_and_the_page_says_so_once(self):
        from app.services.guided_setup.answer import Gate
        g = self.gate(self.frame())
        g.made = [{"name": "state_done_pct", "expression": 'IF(state == "done", 100, 0)'}]
        g._share_of = lambda m: Gate._share_of(g, m)
        g.open_values = lambda c: Gate.open_values(g, c)
        w = {"widget_type": "line", "config": {"dimension": "began", "measure": "state_done_pct", "aggregation": "avg"}}
        got = Gate._known_outcomes(g, w)
        assert got["config"]["filters"] == [{"column": "state", "op": "neq", "value": "moving"}]
        assert g.open_notes == {"state": ["moving"]}
        # A chart of something else, and one that already filters the column, are left as they are.
        other = {"widget_type": "kpi", "config": {"measure": "n", "aggregation": "sum"}}
        assert Gate._known_outcomes(g, other) is other
        own = {**w, "config": {**w["config"], "filters": [{"column": "state", "op": "eq", "value": "back"}]}}
        assert Gate._known_outcomes(g, own) is own


class TestQuestionsTheScopeRulesOut:
    DEM = {"questions": [
        {"id": "q1", "text": "What share of first kind items were on time?", "asked": True},
        {"id": "q2", "text": "How does the first kind compare to second kind and third kind?", "asked": False},
        {"id": "q3", "text": "How do ratings compare across each kind?", "asked": False},
        {"id": "q4", "text": "How long do they usually take?", "asked": False},
        {"id": "q5", "text": "How does it compare to the second kind?", "asked": True},
    ]}

    def df(self):
        import pandas as pd
        return pd.DataFrame({"kind": ["first kind", "second kind", "third kind"] * 4, "days": range(12)})

    def test_added_questions_that_compare_across_the_narrowed_column_are_dropped(self):
        from app.services.guided_setup.answer import without_impossible
        got = without_impossible(self.DEM, [{"column": "kind", "op": "in", "value": ["first kind"]}], self.df())
        # q2 names other values, q3 names the column; q4 is fine; the person's own q5 is never touched.
        assert [q["id"] for q in got["questions"]] == ["q1", "q4", "q5"]

    def test_nothing_is_dropped_without_a_narrowing_to_one_value(self):
        from app.services.guided_setup.answer import without_impossible
        assert without_impossible(self.DEM, [], self.df()) is self.DEM
        two = [{"column": "kind", "op": "in", "value": ["first kind", "second kind"]}]
        assert without_impossible(self.DEM, two, self.df()) is self.DEM


def test_the_answer_writer_is_given_a_share_with_its_sign():
    from types import SimpleNamespace
    from app.services.guided_setup import answer as a
    w = {"widget_type": "bar", "title": "Share by group", "finding": "Highest: x (0.5%)",
         "config": {"dimension": "g", "measure": "flag_pct", "aggregation": "avg"}}
    result = {"type": "series", "rows": [{"name": "x", "value": 0.511}, {"name": "y", "value": 0.349}]}
    gate = SimpleNamespace(results={a._key(w): result}, dates=set(), percent={"flag_pct"})
    text, _allowed = a._digest({"widgets": [w]}, gate)
    assert "x=0.511%" in text and "y=0.349%" in text
    gate.percent = set()
    assert "x=0.511%" not in a._digest({"widgets": [w]}, gate)[0]
