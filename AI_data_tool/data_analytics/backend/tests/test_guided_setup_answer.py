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
