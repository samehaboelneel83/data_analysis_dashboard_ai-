"""Automated prediction: fit several models, name the one that wins.

SAS runs a handful of candidates and picks a champion. The pieces were all here
already -- a decision tree, regressions, a logistic model -- and nothing put
them in the same room and compared them.

Four things decide whether this is a useful answer or a number generator:

  * **One split, shared by every candidate.** Comparing a tree scored on one
    random quarter against a forest scored on a different quarter compares the
    quarters, not the models. This is the single most important property here
    and the easiest to get silently wrong.

  * **A dumb baseline always runs.** "Always guess the majority class" is the
    score any real model must beat to have earned its place. Reporting 82%
    accuracy without mentioning that guessing gets 79% is the most common way a
    prediction result misleads.

  * **The margin is the headline, not the score.** A champion that beats the
    baseline by half a point is a champion of nothing, and the result says so
    in words rather than leaving the reader to subtract.

  * **Nothing is persisted, and that is stated.** No fitted model is stored
    anywhere in this codebase; every endpoint refits and discards. So this
    answers "what could predict this, and how well" -- not "score these new
    rows", which would need a model store that does not exist.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.automated_prediction import (
    AutomatedPredictionError, automated_prediction)


@pytest.fixture
def learnable():
    """An outcome a model can genuinely find: churn driven by margin."""
    rng = np.random.default_rng(0)
    n = 500
    margin = rng.uniform(0, 40, n)
    return pd.DataFrame({
        "margin_pct": margin,
        "region": rng.choice(["North", "South", "East"], n),
        "spend": rng.uniform(100, 900, n),
        "churned": np.where(margin < 12, "yes", "no"),
    })


@pytest.fixture
def noise():
    """No signal at all: the outcome is a coin flip, and the honest answer is
    that nothing beats guessing."""
    rng = np.random.default_rng(1)
    n = 400
    return pd.DataFrame({
        "a": rng.uniform(0, 1, n),
        "b": rng.uniform(0, 1, n),
        "outcome": rng.choice(["yes", "no"], n),
    })


@pytest.fixture
def numeric():
    rng = np.random.default_rng(2)
    n = 400
    units = rng.uniform(1, 100, n)
    return pd.DataFrame({"units": units, "noise": rng.uniform(0, 1, n),
                         "revenue": units * 12 + rng.normal(0, 4, n)})


class TestItComparesSeveralAndPicksOne:
    def test_it_names_a_champion(self, learnable):
        got = automated_prediction(learnable, target="churned")
        assert got["champion"]["model"] in {c["model"] for c in got["candidates"]}

    def test_it_actually_tries_several(self, learnable):
        got = automated_prediction(learnable, target="churned")
        assert len(got["candidates"]) >= 3

    def test_the_champion_is_the_best_scoring_candidate(self, learnable):
        got = automated_prediction(learnable, target="churned")
        best = max(got["candidates"], key=lambda c: c["score"])
        assert got["champion"]["model"] == best["model"]
        assert got["champion"]["score"] == best["score"]

    def test_every_candidate_is_scored_on_the_same_rows(self, learnable):
        """The property the whole comparison rests on. Different splits would
        compare the splits, not the models."""
        got = automated_prediction(learnable, target="churned")
        assert len({c["n_test"] for c in got["candidates"]}) == 1
        assert got["n_test"] == got["candidates"][0]["n_test"]

    def test_a_numeric_outcome_is_a_regression(self, numeric):
        got = automated_prediction(numeric, target="revenue")
        assert got["task"] == "regression"
        assert got["score_name"] == "r2"

    def test_it_is_reproducible(self, learnable):
        first = automated_prediction(learnable, target="churned")
        second = automated_prediction(learnable, target="churned")
        assert first["champion"] == second["champion"]


class TestTheBaselineIsAlwaysThere:
    def test_a_baseline_candidate_is_always_run(self, learnable):
        got = automated_prediction(learnable, target="churned")
        assert any(c["is_baseline"] for c in got["candidates"])

    def test_the_margin_over_it_is_reported(self, learnable):
        got = automated_prediction(learnable, target="churned")
        baseline = next(c for c in got["candidates"] if c["is_baseline"])
        assert got["baseline_score"] == baseline["score"]
        assert got["lift_over_baseline"] == round(
            got["champion"]["score"] - baseline["score"], 4)

    def test_a_real_signal_beats_guessing_by_a_lot(self, learnable):
        got = automated_prediction(learnable, target="churned")
        assert got["beats_baseline"] is True
        assert got["lift_over_baseline"] > 0.1

    def test_pure_noise_says_nothing_beats_guessing(self, noise):
        """The answer that matters most and is least often given. A champion
        that cannot beat a coin flip has to be reported as one."""
        got = automated_prediction(noise, target="outcome")
        assert got["beats_baseline"] is False
        assert any("baseline" in c.lower() or "guess" in c.lower()
                   for c in got["caveats"])


class TestItIsHonestAboutWhatItIsNot:
    def test_it_says_nothing_is_saved(self, learnable):
        """No fitted model is persisted anywhere in this codebase. A result
        that implied otherwise would have somebody waiting for a scoring
        endpoint that does not exist."""
        got = automated_prediction(learnable, target="churned")
        assert any("not saved" in c.lower() or "not stored" in c.lower()
                   or "refit" in c.lower() for c in got["caveats"])

    def test_it_names_the_columns_it_could_not_use(self, learnable):
        learnable = learnable.assign(ref=[f"R{i}" for i in range(len(learnable))])
        got = automated_prediction(learnable, target="churned")
        assert "ref" in {s["column"] for s in got["predictors_skipped"]}

    def test_association_not_causation(self, learnable):
        got = automated_prediction(learnable, target="churned")
        assert any("caus" in c.lower() for c in got["caveats"])

    def test_each_candidate_reports_its_training_score_too(self, learnable):
        # So a candidate that memorised is visible as one, not hidden behind a
        # respectable held-out number.
        got = automated_prediction(learnable, target="churned")
        assert all(c.get("train_score") is not None for c in got["candidates"])


class TestItRefusesRatherThanGuessing:
    def test_a_missing_target(self, learnable):
        with pytest.raises(AutomatedPredictionError):
            automated_prediction(learnable, target="nope")

    def test_a_constant_target(self, learnable):
        with pytest.raises(AutomatedPredictionError):
            automated_prediction(learnable.assign(churned="no"), target="churned")

    def test_too_few_rows(self):
        tiny = pd.DataFrame({"x": [1, 2, 3, 4], "y": ["a", "b", "a", "b"]})
        with pytest.raises(AutomatedPredictionError):
            automated_prediction(tiny, target="y")

    def test_no_usable_predictor(self):
        rng = np.random.default_rng(3)
        df = pd.DataFrame({"id": [f"r{i}" for i in range(200)],
                           "outcome": rng.choice(["a", "b"], 200)})
        with pytest.raises(AutomatedPredictionError):
            automated_prediction(df, target="outcome")


class TestItIsInTheCatalogue:
    def test_registered_and_runnable(self):
        from app.services.analysis.registry import get
        spec = get("automated_prediction")
        assert spec is not None
        assert spec.to_dict()["runnable"] is True

    def test_the_dispatcher_runs_it(self, learnable):
        from app.services.analysis.registry import run_analysis
        got = run_analysis("automated_prediction", learnable, {"target": "churned"})
        assert got["champion"]["score"] > 0


def test_a_partition_column_is_the_split_and_is_never_a_predictor():
    import numpy as np
    import pandas as pd
    from app.services.analysis.automated_prediction import automated_prediction
    rng = np.random.default_rng(1)
    n = 200
    x = rng.normal(size=n)
    df = pd.DataFrame({"x": x, "noise": rng.normal(size=n), "y": 3 * x + rng.normal(scale=0.1, size=n),
                       "_Partition_": ["Training"] * 150 + ["Validation"] * 50})
    got = automated_prediction(df, "y", partition="_Partition_")
    assert got["split"] == {"kind": "partition", "column": "_Partition_"}
    assert got["n_train"] == 150 and got["n_test"] == 50
    assert "_Partition_" not in got["predictors_used"]
    assert any("partition column '_Partition_'" in c for c in got["caveats"])
    import pytest
    from app.services.analysis.automated_prediction import AutomatedPredictionError
    with pytest.raises(AutomatedPredictionError):
        automated_prediction(df.assign(_Partition_="Training"), "y", partition="_Partition_")
