"""A decision tree: the rules that separate one outcome from another.

SAS Visual Statistics' headline object, and the one analysis in this catalogue
that answers "why" with something a non-statistician can read out loud: *if
margin is below 12% and the channel is Wholesale, three quarters of these
churn*. Correlations and effect sizes describe; a tree gives you the branch.

scikit-learn is already a dependency (`segment.py` uses it) and is imported
LAZILY here for the same reason — a heavy BLAS/model-selection import must not
land on the app-import path.

Three decisions carry most of the honesty:

  * **Scored on rows it never saw.** A tree deep enough will reproduce its
    training data perfectly, so a tree reporting its training accuracy is
    reporting nothing. The score here is held out, and the training score comes
    back beside it precisely so the gap between them is visible.

  * **Shallow by default and capped.** A depth-20 tree is not an explanation of
    anything; it is the data written out longhand. Four levels is what a person
    can actually read, and the cap means an author cannot accidentally ask for
    the longhand version.

  * **Columns it cannot use are named, not dropped silently.** A high-cardinality
    identifier is not a predictor, and a reader who is not told it was skipped
    will assume it was considered and found unimportant — the opposite of the
    truth.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.decision_tree import DecisionTreeError, decision_tree


@pytest.fixture
def churn():
    """A rule the tree must be able to find: low margin churns, high margin does
    not, with a little noise so it is not a trivial lookup."""
    rng = np.random.default_rng(0)
    n = 400
    margin = rng.uniform(0, 40, n)
    noise = rng.uniform(0, 1, n)
    return pd.DataFrame({
        "margin_pct": margin,
        "region": rng.choice(["North", "South", "East", "West"], n),
        "spend": rng.uniform(100, 900, n),
        "churned": np.where((margin < 12) & (noise < 0.9), "yes", "no"),
    })


@pytest.fixture
def numeric_outcome():
    rng = np.random.default_rng(1)
    n = 300
    units = rng.uniform(1, 100, n)
    return pd.DataFrame({
        "units": units,
        "channel": rng.choice(["Retail", "Wholesale"], n),
        "revenue": units * 12 + rng.normal(0, 5, n),
    })


class TestItFindsTheRule:
    def test_a_categorical_outcome_is_a_classification(self, churn):
        got = decision_tree(churn, target="churned")
        assert got["task"] == "classification"

    def test_it_splits_on_the_column_that_actually_decides(self, churn):
        got = decision_tree(churn, target="churned")
        assert got["importance"][0]["column"] == "margin_pct"

    def test_the_root_split_is_near_the_real_boundary(self, churn):
        # The rule is margin < 12. A tree that splits at 3 or at 30 has not
        # found it, and "it split on the right column" would not catch that.
        got = decision_tree(churn, target="churned")
        assert 8 <= got["tree"]["threshold"] <= 16

    def test_a_numeric_outcome_is_a_regression(self, numeric_outcome):
        got = decision_tree(numeric_outcome, target="revenue")
        assert got["task"] == "regression"
        assert got["importance"][0]["column"] == "units"


class TestItIsScoredOnRowsItNeverSaw:
    def test_the_score_is_held_out(self, churn):
        got = decision_tree(churn, target="churned")
        assert 0.0 <= got["score"] <= 1.0
        assert got["n_test"] > 0
        assert got["n_train"] > got["n_test"]

    def test_the_training_score_is_reported_beside_it(self, churn):
        """So the gap between them is visible. A tree that scores 1.00 on its
        training rows and 0.6 on held-out rows has memorised, and hiding the
        first number hides that."""
        got = decision_tree(churn, target="churned")
        assert "train_score" in got
        assert got["train_score"] is not None

    def test_the_scores_name_what_they_measure(self, churn, numeric_outcome):
        assert decision_tree(churn, target="churned")["score_name"] == "accuracy"
        assert decision_tree(numeric_outcome, target="revenue")["score_name"] == "r2"

    def test_it_is_reproducible(self, churn):
        # Seeded, like every other stochastic analysis here: two runs on one
        # frame that disagree are two answers presented as one fact.
        first = decision_tree(churn, target="churned")
        second = decision_tree(churn, target="churned")
        assert first["tree"] == second["tree"]
        assert first["score"] == second["score"]


class TestTheTreeIsReadable:
    def test_it_is_shallow_by_default(self, churn):
        got = decision_tree(churn, target="churned")
        assert got["max_depth"] <= 4

    def test_a_deeper_tree_can_be_asked_for_but_not_an_unreadable_one(self, churn):
        deep = decision_tree(churn, target="churned", max_depth=50)
        # Capped, not obeyed: a depth-50 tree is the data written out longhand.
        assert deep["max_depth"] <= 8

    def test_every_node_says_how_many_rows_reached_it(self, churn):
        got = decision_tree(churn, target="churned")

        def walk(node):
            assert node["samples"] > 0
            for child in node.get("children") or []:
                walk(child)
        walk(got["tree"])

    def test_a_leaf_states_its_prediction(self, churn):
        got = decision_tree(churn, target="churned")

        def leaves(node):
            kids = node.get("children") or []
            if not kids:
                yield node
            for child in kids:
                yield from leaves(child)
        for leaf in leaves(got["tree"]):
            assert leaf["prediction"] is not None
            assert leaf.get("feature") is None

    def test_a_split_reads_as_a_sentence(self, churn):
        # `margin_pct <= 11.94` is the whole value of a tree over a coefficient.
        got = decision_tree(churn, target="churned")
        assert got["tree"]["feature"] == "margin_pct"
        assert got["tree"]["label"].startswith("margin_pct")

    def test_a_categorical_split_reads_as_membership_not_arithmetic(self):
        """One-hot encoding makes a split `region_North <= 0.5`, which is true
        and unreadable. It has to come back as "region is not North"."""
        rng = np.random.default_rng(2)
        n = 300
        region = rng.choice(["North", "South"], n)
        df = pd.DataFrame({"region": region, "filler": rng.uniform(0, 1, n),
                           "outcome": np.where(region == "North", "a", "b")})
        got = decision_tree(df, target="outcome")
        assert " is " in got["tree"]["label"]
        assert "0.5" not in got["tree"]["label"]


class TestItSaysWhatItCouldNotUse:
    def test_a_high_cardinality_column_is_skipped_and_named(self, churn):
        churn = churn.assign(invoice_id=[f"INV-{i}" for i in range(len(churn))])
        got = decision_tree(churn, target="churned")
        skipped = {s["column"] for s in got["predictors_skipped"]}
        assert "invoice_id" in skipped
        assert "invoice_id" not in got["predictors_used"]

    def test_the_reason_is_given(self, churn):
        churn = churn.assign(invoice_id=[f"INV-{i}" for i in range(len(churn))])
        got = decision_tree(churn, target="churned")
        reason = next(s["reason"] for s in got["predictors_skipped"]
                      if s["column"] == "invoice_id")
        assert "distinct" in reason.lower() or "identifier" in reason.lower()

    def test_named_predictors_are_honoured(self, churn):
        got = decision_tree(churn, target="churned", predictors=["spend"])
        assert got["predictors_used"] == ["spend"]

    def test_the_target_never_predicts_itself(self, churn):
        got = decision_tree(churn, target="churned")
        assert "churned" not in got["predictors_used"]


class TestItRefusesRatherThanMisleading:
    def test_a_missing_target(self, churn):
        with pytest.raises(DecisionTreeError):
            decision_tree(churn, target="nope")

    def test_a_target_with_one_value_only(self, churn):
        flat = churn.assign(churned="no")
        with pytest.raises(DecisionTreeError):
            decision_tree(flat, target="churned")

    def test_too_few_rows_to_hold_any_out(self):
        tiny = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "a"]})
        with pytest.raises(DecisionTreeError):
            decision_tree(tiny, target="y")

    def test_no_usable_predictor_at_all(self):
        rng = np.random.default_rng(3)
        df = pd.DataFrame({"id": [f"r{i}" for i in range(200)],
                           "outcome": rng.choice(["a", "b"], 200)})
        with pytest.raises(DecisionTreeError) as e:
            decision_tree(df, target="outcome")
        assert "predictor" in str(e.value).lower()

    def test_a_target_with_too_many_classes(self):
        """A 'classification' over 200 distinct labels is not a tree anybody
        reads; it is an identifier wearing an outcome's clothes."""
        rng = np.random.default_rng(4)
        df = pd.DataFrame({"x": rng.uniform(0, 1, 400),
                           "outcome": [f"c{i}" for i in range(400)]})
        with pytest.raises(DecisionTreeError):
            decision_tree(df, target="outcome")


class TestItCarriesItsCaveats:
    def test_association_is_not_causation(self, churn):
        got = decision_tree(churn, target="churned")
        assert any("caus" in c.lower() for c in got["caveats"])

    def test_a_memorising_tree_says_so(self, churn):
        """The gap between training and held-out scores is the one thing a
        reader most needs pointed out, and the one they are least likely to
        compute themselves."""
        got = decision_tree(churn, target="churned", max_depth=8)
        assert "train_score" in got and got["score"] is not None
        if got["train_score"] - got["score"] > 0.15:
            assert any("memor" in c.lower() or "overfit" in c.lower()
                       for c in got["caveats"])


class TestItIsInTheCatalogue:
    def test_it_is_registered_and_runnable(self):
        from app.services.analysis.registry import get
        spec = get("decision_tree")
        assert spec is not None
        assert spec.to_dict()["runnable"] is True

    def test_the_dispatcher_runs_it(self, churn):
        from app.services.analysis.registry import run_analysis
        got = run_analysis("decision_tree", churn, {"target": "churned"})
        assert got["tree"]["feature"] == "margin_pct"


class TestNothingHeavyIsImportedToRegister:
    def test_importing_the_registry_still_does_not_pull_in_sklearn(self):
        """`segment.py` and `anomaly.py` exist to keep sklearn off the
        app-import path. A third sklearn analysis must not be the one that
        undoes it."""
        import subprocess
        import sys
        code = ("import sys; import app.services.analysis.registry as r; "
                "print('sklearn' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, cwd=".")
        assert out.stdout.strip() == "False", out.stdout + out.stderr
