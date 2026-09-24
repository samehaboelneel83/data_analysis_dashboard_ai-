"""Reading PostgreSQL's own statistics instead of scanning the table.

ARCHITECTURE.md principle 2: "Read the engine's own statistics before computing
your own. pg_stats in milliseconds beats a full scan in minutes."

The catch is that pg_stats does not hand back the numbers in the shape you want
them, and two of its conventions will silently produce garbage if taken at face
value:

  n_distinct < 0    is a NEGATIVE FRACTION OF ROWS, not a count. -0.5 on a
                    million-row table means 500,000 distinct values. Read as a
                    count it means "-0.5 distinct values", and every downstream
                    dimension-vs-measure decision made from it is wrong.

  most_common_vals  is a Postgres array LITERAL in text form ({a,b,"c,d"}), not
                    JSON. json.loads cannot read it; eval must never see it.

Both are tested here against real pg_stats output shapes, because both fail
quietly rather than loudly.
"""
import pytest

from app.services.metadata import profile


class TestNormalizeNDistinct:
    """The negative-fraction convention."""

    def test_positive_value_is_an_absolute_count(self):
        assert profile.normalize_n_distinct(42.0, row_count=1_000_000) == 42

    def test_negative_value_is_a_fraction_of_rows(self):
        # -0.5 on a million rows means half the rows hold a distinct value.
        assert profile.normalize_n_distinct(-0.5, row_count=1_000_000) == 500_000

    def test_negative_one_means_every_row_is_unique(self):
        """-1 is how Postgres reports a candidate key, which is exactly the
        signal Stage 4 uses to find undeclared primary keys."""
        assert profile.normalize_n_distinct(-1.0, row_count=5_000) == 5_000

    def test_zero_means_unknown(self):
        """Postgres reports 0 when ANALYZE has never run. That is 'no data',
        not 'no distinct values' — reporting it as 0 would make the column look
        empty."""
        assert profile.normalize_n_distinct(0.0, row_count=1_000) is None

    def test_none_stays_none(self):
        assert profile.normalize_n_distinct(None, row_count=1_000) is None

    def test_unknown_row_count_makes_a_fraction_unusable(self):
        """A fraction is meaningless without the total to multiply it by."""
        assert profile.normalize_n_distinct(-0.5, row_count=None) is None

    def test_a_fraction_never_exceeds_the_row_count(self):
        assert profile.normalize_n_distinct(-1.0, row_count=100) == 100

    def test_result_is_always_an_int_not_a_float(self):
        """distinct_count is a BIGINT column; a float would round-trip oddly and
        compare badly against integer thresholds."""
        got = profile.normalize_n_distinct(-0.333, row_count=1_000)
        assert isinstance(got, int) and got == 333


class TestParsePgArray:
    """most_common_vals is a Postgres array literal, not JSON."""

    def test_simple_unquoted_values(self):
        assert profile.parse_pg_array("{active,churned,pending}") == [
            "active", "churned", "pending"
        ]

    def test_quoted_values_keep_embedded_commas(self):
        """The reason a naive split(',') is wrong."""
        assert profile.parse_pg_array('{"Cairo, EG","Giza, EG"}') == [
            "Cairo, EG", "Giza, EG"
        ]

    def test_escaped_quotes_inside_a_value(self):
        assert profile.parse_pg_array(r'{"say \"hi\""}') == ['say "hi"']

    def test_null_element(self):
        assert profile.parse_pg_array("{active,NULL,pending}") == [
            "active", None, "pending"
        ]

    def test_quoted_null_is_the_literal_string(self):
        """A customer whose status really is the four letters N-U-L-L."""
        assert profile.parse_pg_array('{"NULL"}') == ["NULL"]

    def test_empty_array(self):
        assert profile.parse_pg_array("{}") == []

    def test_none_and_blank_are_empty(self):
        assert profile.parse_pg_array(None) == []
        assert profile.parse_pg_array("") == []

    def test_numeric_values_stay_strings(self):
        """min_value/max_value/top_k are TEXT columns — the semantic layer keeps
        the raw form so `st_cd = 3` renders as it appears in the database."""
        assert profile.parse_pg_array("{1,2,3}") == ["1", "2", "3"]

    def test_a_list_passes_through(self):
        """Some drivers already decode anyarray into a Python list."""
        assert profile.parse_pg_array(["a", "b"]) == ["a", "b"]


class TestBuildTopK:
    def test_pairs_values_with_their_frequencies(self):
        got = profile.build_top_k(
            ["active", "churned"], [0.8, 0.2], row_count=1000
        )
        assert got == [
            {"value": "active", "count": 800, "ratio": 0.8},
            {"value": "churned", "count": 200, "ratio": 0.2},
        ]

    def test_orders_most_common_first(self):
        got = profile.build_top_k(["a", "b"], [0.2, 0.8], row_count=100)
        assert [e["value"] for e in got] == ["b", "a"]

    def test_missing_row_count_still_yields_ratios(self):
        got = profile.build_top_k(["a"], [0.5], row_count=None)
        assert got[0]["ratio"] == 0.5
        assert got[0]["count"] is None

    def test_mismatched_lengths_are_truncated_not_crashed(self):
        """pg_stats can return the two arrays at different lengths; a stats read
        must never take down a sync."""
        got = profile.build_top_k(["a", "b", "c"], [0.5], row_count=10)
        assert len(got) == 1

    def test_empty_inputs_give_none_not_an_empty_list(self):
        """None means 'not computed'; [] would claim the column has no common
        values, which is a different and false statement."""
        assert profile.build_top_k([], [], row_count=10) is None
        assert profile.build_top_k(None, None, row_count=10) is None

    def test_caps_at_one_hundred_entries(self):
        vals = [f"v{i}" for i in range(250)]
        freqs = [0.001] * 250
        assert len(profile.build_top_k(vals, freqs, row_count=1000)) == 100


class TestShouldComputeTopK:
    """ARCHITECTURE.md: "Always compute top_k where distinct_count < 100"."""

    def test_low_cardinality_qualifies(self):
        assert profile.should_compute_top_k(3) is True
        assert profile.should_compute_top_k(99) is True

    def test_at_and_above_the_threshold_does_not(self):
        assert profile.should_compute_top_k(100) is False
        assert profile.should_compute_top_k(50_000) is False

    def test_unknown_cardinality_does_not_qualify(self):
        """Without a count there is no way to know the query is bounded, and an
        unbounded GROUP BY against a customer's production table is exactly what
        the metadata plane exists to avoid."""
        assert profile.should_compute_top_k(None) is False
