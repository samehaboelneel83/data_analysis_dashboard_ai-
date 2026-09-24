"""The two SAS-shaped analyses that were not in the catalogue.

This platform already ships an automated explanation and a goal-seek. Both name
SAS in their own docstrings. Neither was in the analysis registry, so neither
appeared in `GET /analysis/registry`, neither could be driven by the generic
statistics panel, and the agent's prompt block -- which is rendered from the
registry -- did not know they existed.

`explain_response` lived in `services/explain.py`, reachable only from one
dialog. `goal_seek` lived *inside a router function*, its arithmetic tangled
with `HTTPException` and `Depends`, so nothing could call it but HTTP.

Registering them changes no behaviour for existing callers. It makes them
findable, which for a capability is most of the difference between having it and
not.
"""
import pandas as pd
import pytest

from app.services.analysis.goal_seek import GoalSeekError, goal_seek
from app.services.analysis.registry import all_analyses, get, run_analysis


@pytest.fixture
def frame():
    """y = 2x + 1 exactly, so every fitted number has a known right answer."""
    return pd.DataFrame({"spend": list(range(20)),
                         "revenue": [2 * i + 1 for i in range(20)],
                         "region": ["n", "s"] * 10})


class TestGoalSeekAsAService:
    def test_it_solves_for_the_required_x(self, frame):
        got = goal_seek(frame, "spend", "revenue", target_y=41.0)
        assert got["required_x"] == pytest.approx(20.0)

    def test_it_reports_the_fit(self, frame):
        got = goal_seek(frame, "spend", "revenue", target_y=41.0)
        assert got["slope"] == pytest.approx(2.0)
        assert got["intercept"] == pytest.approx(1.0)
        assert got["r2"] == pytest.approx(1.0)

    def test_it_says_when_the_answer_is_an_extrapolation(self, frame):
        """A goal outside the observed data is a guess, and the caller is owed
        that fact rather than a confident number."""
        got = goal_seek(frame, "spend", "revenue", target_y=1001.0)
        assert got["within_observed_range"] is False

    def test_it_says_when_the_answer_is_inside_the_data(self, frame):
        got = goal_seek(frame, "spend", "revenue", target_y=21.0)
        assert got["within_observed_range"] is True

    def test_bounds_report_infeasibility_with_the_best_achievable(self, frame):
        """SAS's goal-seek constraint: when the required x is out of bounds,
        report the binding bound and the y actually reachable there."""
        got = goal_seek(frame, "spend", "revenue", target_y=41.0,
                        x_min=0.0, x_max=5.0)
        assert got["within_bounds"] is False
        assert got["bound_x"] == pytest.approx(5.0)
        assert got["achievable_y"] == pytest.approx(11.0)

    def test_bounds_that_contain_the_answer_are_feasible(self, frame):
        got = goal_seek(frame, "spend", "revenue", target_y=21.0,
                        x_min=0.0, x_max=50.0)
        assert got["within_bounds"] is True


class TestGoalSeekRefusesHonestly:
    """Every refusal is a ValueError the router maps to a 400 -- the service
    raises no HTTPException, so it stays callable from anywhere."""

    def test_a_flat_relationship_is_refused(self):
        flat = pd.DataFrame({"x": range(20), "y": [7] * 20})
        with pytest.raises(GoalSeekError):
            goal_seek(flat, "x", "y", target_y=9.0)

    def test_too_few_rows_is_refused(self):
        with pytest.raises(GoalSeekError):
            goal_seek(pd.DataFrame({"x": [1, 2], "y": [2, 4]}), "x", "y", 6.0)

    def test_a_constant_x_is_refused(self):
        with pytest.raises(GoalSeekError):
            goal_seek(pd.DataFrame({"x": [3] * 20, "y": range(20)}),
                      "x", "y", 5.0)

    def test_reversed_bounds_are_refused(self, frame):
        with pytest.raises(GoalSeekError):
            goal_seek(frame, "spend", "revenue", 21.0, x_min=9.0, x_max=1.0)

    def test_a_missing_column_is_refused(self, frame):
        with pytest.raises(GoalSeekError):
            goal_seek(frame, "nope", "revenue", 21.0)


class TestBothAreInTheCatalogue:
    @pytest.mark.parametrize("name", ["explain_response", "goal_seek"])
    def test_it_is_registered(self, name):
        assert get(name) is not None, f"{name} is not in the registry"

    @pytest.mark.parametrize("name", ["explain_response", "goal_seek"])
    def test_it_is_runnable(self, name):
        assert get(name).to_dict()["runnable"] is True

    def test_goal_seek_runs_through_the_dispatcher(self, frame):
        got = run_analysis("goal_seek", frame,
                           {"x_column": "spend", "y_column": "revenue",
                            "target_y": 41.0})
        assert got["required_x"] == pytest.approx(20.0)

    def test_explain_runs_through_the_dispatcher(self, frame):
        got = run_analysis("explain_response", frame, {"response": "revenue"})
        assert got["factors"], got

    def test_the_top_factor_scores_one(self, frame):
        """SAS's scale: the most important factor is 1.0 and the rest are
        proportional to it."""
        got = run_analysis("explain_response", frame, {"response": "revenue"})
        assert got["factors"][0]["relative"] == pytest.approx(1.0)

    def test_the_catalogue_grew_by_exactly_two(self):
        names = [s.name for s in all_analyses()]
        assert len(names) == len(set(names)), "duplicate registration"
        assert {"explain_response", "goal_seek"} <= set(names)
