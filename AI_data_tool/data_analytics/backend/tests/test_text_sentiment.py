"""Phase 6.6: offline sentiment (English + Arabic), Arabic-aware topics."""
import pandas as pd
import pytest

from app.services.analysis.text_sentiment import TextSentimentError, text_sentiment
from app.services.analysis.text_topics import text_topics
from app.services.text_lang import (detect_languages, label_of, normalize_arabic, score_text,
                                    sentiment_series, stop_words_for, tokens)


class TestScoring:
    @pytest.mark.parametrize("text,sign", [
        ("The staff were friendly and delivery was fast", 1),
        ("Terrible service, the order arrived broken", -1),
        ("not bad at all", 1),
        ("not good", -1),
        ("Great product but the delivery was terrible", -1),
        ("الخدمة ممتازة جدا", 1),
        ("التوصيل متأخر والمنتج مكسور", -1),
        ("مش كويس", -1),
        ("لم يعجبني المنتج", -1),
        ("المنتج جميل لكن السعر غالي", -1),
    ])
    def test_sign(self, text, sign):
        s, hits = score_text(text)
        assert hits and (s > 0) == (sign > 0)

    def test_arabic_intensifier_after_the_word_strengthens_it(self):
        assert score_text("الخدمة ممتازة جدا")[0] > score_text("الخدمة ممتازة")[0]

    def test_text_with_no_lexicon_word_is_unscored_not_neutral(self):
        assert score_text("order 12345 shipped to Riyadh") == (0.0, [])
        assert label_of(sentiment_series(pd.Series(["order 12345"])).iloc[0]) == "unscored"

    def test_normalisation_unifies_spellings(self):
        assert normalize_arabic("إِدارة") == normalize_arabic("اداره")
        assert tokens("والمنتجات الجميلة") == ["منتجات", "جميله"]


class TestLanguages:
    def test_bilingual_column_gets_both_lists(self):
        d = detect_languages(["الخدمة ممتازة جدا", "the app is great and the staff is nice", "التوصيل متأخر"])
        assert {"ar", "en"} <= set(d["languages"])

    def test_french_is_recognised(self):
        assert detect_languages(["le service est très bien et la livraison rapide"] * 3)["primary"] == "fr"

    def test_arabic_stop_words_include_dialect_fillers(self):
        ar = stop_words_for(["ar"])
        assert {"في", "من", "اللي", "عشان"} <= ar


def _reviews():
    pos_en = ["Excellent service and friendly staff", "Great quality, fast delivery", "Love it, highly recommend"]
    neg_en = ["Terrible support, very slow", "The item arrived broken", "Worst experience, rude staff"]
    pos_ar = ["الخدمة ممتازة جدا", "منتج رائع وسريع", "التعامل محترم وانصح به"]
    neg_ar = ["التوصيل متأخر جدا", "المنتج مكسور وسيء", "خدمة العملاء سيئة للأسف"]
    rows = []
    for i in range(3):
        for t in pos_en + pos_ar:
            rows.append({"comment": t, "label": "positive", "branch": "North" if i % 2 else "South", "stars": 5})
        for t in neg_en + neg_ar:
            rows.append({"comment": t, "label": "negative", "branch": "South", "stars": 1})
    rows += [{"comment": "order 5512 shipped", "label": "neutral", "branch": "North", "stars": 3}] * 4
    return pd.DataFrame(rows)


class TestAnalysis:
    def test_split_coverage_words_and_examples(self):
        got = text_sentiment(_reviews(), column="comment")
        assert got["split"]["positive"] == 18 and got["split"]["negative"] == 18
        assert got["split"]["unscored"] == 4
        assert got["coverage"] == pytest.approx(36 / 40)
        assert {"ar", "en"} <= set(got["languages"]["languages"])
        assert got["most_negative"][0]["score"] < 0 < got["most_positive"][0]["score"]
        assert any(w["word"] in ("ممتازه", "excellent") for w in got["top_positive_words"])
        assert any("unscored" in c for c in got["caveats"])

    def test_agreement_with_a_label_column_and_with_ratings(self):
        by_label = text_sentiment(_reviews(), column="comment", validate_against="label")
        assert by_label["agreement"]["agreement"] == 1.0
        by_stars = text_sentiment(_reviews(), column="comment", validate_against="stars")
        assert by_stars["agreement"]["compared"] == 36
        assert by_stars["agreement"]["polar_agreement"] == 1.0

    def test_group_split_orders_worst_first(self):
        got = text_sentiment(_reviews(), column="comment", group_by="branch")
        assert got["groups"]["rows"][0]["group"] == "South"

    def test_refusals(self):
        with pytest.raises(TextSentimentError):
            text_sentiment(_reviews(), column="nope")
        with pytest.raises(TextSentimentError):
            text_sentiment(_reviews(), column="stars")
        with pytest.raises(TextSentimentError):
            text_sentiment(pd.DataFrame({"c": ["order 1 shipped"] * 20}), column="c")


class TestArabicTopics:
    def test_arabic_topics_drop_arabic_stop_words_and_carry_tone(self):
        delivery = ["التوصيل متأخر جدا والسائق لم يتصل", "تأخر التوصيل ثلاثة أيام", "السائق وصل متأخر والتوصيل بطيء",
                    "التوصيل كان متأخرا عن الموعد", "مشكلة في التوصيل والسائق"] * 3
        quality = ["جودة المنتج ممتازة والتغليف رائع", "المنتج جودته عالية وممتاز", "جودة ممتازة وسعر مناسب",
                   "المنتج رائع والجودة ممتازة", "التغليف جميل والمنتج ممتاز"] * 3
        df = pd.DataFrame({"c": delivery + quality})
        got = text_topics(df, column="c", topics=2)
        assert got["languages"] == ["ar"]
        all_terms = {t["term"] for topic in got["topics"] for t in topic["terms"]}
        assert not all_terms & {"في", "من", "و", "كان", "عن"}
        tones = sorted(t["sentiment"]["average"] for t in got["topics"])
        assert tones[0] < 0 < tones[1]


class TestCalcColumn:
    def test_sentiment_functions_in_calculated_columns(self):
        from app.services.widget_data import apply_calculated_columns
        df = pd.DataFrame({"c": ["excellent service", "الخدمة سيئة", "order 12"]})
        out = apply_calculated_columns(df, [{"name": "tone", "expression": "SENTIMENT(c)"},
                                            {"name": "mood", "expression": "SENTIMENT_LABEL(c)"}])
        assert out["tone"].iloc[0] > 0 > out["tone"].iloc[1]
        assert pd.isna(out["tone"].iloc[2])
        assert list(out["mood"]) == ["positive", "negative", "unscored"]


def test_negated_words_are_reported_as_negated_and_examples_are_distinct():
    s, hits = score_text("switched over without any friction")
    assert s > 0 and hits[0][0] == "not friction"
    df = pd.DataFrame({"c": ["Love it, great"] * 12 + ["Terrible and slow"] * 6 + ["good enough"] * 4})
    got = text_sentiment(df, column="c")
    assert len({e["text"] for e in got["most_positive"]}) == len(got["most_positive"])
