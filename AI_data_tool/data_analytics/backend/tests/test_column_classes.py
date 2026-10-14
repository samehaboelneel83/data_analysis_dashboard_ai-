"""One classification per column, stored and read by every engine
(docs/suggestions/PLAN.md, phase 1)."""
import numpy as np
import pandas as pd

from app.services import column_classes as cc
from app.services import semantic_guard as guard


class TestOrder:
    def test_a_scale_written_in_words_is_put_in_its_order(self):
        assert cc.ordered_values(["High", "Low", "Medium"]) == ["Low", "Medium", "High"]
        assert cc.ordered_values(["good", "excellent", "poor", "very good"]) == ["poor", "good", "very good", "excellent"]

    def test_in_arabic_too(self):
        assert cc.ordered_values(["مرتفع", "منخفض", "متوسط"]) == ["منخفض", "متوسط", "مرتفع"]
        assert cc.ordered_values(["ممتاز", "مقبول", "جيد جدا", "جيد"]) == ["مقبول", "جيد", "جيد جدا", "ممتاز"]

    def test_numbered_labels_and_bands(self):
        assert cc.ordered_values(["3 - Closed", "1 - New", "2 - Open"]) == ["1 - New", "2 - Open", "3 - Closed"]
        assert cc.ordered_values(["18-25", "65+", "<18", "26-45", "46-64"]) == ["<18", "18-25", "26-45", "46-64", "65+"]

    def test_months_and_weekdays(self):
        assert cc.ordered_values(["Mar", "Jan", "Feb"]) == ["Jan", "Feb", "Mar"]
        assert cc.ordered_values(["Friday", "Monday", "Wednesday"]) == ["Monday", "Wednesday", "Friday"]

    def test_ordinary_categories_are_not_a_scale(self):
        assert cc.ordered_values(["Cairo", "Giza", "Aswan"]) is None
        assert cc.ordered_values(["Standard", "Express", "Same Day"]) is None
        assert cc.ordered_values(["High"]) is None


def frame(n=400):
    rng = np.random.default_rng(3)
    return pd.DataFrame({
        "row_ref": np.arange(1000, 1000 + n),                      # a key issued in order, unhelpfully named
        "val2": rng.integers(1, 6, n).astype(float),              # nothing in the name
        "delivery_fee_egp": rng.uniform(50, 900, n).round(2),
        "delivery_days": rng.uniform(0.5, 9, n).round(1),
        "customer_rating": rng.integers(1, 6, n).astype(float),
        "priority": rng.choice(["Low", "Medium", "High"], n),
        "service_type": rng.choice(["Standard", "Express"], n),
        "governorate": rng.choice(["Cairo", "Giza"], n),
        "is_late": pd.Series(rng.choice([True, False], n), dtype=object),
        "created_at": pd.date_range("2024-01-01", periods=n, freq="D"),
    })


class TestClassify:
    def test_what_the_rows_and_names_show(self):
        got = cc.classify(frame())
        assert got["row_ref"]["number"] == "code" and got["row_ref"]["level"] == "nominal"
        assert got["delivery_fee_egp"]["number"] == "amount" and got["delivery_fee_egp"]["level"] == "ratio"
        assert got["delivery_days"]["number"] == "duration"
        assert got["customer_rating"] == {"class_source": "measured", "number": "score",
                                          "direction": "higher_better", "level": "ordinal"}
        assert got["priority"]["level"] == "ordinal" and got["priority"]["order"] == ["Low", "Medium", "High"]
        assert got["service_type"]["level"] == "nominal" and "order" not in got["service_type"]
        assert got["governorate"]["geo_level"] == "region"
        assert got["is_late"]["outcome"] is True
        assert got["created_at"]["level"] == "interval"

    def test_the_meaning_map_outranks_the_name(self):
        got = cc.classify(frame(), numbers={"val2": {"kind": "score", "unit": "", "direction": "higher_better"},
                                            "delivery_days": {"kind": "duration", "unit": "days",
                                                              "direction": "higher_worse"}},
                          outcomes={"service_type"})
        assert got["val2"]["number"] == "score" and got["val2"]["class_source"] == "ai"
        assert got["delivery_days"]["unit"] == "days" and got["delivery_days"]["direction"] == "higher_worse"
        assert got["service_type"]["outcome"] is True

    def test_the_authors_role_is_respected(self):
        got = cc.classify(frame(), {"val2": {"role": "identifier"}, "customer_rating": {"role": "category"}})
        assert got["val2"]["number"] == "code"
        assert "number" not in got["customer_rating"]


class TestMerge:
    def test_fills_what_is_missing_and_keeps_everything_else(self):
        meta = {"priority": {"label": "Priority", "hidden": False}, "__prep_steps__": [{"kind": "trim"}]}
        merged, changed = cc.merge(meta, cc.classify(frame()[["priority", "val2"]]))
        assert changed and merged["priority"]["label"] == "Priority" and merged["priority"]["level"] == "ordinal"
        assert merged["__prep_steps__"] == [{"kind": "trim"}]

    def test_an_authors_confirmed_classification_is_never_overwritten(self):
        meta = {"val2": {"number": "amount", "class_source": "confirmed"}}
        merged, changed = cc.merge(meta, cc.classify(frame()[["val2"]], numbers={"val2": {"kind": "score"}}))
        assert not changed and merged["val2"] == {"number": "amount", "class_source": "confirmed"}


class TestOneReader:
    """Every engine reads the classification through semantic_guard."""

    def test_a_column_with_no_hint_in_its_name_is_read_from_its_classification(self):
        meta = {"val2": {"number": "score"}, "col_a": {"number": "amount"}, "x9": {"number": "code"}}
        assert guard.default_summary("val2", meta) == "avg" and guard.is_intensive("val2", meta)
        assert guard.default_summary("col_a", meta) == "sum" and not guard.is_intensive("col_a", meta)
        assert not guard.is_quantity("x9", meta) and guard.default_summary("x9", meta) == "countd"
        assert guard.aggregation_refusal("x9", "sum", meta) is not None

    def test_the_classification_outranks_a_misleading_name(self):
        # "invoice_no" looks like an identifier; the author says it is an amount.
        meta = {"invoice_no": {"number": "amount", "class_source": "confirmed"}}
        assert not guard.is_quantity("invoice_no") and guard.is_quantity("invoice_no", meta)
        assert guard.aggregation_refusal("invoice_no", "sum", meta) is None

    def test_an_unclassified_column_still_falls_back_to_its_name(self):
        # The fallback knows only how a number is MEASURED (a price, a rate),
        # never one industry's nouns: a salary is classified, not recognised.
        assert guard.default_summary("unit_price", {}) == "avg" and not guard.is_quantity("customer_id", {})
        assert guard.default_summary("salary", {}) == "sum"
        assert guard.default_summary("salary", {"salary": {"number": "level"}}) == "avg"

    def test_order_direction_and_outcome(self):
        meta = {"priority": {"level": "ordinal", "order": ["Low", "High"]},
                "rating": {"direction": "higher_better"}, "is_late": {"outcome": True}}
        assert guard.value_order("priority", meta) == ["Low", "High"] and guard.value_order("rating", meta) is None
        assert guard.direction_of("rating", meta) == "higher_better" and guard.direction_of("x", meta) == "neither"
        assert guard.is_outcome("is_late", meta) and not guard.is_outcome("rating", meta)


class TestEveryEngineReadsIt:
    def test_the_designers_see_what_each_column_is(self):
        from app.services.dataset_profile import build_profile, describe_for_prompt
        df = frame()
        meta, _ = cc.classified(df, {})
        text = describe_for_prompt(build_profile(df, None, meta))
        assert "[score: average it (or take its median); never total it; higher is BETTER]" in text
        assert "ORDERED, low to high: Low < Medium < High" in text
        assert "[amount: add it up]" in text
        assert "row_ref (" in text and "[identifier" in text.split("row_ref (")[1].split("\n")[0]

    def test_the_shared_repair_never_totals_a_score_and_keeps_a_scale_in_order(self):
        from app.services.analyst_panel import _respect_classes
        meta, _ = cc.classified(frame(), {})
        summed = {"widget_type": "bar", "config": {"dimension": "priority", "measure": "customer_rating",
                                                   "aggregation": "sum"}}
        fixed = _respect_classes(summed, meta)["config"]
        assert fixed["aggregation"] == "avg"
        assert fixed["sort_by"] == "order" and fixed["category_order"] == ["Low", "Medium", "High"]
        # A ranking the proposal asked for keeps its ranking.
        top = {"widget_type": "bar", "config": {"dimension": "priority", "measure": "delivery_fee_egp",
                                                "aggregation": "sum", "limit": 2}}
        assert "category_order" not in _respect_classes(top, meta)["config"]
        coded = {"widget_type": "kpi", "config": {"measure": "row_ref", "aggregation": "sum"}}
        assert _respect_classes(coded, meta)["config"]["aggregation"] == "countd"

    def test_a_frame_in_a_worker_thread_is_classified_without_touching_what_was_decided(self):
        meta = {"val2": {"number": "amount", "class_source": "confirmed"}}
        got, changed = cc.classified(frame(), meta)
        assert changed and got["val2"] == meta["val2"] and got["priority"]["level"] == "ordinal"
        again, changed_again = cc.classified(frame(), got)
        assert not changed_again and again == got


class TestGeography:
    def test_places_are_recognised_by_what_they_are_in_english_and_arabic(self):
        assert cc.geo_level("destination_governorate") == "region"
        assert cc.geo_level("country_name") == "country"
        assert cc.geo_level("customer_city") == "city"
        assert cc.geo_level("zip_code") == "postcode"
        assert cc.geo_level("المحافظة") == "region" and cc.geo_level("المدينة") == "city"
        assert cc.geo_level("capacity") is None and cc.geo_level("priority") is None

    def test_places_nest_by_what_they_are_not_by_how_many_values_they_have(self):
        from app.services.dataset_profile import build_profile
        import numpy as np
        rng = np.random.default_rng(5)
        n = 300
        df = pd.DataFrame({
            # More countries than cities here: value counts would nest them upside down.
            "ship_country": rng.choice([f"C{i}" for i in range(12)], n),
            "ship_city": rng.choice(["Cairo", "Giza", "Luxor"], n),
            "amount": rng.uniform(1, 9, n),
        })
        meta, _ = cc.classified(df, {})
        hier = build_profile(df, None, meta)["structure"]["hierarchies"]
        assert hier[0] == ["ship_country", "ship_city"]

    def test_a_column_marked_as_countries_makes_a_map_possible_whatever_it_is_called(self):
        from app.services.dataset_profile import build_profile
        from app.services.suggest_dataset_dashboard import _has_country_column
        df = pd.DataFrame({"market": ["Egypt", "Jordan"] * 30, "amount": range(60)})
        assert not _has_country_column(build_profile(df, None, {}))
        assert _has_country_column(build_profile(df, None, {"market": {"geo_level": "country"}}))


class TestNeutralVocabulary:
    """A general-purpose platform: what a column is comes from its values and
    its stored classification, never from one field of work's column names."""

    def test_a_long_fixed_width_number_is_a_code_whatever_it_is_called(self):
        import numpy as np
        rng = np.random.default_rng(0)
        df = pd.DataFrame({"f7": rng.integers(350_000_000_000_000, 359_999_999_999_999, 400),
                           "qty": rng.integers(1, 40, 400)})
        got = cc.classify(df)
        assert got["f7"]["number"] == "code" and got["qty"]["number"] == "count"

    def test_no_industry_noun_decides_anything(self):
        for name in ("salary", "wage", "mileage", "gpa", "premium", "imei", "msisdn", "tuition"):
            assert guard.is_quantity(name) and not guard.is_intensive(name), name
        # ...and each is whatever its classification says.
        assert guard.is_intensive("mileage", {"mileage": {"number": "level"}})
        assert not guard.is_quantity("imei", {"imei": {"number": "code"}})

    def test_measurement_words_are_read_in_arabic_too(self):
        assert guard.is_intensive("سعر الوحدة") and guard.is_intensive("نسبة_التأخير")
        assert guard.non_additive_kind("رقم_الطلب") == "identifier"

    def test_the_model_is_asked_once_and_its_answer_kept(self):
        import asyncio
        from types import SimpleNamespace

        class Rows:
            def __init__(self, rows): self._rows = rows
            def scalars(self): return self
            def all(self): return self._rows

        class Db:
            commits = 0
            async def execute(self, *_a, **_k):
                return Rows([SimpleNamespace(name="x1", dtype="numeric", stats={"min": 3000, "max": 90000},
                                             description=None),
                             SimpleNamespace(name="grp", dtype="categorical", stats={}, description=None),
                             SimpleNamespace(name="hidden", dtype="numeric", stats={}, description=None)])
            async def commit(self): Db.commits += 1
            async def rollback(self): pass

        class Model:
            enabled, model, calls, seen = True, "m", 0, ""
            async def complete_json(self, messages, schema, **kw):
                Model.calls += 1
                Model.seen = messages[-1]["content"]
                return {"numbers": [{"column": "x1", "kind": "level", "unit": "USD", "direction": "neither"},
                                    {"column": "made_up", "kind": "amount", "unit": "", "direction": "neither"}]}

        from app.models.models import Dataset
        ds = Dataset(id=1, name="t", column_meta={})
        first = asyncio.run(cc.model_hints(Db(), ds, Model(), denied={"hidden"}))
        assert first == {"x1": {"kind": "level", "unit": "USD", "direction": "neither"}}     # invented column dropped
        assert "hidden" not in Model.seen                                                    # never shown a hidden column
        again = asyncio.run(cc.model_hints(Db(), ds, Model(), denied={"hidden"}))
        assert again == first and Model.calls == 1                                           # asked once
        # ...and the answer outranks what the rows alone suggested.
        df = pd.DataFrame({"x1": [3000.0, 52000.0, 90000.0] * 20})
        meta, changed = cc.classified(df, {"x1": {"number": "amount", "class_source": "measured"}}, first)
        assert changed and meta["x1"]["number"] == "level" and meta["x1"]["class_source"] == "ai"
