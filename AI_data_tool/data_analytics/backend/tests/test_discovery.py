"""Discovery: what a dataset supports and what it shows, without a model
(docs/discovery/PLAN.md, phase 1)."""
import asyncio

import numpy as np
import pandas as pd
import pytest

from app.services.discovery import capabilities as caps
from app.services.discovery import engine
from app.services.discovery import profile as store


def frame(n=600, seed=3):
    rng = np.random.default_rng(seed)
    day = pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, 700, n), "D")
    group = rng.choice(["a", "b", "c"], n)
    return pd.DataFrame({
        "k_id": np.arange(n) + 1000, "d1": day, "g": group, "h": rng.choice(["x", "y"], n),
        "v1": rng.uniform(10, 500, n).round(2), "v2": rng.normal(50, 8, n),
        "done": rng.random(n) < np.where(group == "a", 0.6, 0.2),
        "note": [f"free text number {i} with several different words in it" for i in range(n)],
    })


META = {"v1": {"number": "amount"}, "v2": {"number": "level"}, "k_id": {"number": "code"}}


class TestTheStoredProfile:
    def test_it_measures_each_column_by_what_it_holds(self):
        got = store.compute(frame())
        c = got["columns"]
        assert got["table"]["rows"] == 600 and got["table"]["sampled"] is False
        assert c["v1"]["kind"] == "number" and c["v1"]["min"] >= 10 and c["v1"]["p50"] < c["v1"]["p95"]
        assert c["d1"]["kind"] == "date" and c["d1"]["periods"] >= 20
        assert c["done"]["kind"] == "flag"
        assert c["g"]["kind"] == "text" and [v for v, _ in c["g"]["top"]] and c["g"]["distinct"] == 3
        assert "top" not in c["note"] and c["note"]["len_avg"] > 25        # free text: its shape, never its contents

    def test_a_text_column_of_numbers_is_noticed(self):
        df = pd.DataFrame({"t": [str(i) for i in range(80)] + ["n/a"] * 20})
        assert store.compute(df)["columns"]["t"]["numeric_share"] == pytest.approx(0.8, abs=0.05)

    def test_a_reader_under_a_row_rule_gets_no_values_and_no_hidden_column(self):
        full = store.compute(frame())
        seen = store.for_reader(full, denied={"v2"}, row_rule=True)
        assert "v2" not in seen["columns"] and seen["restricted"] is True
        assert "min" not in seen["columns"]["v1"] and "top" not in seen["columns"]["g"]
        assert seen["columns"]["v1"]["kind"] == "number"                    # what it is, not what it holds

    def test_the_version_follows_the_file(self, tmp_path):
        from types import SimpleNamespace
        f = tmp_path / "d.csv"
        f.write_text("a\n1\n")
        ds = SimpleNamespace(filename=str(f), mode="import", row_count=1)
        before = store.fingerprint(ds)
        f.write_text("a\n1\n2\n")
        assert store.fingerprint(ds) != before


class TestTheRegistry:
    def test_every_proposable_widget_and_every_analysis_is_described(self):
        from app.services.analysis import registry
        assert caps.undescribed_widgets() == []
        assert [s.name for s in registry.all_analyses() if caps.analysis(s.name) is None] == []
        assert [n for n in caps._ANALYSES if registry.get(n) is None] == []

    def test_its_minimums_are_the_analyses_own(self):
        from app.services.analysis import (automated_prediction, decision_tree, forecast_scenario, influencers,
                                           segment, text_sentiment, text_topics)
        assert caps.analysis("automated_prediction").minimum["rows"] == automated_prediction.MIN_ROWS
        assert caps.analysis("decision_tree").minimum["rows"] == decision_tree.MIN_ROWS
        assert caps.analysis("key_influencers").minimum["rows"] == influencers.MIN_ROWS
        assert caps.analysis("segment").minimum["rows"] == segment.MIN_ROWS
        assert caps.analysis("forecast_scenario").minimum["periods"] == forecast_scenario.MIN_PERIODS
        assert caps.analysis("text_topics").minimum["texts"] == text_topics.MIN_DOCUMENTS
        assert caps.analysis("text_sentiment").minimum["texts"] == text_sentiment.MIN_DOCUMENTS

    def test_every_record_uses_the_shared_words(self):
        for c in caps.all_capabilities().values():
            assert c.family in caps.FAMILIES and c.claim in caps.CLAIMS, c.name
            assert set(c.needs) <= set(caps.KINDS) and set(c.answers) <= set(caps.ANSWERS), c.name
            assert c.llm == "none"                         # nothing in the catalogue needs a model

    def test_a_time_chart_needs_a_date_not_a_category(self):
        assert caps.widget("line").needs == {"date": 1}
        assert caps.widget("map_points").needs == {"coords": 1}

    def test_the_designer_reads_the_same_requirements(self):
        from app.services import suggest_dataset_dashboard as sdd
        assert sdd._NEEDS_DATE is caps.NEEDS_DATE and sdd._NEEDS_STRUCTURE is caps.NEEDS_STRUCTURE


class TestWhatTheDataSupports:
    def kinds(self):
        return engine.column_kinds(store.compute(frame()), META)

    def test_columns_are_read_by_shape_and_classification(self):
        k = self.kinds()
        assert k["v1"] == {"number", "additive"} and k["v2"] == {"number", "level"}
        assert k["k_id"] == {"key"} and k["d1"] == {"date"} and k["note"] == {"text"}
        assert k["done"] == {"category", "outcome"} and k["g"] == {"category"}

    def test_a_hidden_or_withheld_column_takes_no_part(self):
        k = engine.column_kinds(store.compute(frame()), {**META, "v2": {"hidden": True},
                                                          "g": {"eligible_for_suggestion": False}})
        assert "v2" not in k and "g" not in k

    def test_it_says_why_something_is_not_supported_in_plain_words(self):
        df = frame()[["g", "h", "v1"]]
        base = engine.tier0(store.compute(df), META)
        no = {n["capability"]: n["reason"] for n in base["not_offered"]}
        assert no["forecast_ets"] == "needs a date column; this data has none"
        assert no["text_topics"] == "needs a column of free text; this data has none"
        assert "key_influencers" in no and "outcome" not in no["key_influencers"]     # said in words, not jargon

    def test_tier_zero_reads_no_rows(self):
        """From the stored figures alone: the frame is not an argument at all."""
        base = engine.tier0(store.compute(frame()), META)
        names = {c["capability"] for c in base["cards"]}
        assert {"forecast_ets", "key_influencers", "segment", "association_rules", "text_topics"} <= names
        for c in base["cards"]:
            assert c["source"] == "deterministic" and c["llm"] == "none"
            if c["kind"] in ("analysis", "widget"):      # a widget here is a calendar reading (PLAN §N-1)
                assert c["evidence"] is None and c["why"]["reason"] == "fit"        # nothing computed, and it says so
            else:
                assert c["cost"]["tier"] == 0                                        # read off the stored profile

    def test_the_columns_chosen_for_an_analysis_are_real_ones_of_the_right_kind(self):
        base = engine.tier0(store.compute(frame()), META)
        fc = next(c for c in base["cards"] if c["capability"] == "forecast_ets")
        assert fc["action"] == {"kind": "add_widget", "widget_type": "forecast",
                                "config": {"dimension": "d1", "measure": "v1", "aggregation": "sum"}}
        ki = next(c for c in base["cards"] if c["capability"] == "key_influencers")
        # Key influencers go on the page as a widget now (phase 3).
        assert ki["action"]["widget_type"] == "model_influencers" and ki["action"]["config"]["response"] == "done"
        assert "k_id" not in ki["action"]["config"]["predictors"]

    def test_too_little_data_is_refused_with_the_number(self):
        base = engine.tier0(store.compute(frame(n=30)), META)
        no = {n["capability"]: n["reason"] for n in base["not_offered"]}
        assert no["automated_prediction"] == "needs at least 60 rows; this data has 30"


class TestWhatTheDataShows:
    def cards(self, df, meta=META):
        from app.services.analytics import detect_types
        from app.services.insights import effective_roles, generate_insights, suggest_widgets_from_findings
        from app.services import column_classes
        tm = detect_types(df.copy())
        # As the platform holds a dataset: each column classified once.
        meta, _ = column_classes.classified(df, meta)
        findings = generate_insights(df, tm, meta)["findings"]
        sug = suggest_widgets_from_findings(findings, effective_roles(tm, meta), None, column_meta=meta, frame=df)
        return engine.evidence_cards(sug, findings), findings

    def test_a_planted_difference_becomes_a_card_with_its_evidence(self):
        cards, _ = self.cards(frame())
        rate = next(c for c in cards if (c["evidence"] or {}).get("kind") == "rate")
        assert rate["claim"] == "observation" and rate["evidence"]["band"] in ("strong", "moderate")
        assert rate["action"]["widget_type"] == "bar" and "done" in rate["fields"]

    def test_noise_produces_no_evidence(self):
        rng = np.random.default_rng(11)
        n = 800
        noise = pd.DataFrame({"g": rng.choice(["a", "b", "c"], n), "v1": rng.normal(100, 5, n),
                              "v2": rng.normal(10, 1, n), "flag": rng.random(n) < 0.3})
        cards, _ = self.cards(noise, {"v1": {"number": "amount"}, "v2": {"number": "level"}})
        strong = [c["title"] for c in cards if (c["evidence"] or {}).get("band") == "strong"
                  and c["evidence"]["kind"] not in ("rules",)]
        assert strong == []

    def test_a_chart_offered_for_coverage_claims_no_evidence(self):
        cards, _ = self.cards(frame())
        basics = [c for c in cards if c["family"] == "basics"]
        assert basics and all(c["evidence"] is None for c in basics)

    def test_an_association_says_it_is_not_a_cause(self):
        rng = np.random.default_rng(5)
        x = rng.normal(0, 1, 900)
        df = pd.DataFrame({"v1": x * 10 + 100, "v2": x * 3 + rng.normal(0, 0.5, 900) + 50, "g": rng.choice(["a", "b"], 900)})
        cards, _ = self.cards(df, {"v1": {"number": "amount"}, "v2": {"number": "amount"}})
        rel = next(c for c in cards if c["claim"] == "association")
        assert any("not that one causes the other" in line for line in rel["limits"])


class TestRanking:
    def card(self, family, band=None, tier=1, fields=("v1",), n=0):
        cap = caps.widget("bar")
        c = engine._card(cap, f"{family}{n}", "", list(fields), {"kind": "add_widget", "n": n},
                         why={}, evidence={"band": band, "strength": 0.5} if band else None, family=family)
        c["cost"]["tier"] = tier
        return c

    def test_what_bears_on_the_goal_comes_first_then_evidence_then_cost(self):
        cards = [self.card("compare", "weak", n=1), self.card("trend", "strong", tier=2, n=2),
                 self.card("trend", "strong", tier=1, n=3), self.card("basics", None, fields=("region_name",), n=4)]
        ranked = engine.rank(cards, goal="how do regions compare")
        assert [c["title"] for c in ranked] == ["basics4", "trend3", "trend2", "compare1"]
        assert ranked[0]["relevance"] == {"matches_goal": True}

    def test_no_family_takes_more_than_its_share_and_nothing_is_offered_twice(self):
        cards = [self.card("compare", "strong", n=i) for i in range(10)] + [self.card("trend", "weak", n=99)]
        cards.append(dict(cards[0]))
        ranked = engine.rank(cards)
        assert sum(c["family"] == "compare" for c in ranked) == engine.PER_FAMILY
        assert len({c["id"] for c in ranked}) == len(ranked) and ranked[-1]["family"] == "trend"


def test_a_date_kept_as_text_is_measured_as_a_date():
    df = pd.DataFrame({"when": ["2024-01-05", "2024-03-09", "2024-06-30"] * 20, "v": range(60)})
    assert store.compute(df)["columns"]["when"]["kind"] == "text"                 # as the file holds it
    got = store.compute(df, {"when": "datetime", "v": "numeric"})["columns"]["when"]
    assert got["kind"] == "date" and got["periods"] == 3


def test_the_start_date_is_the_one_every_row_has_even_when_another_runs_earlier():
    """A finish date empty for the few rows still open has an EARLIER median
    (it leaves the newest rows out); it is still not when the record began."""
    n = 1000
    began = pd.Timestamp("2024-01-01") + pd.to_timedelta(np.arange(n), "D")
    ended = pd.Series(began + pd.Timedelta(days=1))
    ended.iloc[-15:] = pd.NaT                                         # 1.5% still open
    df = pd.DataFrame({"d_a": ended, "d_b": began, "v": np.arange(n, dtype=float)})
    prof = store.compute(df)
    kinds = engine.column_kinds(prof, {"v": {"number": "amount"}})
    assert engine._pick(kinds, prof, "date")[0] == "d_b"
    from app.services.insights import order_event_dates
    assert order_event_dates(["d_a", "d_b"], df)[0] == "d_b"


class TestTheColumnProfileCard:
    def messy(self):
        n = 400
        rng = np.random.default_rng(8)
        qty = [str(v) for v in rng.integers(1, 90, n)]
        for i in range(0, 24):
            qty[i] = "n/a"                                             # 6% of a number column is text
        ref = [f"AB-{1000 + i}" for i in range(n)]
        df = pd.DataFrame({"qty": qty, "ref": ref, "kind": rng.choice(["online", "phone", "post"], n, p=[.7, .2, .1]),
                           "when": pd.Timestamp("2024-03-01") + pd.to_timedelta(rng.integers(0, 60, n), "D"),
                           "amount": rng.uniform(1, 50, n)})
        df.loc[5, "kind"] = None
        return pd.concat([df, df.iloc[:8]], ignore_index=True)        # eight exact copies

    def test_it_counts_valid_mistyped_missing_and_unique(self):
        prof = store.compute(self.messy())
        qty = store.card_of("qty", prof["columns"]["qty"])
        assert qty["mistyped"]["holds"] == "number" and qty["mistyped"]["count"] >= 24
        assert qty["valid"]["count"] + qty["invalid"]["count"] == qty["cells"]
        ref = store.card_of("ref", prof["columns"]["ref"])
        assert ref["pattern"] == "AA-9999" and ref["len_min"] == ref["len_max"] == 7
        kind = store.card_of("kind", prof["columns"]["kind"])
        assert kind["most_common"][0] == "online" and kind["least"][0] == "post" and kind["missing"]["count"] >= 1
        assert kind["unique"]["count"] == 0 and kind["distinct"] == 3

    def test_how_old_the_newest_date_is(self):
        from datetime import datetime, timezone
        prof = store.compute(self.messy())
        card = store.card_of("when", prof["columns"]["when"], now=datetime(2024, 6, 1, tzinfo=timezone.utc))
        assert 24 * 30 < card["delay_hours"] < 24 * 95
        ahead = store.card_of("when", {"kind": "date", "max": "2999-01-01", "count": 1}, now=datetime(2024, 6, 1, tzinfo=timezone.utc))
        assert ahead["delay_hours"] is None                             # a date in the future has no delay

    def test_the_shape_of_a_value(self):
        assert store.mask_of("AB-1234") == "AA-9999" and store.mask_of("2024/05/01") == "9999/99/99"
        assert store.mask_of("طلب 12") == "aaa 99"                     # letters of any script

    def test_what_the_profile_shows_becomes_cards_without_reading_anything(self):
        prof = store.compute(self.messy())
        base = engine.tier0(prof, {"amount": {"number": "amount"}})
        by = {c["capability"]: c for c in base["cards"]}
        assert "values in qty are not numbers" in by["mistyped_values"]["title"]
        assert by["mistyped_values"]["action"] == {"kind": "open", "target": "columns", "column": "qty"}
        assert by["duplicate_rows"]["title"].startswith("8 rows are exact copies")
        assert by["data_delay"]["fields"] == ["when"] and by["data_delay"]["evidence"]["band"] == "strong"
        assert all(c["cost"]["tier"] == 0 for c in (by["mistyped_values"], by["duplicate_rows"], by["data_delay"]))

    def test_a_clean_table_gets_none_of_them(self):
        prof = store.compute(frame().assign(d1=pd.Timestamp.now().normalize()))
        base = engine.tier0(prof, META)
        assert not {c["capability"] for c in base["cards"]} & {"mistyped_values", "duplicate_rows", "data_delay"}

    def test_a_reader_under_a_row_rule_sees_counts_but_no_value(self):
        prof = store.for_reader(store.compute(self.messy()), row_rule=True)
        card = store.card_of("kind", prof["columns"]["kind"])
        assert "top" not in card and "most_common" not in card and "least" not in card
        assert card["missing"]["count"] >= 1 and card["distinct"] == 3
        assert "pattern" not in store.card_of("ref", prof["columns"]["ref"])


class TestATableOfGroupsAndTheirLines:
    def lines(self):
        rng = np.random.default_rng(6)
        rows = []
        for g in range(400):
            for thing in rng.choice([f"t{i}" for i in range(60)], rng.integers(2, 6), replace=False):
                rows.append((f"G-{1000 + g}", thing, float(rng.uniform(1, 9))))
        return pd.DataFrame(rows, columns=["ref", "thing", "amount"])

    def test_the_shape_is_read_from_the_stored_figures(self):
        prof = store.compute(self.lines())
        kinds = engine.column_kinds(prof, {"amount": {"number": "amount"}})
        assert "key" in kinds["ref"] and "item" in kinds["thing"]
        assert engine.group_key(kinds, prof) == "ref"
        base = engine.tier0(prof, {"amount": {"number": "amount"}})
        card = next(c for c in base["cards"] if c["capability"] == "basket_rules")
        assert card["action"] == {"kind": "add_widget", "widget_type": "model_rules",
                                  "config": {"basket": "ref", "item": "thing"}}
        assert card["claim"] == "association" and card["evidence"] is None

    def test_a_table_with_one_row_per_key_is_not_one(self):
        prof = store.compute(frame())                                   # k_id: a value per row
        base = engine.tier0(prof, META)
        assert "basket_rules" not in {c["capability"] for c in base["cards"]}
        no = {n["capability"]: n["reason"] for n in base["not_offered"]}
        assert "basket_rules" in no


def test_a_year_is_neither_a_quantity_nor_a_groups_key():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"model_year": rng.integers(1960, 2025, 2000), "thing": rng.choice([f"t{i}" for i in range(30)], 2000)})
    prof = store.compute(df)
    kinds = engine.column_kinds(prof, {})
    assert "model_year" not in kinds and engine.group_key(kinds, prof) is None


def test_how_many_rows_are_measured_is_a_setting(monkeypatch):
    """A larger table is sampled at the size set, seeded, and says so."""
    import numpy as np
    import pandas as pd
    from app.core.config import settings
    df = pd.DataFrame({"v": np.arange(5000.0), "g": ["a", "b"] * 2500})
    whole = store.compute(df)
    assert whole["table"]["sampled"] is False and whole["table"]["measured_rows"] == 5000
    monkeypatch.setattr(settings, "discovery_sample_rows", 1000)
    part = store.compute(df)
    assert part["table"] == {**part["table"], "rows": 5000, "measured_rows": 1000, "sampled": True}
    assert store.compute(df)["columns"]["v"] == part["columns"]["v"]                # the same sample each time
