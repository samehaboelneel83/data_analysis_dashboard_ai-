"""The aggregations SAS offers on a data item that this product did not.

SAS's aggregation menu runs to eighteen entries; ours stopped at fourteen and
the gap was entirely statistical: standard error, skewness, kurtosis,
coefficient of variation, the two sums of squares, and the one-sample t test.

They matter for the same reason the rest of this catalogue does. "Average sale
is 412" invites a decision; "average sale is 412 with a coefficient of variation
of 180%" stops it. Every one of these is a line of pandas, and their absence
meant an author who wanted one had to leave and compute it elsewhere.

Two properties they must share with the aggregations that already existed:

  * **The same answer whether or not the widget groups.** `_agg_series` powers
    a KPI (one number) and `_pandas_agg_fn` powers a bar (one per group); a
    statistic that disagrees between them is worse than one that is missing.

  * **A group too small to support the statistic gets nothing, not a lie.**
    Skewness of two points and a t statistic of one are not numbers, they are
    artefacts of the formula.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.widget_data import _agg_series, _pandas_agg_fn

SAMPLE = pd.Series([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])


class TestTheNewStatistics:
    def test_standard_error(self):
        assert _agg_series(SAMPLE, "stderr") == pytest.approx(float(SAMPLE.sem()), rel=1e-9)

    def test_skewness(self):
        assert _agg_series(SAMPLE, "skewness") == pytest.approx(float(SAMPLE.skew()), rel=1e-9)

    def test_kurtosis(self):
        assert _agg_series(SAMPLE, "kurtosis") == pytest.approx(float(SAMPLE.kurt()), rel=1e-9)

    def test_coefficient_of_variation_is_a_percentage(self):
        # SAS reports CV as a percentage, which is the only reading that makes
        # "180%" mean what people expect.
        expected = float(SAMPLE.std() / SAMPLE.mean() * 100)
        assert _agg_series(SAMPLE, "cv") == pytest.approx(expected, rel=1e-9)

    def test_uncorrected_sum_of_squares(self):
        assert _agg_series(SAMPLE, "uss") == pytest.approx(float((SAMPLE ** 2).sum()), rel=1e-9)

    def test_corrected_sum_of_squares(self):
        expected = float(((SAMPLE - SAMPLE.mean()) ** 2).sum())
        assert _agg_series(SAMPLE, "css") == pytest.approx(expected, rel=1e-9)

    def test_t_statistic_tests_the_mean_against_zero(self):
        expected = float(SAMPLE.mean() / SAMPLE.sem())
        assert _agg_series(SAMPLE, "tstat") == pytest.approx(expected, rel=1e-9)

    def test_p_value_belongs_to_that_t_statistic(self):
        from scipy import stats
        expected = float(stats.ttest_1samp(SAMPLE, 0.0).pvalue)
        assert _agg_series(SAMPLE, "pvalue") == pytest.approx(expected, rel=1e-9)

    def test_a_mean_of_zero_gives_a_p_value_of_one(self):
        # The sanity check on the pair: a sample centred on zero has no evidence
        # against "the mean is zero".
        centred = pd.Series([-2.0, -1.0, 0.0, 1.0, 2.0])
        assert _agg_series(centred, "pvalue") == pytest.approx(1.0, abs=1e-9)


class TestGroupedAndUngroupedAgree:
    """A KPI and a bar chart must not disagree about the same statistic."""

    @pytest.mark.parametrize("agg", ["stderr", "skewness", "kurtosis", "cv",
                                     "uss", "css", "tstat", "pvalue"])
    def test_one_group_matches_the_scalar(self, agg):
        df = pd.DataFrame({"g": ["a"] * len(SAMPLE), "v": SAMPLE.to_numpy()})
        grouped = df.groupby("g")["v"].agg(_pandas_agg_fn(agg))
        assert float(grouped.iloc[0]) == pytest.approx(_agg_series(SAMPLE, agg), rel=1e-9)


class TestTooSmallToMean_Anything:
    @pytest.mark.parametrize("agg,n", [("skewness", 2), ("kurtosis", 3), ("tstat", 1),
                                       ("pvalue", 1), ("stderr", 1)])
    def test_a_group_that_cannot_support_the_statistic_gets_nothing(self, agg, n):
        """Not a zero and not a NaN dressed as a number: skewness of two points
        and a t statistic of one are artefacts of the formula, and a dashboard
        that draws them is stating something the data cannot support."""
        tiny = pd.Series([3.0] * n)
        assert _agg_series(tiny, agg) is None

    def test_a_constant_column_has_no_coefficient_of_variation(self):
        # std is 0, mean is 5: CV is 0 and that is true. But a mean of ZERO
        # would divide by it, which is the case that has to be refused.
        assert _agg_series(pd.Series([5.0, 5.0, 5.0]), "cv") == pytest.approx(0.0)
        assert _agg_series(pd.Series([-1.0, 0.0, 1.0]), "cv") is None


class TestTheyAreOffered:
    def test_the_router_accepts_them_as_a_default_aggregation(self):
        from app.routers.datasets import _VALID_AGGREGATIONS
        for agg in ("stderr", "skewness", "kurtosis", "cv", "uss", "css", "tstat", "pvalue"):
            assert agg in _VALID_AGGREGATIONS, agg

    def test_nothing_previously_accepted_was_dropped(self):
        from app.routers.datasets import _VALID_AGGREGATIONS
        for agg in ("sum", "avg", "median", "count", "countd", "std", "min", "max"):
            assert agg in _VALID_AGGREGATIONS, agg
