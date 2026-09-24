"""Date, date-construction and advanced-statistics functions in the expression language.

These close four rows of the gap analysis's calculation-engine category. They follow the
conventions the existing functions established -- named after SAS/DAX rather than Python,
1-based where SAS is 1-based -- because an expression language that is internally
inconsistent is harder to use than one that is merely incomplete.
"""
import pandas as pd
import pytest

from app.services.widget_data import _build_safe_ns


def ev(expr, df):
    g, local = _build_safe_ns(df)
    return eval(expr, g, local)  # noqa: S307


@pytest.fixture
def dates():
    return pd.DataFrame({
        "d": pd.to_datetime(["2024-01-15 09:30:45", "2024-03-31 23:00:00", "2024-12-31 00:00:00"]),
        "y": [2024, 2024, 2023],
        "m": [1, 3, 12],
        "day": [15, 31, 31],
    })


@pytest.fixture
def nums():
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 100.0],
        "b": [2.0, 4.0, 6.0, 8.0, 200.0],
        "c": [5.0, 5.0, 5.0, 1.0, 2.0],
    })


class TestDateComponents:
    def test_weekday_is_one_based_from_monday_like_sas(self, dates):
        # 2024-01-15 is a Monday. Python's dayofweek would say 0; SAS says 1, and this
        # language follows SAS. Asserting the Monday case specifically is the point --
        # an off-by-one is invisible on any other day of the week.
        assert list(ev("WEEKDAY(d)", dates)) == [1, 7, 2]

    def test_time_components(self, dates):
        assert list(ev("HOUR(d)", dates)) == [9, 23, 0]
        assert list(ev("MINUTE(d)", dates)) == [30, 0, 0]
        assert list(ev("SECOND(d)", dates)) == [45, 0, 0]

    def test_week_and_day_of_year(self, dates):
        assert list(ev("WEEK(d)", dates)) == [3, 13, 1]        # ISO week; 2024-12-31 is week 1 of 2025
        assert list(ev("DAYOFYEAR(d)", dates)) == [15, 91, 366]  # 2024 is a leap year

    def test_names_are_words_not_numbers(self, dates):
        assert list(ev("MONTHNAME(d)", dates)) == ["January", "March", "December"]
        assert list(ev("DAYNAME(d)", dates)) == ["Monday", "Sunday", "Tuesday"]


class TestDateConstruction:
    def test_date_from_parts(self, dates):
        built = ev("DATEFROMYMD(y, m, day)", dates)
        assert list(built.dt.strftime("%Y-%m-%d")) == ["2024-01-15", "2024-03-31", "2023-12-31"]

    def test_dateadd_months_respects_the_calendar(self, dates):
        # 2024-03-31 + 1 month is 2024-04-30, not 2024-04-31 (which does not exist) and
        # not 2024-04-30 by accident of adding 30 days. This is the case that separates
        # DateOffset from timedelta arithmetic.
        moved = ev('DATEADD(d, 1, "month")', dates)
        assert list(moved.dt.strftime("%Y-%m-%d")) == ["2024-02-15", "2024-04-30", "2025-01-31"]

    def test_dateadd_days_and_weeks(self, dates):
        assert ev('DATEADD(d, 7, "day")', dates).iloc[0].strftime("%Y-%m-%d") == "2024-01-22"
        assert ev('DATEADD(d, 1, "week")', dates).iloc[0].strftime("%Y-%m-%d") == "2024-01-22"

    def test_dateadd_accepts_singular_and_plural_units(self, dates):
        assert ev('DATEADD(d, 1, "months")', dates).iloc[0] == ev('DATEADD(d, 1, "month")', dates).iloc[0]

    def test_dateadd_rejects_an_unknown_unit_rather_than_guessing(self, dates):
        with pytest.raises(ValueError):
            ev('DATEADD(d, 1, "fortnight")', dates)

    def test_datediff_counts_calendar_months_not_average_ones(self, dates):
        df = pd.DataFrame({
            "a": pd.to_datetime(["2024-01-31", "2024-01-01"]),
            "b": pd.to_datetime(["2024-02-01", "2025-01-01"]),
        })
        # One day apart, but a month boundary is crossed: calendar difference is 1.
        # A timedelta divided by 30 would say 0, which is the bug this guards.
        assert list(ev('DATEDIFF(a, b, "month")', df)) == [1, 12]
        assert list(ev('DATEDIFF(a, b, "year")', df)) == [0, 1]

    def test_datediff_days_and_seconds(self, dates):
        df = pd.DataFrame({
            "a": pd.to_datetime(["2024-01-01 00:00:00"]),
            "b": pd.to_datetime(["2024-01-03 01:00:00"]),
        })
        assert list(ev('DATEDIFF(a, b, "day")', df)) == [2]
        assert list(ev('DATEDIFF(a, b, "hour")', df)) == [49]

    def test_today_and_now_are_available_as_zero_argument_calls(self, dates):
        assert ev("TODAY()", dates).hour == 0          # normalised to midnight
        assert ev("NOW()", dates) >= ev("TODAY()", dates)


class TestDateNumberCoercion:
    def test_tonumber_and_todate_round_trip(self, dates):
        # The pair is the point: either alone could be self-consistently wrong.
        back = ev("TODATE(TONUMBER(d))", dates)
        assert list(back.dt.strftime("%Y-%m-%d")) == list(dates["d"].dt.strftime("%Y-%m-%d"))

    def test_tonumber_is_epoch_days(self, dates):
        assert ev("TONUMBER(d)", dates).iloc[0] == (pd.Timestamp("2024-01-15") - pd.Timestamp("1970-01-01")).days

    def test_unparseable_text_becomes_missing_not_an_exception(self):
        df = pd.DataFrame({"t": ["2024-01-15", "not a date"]})
        out = ev("TODATE(t)", df)
        assert out.notna().tolist() == [True, False]


class TestAdvancedStatistics:
    def test_percentile_is_zero_to_one_hundred_like_sas(self, nums):
        # pandas' quantile takes 0-1. Passing 50 there would return the maximum, so a
        # test that only checked "returns a number" would pass against the wrong scale.
        assert ev("PERCENTILE(a, 50)", nums) == 3.0
        assert ev("PERCENTILE(a, 0)", nums) == 1.0
        assert ev("PERCENTILE(a, 100)", nums) == 100.0

    def test_mode_returns_the_most_common_value(self, nums):
        assert ev("MODE(c)", nums) == 5.0

    def test_correlation_and_covariance(self, nums):
        assert ev("CORR(a, b)", nums) == pytest.approx(1.0)      # b is exactly 2a
        assert ev("COVAR(a, b)", nums) > 0

    def test_shape_statistics(self, nums):
        # `a` has one large outlier, so it is right-skewed and heavy-tailed.
        assert ev("SKEW(a)", nums) > 1
        assert ev("KURTOSIS(a)", nums) > 1

    def test_iqr_and_standard_error(self, nums):
        assert ev("IQR(a)", nums) == pytest.approx(nums["a"].quantile(0.75) - nums["a"].quantile(0.25))
        assert ev("SE(a)", nums) == pytest.approx(nums["a"].sem())


def test_the_new_names_are_reachable_through_the_sandbox_not_just_the_namespace(dates):
    """_validate_expr_safety runs before evaluation and forbids attribute access; a
    function added to the namespace but rejected by the validator would be unusable.
    This goes through the real entry point rather than eval'ing directly."""
    from app.services.widget_data import _eval_expr

    out = _eval_expr("MONTHNAME(d)", dates)
    assert list(out) == ["January", "March", "December"]


def test_every_function_the_palette_offers_actually_exists_in_the_engine():
    """The panel's palette once shipped `.str.upper()` and `.dt.year` snippets that the
    sandbox rejects outright -- buttons producing expressions that could never run.

    A structural guard on the frontend catches attribute access, but not a name that
    simply does not exist. This checks from the side that owns the truth: every
    UPPERCASE call in a palette snippet must be a real entry in the safe namespace.
    Adding a palette button for a function nobody implemented now fails here.
    """
    import re
    from pathlib import Path

    report = Path(__file__).resolve().parents[2] / "frontend/src/components/report"
    # The palette's function catalog moved out of the panel into its own module;
    # both are read so a snippet in either place is checked.
    files = [report / "calcColumns/catalog.ts", report / "CalcColumnsPanel.tsx"]
    if not files[0].exists():                   # backend-only checkouts
        pytest.skip("frontend source not present")

    source = "\n".join(f.read_text(encoding="utf-8") for f in files if f.exists())
    snippets = re.findall(r"snippet:\s*'([^']*)'", source)
    assert snippets, "found no palette snippets to check -- the regex has drifted"

    offered = {m for s in snippets for m in re.findall(r"\b([A-Z][A-Z0-9_]{1,})\s*\(", s)}
    assert offered, "found no function names in the palette"

    known, _ = _build_safe_ns(pd.DataFrame({"x": [1.0]}))
    missing = sorted(name for name in offered if name not in known)
    assert not missing, f"palette offers functions the engine does not have: {missing}"


class TestSasNamedStatistics:
    """The gap-analysis row named five SAS functions this language lacked: CoefVar,
    CSS, Kurtosis, Skewness, PvalT, First and Last. All but PvalT are now present --
    that one needs a t-distribution and so a scipy dependency, which is a larger
    decision than a function addition."""

    def test_coefvar_is_a_percentage(self, nums):
        assert ev("COEFVAR(a)", nums) == pytest.approx(nums["a"].std() / nums["a"].mean() * 100)

    def test_coefvar_returns_missing_rather_than_infinity_on_a_zero_mean(self):
        df = pd.DataFrame({"z": [-1.0, 0.0, 1.0]})       # mean is exactly zero
        assert pd.isna(ev("COEFVAR(z)", df))

    def test_corrected_sum_of_squares(self, nums):
        assert ev("CSS(a)", nums) == pytest.approx(((nums["a"] - nums["a"].mean()) ** 2).sum())

    def test_first_and_last_follow_row_order(self, nums):
        assert ev("FIRST(a)", nums) == 1.0
        assert ev("LAST(a)", nums) == 100.0


class TestPvalT:
    def test_pvalt_is_a_two_sided_one_sample_t_test(self, nums):
        from scipy import stats
        expected = stats.ttest_1samp(nums["a"], 0.0).pvalue
        assert ev("PVALT(a)", nums) == pytest.approx(float(expected))

    def test_pvalt_against_a_nonzero_mu(self, nums):
        # A sample centred exactly on mu should be maximally unsurprising.
        df = pd.DataFrame({"x": [9.0, 10.0, 11.0, 10.0]})
        assert ev("PVALT(x, 10)", df) > 0.9
        assert ev("PVALT(x, 0)", df) < 0.01

    def test_pvalt_needs_two_points(self):
        df = pd.DataFrame({"x": [1.0]})
        assert pd.isna(ev("PVALT(x)", df))
