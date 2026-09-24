"""Profiling where pg_stats is not available: other SQL families, and the
imported frames that back uploaded datasets.

The distinction that matters is the `exact` flag. Postgres statistics are
ESTIMATES sampled by ANALYZE; a computed aggregate is a MEASUREMENT. Both are
useful and they are not interchangeable, so every stats row records which one it
is. A caller deciding "dimension or measure?" is fine with an estimate; a caller
about to show a user a distinct count as fact is not.
"""
import pandas as pd

from app.services.metadata import profile


def _frame():
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "status": ["active", "active", "churned", "active", None],
        "amount": [10.5, 20.0, 30.25, 40.0, 50.75],
        "city": ["Cairo", "Giza", "Cairo", "Luxor", "Cairo"],
    })


class TestProfileFrame:
    def test_marks_results_as_exact(self):
        """Computed from every row, so it is a measurement, not an estimate."""
        stats = profile.profile_frame(_frame())
        assert all(s["exact"] is True for s in stats.values())

    def test_counts_distinct_values_excluding_nulls(self):
        stats = profile.profile_frame(_frame())
        assert stats["status"]["distinct_count"] == 2   # active, churned
        assert stats["id"]["distinct_count"] == 5

    def test_null_ratio(self):
        stats = profile.profile_frame(_frame())
        assert stats["status"]["null_ratio"] == 0.2     # 1 of 5
        assert stats["amount"]["null_ratio"] == 0.0

    def test_min_and_max_are_stored_as_text(self):
        """The columns are TEXT so a date, a decimal and an integer all round
        trip without the storage layer picking a lossy type for them."""
        stats = profile.profile_frame(_frame())
        assert stats["amount"]["min_value"] == "10.5"
        assert stats["amount"]["max_value"] == "50.75"
        assert isinstance(stats["amount"]["min_value"], str)

    def test_top_k_for_a_low_cardinality_column(self):
        stats = profile.profile_frame(_frame())
        top = stats["status"]["top_k"]
        assert top[0] == {"value": "active", "count": 3, "ratio": 0.75}

    def test_top_k_ratio_is_of_non_null_values(self):
        """3 of the 4 present values are 'active'. Dividing by 5 instead would
        make the ratios of a nullable column silently fail to sum to 1."""
        stats = profile.profile_frame(_frame())
        assert sum(e["ratio"] for e in stats["status"]["top_k"]) == 1.0

    def test_high_cardinality_column_gets_no_top_k(self):
        df = pd.DataFrame({"uid": [f"u{i}" for i in range(150)]})
        stats = profile.profile_frame(df)
        assert stats["uid"]["distinct_count"] == 150
        assert stats["uid"]["top_k"] is None

    def test_empty_frame_does_not_crash(self):
        stats = profile.profile_frame(pd.DataFrame({"a": []}))
        assert stats["a"]["distinct_count"] == 0
        assert stats["a"]["null_ratio"] is None    # 0/0 is unknown, not zero

    def test_all_null_column(self):
        stats = profile.profile_frame(pd.DataFrame({"a": [None, None, None]}))
        assert stats["a"]["null_ratio"] == 1.0
        assert stats["a"]["distinct_count"] == 0
        assert stats["a"]["top_k"] is None

    def test_avg_width_is_bytes_for_text(self):
        stats = profile.profile_frame(pd.DataFrame({"a": ["ab", "abcd"]}))
        assert stats["a"]["avg_width"] == 3

    def test_datetime_min_max_are_isoformatted(self):
        df = pd.DataFrame({"when": pd.to_datetime(["2026-01-01", "2026-06-30"])})
        stats = profile.profile_frame(df)
        assert stats["when"]["min_value"].startswith("2026-01-01")
        assert stats["when"]["max_value"].startswith("2026-06-30")


class TestGenericSqlPlan:
    """The aggregate query used where pg_stats does not exist. Built as text and
    checked here rather than executed, so the shape is pinned per dialect
    without needing five live databases in CI."""

    def test_builds_one_aggregate_query_per_column(self):
        sql = profile.build_profile_sql("orders", ["amount"], family="mysql")
        lowered = sql.lower()
        assert "count(*)" in lowered
        assert "count(distinct" in lowered
        assert "min(" in lowered and "max(" in lowered

    def test_quotes_identifiers_per_family(self):
        """An unquoted column named `order` is a syntax error, and a column named
        `select` is worse. Quoting is per-dialect, not optional."""
        assert '"order"' in profile.build_profile_sql("t", ["order"], family="postgresql")
        assert "`order`" in profile.build_profile_sql("t", ["order"], family="mysql")
        assert "[order]" in profile.build_profile_sql("t", ["order"], family="sqlserver")

    def test_rejects_an_identifier_that_could_break_out(self):
        """Column names reach here from a source catalog, which is not a trusted
        input — a table can be created with a quote in its column name."""
        import pytest
        with pytest.raises(ValueError):
            profile.build_profile_sql("t", ['bad"name'], family="postgresql")

    def test_top_k_query_is_bounded(self):
        sql = profile.build_top_k_sql("orders", "status", family="postgresql")
        assert "group by" in sql.lower()
        assert "limit 100" in sql.lower()

    def test_top_k_query_orders_by_frequency(self):
        sql = profile.build_top_k_sql("orders", "status", family="postgresql").lower()
        assert "order by" in sql and "desc" in sql


class TestExactFlagContract:
    def test_frame_profiling_is_exact_and_pg_stats_is_not(self):
        """The one-line summary of this whole module."""
        frame_stats = profile.profile_frame(_frame())
        assert frame_stats["id"]["exact"] is True

        pg_row = {
            "null_frac": 0.0, "n_distinct": -1.0, "avg_width": 4,
            "most_common_vals": None, "most_common_freqs": None,
        }
        converted = profile.from_pg_stats_row(pg_row, row_count=5)
        assert converted["exact"] is False
        assert converted["distinct_count"] == 5


class TestFromPgStatsRow:
    def test_assembles_a_complete_stats_dict(self):
        row = {
            "null_frac": 0.25,
            "n_distinct": 2.0,
            "avg_width": 7,
            "most_common_vals": "{active,churned}",
            "most_common_freqs": [0.6, 0.4],
        }
        got = profile.from_pg_stats_row(row, row_count=100)
        assert got["null_ratio"] == 0.25
        assert got["distinct_count"] == 2
        assert got["avg_width"] == 7
        assert got["top_k"][0] == {"value": "active", "count": 60, "ratio": 0.6}
        assert got["exact"] is False

    def test_survives_a_row_with_everything_missing(self):
        """A column ANALYZE has never touched. Absent statistics are normal and
        must not fail the stage."""
        got = profile.from_pg_stats_row({}, row_count=None)
        assert got["distinct_count"] is None
        assert got["top_k"] is None
        assert got["exact"] is False
