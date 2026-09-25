"""When will this reach X? — goal-seek along a forecast.

Goal-seek existed, solving for the x a target y needs on a linear fit of one
column against another. A forecast existed, projecting a series forward with a
95% band. Neither knew about the other, so the question a forecast most
obviously invites — *when* do we get there — had no answer in the product.

Three things make this honest rather than a number generator:

  * **History is consulted first.** On the demo data, revenue peaked at 422k
    over a year ago and the projection has since settled near 380k. Asked "when
    do we reach 400k?", "not within the horizon" is true and useless; "already
    reached, in 2025-05, and not expected to recross" is the answer somebody can
    act on.

  * **The band decides earliest and latest.** The central estimate gives the
    expected period; the optimistic edge of the band gives the soonest it could
    happen and the pessimistic edge the latest. A forecast whose uncertainty
    does not grow is lying about one of the two, and an answer that ignores the
    band inherits that lie.

  * **Direction comes from the data.** A target above the last actual is a rise
    and a target below it is a fall, and which edge of the band counts as
    "optimistic" swaps between them.

Deliberately NOT in scope: scenario analysis over underlying factors. AutoETS
takes no exogenous regressors, so "if marketing spend rose 10%..." needs a
different model. This is the trajectory question only.
"""
import pytest

from app.services.analysis.forecast_goal import ForecastGoalError, forecast_goal


def hist(*pairs):
    return [{"name": n, "value": v} for n, v in pairs]


def fc(*triples):
    return [{"name": n, "yhat": y, "lo": lo, "hi": hi} for n, y, lo, hi in triples]


RISING = fc(("2026-01", 100.0, 80.0, 115.0),
            ("2026-02", 110.0, 85.0, 135.0),
            ("2026-03", 120.0, 88.0, 152.0),
            ("2026-04", 130.0, 90.0, 170.0))


class TestARiseToTheTarget:
    def test_it_names_the_period_the_projection_crosses(self):
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 120.0)
        assert got["expected_period"] == "2026-03"

    def test_the_band_gives_a_soonest_and_a_latest(self):
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 120.0)
        # The optimistic edge reaches 120 in Feb (hi=135); the pessimistic edge
        # never does within the horizon.
        assert got["earliest_period"] == "2026-02"
        assert got["latest_period"] is None

    def test_soonest_is_never_after_expected(self):
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 130.0)
        names = [p["name"] for p in RISING]
        assert names.index(got["earliest_period"]) <= names.index(got["expected_period"])

    def test_the_direction_is_read_from_the_data(self):
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 120.0)
        assert got["direction"] == "rise"

    def test_a_target_exactly_on_the_projection_counts_as_reached(self):
        # `>=`, not `>`: hitting the number exactly is hitting it.
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 110.0)
        assert got["expected_period"] == "2026-02"


class TestAFallToTheTarget:
    """A target below today is a target to fall to — cost, churn, waiting time.
    The band's edges swap: the LOW edge is now the optimistic one."""

    FALLING = fc(("2026-01", 90.0, 70.0, 110.0),
                 ("2026-02", 80.0, 55.0, 105.0),
                 ("2026-03", 70.0, 40.0, 100.0))

    def test_direction_is_a_fall(self):
        got = forecast_goal(hist(("2025-12", 100.0)), self.FALLING, 75.0)
        assert got["direction"] == "fall"

    def test_it_crosses_downwards(self):
        got = forecast_goal(hist(("2025-12", 100.0)), self.FALLING, 75.0)
        assert got["expected_period"] == "2026-03"

    def test_the_low_edge_is_the_optimistic_one_now(self):
        got = forecast_goal(hist(("2025-12", 100.0)), self.FALLING, 75.0)
        assert got["earliest_period"] == "2026-01"   # lo=70 already below 75


class TestItAlreadyHappened:
    """The case the demo data is full of, and the one a horizon-only answer gets
    exactly wrong."""

    def test_a_target_history_already_passed_is_reported_from_history(self):
        # Ends BELOW the target: the series peaked, then fell back. That is
        # what makes "already reached" the interesting answer rather than a
        # fall of two points.
        history = hist(("2025-04", 300.0), ("2025-05", 422.0), ("2025-06", 385.0))
        flat = fc(("2026-01", 380.0, 307.0, 453.0), ("2026-02", 381.0, 307.0, 454.0))
        got = forecast_goal(history, flat, 400.0)
        assert got["reached_in_history"] == {"period": "2025-05", "value": 422.0}

    def test_it_says_the_projection_does_not_recross(self):
        history = hist(("2025-05", 422.0), ("2025-06", 385.0))
        flat = fc(("2026-01", 380.0, 307.0, 453.0))
        got = forecast_goal(history, flat, 400.0)
        assert got["reached_in_history"] is not None
        assert got["expected_period"] is None
        assert got["within_horizon"] is False

    def test_the_earliest_time_it_happened_is_the_one_reported(self):
        """Not the most recent crossing: "when did we first get there" is the
        question, and the last one would move every time a period is added.

        The history has to end BELOW the target for this to be a rise — a
        series sitting above its target is asking a different question (how
        long until it drops back), and the answer changes accordingly. Three
        fixtures in this file got that wrong before the code did.
        """
        history = hist(("2025-01", 410.0), ("2025-02", 390.0), ("2025-03", 395.0))
        got = forecast_goal(history, RISING, 400.0)
        assert got["reached_in_history"]["period"] == "2025-01"


class TestItSaysHowFarShortInstead:
    def test_a_target_beyond_the_horizon_reports_where_it_ends_up(self):
        """"Not within 6 periods" alone leaves the reader guessing whether they
        missed by a little or by a factor of two."""
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 900.0)
        assert got["within_horizon"] is False
        assert got["expected_period"] is None
        assert got["end_value"] == 130.0
        assert got["end_hi"] == 170.0

    def test_a_band_that_crosses_when_the_estimate_does_not_is_said_so(self):
        # 150 is inside the optimistic edge by April but not the central line:
        # "possible, not expected" is a different answer from "no".
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 150.0)
        assert got["expected_period"] is None
        assert got["earliest_period"] == "2026-03"
        assert got["within_horizon"] is False

    def test_the_horizon_length_is_reported(self):
        got = forecast_goal(hist(("2025-12", 95.0)), RISING, 900.0)
        assert got["horizon"] == 4


class TestItRefusesRatherThanGuessing:
    def test_an_empty_forecast(self):
        with pytest.raises(ForecastGoalError):
            forecast_goal(hist(("2025-12", 95.0)), [], 120.0)

    def test_no_history_at_all(self):
        # Direction is read from the last actual; without one there is nothing
        # to read it from.
        with pytest.raises(ForecastGoalError):
            forecast_goal([], RISING, 120.0)

    def test_a_target_that_is_not_a_number(self):
        with pytest.raises(ForecastGoalError):
            forecast_goal(hist(("2025-12", 95.0)), RISING, None)

    def test_a_forecast_missing_its_band_still_answers_the_central_question(self):
        """A `simple` forecast can come back without lo/hi. That should cost the
        earliest/latest range, not the whole answer."""
        bare = [{"name": "2026-01", "yhat": 100.0}, {"name": "2026-02", "yhat": 130.0}]
        got = forecast_goal(hist(("2025-12", 95.0)), bare, 120.0)
        assert got["expected_period"] == "2026-02"
        assert got["earliest_period"] is None
        assert got["latest_period"] is None


class TestItIsRunnableFromTheCatalogue:
    """The dispatcher hands analyses a DataFrame, and this one reasons about a
    forecast. The wrapper builds that forecast with the SAME shaper the widget
    uses, so the answer cannot disagree with the chart the reader is looking
    at — a second fit would be a second opinion presented as one fact.
    """

    def frame(self):
        import pandas as pd
        # Two years of a clean upward trend, monthly.
        dates = pd.date_range("2024-01-01", periods=24, freq="MS")
        return pd.DataFrame({"month": dates,
                             "revenue": [100 + 5 * i for i in range(24)]})

    def test_it_forecasts_and_then_answers(self):
        from app.services.analysis.forecast_goal import forecast_goal_over
        got = forecast_goal_over(self.frame(), date_column="month",
                                 measure="revenue", target=260.0)
        assert got["direction"] == "rise"
        assert got["horizon"] > 0

    def test_it_carries_the_series_so_the_answer_can_be_drawn(self):
        from app.services.analysis.forecast_goal import forecast_goal_over
        got = forecast_goal_over(self.frame(), date_column="month",
                                 measure="revenue", target=260.0)
        assert got["forecast"], "the projection itself is part of the answer"

    def test_a_column_that_is_not_there(self):
        from app.services.analysis.forecast_goal import forecast_goal_over
        with pytest.raises(ForecastGoalError):
            forecast_goal_over(self.frame(), date_column="nope",
                               measure="revenue", target=1.0)

    def test_it_is_registered_and_runnable(self):
        from app.services.analysis.registry import get
        spec = get("forecast_goal")
        assert spec is not None
        assert spec.to_dict()["runnable"] is True

    def test_the_registry_can_dispatch_it(self):
        from app.services.analysis.registry import run_analysis
        got = run_analysis("forecast_goal", self.frame(),
                           {"date_column": "month", "measure": "revenue",
                            "target": 260.0})
        assert "expected_period" in got


class TestTheWidgetCarriesTheAnswer:
    """The forecast widget already has the history and the projection in hand.

    Computing "when do we reach X" a second time — in the browser, or through a
    second endpoint that re-fits — would put a caption on screen that could
    disagree with the chart above it. So the shaper answers it, when and only
    when the widget's config names a target.
    """

    def frame(self):
        import pandas as pd
        dates = pd.date_range("2024-01-01", periods=24, freq="MS")
        return pd.DataFrame({"month": dates,
                             "revenue": [100 + 5 * i for i in range(24)]})

    def shaped(self, **extra):
        from app.services.widget_data import shape_forecast
        return shape_forecast(self.frame(), {
            "dimension": "month", "measure": "revenue",
            "aggregation": "sum", "dimension_granularity": "month", **extra})

    def test_no_target_means_no_answer_and_no_extra_work(self):
        # The overwhelmingly common case: every forecast widget that has never
        # been given a target must be byte-for-byte what it was.
        assert "goal" not in self.shaped()

    def test_a_target_attaches_the_answer(self):
        out = self.shaped(forecast_target=260)
        assert out["goal"]["target"] == 260
        assert out["goal"]["direction"] == "rise"

    def test_the_answer_is_about_the_series_on_screen(self):
        # Same rows, same forecast, one fit.
        out = self.shaped(forecast_target=260)
        assert out["goal"]["horizon"] == len(out["forecast"])
        assert out["goal"]["last_actual"] == out["rows"][-1]["value"]

    def test_an_unreachable_target_still_answers(self):
        out = self.shaped(forecast_target=10_000)
        assert out["goal"]["within_horizon"] is False
        assert out["goal"]["end_value"] is not None

    def test_a_target_that_makes_no_sense_does_not_break_the_chart(self):
        """A widget whose caption cannot be computed must still draw. The
        forecast is the point; the target is an annotation on it."""
        out = self.shaped(forecast_target="not a number")
        assert out["type"] == "forecast"
        assert out["forecast"]
        assert "goal" not in out
