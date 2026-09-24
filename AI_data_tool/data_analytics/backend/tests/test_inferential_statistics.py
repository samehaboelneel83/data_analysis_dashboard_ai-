"""Inferential statistics: is the difference real, or is it noise?

The eight analyses that preceded these are descriptive, forecasting, clustering
or anomaly detection -- every one can say THAT groups differ, none can say
whether the difference would survive another sample.

Two properties decide whether this feature helps or harms, and both are pinned
below:

  * EVERY test reports an effect size beside its p-value. With a two-million-row
    import cap, p alone is nearly content-free: at large n almost any difference
    is "significant". A feature that reported only p would be a machine for
    manufacturing confident trivia.

  * A test with too little data is REFUSED, not computed. A p-value from five
    rows is not a weak answer; it is a meaningless one, and a number is exactly
    what a reader will act on.

The tests use data with a KNOWN answer -- including negative controls, where the
right result is "not significant". A statistics module that only ever confirms
is worse than none.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis import inferential as I


@pytest.fixture
def frame():
    """B genuinely differs from A; C is drawn from A's distribution."""
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({
        "grp": np.repeat(["A", "B", "C"], n),
        "value": np.concatenate([
            rng.normal(100, 15, n),
            rng.normal(115, 15, n),
            rng.normal(100, 15, n),
        ]),
        "noise": rng.normal(0, 1, 3 * n),
    })
    df["driver"] = df["value"] * 0.8 + rng.normal(0, 5, 3 * n)
    df["region"] = rng.choice(["EMEA", "APAC"], 3 * n)
    return df


class TestCompareGroups:
    def test_it_finds_a_real_difference(self, frame):
        two = frame[frame.grp.isin(["A", "B"])]
        r = I.compare_groups(two, "value", "grp")
        assert r.significant
        assert r.detail["test"] == "Welch's t-test"

    def test_it_does_not_invent_one(self, frame):
        """NEGATIVE CONTROL. A and C are drawn from the same distribution, so a
        module that reported a difference here would be worse than useless."""
        ac = frame[frame.grp.isin(["A", "C"])]
        r = I.compare_groups(ac, "value", "grp")
        assert not r.significant

    def test_three_groups_use_anova(self, frame):
        r = I.compare_groups(frame, "value", "grp")
        assert r.detail["test"] == "One-way ANOVA"
        assert r.effect_name == "eta_squared"

    def test_welch_is_the_default_not_student(self, frame):
        """Student's t assumes equal variances, which business data rarely has;
        the wrong assumption produces an OVERCONFIDENT p. The caveat states the
        choice so a reader can check it."""
        two = frame[frame.grp.isin(["A", "B"])]
        r = I.compare_groups(two, "value", "grp")
        assert any("equal variances" in c for c in r.caveats)

    def test_it_reports_an_effect_size(self, frame):
        two = frame[frame.grp.isin(["A", "B"])]
        r = I.compare_groups(two, "value", "grp")
        assert r.effect_name == "cohens_d"
        assert r.effect_label in ("negligible", "small", "medium", "large")

    def test_too_few_rows_is_refused(self, frame):
        # A FIXED size, not one derived from the constant: reading
        # MIN_ROWS_PER_GROUP here would make the fixture shrink alongside any
        # lowering of it, so the test would keep passing while the guard was
        # being removed -- which is exactly what happened on the first attempt.
        rng = np.random.default_rng(11)
        thin = pd.DataFrame({
            "grp": ["A"] * 4 + ["B"] * 4,
            "value": rng.normal(100, 10, 8),
        })
        with pytest.raises(I.StatisticalError, match="at least two groups"):
            I.compare_groups(thin, "value", "grp")

    def test_one_group_is_refused_for_its_own_reason(self, frame):
        """Distinct from the floor: enough rows, but nothing to compare against."""
        single = frame[frame.grp == "A"]
        with pytest.raises(I.StatisticalError, match="at least two groups"):
            I.compare_groups(single, "value", "grp")

    def test_a_missing_column_names_itself(self, frame):
        # Both columns are checked -- an unchecked value column surfaces as a
        # raw pandas KeyError, which reaches the user as a 500.
        with pytest.raises(I.StatisticalError, match="nope"):
            I.compare_groups(frame, "nope", "grp")
        with pytest.raises(I.StatisticalError, match="nope"):
            I.compare_groups(frame, "value", "nope")

    def test_too_many_groups_is_refused(self):
        rng = np.random.default_rng(3)
        many = pd.DataFrame({
            "g": np.repeat([f"g{i}" for i in range(30)], 12),
            "v": rng.normal(0, 1, 360),
        })
        with pytest.raises(I.StatisticalError, match="too many"):
            I.compare_groups(many, "v", "g")


class TestIndependence:
    def test_independent_columns_are_not_flagged(self, frame):
        """NEGATIVE CONTROL: region is assigned at random, so it cannot be
        associated with grp."""
        r = I.test_independence(frame, "grp", "region")
        assert not r.significant

    def test_a_real_association_is_found(self):
        df = pd.DataFrame({
            "a": ["x"] * 200 + ["y"] * 200,
            "b": ["p"] * 180 + ["q"] * 20 + ["p"] * 20 + ["q"] * 180,
        })
        r = I.test_independence(df, "a", "b")
        assert r.significant
        assert r.effect_name == "cramers_v"

    def test_small_expected_counts_are_disclosed(self):
        """Chi-square's approximation degrades on sparse tables. Saying so beats
        emitting a confident number the reader cannot evaluate."""
        df = pd.DataFrame({
            "a": ["x"] * 10 + ["y"] * 3 + ["z"] * 2,
            "b": ["p", "q"] * 7 + ["p"],
        })
        r = I.test_independence(df, "a", "b")
        assert any("expected count" in c for c in r.caveats)

    def test_a_single_valued_column_is_refused(self, frame):
        flat = frame.assign(only="same")
        with pytest.raises(I.StatisticalError, match="two distinct values"):
            I.test_independence(flat, "only", "region")


class TestCorrelation:
    def test_a_strong_relationship_is_significant(self, frame):
        r = I.correlation_test(frame, "value", "driver")
        assert r.significant and r.effect_label == "large"

    def test_noise_is_not(self, frame):
        """NEGATIVE CONTROL."""
        r = I.correlation_test(frame, "value", "noise")
        assert not r.significant

    def test_spearman_is_available(self, frame):
        r = I.correlation_test(frame, "value", "driver", method="spearman")
        assert "Spearman" in r.detail["test"]

    def test_it_says_correlation_is_not_causation(self, frame):
        r = I.correlation_test(frame, "value", "driver")
        assert any("not causation" in c for c in r.caveats)

    def test_a_constant_column_is_refused(self, frame):
        with pytest.raises(I.StatisticalError, match="constant"):
            I.correlation_test(frame.assign(flat=1.0), "flat", "value")

    def test_an_unknown_method_is_refused(self, frame):
        with pytest.raises(I.StatisticalError, match="pearson"):
            I.correlation_test(frame, "value", "driver", method="kendall")


class TestRegression:
    def test_it_recovers_a_known_structure(self, frame):
        """value was built from driver plus noise, so driver must be
        significant and noise must not."""
        r = I.regression(frame, "value", ["driver", "noise"])
        by_term = {c["term"]: c for c in r.detail["coefficients"]}
        assert by_term["driver"]["significant"]
        assert not by_term["noise"]["significant"]
        assert r.detail["r_squared"] > 0.5

    def test_every_coefficient_carries_a_confidence_interval(self, frame):
        r = I.regression(frame, "value", ["driver"])
        for c in r.detail["coefficients"]:
            assert c["ci_low"] is not None and c["ci_high"] is not None
            assert c["ci_low"] <= c["coefficient"] <= c["ci_high"]

    def test_it_admits_its_assumptions(self, frame):
        r = I.regression(frame, "value", ["driver"])
        assert any("linear relationship" in c for c in r.caveats)
        assert any("not causation" in c for c in r.caveats)

    def test_no_predictors_is_refused(self, frame):
        with pytest.raises(I.StatisticalError, match="predictor"):
            I.regression(frame, "value", [])

    def test_too_few_rows_for_the_predictor_count_is_refused(self, frame):
        with pytest.raises(I.StatisticalError, match="need at least"):
            I.regression(frame.head(8), "value", ["driver", "noise"])


class TestTheEffectSizeRule:
    """The property that keeps this honest at scale."""

    def test_a_trivial_difference_at_huge_n_is_flagged_as_negligible(self):
        # 40,000 rows, means differing by 0.05 of a standard deviation: p will
        # be tiny and the finding worthless. The interpretation must say so
        # rather than leaving a reader with only the asterisk.
        rng = np.random.default_rng(7)
        n = 20_000
        df = pd.DataFrame({
            "g": np.repeat(["A", "B"], n),
            "v": np.concatenate([rng.normal(100, 20, n), rng.normal(101, 20, n)]),
        })
        r = I.compare_groups(df, "v", "g")
        assert r.significant, "sanity: at this n it should reach significance"
        assert r.effect_label in ("negligible", "small")
        assert "negligible" in r.interpretation or "small" in r.interpretation

    def test_every_result_carries_both_numbers(self, frame):
        for r in (
            I.compare_groups(frame, "value", "grp"),
            I.test_independence(frame, "grp", "region"),
            I.correlation_test(frame, "value", "driver"),
            I.regression(frame, "value", ["driver"]),
        ):
            d = r.to_dict()
            assert d["p_value"] is not None
            assert d["effect_size"] is not None and d["effect_name"]
            assert d["interpretation"]

    def test_a_non_significant_result_does_not_claim_proof(self, frame):
        """Absence of evidence is not evidence of absence, and the sentence
        must not imply otherwise."""
        ac = frame[frame.grp.isin(["A", "C"])]
        r = I.compare_groups(ac, "value", "grp")
        assert "does not prove" in r.interpretation


class TestInsightsSignificance:
    """The insights engine's six detectors were all descriptive: they could say
    a category carries 60% of revenue, never whether that split is
    distinguishable from an even one. These pin the helpers that decide it."""

    def test_a_strong_correlation_gets_a_small_p(self):
        from app.services.insights import _pearson_p
        rng = np.random.default_rng(1)
        x = pd.Series(rng.normal(0, 1, 500))
        y = pd.Series(x * 0.9 + rng.normal(0, 0.3, 500))
        assert _pearson_p(x, y) < 0.001

    def test_noise_does_not(self):
        from app.services.insights import _pearson_p
        rng = np.random.default_rng(1)
        a = pd.Series(rng.normal(0, 1, 60))
        b = pd.Series(rng.normal(0, 1, 60))
        assert _pearson_p(a, b) > 0.05

    def test_an_untestable_pair_reports_no_p_rather_than_a_wrong_one(self):
        from app.services.insights import _pearson_p
        rng = np.random.default_rng(1)
        b = pd.Series(rng.normal(0, 1, 30))
        assert _pearson_p(b.head(4), b.head(4)) is None      # too few rows
        assert _pearson_p(pd.Series([1.0] * 30), b) is None  # constant

    def test_a_skewed_split_is_significant_only_at_scale(self):
        """The same 90/5/5 shape: real with 1,000 observations, indistinguishable
        from chance with 12. This is the whole point of testing a 'standout'."""
        from app.services.insights import _uniformity_p
        assert _uniformity_p(pd.Series([900.0, 50.0, 50.0])) < 0.001
        assert _uniformity_p(pd.Series([6.0, 3.0, 3.0])) > 0.05

    def test_an_even_split_is_never_significant(self):
        from app.services.insights import _uniformity_p
        assert _uniformity_p(pd.Series([100.0, 100.0, 100.0])) == pytest.approx(1.0)

    def test_a_measure_that_goes_negative_is_not_treated_as_a_frequency(self):
        """Profit or variance can be negative; chi-square on such values is
        arithmetic dressed as inference, so it returns no p at all."""
        from app.services.insights import _uniformity_p
        # Sum well ABOVE MIN_ROWS_FOR_TEST, so the only thing that can return
        # None is the negativity check itself. The obvious fixture
        # ([-5, 10, 3]) sums to 8 and is caught by the row floor instead --
        # it passed even with the negativity guard deleted.
        assert _uniformity_p(pd.Series([-40.0, 500.0, 300.0])) is None
        # ... while the same magnitudes, all non-negative, ARE testable.
        assert _uniformity_p(pd.Series([40.0, 500.0, 300.0])) is not None

    def test_findings_carry_their_p_value(self):
        from app.services.insights import generate_insights
        rng = np.random.default_rng(0)
        n = 600
        df = pd.DataFrame({"cat": rng.choice(["A", "B", "C"], n, p=[.6, .25, .15]),
                           "x": rng.normal(100, 10, n)})
        df["revenue"] = np.where(df.cat == "A", 300, 60) + rng.normal(0, 10, n)
        tm = {"cat": "categorical", "x": "numeric", "revenue": "numeric"}
        out = generate_insights(df, tm, None)
        findings = out["findings"] if isinstance(out, dict) else out
        tested = [f for f in findings if f.get("p_value") is not None]
        assert tested, "no finding carried a p-value"
        assert all(f.get("significant") is not None for f in tested)


# ── Advanced models ──────────────────────────────────────────────────────────
# GLM, mixed models, survival and multiple-comparison correction. All four come
# from statsmodels, which was already in the image -- so, like the four tests
# above, this exposes capability already paid for rather than buying breadth.


@pytest.fixture
def churn_frame():
    """Churn driven by tenure; `noise` is unrelated by construction."""
    rng = np.random.default_rng(0)
    n = 800
    tenure = rng.normal(24, 8, n)
    logit = -0.15 * (tenure - 24)
    return pd.DataFrame({
        "tenure": tenure,
        "noise": rng.normal(0, 1, n),
        "churn": rng.binomial(1, 1 / (1 + np.exp(-logit))),
    })


class TestLogisticRegression:
    def test_it_finds_the_real_driver_and_not_the_noise(self, churn_frame):
        r = I.glm_logistic(churn_frame, "churn", ["tenure", "noise"])
        by = {c["term"]: c for c in r.detail["coefficients"]}
        assert by["tenure"]["significant"]
        assert not by["noise"]["significant"]

    def test_it_reports_odds_ratios_with_intervals(self, churn_frame):
        """A log-odds means nothing to the person asking the question; an odds
        ratio of 1.4 means '40% higher odds', which is actionable."""
        r = I.glm_logistic(churn_frame, "churn", ["tenure"])
        for c in r.detail["coefficients"]:
            assert c["odds_ratio"] is not None
            assert c["or_ci_low"] <= c["odds_ratio"] <= c["or_ci_high"]

    def test_the_fit_metric_is_named_as_pseudo(self, churn_frame):
        """A reader who takes McFadden's for an OLS R-squared badly underrates
        the model: 0.2 is a good fit here, not a poor one."""
        r = I.glm_logistic(churn_frame, "churn", ["tenure"])
        assert r.effect_name == "mcfadden_pseudo_r2"
        assert any("pseudo-R squared" in c or "pseudo-R" in c or "pseudo" in c
                   for c in r.caveats)

    def test_an_explicit_target_value_is_honoured(self, churn_frame):
        r = I.glm_logistic(churn_frame, "churn", ["tenure"], target_value="1")
        assert r.detail["positive_outcome"] == "1"

    def test_a_multi_valued_target_is_refused_without_a_choice(self, churn_frame):
        rng = np.random.default_rng(5)
        three = churn_frame.assign(churn=rng.integers(0, 3, len(churn_frame)))
        with pytest.raises(I.StatisticalError, match="binary outcome"):
            I.glm_logistic(three, "churn", ["tenure"])

    def test_too_few_events_is_refused(self, churn_frame):
        # A FIXED count, not one derived from the constant: a fixture that read
        # MIN_EVENTS_PER_PREDICTOR would shrink alongside any lowering of it and
        # keep passing while the guard was removed.
        rare = churn_frame.copy()
        rare["churn"] = 0
        rare.loc[rare.index[:3], "churn"] = 1
        with pytest.raises(I.StatisticalError, match="outcome"):
            I.glm_logistic(rare, "churn", ["tenure"])

    def test_perfect_separation_is_refused_not_reported(self, churn_frame):
        """statsmodels returns enormous coefficients with enormous standard
        errors rather than raising. Passing that through would be emitting
        garbage with a p-value attached."""
        sep = churn_frame.copy()
        sep["giveaway"] = sep["churn"] * 1.0
        with pytest.raises(I.StatisticalError):
            I.glm_logistic(sep, "churn", ["giveaway"])


class TestMixedModel:
    @pytest.fixture
    def panel(self):
        """Forty stores, twenty weeks each: 800 rows, nothing like 800
        independent observations."""
        rng = np.random.default_rng(0)
        week = np.tile(np.arange(20), 40)
        return pd.DataFrame({
            "store": np.repeat([f"s{i}" for i in range(40)], 20),
            "week": week,
            "sales": (100 + np.repeat(rng.normal(0, 10, 40), 20)
                      + 1.5 * week + rng.normal(0, 3, 800)),
        })

    def test_it_recovers_the_true_slope(self, panel):
        r = I.mixed_model(panel, "sales", ["week"], "store")
        by = {c["term"]: c for c in r.detail["coefficients"]}
        assert by["week"]["coefficient"] == pytest.approx(1.5, abs=0.15)
        assert by["week"]["significant"]

    def test_the_icc_shows_the_grouping_matters(self, panel):
        """The question the model exists to answer: how much of the variation is
        between groups rather than within them?"""
        r = I.mixed_model(panel, "sales", ["week"], "store")
        assert r.effect_name == "icc"
        assert r.effect_size > 0.5, "between-store variance dominates by construction"

    def test_it_says_why_ordinary_regression_would_mislead(self, panel):
        r = I.mixed_model(panel, "sales", ["week"], "store")
        assert "independent" in r.interpretation

    def test_too_few_groups_is_refused(self, panel):
        two = panel[panel.store.isin(["s0", "s1"])]
        with pytest.raises(I.StatisticalError, match="at least 3"):
            I.mixed_model(two, "sales", ["week"], "store")

    def test_one_row_per_group_is_refused(self):
        """No repeated measurements means nothing to model -- ordinary
        regression is the right tool, and saying so is more useful than a
        degenerate fit."""
        rng = np.random.default_rng(2)
        flat = pd.DataFrame({"g": [f"g{i}" for i in range(30)],
                             "x": rng.normal(0, 1, 30),
                             "y": rng.normal(0, 1, 30)})
        with pytest.raises(I.StatisticalError, match="repeated measurements"):
            I.mixed_model(flat, "y", ["x"], "g")

    def test_random_intercepts_only_is_disclosed(self, panel):
        r = I.mixed_model(panel, "sales", ["week"], "store")
        assert any("Random intercepts only" in c for c in r.caveats)


class TestSurvival:
    @pytest.fixture
    def lifetimes(self):
        """Right-censored durations: risk raises the hazard by a known amount."""
        rng = np.random.default_rng(0)
        n = 800
        risk = rng.normal(0, 1, n)
        dur = rng.exponential(np.exp(-0.8 * risk))
        cens = rng.exponential(2.0, n)
        return pd.DataFrame({
            "risk": risk,
            "months": np.minimum(dur, cens),
            "churned": (dur <= cens).astype(int),
        })

    def test_it_recovers_the_true_hazard_ratio(self, lifetimes):
        r = I.survival(lifetimes, "months", "churned", ["risk"])
        c = r.detail["coefficients"][0]
        # True coefficient 0.8 -> hazard ratio e^0.8 = 2.23.
        assert c["hazard_ratio"] == pytest.approx(2.23, abs=0.25)
        assert c["hr_ci_low"] <= c["hazard_ratio"] <= c["hr_ci_high"]

    def test_censored_rows_are_used_not_discarded(self, lifetimes):
        """The whole point of survival analysis. A customer who has not churned
        yet is information about 'at least this long'."""
        r = I.survival(lifetimes, "months", "churned", ["risk"])
        assert r.detail["censored"] > 0
        assert r.n == r.detail["events"] + r.detail["censored"]
        assert any("censored" in c for c in r.caveats)

    def test_all_censored_is_refused(self, lifetimes):
        with pytest.raises(I.StatisticalError, match="No events"):
            I.survival(lifetimes.assign(churned=0), "months", "churned", ["risk"])

    def test_too_few_events_is_refused(self, lifetimes):
        # Fixed count again, for the reason stated in the logistic tests.
        few = lifetimes.copy()
        few["churned"] = 0
        few.loc[few.index[:4], "churned"] = 1
        with pytest.raises(I.StatisticalError, match="event"):
            I.survival(few, "months", "churned", ["risk"])

    def test_a_non_positive_duration_is_refused(self, lifetimes):
        with pytest.raises(I.StatisticalError, match="positive"):
            I.survival(lifetimes.assign(months=-1.0), "months", "churned", ["risk"])

    def test_a_non_binary_event_column_is_refused(self, lifetimes):
        with pytest.raises(I.StatisticalError, match="censored"):
            I.survival(lifetimes.assign(churned=2), "months", "churned", ["risk"])

    def test_the_proportional_hazards_assumption_is_disclosed(self, lifetimes):
        r = I.survival(lifetimes, "months", "churned", ["risk"])
        assert any("proportional hazards" in c for c in r.caveats)


class TestMultipleComparisons:
    def test_correction_removes_findings_from_pure_noise(self):
        """THE point. Twenty independent tests of noise produce about one
        'significant' result at alpha=0.05, and a dashboard scanning six
        measures against six categories runs far more than twenty."""
        rng = np.random.default_rng(0)
        from scipy import stats
        ps = []
        for _ in range(20):
            a, b = rng.normal(0, 1, 60), rng.normal(0, 1, 60)
            ps.append(float(stats.ttest_ind(a, b, equal_var=False).pvalue))
        naive = sum(1 for p in ps if p < 0.05)
        corrected = I.correct_p_values(ps)
        assert naive >= 1, "sanity: noise should produce a false finding or two"
        assert sum(corrected["rejected"]) < naive

    def test_a_real_effect_survives_correction(self):
        """A correction that suppressed everything would be useless."""
        rng = np.random.default_rng(1)
        from scipy import stats
        ps = [float(stats.ttest_ind(rng.normal(0, 1, 80),
                                    rng.normal(1.2, 1, 80), equal_var=False).pvalue)]
        ps += [float(stats.ttest_ind(rng.normal(0, 1, 60),
                                     rng.normal(0, 1, 60), equal_var=False).pvalue)
               for _ in range(19)]
        assert I.correct_p_values(ps)["rejected"][0]

    def test_it_handles_missing_p_values(self):
        out = I.correct_p_values([0.01, None, 0.9])
        assert out["n_tests"] == 2
        assert out["adjusted"][1] is None and out["rejected"][1] is False

    def test_bonferroni_is_stricter_than_bh(self):
        ps = [0.01, 0.02, 0.03, 0.04, 0.045]
        bh = sum(I.correct_p_values(ps, method="fdr_bh")["rejected"])
        bon = sum(I.correct_p_values(ps, method="bonferroni")["rejected"])
        assert bon <= bh


class TestPairwiseComparisons:
    @pytest.fixture
    def four_groups(self):
        """Only D genuinely differs; A, B and C share a distribution."""
        rng = np.random.default_rng(0)
        return pd.DataFrame({
            "grp": np.repeat(["A", "B", "C", "D"], 150),
            "val": np.concatenate([rng.normal(100, 15, 150),
                                   rng.normal(100, 15, 150),
                                   rng.normal(100, 15, 150),
                                   rng.normal(118, 15, 150)]),
        })

    def test_it_finds_exactly_the_pairs_that_differ(self, four_groups):
        r = I.pairwise_comparisons(four_groups, "val", "grp")
        sig = {tuple(sorted((p["group_a"], p["group_b"])))
               for p in r.detail["pairs"] if p["significant"]}
        assert sig == {("A", "D"), ("B", "D"), ("C", "D")}

    def test_every_pair_carries_an_adjusted_p(self, four_groups):
        r = I.pairwise_comparisons(four_groups, "val", "grp")
        for p in r.detail["pairs"]:
            assert p["p_adjusted"] is not None
            # Adjustment can only make a p-value larger or leave it alone.
            assert p["p_adjusted"] >= p["p_raw"] - 1e-9

    def test_welch_not_tukey(self, four_groups):
        """Tukey's HSD assumes equal variances -- the exact assumption
        compare_groups refuses to make. Using it here would have the platform
        contradicting itself between two adjacent screens."""
        r = I.pairwise_comparisons(four_groups, "val", "grp")
        assert any("Tukey" in c for c in r.caveats)

    def test_it_reports_how_many_the_correction_removed(self):
        """When naive counting would have found more, say so -- otherwise the
        reader cannot tell that a correction happened at all."""
        rng = np.random.default_rng(3)
        noise = pd.DataFrame({
            "grp": np.repeat([f"g{i}" for i in range(6)], 40),
            "val": rng.normal(100, 15, 240),
        })
        r = I.pairwise_comparisons(noise, "val", "grp")
        naive = sum(1 for p in r.detail["pairs"] if (p["p_raw"] or 1) < 0.05)
        if naive > r.detail["significant_pairs"]:
            assert any("without the correction" in c for c in r.caveats)

    def test_too_many_groups_is_refused(self):
        rng = np.random.default_rng(4)
        many = pd.DataFrame({
            "g": np.repeat([f"g{i}" for i in range(30)], 12),
            "v": rng.normal(0, 1, 360),
        })
        with pytest.raises(I.StatisticalError, match="comparisons"):
            I.pairwise_comparisons(many, "v", "g")


class TestInsightsCorrectsItsOwnFamily:
    """The insights engine runs a standout test per (category x measure) and a
    correlation test per measure-pair -- easily twenty tests on one dataset,
    where roughly one reaches p<0.05 by chance. Shipping it without correction
    would have been the exact failure these tests exist to warn about."""

    def _scan(self, df):
        from app.services.insights import generate_insights
        tm = {c: ("numeric" if pd.api.types.is_numeric_dtype(df[c])
                  else "categorical") for c in df.columns}
        out = generate_insights(df, tm, None)
        return out["findings"] if isinstance(out, dict) else out

    def test_pure_noise_yields_no_significant_findings(self):
        rng = np.random.default_rng(7)
        n = 400
        noise = pd.DataFrame({f"m{i}": rng.normal(100, 20, n) for i in range(6)})
        for j in range(3):
            noise[f"c{j}"] = rng.choice(list("XYZ"), n)
        sig = [f for f in self._scan(noise) if f.get("significant")]
        assert not sig, f"claimed {len(sig)} significant findings from random data"

    def test_real_patterns_survive_the_correction(self):
        """A correction that suppressed everything would be useless."""
        rng = np.random.default_rng(7)
        n = 400
        real = pd.DataFrame({f"m{i}": rng.normal(100, 20, n) for i in range(4)})
        real["cat"] = rng.choice(["A", "B", "C"], n, p=[0.7, 0.2, 0.1])
        real["paired"] = real["m0"] * 0.95 + rng.normal(0, 3, n)
        sig = [f for f in self._scan(real) if f.get("significant")]
        assert sig, "correction suppressed genuine findings"

    def test_tested_findings_carry_an_adjusted_p(self):
        """The first version of this silently did nothing -- a relative import
        one level too deep, swallowed by a broad except. The adjusted value is
        the only observable proof the correction actually ran."""
        rng = np.random.default_rng(7)
        n = 400
        real = pd.DataFrame({f"m{i}": rng.normal(100, 20, n) for i in range(4)})
        real["cat"] = rng.choice(["A", "B", "C"], n, p=[0.7, 0.2, 0.1])
        real["paired"] = real["m0"] * 0.95 + rng.normal(0, 3, n)
        tested = [f for f in self._scan(real) if f.get("p_value") is not None]
        assert tested
        assert all("p_adjusted" in f for f in tested)

    def test_a_demoted_finding_is_kept_and_explained(self):
        from app.services.insights import _apply_multiple_comparison_correction
        # A few borderline findings among MANY nulls. The obvious fixture --
        # 30 findings all tied at 0.045 -- does not demote anything, and that
        # is BH behaving correctly rather than a bug: at rank 31 the threshold
        # is (31/31)*0.05 = 0.05, so 0.045 clears it. Benjamini-Hochberg
        # controls the false-discovery RATE, so a large block of consistently
        # borderline results is collectively credible. Demotion needs the
        # borderline few to be outnumbered by clear nulls.
        findings = [{"p_value": 0.04, "score": 0.9, "significant": True, "detail": "b"}
                    for _ in range(5)]
        findings += [{"p_value": 0.9, "score": 0.2, "significant": False, "detail": "n"}
                     for _ in range(60)]
        _apply_multiple_comparison_correction(findings)
        demoted = [f for f in findings if f["detail"].startswith("b")
                   and not f["significant"]]
        assert demoted, "borderline findings among 60 nulls should be demoted"
        # Kept, not deleted: the pattern is real in these rows, just not
        # evidence beyond them -- and the text must say which.
        assert len(findings) == 65
        assert all("no longer significant" in f["detail"] for f in demoted)

    def test_a_single_test_is_not_corrected(self):
        """One test is not a family; inflating its p-value would be wrong."""
        from app.services.insights import _apply_multiple_comparison_correction
        one = [{"p_value": 0.04, "score": 1.0, "significant": True, "detail": "x"}]
        _apply_multiple_comparison_correction(one)
        assert one[0]["significant"]
