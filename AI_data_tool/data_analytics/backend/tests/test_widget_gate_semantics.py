"""Defect 3: the gate checked shape, never sense.

On a real upload the model proposed 17 widgets and `validate_widget` rejected
none of them -- including a KPI that was a SUM OF EXAM SCORES across 240
students, which was the lead tile on both composed reports. Verified before
these tests were written:

    validate_widget(sum of final_score, profile)  ->  (True, '')
    18 real model proposals                       ->  0 rejected

A total of 240 scores is a number with no referent. Nothing can be compared
against it, it grows with the class size rather than with attainment, and no
reader can act on it. The shape was valid; the question was meaningless.

These tests are written against the REASON TEXT as well as the verdict, because
a rejection a person cannot understand is a rejection they cannot overrule --
and step 5 puts these sentences in front of somebody deciding whether to accept
a dashboard.
"""
import pytest

from app.services.suggest_dataset_dashboard import validate_widget


def _profile(columns):
    return {"row_count": 240, "columns": columns, "other_columns": [],
            "structure": {"coordinate_pairs": [], "parent_child": [],
                          "hierarchies": [], "date_range": None}}


def _numeric(name, lo, hi, distinct=100):
    return {"name": name, "role": "numeric", "distinct": distinct,
            "missing_pct": 0.0, "is_identifier": False, "is_personal": False,
            "is_flag": False, "top_values": [], "min": lo, "max": hi}


def _cat(name, values=("a", "b", "c")):
    return {"name": name, "role": "categorical", "distinct": len(values),
            "missing_pct": 0.0, "is_identifier": False, "is_personal": False,
            "is_flag": False,
            "top_values": [{"value": v, "count": 10} for v in values],
            "min": None, "max": None}


SCORE = _numeric("final_score", 52.0, 92.9, distinct=174)
FEE = _numeric("tuition_fee", 8800.0, 15800.0, distinct=4)
FACULTY = _cat("faculty", ("Engineering", "Law", "Medicine"))
PROFILE = _profile([SCORE, FEE, FACULTY])


def _widget(measure, agg, wt="kpi", title=None, **cfg):
    return {"widget_type": wt, "title": title or f"{agg} of {measure}",
            "config": {"measure": measure, "aggregation": agg, **cfg}}


class TestSummingABoundedMeasureIsRefused:
    def test_the_exact_widget_that_shipped_is_now_rejected(self):
        """The lead KPI on both composed reports."""
        ok, why = validate_widget(_widget("final_score", "sum"), PROFILE)
        assert ok is False
        assert why, "rejected with no reason at all"

    def test_the_reason_names_the_column_and_says_what_to_do_instead(self):
        """Read as a USER. A reason that only says 'invalid' tells the person
        deciding nothing about whether to overrule it."""
        _ok, why = validate_widget(_widget("final_score", "sum"), PROFILE)
        low = why.lower()
        assert "final_score" in why, "the reason does not say which column"
        assert "sum" in low or "total" in low or "adding" in low
        assert "average" in low or "avg" in low or "distribution" in low, (
            f"the reason does not say what would work instead: {why!r}")

    @pytest.mark.parametrize("name", ["final_score", "pass_rate", "score_pct",
                                      "satisfaction_rating", "completion_ratio"])
    def test_the_whole_family_of_bounded_names(self, name):
        profile = _profile([_numeric(name, 0.0, 100.0), FACULTY])
        ok, _why = validate_widget(_widget(name, "sum"), profile)
        assert ok is False, f"summing {name} was allowed"

    def test_a_zero_to_one_ratio_is_caught_by_its_range_not_its_name(self):
        """A column nobody named helpfully. 0..1 is a proportion whatever it is
        called, and proportions do not add up to anything."""
        profile = _profile([_numeric("q4", 0.0, 1.0), FACULTY])
        ok, _why = validate_widget(_widget("q4", "sum"), profile)
        assert ok is False


class TestRealQuantitiesStillSum:
    def test_money_still_sums(self):
        """The rule must not swallow the case sums exist for. Total tuition
        across an intake is exactly the question a registrar asks."""
        ok, why = validate_widget(_widget("tuition_fee", "sum"), PROFILE)
        assert ok is True, why

    def test_averaging_a_score_is_untouched(self):
        ok, why = validate_widget(_widget("final_score", "avg"), PROFILE)
        assert ok is True, why

    def test_a_distribution_of_a_score_is_untouched(self):
        ok, why = validate_widget(
            {"widget_type": "histogram", "title": "Score distribution",
             "config": {"measure": "final_score"}}, PROFILE)
        assert ok is True, why

    def test_counting_rows_of_anything_is_untouched(self):
        ok, why = validate_widget(
            _widget("final_score", "count", wt="bar", dimension="faculty"),
            PROFILE)
        assert ok is True, why


class TestTheReasonsAreLegibleToSomeoneWhoDidNotWriteTheCode:
    """Step 5 shows these to a person deciding whether to accept a dashboard.
    Jargon, symbol names or bare verdicts make that decision impossible."""

    def test_no_reason_is_a_bare_verdict(self):
        _ok, why = validate_widget(_widget("final_score", "sum"), PROFILE)
        assert len(why.split()) >= 8, f"too terse to act on: {why!r}"

    def test_no_reason_leaks_an_internal_symbol(self):
        _ok, why = validate_widget(_widget("final_score", "sum"), PROFILE)
        for token in ("None", "validate_widget", "ROLE_SPECS", "config[",
                      "widget_type=", "Traceback"):
            assert token not in why, f"internal detail in a user-facing reason: {why!r}"
