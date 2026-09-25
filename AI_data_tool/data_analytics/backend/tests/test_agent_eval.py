"""The accuracy gate. Structural enforcement was MEASURED passing
semantically wrong answers (spec F2: a trend question classified `lookup`,
valid JSON, confidence 0) — this harness is the only defence, which is why
it is a test and not a script someone remembers to run.

Execution accuracy, not string match: `SELECT sum(total)` and
`SELECT SUM(orders.total)` are the same answer.
"""
from evals.run_eval import evaluate, rows_equal


class TestRowComparison:
    def test_identical_rows_match(self):
        assert rows_equal([{"n": 1}], [{"n": 1}])

    def test_order_does_not_matter(self):
        assert rows_equal([{"c": "a"}, {"c": "b"}], [{"c": "b"}, {"c": "a"}])

    def test_column_names_do_not_matter_values_do(self):
        """Aliases differ between golden and generated SQL; the ANSWER is the
        values, not the labels."""
        assert rows_equal([{"total": 30}], [{"sum": 30}])

    def test_different_values_do_not_match(self):
        assert not rows_equal([{"n": 1}], [{"n": 2}])

    def test_numeric_text_equivalence(self):
        assert rows_equal([{"n": 30}], [{"n": 30.0}])


class TestEvaluate:
    def test_accuracy_and_per_intent_breakdown(self):
        def execute(sql):
            return {"SELECT 1 AS n": [{"n": 1}],
                    "SELECT 2 AS n": [{"n": 2}]}[sql]

        report = evaluate(
            [{"question": "q1", "golden_sql": "SELECT 1 AS n",
              "generated_sql": "SELECT 1 AS n", "intent": "lookup"},
             {"question": "q2", "golden_sql": "SELECT 1 AS n",
              "generated_sql": "SELECT 2 AS n", "intent": "trend"}],
            execute)
        assert report["accuracy"] == 0.5
        assert report["by_intent"]["lookup"]["correct"] == 1
        assert report["by_intent"]["trend"]["correct"] == 0

    def test_a_generated_query_that_crashes_counts_as_wrong(self):
        def execute(sql):
            if sql == "BROKEN":
                raise RuntimeError("nope")
            return [{"n": 1}]

        report = evaluate([{"question": "q", "golden_sql": "SELECT 1",
                            "generated_sql": "BROKEN", "intent": "lookup"}],
                          execute)
        assert report["correct"] == 0
