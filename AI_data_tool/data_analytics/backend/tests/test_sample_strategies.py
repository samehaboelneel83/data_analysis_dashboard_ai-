"""Stage 3 — choosing HOW to take a sample.

There is no single right sampling method, because the constraint differs by
source. TABLESAMPLE is nearly free but only works on physical tables in some
engines. ORDER BY random() is universal and expensive. Stratified sampling is
the only way to see rare category values at all — and rare values are exactly
what the semantic layer needs, because a status that appears in 0.2% of rows is
still a status the agent must know about.

The rules are pinned here rather than inlined at the call site so that adding a
sixth SQL family is a table edit with a test, not an archaeology exercise.
"""
import pandas as pd
import pytest

from app.services.metadata import sample


class TestChooseStrategy:
    def test_a_large_physical_table_on_postgres_uses_tablesample(self):
        assert sample.choose_strategy(
            family="postgresql", kind="table", row_count=5_000_000) == "tablesample"

    def test_sqlserver_also_supports_tablesample(self):
        assert sample.choose_strategy(
            family="sqlserver", kind="table", row_count=5_000_000) == "tablesample"

    def test_a_small_table_is_read_rather_than_sampled(self):
        """TABLESAMPLE works in PAGES. A 40-row table is one page, so a 1%
        sample returns nothing at all — not a smaller sample, NO sample. Real
        data hit this: maps_states (40 rows) produced an empty cache and a sync
        that reported six green stages while learning nothing."""
        assert sample.choose_strategy(
            family="postgresql", kind="table", row_count=40) == "random"

    def test_an_unknown_row_count_takes_a_bounded_read_not_a_sort(self):
        """Without a row count we cannot know a sort is affordable, and
        ORDER BY random() cannot stop at the LIMIT — every row is produced,
        randomised and sorted first. Measured against a real view over
        million-row tables: nine and a half minutes for one object."""
        assert sample.choose_strategy(family="postgresql", kind="table") == "head"
        assert sample.choose_strategy(
            family="postgresql", kind="table", row_count=0) == "head"

    def test_a_view_is_never_sorted(self):
        """A view's size is unknowable without running it, and sorting one
        materialises the whole query first."""
        assert sample.choose_strategy(family="postgresql", kind="view") == "head"
        assert sample.choose_strategy(
            family="postgresql", kind="view", row_count=100) == "head"

    def test_a_large_table_without_tablesample_support_is_not_sorted(self):
        """MySQL has no usable TABLESAMPLE. Sorting 5 million rows to keep 1000
        is not the answer."""
        assert sample.choose_strategy(
            family="mysql", kind="table", row_count=5_000_000) == "head"

    def test_a_view_never_uses_tablesample(self):
        """TABLESAMPLE addresses physical pages. A view has none, and the engine
        either errors or silently ignores the clause — both worse than not
        asking."""
        assert sample.choose_strategy(family="postgresql", kind="view") != "tablesample"

    def test_mysql_without_a_row_count_takes_a_bounded_read(self):
        assert sample.choose_strategy(family="mysql", kind="table") == "head"

    def test_mysql_with_a_small_table_may_be_sorted(self):
        assert sample.choose_strategy(
            family="mysql", kind="table", row_count=500) == "random"

    def test_stratify_wins_even_over_tablesample(self):
        """Seeing every value of `status` matters more than page-level speed:
        a value the sample misses is a value the semantic layer will never
        know exists."""
        got = sample.choose_strategy(
            family="postgresql", kind="table", stratify_column="status"
        )
        assert got == "stratified"

    def test_import_mode_uses_reservoir(self):
        assert sample.choose_strategy(family=None, kind="table", is_import=True) == "reservoir"

    def test_unknown_family_is_handled_conservatively(self):
        assert sample.choose_strategy(family="teradata", kind="table") == "head"


class TestBuildSampleSql:
    def test_tablesample_includes_a_percentage_and_a_limit(self):
        sql = sample.build_sample_sql(
            "orders", family="postgresql", strategy="tablesample", n=1000, row_count=1_000_000
        ).lower()
        assert "tablesample" in sql
        assert "limit 1000" in sql

    def test_tablesample_percentage_scales_to_the_table_size(self):
        """A fixed 1% of a billion rows is ten million rows read to keep a
        thousand. The fraction has to track the row count."""
        big = sample.build_sample_sql(
            "t", family="postgresql", strategy="tablesample", n=1000, row_count=10_000_000
        )
        small = sample.build_sample_sql(
            "t", family="postgresql", strategy="tablesample", n=1000, row_count=10_000
        )
        assert sample._percentage_for(1000, 10_000_000) < sample._percentage_for(1000, 10_000)
        assert "TABLESAMPLE" in big and "TABLESAMPLE" in small

    def test_tablesample_percentage_never_reaches_zero(self):
        """A rounded-down 0% returns nothing, which would look like an empty
        table and trip the deprecation heuristic."""
        assert sample._percentage_for(1000, 10**12) > 0

    def test_unknown_row_count_still_produces_valid_sql(self):
        sql = sample.build_sample_sql(
            "t", family="postgresql", strategy="tablesample", n=100, row_count=None
        )
        assert "TABLESAMPLE" in sql

    @pytest.mark.parametrize("family,expected_fn", [
        ("postgresql", "random()"),
        ("mysql", "rand()"),
        ("sqlserver", "newid()"),
        ("sqlite", "random()"),
        ("oracle", "dbms_random.value"),
    ])
    def test_random_uses_each_dialects_own_function(self, family, expected_fn):
        sql = sample.build_sample_sql(
            "t", family=family, strategy="random", n=50, row_count=None
        ).lower()
        assert expected_fn in sql

    def test_sqlserver_random_uses_top_not_limit(self):
        sql = sample.build_sample_sql(
            "t", family="sqlserver", strategy="random", n=50, row_count=None
        ).lower()
        assert "top 50" in sql
        assert "limit" not in sql

    def test_oracle_random_uses_fetch_first(self):
        sql = sample.build_sample_sql(
            "t", family="oracle", strategy="random", n=50, row_count=None
        ).lower()
        assert "fetch first 50 rows only" in sql

    def test_stratified_partitions_by_the_chosen_column(self):
        sql = sample.build_sample_sql(
            "orders", family="postgresql", strategy="stratified", n=100,
            row_count=None, stratify_column="status",
        ).lower()
        assert "partition by" in sql
        assert "status" in sql

    def test_identifiers_are_quoted(self):
        sql = sample.build_sample_sql(
            "order", family="postgresql", strategy="random", n=10, row_count=None
        )
        assert '"order"' in sql

    def test_a_dangerous_identifier_is_refused(self):
        with pytest.raises(ValueError):
            sample.build_sample_sql(
                'x"; drop table y; --', family="postgresql",
                strategy="random", n=10, row_count=None,
            )

    def test_head_takes_a_bounded_read_with_no_sort(self):
        """The whole point: no ORDER BY, so the engine stops at the LIMIT."""
        sql = sample.build_sample_sql(
            "big_view", family="postgresql", strategy="head", n=1000,
            row_count=None).lower()
        assert "order by" not in sql
        assert "limit 1000" in sql

    def test_head_still_quotes_and_bounds_on_every_dialect(self):
        for family, token in [("postgresql", "limit 25"), ("mysql", "limit 25"),
                              ("sqlserver", "top 25"), ("oracle", "fetch first 25"),
                              ("sqlite", "limit 25")]:
            sql = sample.build_sample_sql(
                "t", family=family, strategy="head", n=25, row_count=None).lower()
            assert token in sql
            assert "order by" not in sql

    def test_row_limit_is_always_present(self):
        """An unbounded sample against a production table is the exact failure
        the metadata plane exists to prevent."""
        for family in ("postgresql", "mysql", "sqlserver", "oracle", "sqlite"):
            for strategy in ("random", "tablesample", "head"):
                sql = sample.build_sample_sql(
                    "t", family=family, strategy=strategy, n=25, row_count=1000
                ).lower()
                assert any(tok in sql for tok in ("limit 25", "top 25", "fetch first 25"))


class TestReservoir:
    def test_returns_every_row_when_the_frame_is_small(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        assert len(sample.reservoir_sample_frame(df, 100)) == 3

    def test_caps_at_the_requested_size(self):
        df = pd.DataFrame({"a": range(5000)})
        assert len(sample.reservoir_sample_frame(df, 1000)) == 1000

    def test_is_deterministic_for_the_same_frame(self):
        """Two syncs of an unchanged table must cache the same rows, or every
        overlap ratio would drift between runs for no real reason."""
        df = pd.DataFrame({"a": range(5000)})
        first = sample.reservoir_sample_frame(df, 100)
        second = sample.reservoir_sample_frame(df, 100)
        assert [r["a"] for r in first] == [r["a"] for r in second]

    def test_returns_dicts_ready_for_the_cache(self):
        df = pd.DataFrame({"a": [1], "b": ["x"]})
        got = sample.reservoir_sample_frame(df, 10)
        assert got == [{"a": 1, "b": "x"}]

    def test_empty_frame_yields_no_rows(self):
        assert sample.reservoir_sample_frame(pd.DataFrame({"a": []}), 10) == []


class TestPickStratifyColumn:
    def test_prefers_a_low_cardinality_non_null_column(self):
        stats = {
            "status": {"distinct_count": 3, "null_ratio": 0.0},
            "customer_id": {"distinct_count": 90_000, "null_ratio": 0.0},
        }
        assert sample.pick_stratify_column(stats) == "status"

    def test_ignores_columns_above_the_cardinality_ceiling(self):
        stats = {"city": {"distinct_count": 400, "null_ratio": 0.0}}
        assert sample.pick_stratify_column(stats) is None

    def test_ignores_a_constant_column(self):
        """One distinct value stratifies into a single group, which is just an
        ordinary sample wearing a more expensive query."""
        stats = {"flag": {"distinct_count": 1, "null_ratio": 0.0}}
        assert sample.pick_stratify_column(stats) is None

    def test_ignores_a_mostly_null_column(self):
        stats = {"tier": {"distinct_count": 4, "null_ratio": 0.95}}
        assert sample.pick_stratify_column(stats) is None

    def test_returns_none_when_nothing_qualifies(self):
        assert sample.pick_stratify_column({}) is None


class TestStatementTimeout:
    """ARCHITECTURE.md lists statement_timeout among the security requirements.

    A real source proved why it is not optional: after removing the count(*)
    scans and the ORDER BY random() sorts, one view still took nearly two
    minutes to return its first 1000 rows — the cost is in the view definition,
    and no sampling strategy can avoid it. Everything the metadata plane
    produces is an improvement rather than a requirement, so a deadline is the
    right trade.
    """

    def test_postgres_sets_a_statement_timeout(self):
        sql = sample.statement_timeout_sql("postgresql", 20)
        assert sql == "SET statement_timeout = 20000"

    def test_mysql_uses_its_own_spelling(self):
        sql = sample.statement_timeout_sql("mysql", 20)
        assert "max_execution_time" in sql
        assert "20000" in sql

    def test_a_family_without_one_returns_none(self):
        """Better to sample without a deadline than to refuse to sample."""
        assert sample.statement_timeout_sql("sqlite", 20) is None
        assert sample.statement_timeout_sql("sqlserver", 20) is None

    def test_the_floor_prevents_an_instantly_cancelling_timeout(self):
        """A sub-second budget would cancel almost every query, turning the
        governor into an outage."""
        assert sample.statement_timeout_sql("postgresql", 0) == "SET statement_timeout = 1000"
