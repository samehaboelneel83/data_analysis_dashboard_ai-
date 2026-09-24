"""Saving the champion, and scoring rows it has never seen.

`automated_prediction` compares candidates and throws every fitted model away.
Its own caveat says so: "this answers what CAN be predicted and how well, not
'score these new rows'". This is the store that closes that, and the whole
difficulty is in one place.

**Feature alignment.** `_encode` one-hot encodes with `pd.get_dummies`, so the
COLUMNS IT PRODUCES DEPEND ON THE VALUES PRESENT. A model trained on regions
{North, South} has features `region_North`, `region_South`; score a frame
containing only South and get one column, in a different position. sklearn
either raises or -- worse -- silently reads the wrong number as the wrong
feature. So the training column list travels with the model and every scored
frame is reindexed onto it.

That also decides what an unseen category means: a value the model never saw
becomes zero in every one of that column's dummies, which is the honest
encoding (the model has no opinion) but has to be REPORTED, or a user scores a
year of new data against a model that recognises none of it and sees only a
column of confident-looking numbers.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.model_store import (ModelStoreError, fit_and_package,
                                               score_frame)


@pytest.fixture
def training():
    """Region and spend predict churn, with enough rows to hold a quarter back."""
    rng = np.random.default_rng(0)
    n = 300
    region = rng.choice(["North", "South", "East"], n)
    spend = rng.normal(100, 20, n)
    # A real signal, so a champion can actually beat the baseline.
    churn = np.where((region == "North") | (spend > 120), "yes", "no")
    return pd.DataFrame({"region": region, "spend": spend, "churn": churn})


class TestPackaging:
    def test_it_returns_an_artifact_and_what_is_needed_to_use_it(self, training):
        pkg = fit_and_package(training, "churn")
        assert pkg.artifact          # bytes
        assert pkg.target == "churn"
        assert set(pkg.features) == {"region", "spend"}
        # The ENCODED column order, which is the thing scoring has to match.
        assert "spend" in pkg.feature_columns
        assert any(c.startswith("region") for c in pkg.feature_columns)
        assert pkg.task == "classification"
        assert pkg.model_family
        assert pkg.score is not None

    def test_it_refuses_what_automated_prediction_refuses(self, training):
        with pytest.raises(ModelStoreError):
            fit_and_package(training, "not_a_column")


class TestScoring:
    def test_it_scores_rows_it_has_never_seen(self, training):
        pkg = fit_and_package(training, "churn")
        fresh = pd.DataFrame({"region": ["North", "South"], "spend": [50.0, 200.0]})

        out = score_frame(pkg, fresh)

        assert len(out["predictions"]) == 2
        assert all(p in ("yes", "no") for p in out["predictions"])

    def test_a_frame_missing_a_category_still_lines_up(self, training):
        # The core alignment case. Trained on three regions, scored on one:
        # get_dummies alone would produce a single column and sklearn would be
        # reading `region_South` as `region_East`, or refuse outright.
        pkg = fit_and_package(training, "churn")
        fresh = pd.DataFrame({"region": ["South", "South"], "spend": [80.0, 130.0]})

        out = score_frame(pkg, fresh)
        assert len(out["predictions"]) == 2

    def test_an_unseen_category_is_reported_not_hidden(self, training):
        # "West" was never in training. Encoding it as all-zeros is the honest
        # answer -- the model has no opinion -- but silently returning a
        # confident-looking prediction for it is not.
        pkg = fit_and_package(training, "churn")
        fresh = pd.DataFrame({"region": ["West", "North"], "spend": [90.0, 90.0]})

        out = score_frame(pkg, fresh)
        assert out["unseen_values"], "an unseen category must be reported"
        assert "region" in out["unseen_values"]
        assert "West" in out["unseen_values"]["region"]

    def test_a_frame_missing_a_feature_is_refused(self, training):
        # Not the same as an unseen VALUE. A missing column means the caller is
        # scoring the wrong data, and quietly filling zeros would return
        # predictions from a model that saw none of its inputs.
        pkg = fit_and_package(training, "churn")
        with pytest.raises(ModelStoreError, match="spend"):
            score_frame(pkg, pd.DataFrame({"region": ["North"]}))

    def test_extra_columns_are_ignored(self, training):
        # Scoring a live table that has grown a column since training is normal
        # and must not be an error.
        pkg = fit_and_package(training, "churn")
        fresh = pd.DataFrame({"region": ["North"], "spend": [90.0], "new_col": ["x"]})
        assert len(score_frame(pkg, fresh)["predictions"]) == 1

    def test_the_target_may_be_absent(self, training):
        # The whole point: rows whose outcome is not known yet.
        pkg = fit_and_package(training, "churn")
        fresh = pd.DataFrame({"region": ["North"], "spend": [90.0]})
        assert "churn" not in fresh.columns
        assert score_frame(pkg, fresh)["predictions"]


class TestTypesArrivingFromJson:
    """A scored row comes off the wire, where every value may be a string.

    This is the quiet one. `_encode` decides one-hot vs numeric by DTYPE, so a
    numeric feature arriving as "50" is treated as a CATEGORY: it becomes a
    dummy column named spend__50, the reindex onto the training columns finds no
    `spend`, and fills 0.0. No error, no unseen-value report -- spend is not a
    tracked category -- just a prediction made from a feature the model was
    handed and never saw. The mirror case is a categorical trained on "1"
    arriving as the integer 1.
    """

    def test_a_numeric_feature_as_a_string_scores_the_same(self, training):
        # region=South so REGION cannot decide it: the fixture's rule is
        # `North or spend > 120`, and a South row is "yes" only because of
        # spend. Asking with region=North would pass even when spend is
        # silently zeroed, which is how a test agrees with a bug.
        pkg = fit_and_package(training, "churn")
        as_number = score_frame(pkg, pd.DataFrame([{"region": "South", "spend": 200.0}]))
        as_string = score_frame(pkg, pd.DataFrame([{"region": "South", "spend": "200"}]))
        assert as_number["predictions"] == ["yes"]      # the model can see spend
        assert as_string["predictions"] == as_number["predictions"]

    def test_a_categorical_feature_as_a_number_is_recognised(self):
        # Trained on the STRINGS "1" and "2"; scored with the integer 1.
        import numpy as np
        rng = np.random.default_rng(3)
        n = 300
        tier = rng.choice(["1", "2"], n)
        spend = rng.normal(100, 20, n)
        df = pd.DataFrame({"tier": tier, "spend": spend,
                           "churn": np.where(tier == "1", "yes", "no")})
        pkg = fit_and_package(df, "churn")

        as_string = score_frame(pkg, pd.DataFrame([{"tier": "1", "spend": 100.0}]))
        as_number = score_frame(pkg, pd.DataFrame([{"tier": 1, "spend": 100.0}]))
        # The PREDICTION, not the unseen report: an integer tier is dropped
        # to all-zeros by the reindex, and `str(1)` is in the known values,
        # so the report stays empty in the broken case too.
        assert as_string["predictions"] == ["yes"]
        assert as_number["predictions"] == as_string["predictions"]

    def test_a_numeric_feature_that_is_not_a_number_is_refused(self, training):
        # Filling zero would answer from a feature the caller never supplied,
        # and zero is a real spend rather than an obvious blank.
        pkg = fit_and_package(training, "churn")
        with pytest.raises(ModelStoreError, match="spend"):
            score_frame(pkg, pd.DataFrame([{"region": "North", "spend": "lots"}]))


class TestRegression:
    def test_a_numeric_target_scores_numbers(self):
        rng = np.random.default_rng(1)
        n = 300
        spend = rng.normal(100, 20, n)
        df = pd.DataFrame({"spend": spend, "region": rng.choice(["A", "B"], n),
                           "revenue": spend * 3 + rng.normal(0, 5, n)})
        pkg = fit_and_package(df, "revenue")
        assert pkg.task == "regression"

        out = score_frame(pkg, pd.DataFrame({"spend": [100.0], "region": ["A"]}))
        assert isinstance(out["predictions"][0], float)


class TestRoundTrip:
    def test_an_artifact_survives_being_stored_as_bytes(self, training):
        # The artifact goes into a database column and comes back. Scoring from
        # the reloaded bytes is what the endpoint will actually do.
        pkg = fit_and_package(training, "churn")
        stored = bytes(pkg.artifact)

        from dataclasses import replace
        reloaded = replace(pkg, artifact=stored)
        out = score_frame(reloaded, pd.DataFrame({"region": ["North"], "spend": [90.0]}))
        assert len(out["predictions"]) == 1
