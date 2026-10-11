"""The sentences the discovery engine writes can be said in the reader's
language: each has a key in both catalogues, and in English the catalogue
says exactly what the server said (docs/discovery/PLAN.md §Z)."""
import os
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
I18N = os.path.join(HERE, "..", "..", "frontend", "src", "i18n")


def _cat(lang):
    path = os.path.join(I18N, f"{lang}.ts")
    if not os.path.exists(path):
        pytest.skip("frontend catalogue not present in this checkout")
    text = open(path, encoding="utf-8").read()
    return {k: v.replace("\\'", "'") for k, v in re.findall(r"^\s*'(rb\.[^']+)': '((?:[^'\\]|\\.)*)',$", text, re.M)}


def _render(cat, said):
    tpl = cat["rb." + said["key"]]
    vals = {k: (_render(cat, v) if isinstance(v, dict) else v) for k, v in (said.get("vars") or {}).items()}
    return re.sub(r"\{(\w+)\}", lambda m: vals[m.group(1)], tpl)


def _same(cat, text, said):
    assert said, text
    rendered = " ".join(_render(cat, said).split())
    assert rendered[:1].upper() + rendered[1:] == " ".join(str(text).split()), (rendered, text)


def _keys_in(*modules):
    keys = set()
    for m in modules:
        src = open(m.__file__, encoding="utf-8").read()
        keys |= {k for k in re.findall(r'_s\(\s*f?"([\w.]+)"', src)}
        keys |= {k for pair in re.findall(r'_s\("([\w.]+)" if [^\n]*? else "([\w.]+)"', src) for k in pair}
    return {k for k in keys if "{" not in k}


def test_every_sentence_has_a_key_in_both_catalogues():
    from app.services import widget_data
    from app.services.discovery import evidence, health
    en, ar = _cat("en"), _cat("ar")
    keys = _keys_in(evidence, health) | {"tl.rose", "tl.fell", "tl.above", "tl.below"}
    keys |= {f"day.{d}" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    keys |= {f"mon.{m.lower()}" for m in evidence._MONTHS}
    keys |= {f"ev.groups.{v}{s}" for v in ("higher", "lower") for s in ("", ".lift")}
    keys -= {"day.", "mon.", "ev.groups."}
    assert len(keys) > 70
    missing = {"rb." + k for k in keys}
    assert missing <= set(en), missing - set(en)
    assert missing <= set(ar), missing - set(ar)
    assert widget_data.timeline_notes                               # the notes' keys are the four named above


def test_timeline_notes_read_the_same_from_the_catalogue():
    from app.services import widget_data
    cat = _cat("en")
    values = [100.0] * 12 + [101, 99, 100, 300, 100, 101] + [160.0] * 14
    result = {"rows": [{"name": f"2024-W{i + 1:02d}", "value": v} for i, v in enumerate(values)]}
    widget_data.read_timeline(result, {"anomaly_band": True, "change_point": True, "dimension_granularity": "week"})
    assert result["notes"]
    for n in result["notes"]:
        _same(cat, n["text"], n["text_i18n"])


def test_health_checks_read_the_same_from_the_catalogue():
    from app.services.discovery import health, profile as store
    cat = _cat("en")
    rng = np.random.default_rng(1)
    days = pd.date_range("2024-01-01", "2025-05-10", freq="D")
    df = pd.DataFrame({"when": np.repeat(days, 5), "amount": rng.normal(100, 5, len(days) * 5), "fixed": "same"})
    df["none"] = None
    df["gaps"] = np.where(np.arange(len(df)) % 10 == 0, None, "x")
    df["mixed"] = [str(i) for i in range(len(df))]
    df.loc[df.index[:50], "mixed"] = "n/a"
    df = pd.concat([df, df.iloc[:300]], ignore_index=True)
    prof = store.compute(df)
    prof["previous"] = {"measured_at": "2025-01-01T00:00:00", "columns": {"when": "date", "amount": "text", "gone": "text"}}
    for profile in (prof, store.compute(df[["when", "amount"]].drop_duplicates())):
        for c in health.checks(profile, "when", datetime(2025, 7, 2, tzinfo=timezone.utc))["checks"]:
            _same(cat, c["title"], c["title_i18n"])
            _same(cat, c["sentence"], c["sentence_i18n"])


def test_what_a_look_at_the_rows_found_reads_the_same_from_the_catalogue():
    from tests.test_discovery_evidence import PAIR_META, events, groups, looked, pair, seasonal
    cat = _cat("en")
    seen = 0
    for df, meta in ((events(), {}), (events(habit=False), {}), (seasonal(), {}), (pair(), PAIR_META),
                     (pair(linked=False), PAIR_META), (groups(), {"done": {"outcome": True}}),
                     (groups(real=False), {"done": {"outcome": True}})):
        kept, withheld = looked(df, meta)
        for c in kept:
            if c.get("found"):
                _same(cat, c["found"], c["found_i18n"]); seen += 1
        for w in withheld:
            _same(cat, w["reason"], w["reason_i18n"]); seen += 1
    assert seen >= 8


def _card_texts(card):
    yield card["title"], card.get("title_i18n")
    yield card["sentence"], card.get("sentence_i18n")
    for line, said in zip(card.get("limits") or [], card.get("limits_i18n") or []):
        yield line, said
    if (card.get("why") or {}).get("detail_i18n"):
        yield card["why"]["detail"], card["why"]["detail_i18n"]


def test_every_card_the_engine_writes_can_be_said_from_both_catalogues():
    """Titles, descriptions, limits and reasons of the cards offered by shape:
    each carries its key, English reads the same, and Arabic has the key."""
    from app.services.discovery import engine, evidence, profile as store
    from tests.test_discovery_evidence import PAIR_META, events, groups, pair
    from tests.test_stage_board import rows as stage_rows
    en, ar = _cat("en"), _cat("ar")
    rng = np.random.default_rng(3)
    wide = events().assign(kind=lambda d: rng.choice(["a", "b", "c"], len(d)), other=lambda d: rng.normal(5, 1, len(d)),
                           place=lambda d: rng.choice(["x", "y", "z", "w"], len(d)),
                           note=lambda d: ["text " * 12 + str(i) for i in range(len(d))])
    mixed = pair().assign(code=[str(i) for i in range(3000)])
    mixed.loc[mixed.index[:40], "code"] = "n/a"
    mixed = pd.concat([mixed, mixed.iloc[:200]], ignore_index=True)
    frames = [(wide, {"amount": {"number": "amount", "target": 100, "target_period": "month", "direction": "higher_better"},
                      "other": {"number": "amount"}, "kind": {"outcome": True}}),
              (mixed, PAIR_META), (groups(), {"done": {"outcome": True}}), (stage_rows(), {})]
    said, keys = 0, set()
    for df, meta in frames:
        prof = store.compute(df)
        base = engine.tier0(prof, meta)
        cards = list(base["cards"]) + [{"action": {"kind": "add_widget", "widget_type": "kpi",
                                                   "config": {"measure": "amount", "aggregation": "sum"}},
                                        "title": "x", "sentence": "x", "limits": [], "limits_i18n": []}]
        engine._with_history(cards, base["kinds"], prof, meta)
        engine._with_targets(cards, base["kinds"], prof, meta)
        cards, _ = evidence.look(cards, df, meta)
        for card in cards:
            assert len(card.get("limits") or []) == len(card.get("limits_i18n") or []), card["title"]
            for text, key in _card_texts(card):
                if key is None:
                    continue
                _same(en, text, key)
                assert "rb." + key["key"] in ar, key["key"]
                keys.add(key["key"]); said += 1
        # A card offered by shape never goes out with untranslatable words of its own.
        for card in base["cards"]:
            assert card.get("title_i18n") and card.get("sentence_i18n"), card["title"]
    assert said > 60 and len(keys) > 40, (said, len(keys))


def test_every_card_key_in_the_source_is_in_both_catalogues():
    import ast
    from app.services.discovery import engine
    en, ar = _cat("en"), _cat("ar")
    src = open(engine.__file__, encoding="utf-8").read()
    keys = {"card." + n.args[0].value for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_T" and n.args and isinstance(n.args[0], ast.Constant)}
    keys |= {"card.mistyped.num.s", "card.mistyped.text.s"} | {f"card.lim.target.{p}" for p in ("month", "quarter", "year")}
    assert len(keys) >= 75
    assert {"rb." + k for k in keys} <= set(en) and {"rb." + k for k in keys} <= set(ar)


def test_what_the_new_analyses_warn_and_conclude_reads_the_same_from_the_catalogue():
    from app.services.analysis.automated_prediction import automated_prediction
    from app.services.analysis.change_drivers import explain_change, explain_variance
    from app.services.analysis.compare_scenarios import compare_scenarios
    from app.services.analysis.stage_board import stage_board
    from app.services.analysis.two_groups import compare_two_groups
    from tests.test_change_drivers import rows as change_rows
    from tests.test_compare_scenarios import DOWN, UP, frame as scenario_frame
    from tests.test_phase3_models import frame as model_frame
    from tests.test_stage_board import rows as stage_rows
    from tests.test_two_groups import trial
    from tests.test_variance import rows as pair_rows
    en, ar = _cat("en"), _cat("ar")
    seen = set()

    def check(text, key):
        assert key, text
        rendered = " ".join(_render(en, key).split())
        assert rendered == " ".join(str(text).split()), (rendered, text)          # exactly: a value's name is not capitalised
        assert "rb." + key["key"] in ar
        seen.add(key["key"])

    gappy = pair_rows()
    gappy.loc[gappy.index[:50], "expected"] = None
    three = trial()
    three["done"] = np.where(np.arange(len(three)) % 97 == 0, "maybe", three["done"])
    undated = stage_rows()
    undated.loc[undated.index[-30:], "due"] = pd.NaT
    for out in (explain_change(change_rows(), "when", "amount"), explain_change(change_rows(), "when", "amount", aggregation="avg"),
                explain_variance(gappy, "reached", "expected"), explain_variance(pair_rows(), "reached", "expected", aggregation="avg"),
                compare_two_groups(trial(n=12000), "arm", "done"), compare_two_groups(trial(other=0.105, seed=11), "arm", "done"),
                compare_two_groups(three, "arm", "done"),
                stage_board(undated, "state", "began", "done_on", "due"), stage_board(stage_rows(), "state", "began")):
        body = out.to_dict()
        assert len(body["warnings"]) == len(body["meta"]["warnings_i18n"])
        for text, key in zip(body["warnings"], body["meta"]["warnings_i18n"]):
            check(text, key)
        if body["meta"].get("sentence_i18n"):
            check(body["meta"]["sentence"], body["meta"]["sentence_i18n"])
    weak = scenario_frame()
    weak["revenue"] = np.random.default_rng(5).normal(1000, 50, len(weak))
    got = compare_scenarios(weak, "month", "revenue", ["spend"], [UP, DOWN])
    check(got["caveats"][0], got["caveats_i18n"][0])
    pred = automated_prediction(model_frame(), "y")
    check(pred["importance_note"], pred["importance_note_i18n"])
    assert {"an.where", "an.avgparts", "an.where.diff", "an.oneonly", "an.random", "an.rarest", "an.tg.higher",
            "an.tg.not_clear", "an.now", "an.open", "an.nofinish", "an.nodue", "an.noorder", "an.weakfit", "an.impnote"} <= seen


def test_the_footnotes_of_the_older_analyses_have_keys_in_both_catalogues():
    """Statistical tests, model comparison, what-if, sentiment, clustering and the
    model widgets: each caveat or warning is a keyed sentence (§AU), so a reader in
    Arabic does not meet an English footnote under an Arabic result."""
    from app.services import model_widgets
    from app.services.analysis import (automated_prediction, compare_scenarios, forecast_scenario, inferential,
                                       segment, text_sentiment)
    en, ar = _cat("en"), _cat("ar")
    keys = _keys_in(automated_prediction, compare_scenarios, forecast_scenario, inferential, segment,
                    text_sentiment, model_widgets)
    assert len(keys) > 40
    wanted = {"rb." + k for k in keys}
    assert wanted <= set(en), wanted - set(en)
    assert wanted <= set(ar), wanted - set(ar)
    for k in wanted:                                   # the same pieces in both languages
        assert set(re.findall(r"\{(\w+)\}", en[k])) == set(re.findall(r"\{(\w+)\}", ar[k])), k


def test_a_statistical_result_carries_its_footnotes_with_keys():
    from app.services.analysis.inferential import correlation_test
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"a": rng.normal(0, 1, 200)})
    df["b"] = df["a"] * 0.5 + rng.normal(0, 1, 200)
    out = correlation_test(df, "a", "b")
    out = out.to_dict() if hasattr(out, "to_dict") else out
    assert len(out["caveats_i18n"]) == len(out["caveats"]) and all(out["caveats_i18n"])
    en = _cat("en")
    for text, said in zip(out["caveats"], out["caveats_i18n"]):
        _same(en, text, said)


def test_the_headline_of_every_statistical_test_can_be_said_from_the_catalogue():
    """The first sentence a reader meets (§BB): composed of pieces -- the
    verdict, what was compared, the size of the gap -- each with its key, and
    in English the catalogue says exactly what the server wrote."""
    from app.services.analysis import inferential as inf
    rng = np.random.default_rng(5)
    n = 300
    df = pd.DataFrame({"g2": rng.choice(["a", "b"], n), "g3": rng.choice(["x", "y", "z"], n),
                       "u": rng.normal(50, 10, n)})
    df["v"] = df["u"] * 0.8 + np.where(df["g2"] == "a", 6.0, 0.0) + rng.normal(0, 5, n)
    df["flat"] = rng.normal(0, 1, n)
    en, ar = _cat("en"), _cat("ar")
    results = [inf.compare_groups(df, "v", "g2"), inf.compare_groups(df, "v", "g3"), inf.compare_groups(df, "flat", "g2"),
               inf.test_independence(df, "g2", "g3"), inf.correlation_test(df, "u", "v"), inf.correlation_test(df, "u", "flat"),
               inf.regression(df, "v", ["u"]), inf.pairwise_comparisons(df, "v", "g3")]
    for r in results:
        out = r.to_dict()
        _same(en, out["interpretation"], out["interpretation_i18n"])
        assert _render(ar, out["interpretation_i18n"])                  # every piece has its Arabic
    gap = results[0].to_dict()["detail"]["business"]
    _same(en, gap["sentence"], gap["sentence_i18n"])


def test_insight_titles_can_be_said_from_the_catalogue():
    """What stands out, in the reader's language (§BB): every title the scan
    writes with a key renders from the catalogue to exactly what it wrote."""
    from app.services.insights import generate_insights
    rng = np.random.default_rng(11)
    n = 900
    g = rng.choice(["north", "south", "east", "west"], n, p=[.55, .25, .15, .05])
    df = pd.DataFrame({"g": g, "day": pd.date_range("2024-01-01", periods=n, freq="D").astype(str),
                       "amount": rng.gamma(2, 100, n) * np.where(g == "north", 1.8, 1.0),
                       "score": rng.normal(50, 10, n) + np.where(g == "west", 12, 0)})
    df.loc[::9, "score"] = np.nan
    df["twin"] = df["amount"] * 0.9 + rng.normal(0, 5, n)
    types = {"g": "categorical", "day": "datetime", "amount": "numeric", "score": "numeric", "twin": "numeric"}
    found = generate_insights(df, types, {"score": {"number": "score"}})["findings"]
    keyed = [f for f in found if f.get("title_i18n")]
    assert len(keyed) >= 4, [f["title"] for f in found]
    en, ar = _cat("en"), _cat("ar")
    for f in keyed:
        # Exactly as written: a title starts with the group's own name, in its own case.
        assert " ".join(_render(en, f["title_i18n"]).split()) == " ".join(f["title"].split()), f["title"]
        assert _render(ar, f["title_i18n"])
        assert type(f["title"]) is str                      # plain text travels; the key rides beside it
