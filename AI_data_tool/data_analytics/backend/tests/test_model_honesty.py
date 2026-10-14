"""Data-scientist tour (2026-10-10): a model must not see the answer, must use
the categories that matter, and every candidate must get a fair try.

On the Cars dataset a saved model "predicted price_egp from ... price_egp
(copy)" and reported R² 0.87; without the copy the honest figure was 0.24.
The car's make (104 brands) was skipped as "too many values", and linear
regression "could not be fitted" because mileage has gaps.
"""
import numpy as np
import pandas as pd
import pytest

from app.routers.prediction_models import _computed_from
from app.services.analysis.automated_prediction import automated_prediction
from app.services.analysis.decision_tree import OTHER, _usable_predictors
from app.services.analysis.model_store import fit_and_package, score_frame

rng = np.random.default_rng(7)
N = 600
BRANDS = [f"brand{i}" for i in range(60)]


def cars():
    make = rng.choice(BRANDS, N)
    year = rng.integers(2015, 2025, N)
    km = rng.integers(0, 200_000, N).astype(float)
    km[rng.random(N) < 0.25] = np.nan                       # a quarter of mileage empty
    premium = np.isin(make, BRANDS[:5]) * 900_000
    price = 300_000 + (year - 2015) * 60_000 + premium + rng.normal(0, 50_000, N)
    return pd.DataFrame({"make": make, "model_year": year, "mileage_km": km, "price": price,
                         "price (copy)": price, "price_k": price / 1000, "id": np.arange(N).astype(str)})


class TestTheAnswerIsNeverAnInput:
    def test_a_copy_or_rescaling_of_the_outcome_is_skipped_with_a_reason(self):
        used, skipped = _usable_predictors(cars(), "price", None, allow_grouping=True)
        assert "price (copy)" not in used and "price_k" not in used
        reasons = {s["column"]: s["reason"] for s in skipped}
        assert reasons["price (copy)"].startswith("a copy of the outcome")
        assert reasons["price_k"].startswith("a copy of the outcome")

    def test_a_genuinely_related_column_is_kept(self):
        used, _ = _usable_predictors(cars(), "price", None, allow_grouping=True)
        assert "model_year" in used

    def test_calculated_columns_built_from_the_outcome_are_found_transitively(self):
        calc = [{"name": "band", "expression": "IF(price > 1e6, 'high', 'low')"},
                {"name": "band_code", "expression": "IF(band == 'high', 1, 0)"},
                {"name": "age", "expression": "2026 - model_year"}]
        assert _computed_from(calc, "price") == {"band", "band_code"}


class TestManyValuedCategories:
    def test_make_is_used_with_its_rarer_brands_grouped(self):
        r = automated_prediction(cars(), "price", None)
        assert "make" in r["predictors_used"] and r["predictors_grouped"]["make"] == 19
        assert "id" not in r["predictors_used"]                 # one value per row: an identifier

    def test_a_saved_model_scores_an_unseen_brand_as_other(self):
        pkg = fit_and_package(cars(), "price")
        assert OTHER in pkg.categories["make"] and len(pkg.categories["make"]) == 20
        new = cars().head(2).copy()
        new.loc[new.index[0], "make"] = "never-seen-brand"
        out = score_frame(pkg, new)
        assert len(out["predictions"]) == 2 and "make" not in (out.get("unseen") or {})


class TestEveryCandidateGetsATry:
    def test_linear_regression_fits_data_with_gaps(self):
        r = automated_prediction(cars(), "price", None)
        lin = next(c for c in r["candidates"] if c["model"] == "linear regression")
        assert lin["score"] is not None and lin["error"] is None

    def test_a_saved_linear_model_scores_rows_with_gaps(self):
        pkg = fit_and_package(cars(), "price", family="linear regression")
        rows = cars().head(40)
        assert rows["mileage_km"].isna().any()                  # some rows to score have gaps
        assert all(np.isfinite(score_frame(pkg, rows)["predictions"]))


class TestAskAIAnswersInTheQuestionsLanguage:
    """Analyst tour (2026-10-10): an English question got an Arabic answer."""

    @pytest.mark.parametrize("q,lang", [
        ("Which region had the highest total revenue in 2025?", "English"),
        ("ما المنطقة التي حققت أعلى إيراد في 2025؟", "Arabic"),
        ("How much did القاهرة sell?", "English"),        # an Arabic value inside an English question
        ("كم باعت Cairo؟ وما الفرق عن العام الماضي", "Arabic"),
    ])
    def test_the_language_is_decided_from_the_question(self, q, lang):
        from app.services.agent.nodes.explain import language_rule, question_language
        assert question_language(q) == lang
        assert language_rule(q).startswith(f"Write the answer in {lang}")
