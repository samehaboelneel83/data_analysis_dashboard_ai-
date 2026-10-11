"""Ask AI with no model: an answer about what can be computed, not a failure
(docs/discovery/PLAN.md, phase 0)."""
from types import SimpleNamespace

from app.services.agent import without_model


def ctx(**tables):
    return SimpleNamespace(objects={name: SimpleNamespace(columns=cols) for name, cols in tables.items()})


def test_it_names_the_columns_the_question_points_at_and_what_they_allow():
    c = ctx(t1={"created_at": "timestamp", "region": "text", "fee_total": "numeric", "c9": "integer"})
    said = without_model.answer("total fees by region last month", c, "AI is switched off for this data")
    assert "AI is switched off for this data" in said and "no query was written" in said
    assert "fee_total (in t1): a number" in said and "region (in t1): a category" in said
    assert "c9" not in said                                   # not asked about


def test_it_lists_only_analyses_the_data_can_support():
    numbers_only = ctx(t={"a": "numeric", "b": "numeric"})
    said = without_model.answer("anything", numbers_only)
    assert "matched a column name" in said                    # says so, rather than guessing
    assert "Project a number into the coming periods" not in said      # no date: no forecast
    with_dates = without_model.answer("anything", ctx(t={"d": "date", "a": "numeric", "g": "text"}))
    assert "Project a number into the coming periods" in with_dates    # a date opens the forecasts
    assert "KMeans" not in with_dates                                  # plain words, not method names


def test_arabic_column_names_are_matched_too():
    c = ctx(t={"المبلغ": "numeric", "المنطقة": "text"})
    said = without_model.answer("ما هو المبلغ حسب المنطقة", c)
    # Asked in Arabic, answered in Arabic (it used to answer in English whatever the question).
    assert "المبلغ (في t): رقم" in said and "المنطقة (في t): فئة" in said
    assert "تعذّر استخدام نموذج الذكاء الاصطناعي" in said and "I could not" not in said
    # ...and the same question in English is still answered in English.
    english = without_model.answer("the المبلغ by المنطقة", ctx(t={"amount": "numeric"}))
    assert english.startswith("تعذّر")                     # Arabic letters in the question decide the language
    assert without_model.answer("amount by group", ctx(t={"amount": "numeric"})).startswith("I could not")
