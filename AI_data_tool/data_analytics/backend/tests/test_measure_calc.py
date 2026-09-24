"""CALC: filter-context manipulation in the measure engine.

This is the capability the audit named as the modelling gap. Its exact words
were "no CALCULATE-equivalent **filter-context manipulation**" -- not "no
language" -- and that is what CALC closes: evaluate an aggregate under a
different row filter than the visual's, then compare the two.

The filter reuses the SAME grammar `apply_filter_expr` and every row-security
rule already speak. That is the design, not a convenience: the grammar is
already safety-validated, already familiar to anyone who has written a filter,
and already translatable to SQL by `sql_expr` for DirectQuery pushdown.

Two properties decide whether CALC tells the truth, and both are pinned below:
the ALIGNMENT rule (when a filtered value is per-group versus a fixed base), and
the fact that a broken filter RAISES instead of silently returning an
unrestricted number dressed up as a filtered one.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.measure_eval import evaluate_measure

EMEA = "`region` == 'EMEA'"


def frame():
    return pd.DataFrame({
        "region": ["EMEA", "EMEA", "APAC", "APAC", "AMER"],
        "segment": ["Ent", "SMB", "Ent", "SMB", "Ent"],
        "revenue": [100.0, 200.0, 50.0, 50.0, 300.0],
    })


class TestItFiltersTheContext:
    def test_it_narrows_to_the_filtered_rows(self):
        assert evaluate_measure(f'CALC(SUM(revenue), "{EMEA}")', frame(), []) == 300.0

    def test_the_unfiltered_total_is_unchanged(self):
        """CALC must not leak its filter into the surrounding expression."""
        df = frame()
        assert evaluate_measure("SUM(revenue)", df, []) == 700.0
        evaluate_measure(f'CALC(SUM(revenue), "{EMEA}")', df, [])
        assert evaluate_measure("SUM(revenue)", df, []) == 700.0

    def test_a_ratio_against_a_filtered_base(self):
        """The reason CALCULATE exists: compare a slice to a chosen context."""
        r = evaluate_measure(f'SUM(revenue) / CALC(SUM(revenue), "{EMEA}")', frame(), [])
        assert r == pytest.approx(700.0 / 300.0)


class TestTheAlignmentRule:
    """The semantic question, and the one an obvious implementation gets wrong."""

    def test_a_filter_on_a_grouping_column_is_per_group(self):
        # Grouped BY region and filtered ON region: the other groups are
        # genuinely outside the context. NaN, not 0 -- 0 would assert "this
        # group had none", a different and false claim.
        r = evaluate_measure(f'CALC(SUM(revenue), "{EMEA}")', frame(), ["region"])
        assert r["EMEA"] == 300.0
        assert np.isnan(r["APAC"]) and np.isnan(r["AMER"])

    def test_a_filter_off_the_grain_broadcasts_as_a_fixed_base(self):
        # Grouped by region, filtered on segment: the filtered context does not
        # vary by region, so it is a fixed comparison base. Reindexing here (the
        # obvious implementation) would give NaN for every region but one and
        # make the comparison unanswerable.
        r = evaluate_measure('CALC(SUM(revenue), "`segment` == \'Ent\'")',
                             frame(), ["region"])
        assert set(r.index) == {"EMEA", "APAC", "AMER"}
        assert (r == 450.0).all(), "the base must broadcast, not reindex to NaN"

    def test_the_broadcast_base_makes_ratios_meaningful(self):
        r = evaluate_measure(
            'SUM(revenue) / CALC(SUM(revenue), "`segment` == \'Ent\'")',
            frame(), ["region"])
        assert r["EMEA"] == pytest.approx(300.0 / 450.0)
        assert r["APAC"] == pytest.approx(100.0 / 450.0)

    def test_a_filter_matching_nothing_yields_nan_everywhere(self):
        r = evaluate_measure('CALC(SUM(revenue), "`region` == \'NOWHERE\'")',
                             frame(), ["region"])
        assert r.isna().all()


class TestItRefusesRatherThanGuessing:
    def test_a_broken_filter_raises_instead_of_returning_the_unfiltered_total(self):
        """THE safety property. `apply_filter_expr` defaults to silent=True,
        which returns the frame UNFILTERED on error -- here that would compute an
        unrestricted total and present it as a filtered one. Silently wrong beats
        nothing only if you never notice; this must raise."""
        # The exception TYPE is not the contract -- an unknown column surfaces
        # as NameError, malformed syntax as SyntaxError. What matters is that
        # something is raised rather than 700.0 being returned as though it had
        # been filtered.
        with pytest.raises(Exception):
            evaluate_measure('CALC(SUM(revenue), "nosuchcol == 1")', frame(), [])

    def test_a_filter_must_be_a_quoted_string(self):
        with pytest.raises(Exception):
            evaluate_measure("CALC(SUM(revenue), `region`)", frame(), [])

    def test_it_needs_both_arguments(self):
        with pytest.raises(ValueError):
            evaluate_measure("CALC(SUM(revenue))", frame(), [])

    def test_context_functions_do_not_nest(self):
        """Each has its own grain; composing them needs a nested group-then-
        regroup this engine deliberately does not model."""
        with pytest.raises(ValueError, match="cannot contain another"):
            evaluate_measure(f'TOTAL(CALC(SUM(revenue), "{EMEA}"))', frame(), [])
        with pytest.raises(ValueError, match="cannot contain another"):
            evaluate_measure(f'CALC(TOTAL(SUM(revenue)), "{EMEA}")', frame(), [])

    def test_the_sandbox_still_applies_inside_a_filter(self):
        """A filter argument must not become a hole in the expression sandbox."""
        with pytest.raises(Exception):
            evaluate_measure('CALC(SUM(revenue), "SUM.__globals__")', frame(), [])


class TestItComposesWithWhatExists:
    def test_calc_alongside_total(self):
        """Side by side is fine -- only NESTING is refused."""
        r = evaluate_measure(
            f'CALC(SUM(revenue), "{EMEA}") / TOTAL(SUM(revenue))', frame(), ["region"])
        assert r["EMEA"] == pytest.approx(300.0 / 700.0)

    def test_several_calcs_in_one_expression(self):
        r = evaluate_measure(
            'CALC(SUM(revenue), "`segment` == \'Ent\'") '
            '- CALC(SUM(revenue), "`segment` == \'SMB\'")',
            frame(), [])
        assert r == pytest.approx(450.0 - 250.0)
