"""What if spend rose 10%? — a projection with factors you can move.

`shape_forecast` is AutoETS: univariate, no exogenous inputs. It answers "where
is this heading" and cannot answer "where would it head if we changed
something", which is the question a plan is actually made of.

**OLS on period totals — `measure ~ time + factors` — rather than SARIMAX with
exogenous regressors**, even though SARIMAX is available. SARIMAX needs FUTURE
values for every factor, which is a second forecasting problem hidden inside the
first: the answer would silently depend on a forecast of spend that nobody
asked for and nobody sees. Asking for the adjustment directly is the honest
shape, because the adjustment is the thing the user actually knows.

Three properties decide whether this is a plan or a plausible-looking number:

  * **Association, not intervention.** Moving a factor inside a fitted model is
    not the same as changing it in the world; the model has only ever seen them
    move together. Said loudly, every time.

  * **Each factor's evidence travels with it.** A coefficient with a p-value of
    0.6 must not lend the same weight to a scenario as one at 0.001, and the
    reader cannot tell them apart unless both are shown.

  * **Extrapolation is named.** "What if spend doubled" is unanswerable from
    data where it never moved more than 20%, and answering anyway with a
    confident number is the failure mode this whole catalogue is built against.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.forecast_scenario import (ForecastScenarioError,
                                                     forecast_scenario)


@pytest.fixture
def spend_drives_revenue():
    """Revenue is 3x spend plus a trend, so the coefficient is knowable and the
    scenario arithmetic can be checked rather than merely exercised."""
    rng = np.random.default_rng(0)
    months = pd.date_range("2024-01-01", periods=30, freq="MS")
    spend = rng.uniform(80, 120, 30)
    revenue = 3.0 * spend + 20 * np.arange(30) + rng.normal(0, 3, 30)
    return pd.DataFrame({"month": months, "spend": spend,
                         "headcount": rng.uniform(9, 11, 30), "revenue": revenue})


class TestItFitsTheFactors:
    def test_it_reports_a_coefficient_per_factor(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend", "headcount"])
        assert {f["column"] for f in got["factors"]} == {"spend", "headcount"}

    def test_the_coefficient_is_about_right(self, spend_drives_revenue):
        # Revenue really is 3x spend; a fit that says 0.4 has not found it.
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"])
        spend = next(f for f in got["factors"] if f["column"] == "spend")
        assert 2.5 <= spend["coefficient"] <= 3.5

    def test_evidence_travels_with_each_factor(self, spend_drives_revenue):
        """A p-value of 0.6 must not lend a scenario the same weight as 0.001,
        and a reader cannot tell without seeing both."""
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend", "headcount"])
        assert all("p_value" in f for f in got["factors"])
        spend = next(f for f in got["factors"] if f["column"] == "spend")
        assert spend["p_value"] < 0.01

    def test_it_reports_how_well_the_model_fits(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"])
        assert got["r2"] > 0.9


class TestTheScenarioItself:
    def test_a_baseline_projection_is_returned(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"], periods=6)
        assert len(got["baseline"]) == 6

    def test_raising_a_positive_factor_raises_the_projection(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"],
                                adjustments={"spend": 0.10}, periods=6)
        assert all(s["value"] > b["value"]
                   for s, b in zip(got["scenario"], got["baseline"]))

    def test_the_size_of_the_change_follows_the_coefficient(self, spend_drives_revenue):
        """+10% on a spend of ~100 is +10 units, times a coefficient of ~3, so
        about +30 per period. Checked rather than assumed: a scenario that moves
        in the right direction by the wrong amount is still wrong."""
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"],
                                adjustments={"spend": 0.10}, periods=3)
        delta = got["scenario"][0]["value"] - got["baseline"][0]["value"]
        assert 20 <= delta <= 45

    def test_lowering_a_factor_lowers_it(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"],
                                adjustments={"spend": -0.10}, periods=4)
        assert all(s["value"] < b["value"]
                   for s, b in zip(got["scenario"], got["baseline"]))

    def test_no_adjustment_means_the_two_agree(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"], periods=4)
        assert [s["value"] for s in got["scenario"]] == \
               [b["value"] for b in got["baseline"]]

    def test_the_total_difference_is_stated(self, spend_drives_revenue):
        # The number somebody actually takes to a meeting.
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"],
                                adjustments={"spend": 0.10}, periods=6)
        assert got["scenario_total"] > got["baseline_total"]
        assert got["difference"] == round(
            got["scenario_total"] - got["baseline_total"], 4)


class TestItNamesAnExtrapolation:
    def test_an_adjustment_beyond_the_observed_range_is_flagged(
            self, spend_drives_revenue):
        """Spend has never left 80-120. "What if it doubled" is a question this
        data cannot answer, and answering anyway with a confident number is the
        failure this catalogue exists to avoid."""
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"],
                                adjustments={"spend": 1.0}, periods=3)
        assert got["extrapolating"] is True
        assert any("outside" in c.lower() or "never" in c.lower()
                   for c in got["caveats"])

    def test_a_modest_adjustment_is_not_flagged(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"],
                                adjustments={"spend": 0.05}, periods=3)
        assert got["extrapolating"] is False

    def test_the_observed_range_is_reported_per_factor(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"])
        spend = next(f for f in got["factors"] if f["column"] == "spend")
        assert spend["observed_min"] < spend["observed_max"]


class TestItSaysWhatItIsNot:
    def test_association_not_intervention(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend"])
        assert any("caus" in c.lower() or "intervent" in c.lower()
                   for c in got["caveats"])

    def test_it_says_factors_are_held_at_their_recent_level(self, spend_drives_revenue):
        got = forecast_scenario(spend_drives_revenue, date_column="month",
                                measure="revenue", factors=["spend", "headcount"],
                                adjustments={"spend": 0.1})
        assert any("held" in c.lower() for c in got["caveats"])


class TestItRefusesRatherThanGuessing:
    def test_a_missing_measure(self, spend_drives_revenue):
        with pytest.raises(ForecastScenarioError):
            forecast_scenario(spend_drives_revenue, date_column="month",
                              measure="nope", factors=["spend"])

    def test_a_missing_factor(self, spend_drives_revenue):
        with pytest.raises(ForecastScenarioError):
            forecast_scenario(spend_drives_revenue, date_column="month",
                              measure="revenue", factors=["nope"])

    def test_no_factors_at_all(self, spend_drives_revenue):
        # Without a factor this is just a forecast, and there is one of those.
        with pytest.raises(ForecastScenarioError):
            forecast_scenario(spend_drives_revenue, date_column="month",
                              measure="revenue", factors=[])

    def test_too_few_periods_to_fit(self):
        df = pd.DataFrame({"month": pd.date_range("2024-01-01", periods=4, freq="MS"),
                           "spend": [1.0, 2, 3, 4], "revenue": [3.0, 6, 9, 12]})
        with pytest.raises(ForecastScenarioError):
            forecast_scenario(df, date_column="month", measure="revenue",
                              factors=["spend"])

    def test_a_non_numeric_factor(self, spend_drives_revenue):
        df = spend_drives_revenue.assign(region=["N", "S"] * 15)
        with pytest.raises(ForecastScenarioError):
            forecast_scenario(df, date_column="month", measure="revenue",
                              factors=["region"])


class TestItIsInTheCatalogue:
    def test_registered_and_runnable(self):
        from app.services.analysis.registry import get
        spec = get("forecast_scenario")
        assert spec is not None
        assert spec.to_dict()["runnable"] is True

    def test_the_dispatcher_runs_it(self, spend_drives_revenue):
        from app.services.analysis.registry import run_analysis
        got = run_analysis("forecast_scenario", spend_drives_revenue,
                           {"date_column": "month", "measure": "revenue",
                            "factors": ["spend"], "adjustments": {"spend": 0.1}})
        assert got["difference"] > 0
