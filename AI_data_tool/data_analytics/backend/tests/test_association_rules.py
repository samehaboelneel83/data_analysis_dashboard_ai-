"""Association rules: which values travel together.

The one gap no existing analysis approached -- correlation needs two numeric
columns, key influencers needs a chosen outcome, and neither can say that
particular values co-occur.

Two properties decide whether the output is worth reading, and each is pinned
below.

**Lift, not confidence.** A rule can be 90% confident and worthless: if the
conclusion holds in 90% of rows anyway, "A implies B, 90% confident" says
nothing about A. Ranking by confidence would put exactly those rules on top.

**Redundancy suppressed.** Adding an independent column nudges lift by chance,
so a wordier restatement of a finding can outrank the finding. Left in, one
real pattern fills the list and buries everything else.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.patterns import (MIN_LIFT, MIN_SUPPORT_COUNT,
                                            PatternError, _dependent_pairs,
                                            association_rules)


@pytest.fixture
def planted():
    """Premium buyers overwhelmingly choose express; `region` is independent
    noise, present so the redundancy tests have something to be tempted by."""
    rng = np.random.default_rng(0)
    n = 600
    tier = rng.choice(["basic", "premium"], n, p=[0.6, 0.4])
    ship = [("express" if rng.random() < 0.9 else "standard") if t == "premium"
            else ("express" if rng.random() < 0.2 else "standard") for t in tier]
    return pd.DataFrame({"tier": tier, "shipping": ship,
                         "region": rng.choice(["N", "S", "E", "W"], n)})


def _rule(rows, if_, then):
    for r in rows:
        if r["if"] == if_ and r["then"] == then:
            return r
    return None


class TestItFindsThePlantedRule:
    def test_the_real_association_is_reported(self, planted):
        out = association_rules(planted)
        hit = _rule(out.rows, "tier=premium", "shipping=express")
        assert hit is not None, [r["if"] + " -> " + r["then"] for r in out.rows]
        assert hit["lift"] > 1.5

    def test_confidence_is_reported_beside_the_base_rate(self, planted):
        """THE honesty property. Confidence alone is unreadable: it must be
        shown against how often the conclusion holds anyway."""
        out = association_rules(planted)
        hit = _rule(out.rows, "tier=premium", "shipping=express")
        assert hit["confidence"] > hit["base_rate"]
        assert 0 < hit["base_rate"] < 1

    def test_every_rule_carries_its_supporting_row_count(self, planted):
        out = association_rules(planted)
        assert out.rows
        for r in out.rows:
            assert r["support_rows"] >= MIN_SUPPORT_COUNT

    def test_no_rule_below_the_lift_floor(self, planted):
        # A rule at lift 1.0 is the definition of no pattern.
        out = association_rules(planted)
        assert all(r["lift"] >= MIN_LIFT for r in out.rows)


class TestRedundancyIsSuppressed:
    """The defect that made the first version unusable: 25 rules, of which the
    top six were all restatements of one finding with an independent column
    attached."""

    def test_a_wordier_restatement_does_not_survive(self, planted):
        out = association_rules(planted)
        simple = _rule(out.rows, "tier=premium", "shipping=express")
        assert simple is not None
        # Nothing may both contain that rule and add only noise.
        for r in out.rows:
            if r is simple:
                continue
            ante = set(r["if"].split(", "))
            cons = set(r["then"].split(", "))
            contains = ({"tier=premium"} <= ante and {"shipping=express"} <= cons)
            if contains:
                assert r["lift"] > simple["lift"] * 1.1, (
                    f"{r['if']} -> {r['then']} restates the simple rule "
                    f"without beating it")

    def test_the_list_stays_short_enough_to_read(self, planted):
        out = association_rules(planted)
        assert len(out.rows) <= 12, (
            f"{len(out.rows)} rules; the list has filled with variations")

    def test_both_sides_are_checked(self, planted):
        """Suppressing only wordier antecedents still left
        `tier=premium -> region=N, shipping=express` -- the same finding with
        an independent column bolted onto the CONCLUSION."""
        out = association_rules(planted)
        for r in out.rows:
            cons = set(r["then"].split(", "))
            if {"shipping=express"} < cons:      # strict superset
                simple = _rule(out.rows, r["if"], "shipping=express")
                if simple:
                    assert r["lift"] > simple["lift"] * 1.1


class TestItRefusesRatherThanGuesses:
    def test_too_few_rows_is_named(self):
        df = pd.DataFrame({"a": ["x", "y"] * 5, "b": ["p", "q"] * 5})
        with pytest.raises(PatternError, match="rows"):
            association_rules(df)

    def test_a_single_categorical_column_cannot_form_rules(self):
        df = pd.DataFrame({"a": ["x", "y"] * 50, "n": range(100)})
        with pytest.raises(PatternError, match="two categorical"):
            association_rules(df)

    def test_a_missing_column_is_named(self, planted):
        with pytest.raises(PatternError, match="nope"):
            association_rules(planted, ["nope", "tier"])

    def test_independent_columns_yield_no_strong_rules(self):
        """The other direction: an engine that always finds something is
        finding nothing."""
        rng = np.random.default_rng(1)
        n = 800
        df = pd.DataFrame({"a": rng.choice(list("xyz"), n),
                           "b": rng.choice(list("pqr"), n)})
        out = association_rules(df)
        assert all(r["lift"] < 1.5 for r in out.rows), [
            (r["if"], r["then"], r["lift"]) for r in out.rows]


class TestTheContract:
    def test_it_says_this_is_not_causation(self, planted):
        # The caveat travels with the payload rather than living in docs: a
        # reader acting on "A implies B" without it is misled.
        out = association_rules(planted)
        assert any("not cause" in w or "causes" in w for w in out.warnings)

    def test_the_shape_matches_the_analysis_contract(self, planted):
        out = association_rules(planted)
        payload = out.to_dict()
        assert payload["kind"] == "association_rules"
        assert {c["name"] for c in payload["columns"]} >= {
            "if", "then", "lift", "confidence", "base_rate", "support_rows"}

    def test_a_sample_says_so(self):
        """A rule mined on a sample must not report as though it saw
        everything."""
        from app.services.analysis import patterns
        rng = np.random.default_rng(2)
        n = patterns.FRAME_SAMPLE_THRESHOLD + 100
        df = pd.DataFrame({"a": rng.choice(list("xy"), n),
                           "b": rng.choice(list("pq"), n)})
        out = association_rules(df)
        assert out.meta["sampled"] is True
        assert any("sample" in w for w in out.warnings)


class TestItIsRegistered:
    def test_the_catalogue_lists_it(self):
        """Registering also makes it visible to the agent's prompt block, so a
        missing entry means the model never knows the capability exists."""
        from app.services.analysis.registry import all_analyses
        assert "association_rules" in {s.name for s in all_analyses()}


@pytest.fixture
def with_hierarchy():
    """The same planted rule, plus a country/region hierarchy beside it.

    This is what real data looks like, and it is what broke the first working
    version: mining the demo sales dataset returned 25 rules of which 25 were
    country/region restatements.
    """
    rng = np.random.default_rng(0)
    n = 800
    country = rng.choice(["Australia", "Japan", "France", "Spain"], n)
    region = ["Asia Pacific" if c in ("Australia", "Japan") else "Europe"
              for c in country]
    tier = rng.choice(["basic", "premium"], n, p=[0.6, 0.4])
    ship = [("express" if rng.random() < 0.9 else "standard") if t == "premium"
            else ("express" if rng.random() < 0.2 else "standard") for t in tier]
    return pd.DataFrame({"country": country, "region": region,
                         "tier": tier, "shipping": ship})


class TestSchemaStructureIsNotAFinding:
    """A column that DETERMINES another is a hierarchy, a lookup or a derived
    column. Rules between such a pair are true, unavoidable and worthless --
    and there are so many of them that they take every slot."""

    def test_a_determining_pair_is_detected(self, with_hierarchy):
        pairs = _dependent_pairs(with_hierarchy, list(with_hierarchy.columns))
        assert frozenset(("country", "region")) in pairs

    def test_independent_columns_are_not_flagged(self, with_hierarchy):
        """The other direction: flagging everything would suppress the real
        findings along with the hierarchy."""
        pairs = _dependent_pairs(with_hierarchy, list(with_hierarchy.columns))
        assert frozenset(("tier", "shipping")) not in pairs

    def test_no_rule_pairs_the_hierarchy_columns(self, with_hierarchy):
        # THE test. Not merely "fewer hierarchy rules" -- none at all, on
        # either side, including inside a compound conclusion. A per-rule
        # confidence filter let `country=Australia -> region=Asia Pacific,
        # shipping=standard` through, which is the same non-finding with a
        # real column bolted on.
        out = association_rules(with_hierarchy)
        for r in out.rows:
            both = r["if"] + ", " + r["then"]
            assert not ("country=" in both and "region=" in both), (
                f"{r['if']} -> {r['then']} restates the schema")

    def test_the_real_pattern_survives_the_suppression(self, with_hierarchy):
        """Suppression that also removed the finding would be worse than the
        clutter it fixes."""
        out = association_rules(with_hierarchy)
        assert _rule(out.rows, "tier=premium", "shipping=express") is not None

    def test_the_hierarchy_no_longer_crowds_out_everything(self, with_hierarchy):
        out = association_rules(with_hierarchy)
        assert 0 < len(out.rows) <= 8, (
            f"{len(out.rows)} rules; the list should be the real findings only")

