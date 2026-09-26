"""E11: the held-out bilingual Ask AI benchmark -- its cases and its scoring.

The benchmark needs the language model to run (scripts/bench_ask.py); these
tests pin what can be pinned without it: every case is well formed and asks
about the demo data it names, English and Arabic ask the same things, and the
scorer marks right, wrong, ungrounded and refused answers correctly.
"""
import json
import os

import numpy as np
import pytest

from app.services.agent.benchmark import grounded, score, stated_numbers, summarise
from app.services.demo_content import _sales_frame

BENCH = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "qa", "ask_benchmark.json"),
                       encoding="utf-8"))


class TestTheCases:
    def test_english_and_arabic_ask_the_same_things(self):
        ids = {c["id"] for c in BENCH["cases"]}
        stems = {i.rsplit(".", 1)[0] for i in ids}
        assert ids == {f"{s}.{lang}" for s in stems for lang in ("en", "ar")}
        by = {c["id"]: c for c in BENCH["cases"]}
        for s in stems:
            assert by[f"{s}.en"]["expect"] == by[f"{s}.ar"]["expect"]
            assert any("؀" <= ch <= "ۿ" for ch in by[f"{s}.ar"]["question"])

    def test_each_expectation_reads_columns_the_demo_data_has(self):
        columns = set(_sales_frame(np.random.default_rng(0)).columns)
        assert BENCH["dataset"] == "Demo — Sales"

        def specs(e):
            return [e[k] for k in ("from", "top_of") if k in e] + list(e.get("difference", []))
        for case in BENCH["cases"]:
            for spec in specs(case["expect"]):
                cfg = spec["config"]
                named = {cfg.get("measure"), cfg.get("dimension")} - {None}
                named |= {f["column"] for f in cfg.get("filters", [])}
                assert named <= columns, (case["id"], named - columns)

    def test_there_are_refusals_as_well_as_answers(self):
        kinds = [c["expect"]["kind"] for c in BENCH["cases"]]
        assert kinds.count("refuse") >= 6 and kinds.count("number") >= 12


def case(kind, **expect):
    return {"id": "x.en", "lang": "en", "expect": {"kind": kind, **expect}}


def ok(answer, untraced=0, status="ok"):
    return {"status": status, "answer": answer, "evidence": {"claims": [], "untraced": untraced}}


class TestScoring:
    def test_a_number_agrees_at_the_precision_it_was_written(self):
        assert score(case("number"), ok("Revenue was 2.2 million."), 2_221_091.66)["correct"]
        assert score(case("number"), ok("Revenue was $2,221,092."), 2_221_091.66)["correct"]
        assert not score(case("number"), ok("Revenue was 2.3 million."), 2_221_091.66)["correct"]

    def test_arabic_digits_and_percentages(self):
        assert score(case("number"), ok("بلغت الإيرادات ٢٬١٩٩٬٣٧٧"), 2_199_376.97)["correct"]
        assert score(case("number"), ok("The average margin is 19.0%."), 18.97)["correct"]
        assert score(case("number"), ok("Share: 40%"), 0.397)["correct"]

    def test_a_date_is_not_a_stated_number(self):
        assert [n["value"] for n in stated_numbers("In 2025-03 it was 12.")] == [12.0]

    def test_mentions(self):
        c = case("mentions", all=["Asia Pacific"])
        assert score(c, ok("Asia Pacific led with 2.2M."))["correct"]
        assert score(c, ok("Europe led."))["why"] == "did not name ['Asia Pacific']"

    def test_refusals(self):
        c = case("refuse")
        assert score(c, ok("I can't create or edit dashboards from Ask AI."))["correct"]
        assert score(c, ok("لا تتوفر بيانات عن الرواتب في هذه المجموعة."))["correct"]
        assert score(c, {"status": "needs_clarification", "answer": "Which salary do you mean?"})["correct"]
        assert score(c, ok("The CEO earns 250,000."))["why"] == "stated a number"

    def test_a_failed_run_is_wrong_whatever_it_says(self):
        r = score(case("number"), {"status": "failed", "error": "LLM unreachable"}, 5.0)
        assert not r["correct"] and "failed" in r["why"]

    def test_grounding(self):
        assert score(case("number"), ok("It was 12.", untraced=0), 12)["grounded"] is True
        assert score(case("number"), ok("It was 12, up 7.", untraced=1), 12)["grounded"] is False
        assert grounded({"answer": "x"}) is None

    def test_the_summary_is_per_language(self):
        rs = [{"lang": "en", "kind": "number", "correct": True, "grounded": True},
              {"lang": "en", "kind": "number", "correct": False, "grounded": False},
              {"lang": "en", "kind": "refuse", "correct": True, "grounded": None},
              {"lang": "ar", "kind": "number", "correct": True, "grounded": True}]
        s = summarise(rs)
        assert s["en"] == {"cases": 3, "correct": 1, "answer_accuracy": 0.5, "refusals_correct": "1/1", "ungrounded": 1}
        assert s["ar"]["answer_accuracy"] == 1.0
