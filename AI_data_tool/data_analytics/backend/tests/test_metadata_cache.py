"""The DuckDB sample cache — the thing that makes the two-plane split real.

ARCHITECTURE.md: "The agent iterates — profiles, guesses a join, fails, retries.
If every iteration hits the customer's production database, you get blocked from
their infrastructure within weeks."

So Stage 3 pulls ~1000 rows per table once, and every subsequent question about
STRUCTURE is answered from here. Foreign-key inference in particular compares
every plausible column pair — quadratic in column count — and does it as a local
DuckDB join rather than N queries against a live source.

The cache is budgeted and LRU-evicted because it is a convenience, not a system
of record: anything evicted is re-samplable on the next sync.
"""
import pytest

from app.services.metadata import cache as cache_module


@pytest.fixture
def cache(tmp_path):
    """A cache on a real DuckDB file, isolated per test."""
    c = cache_module.SampleCache(path=str(tmp_path / "meta.duckdb"), max_mb=8)
    yield c
    c.close()


ROWS = [
    {"id": 1, "status": "active", "city": "Cairo"},
    {"id": 2, "status": "churned", "city": "Giza"},
    {"id": 3, "status": "active", "city": "Cairo"},
]


class TestRoundTrip:
    def test_put_then_get(self, cache):
        cache.put_sample(1, ROWS)
        got = cache.get_sample(1)
        assert len(got) == 3
        assert got[0]["status"] == "active"

    def test_get_missing_returns_empty(self, cache):
        assert cache.get_sample(999) == []

    def test_has_sample_reports_presence(self, cache):
        assert cache.has_sample(1) is False
        cache.put_sample(1, ROWS)
        assert cache.has_sample(1) is True

    def test_put_replaces_rather_than_appends(self, cache):
        """A resync must not double a table's sample every night."""
        cache.put_sample(1, ROWS)
        cache.put_sample(1, ROWS)
        assert len(cache.get_sample(1)) == 3

    def test_empty_sample_is_stored_without_error(self, cache):
        """An empty table is a fact worth recording — it is one of the
        deprecation signals Stage 5 looks for."""
        cache.put_sample(1, [])
        assert cache.get_sample(1) == []

    def test_samples_for_different_datasets_are_independent(self, cache):
        cache.put_sample(1, ROWS)
        cache.put_sample(2, [{"id": 9, "status": "x", "city": "y"}])
        assert len(cache.get_sample(1)) == 3
        assert len(cache.get_sample(2)) == 1

    def test_ragged_rows_are_stored_on_the_union_of_keys(self, cache):
        """Sources return rows of differing shape more often than they should."""
        cache.put_sample(1, [{"a": 1}, {"a": 2, "b": 3}])
        got = cache.get_sample(1)
        assert len(got) == 2
        assert "b" in got[0]

    def test_column_names_needing_quoting_survive(self, cache):
        """Reserved words, spaces and mixed case all appear in real catalogs, and
        the cached name has to match the catalog exactly or inference will not
        line the two up."""
        cache.put_sample(1, [{"order": 1, "select from": "x", "MixedCase": "y"}])
        got = cache.get_sample(1)
        assert set(got[0]) == {"order", "select from", "MixedCase"}

    def test_values_are_stored_as_text_on_purpose(self, cache):
        """Every value is cached as VARCHAR, so an integer comes back as "1".

        This is deliberate, and it is what makes `overlap` work across a source
        that reports ids as BIGINT on one side and VARCHAR on the other — a
        type-strict join would score that pair zero and silently lose a real
        relationship. Nothing reads numbers back out of this cache: statistics
        come from `profile`, which works against the typed frame or the engine's
        own catalog, never from here.
        """
        cache.put_sample(1, [{"n": 1, "f": 2.5, "b": True}])
        got = cache.get_sample(1)
        assert got[0]["n"] == "1"
        assert isinstance(got[0]["f"], str)


class TestOverlap:
    """The measurement foreign-key inference is built on."""

    def test_full_containment_scores_one(self, cache):
        cache.put_sample(1, [{"customer_id": i} for i in range(50)])
        cache.put_sample(2, [{"id": i} for i in range(100)])
        assert cache.overlap(1, "customer_id", 2, "id") == 1.0

    def test_no_shared_values_scores_zero(self, cache):
        cache.put_sample(1, [{"customer_id": i} for i in range(50)])
        cache.put_sample(2, [{"id": i} for i in range(100, 200)])
        assert cache.overlap(1, "customer_id", 2, "id") == 0.0

    def test_partial_overlap_is_the_child_side_fraction(self, cache):
        """Directional on purpose: a foreign key means every CHILD value exists
        in the parent, not the reverse. Measuring the parent side would score a
        lookup table against a huge fact table near zero and discard a real key."""
        cache.put_sample(1, [{"customer_id": i} for i in range(10)])
        cache.put_sample(2, [{"id": i} for i in range(5)])
        assert cache.overlap(1, "customer_id", 2, "id") == 0.5

    def test_nulls_are_excluded_from_the_child_side(self, cache):
        """A nullable foreign key is still a foreign key. Counting nulls as
        misses would push every optional relationship below the threshold."""
        cache.put_sample(1, [{"cid": 1}, {"cid": 2}, {"cid": None}])
        cache.put_sample(2, [{"id": 1}, {"id": 2}])
        assert cache.overlap(1, "cid", 2, "id") == 1.0

    def test_duplicate_child_values_count_once(self, cache):
        """Overlap is over DISTINCT values — otherwise a skewed fact table would
        score by row frequency rather than by key coverage."""
        cache.put_sample(1, [{"cid": 1}] * 90 + [{"cid": 2}] * 10)
        cache.put_sample(2, [{"id": 1}])
        assert cache.overlap(1, "cid", 2, "id") == 0.5

    def test_missing_sample_scores_zero_not_an_error(self, cache):
        cache.put_sample(1, [{"cid": 1}])
        assert cache.overlap(1, "cid", 404, "id") == 0.0

    def test_missing_column_scores_zero_not_an_error(self, cache):
        cache.put_sample(1, [{"cid": 1}])
        cache.put_sample(2, [{"id": 1}])
        assert cache.overlap(1, "nope", 2, "id") == 0.0

    def test_empty_child_scores_zero(self, cache):
        cache.put_sample(1, [{"cid": None}])
        cache.put_sample(2, [{"id": 1}])
        assert cache.overlap(1, "cid", 2, "id") == 0.0

    def test_values_of_different_types_still_compare(self, cache):
        """A source may hand back ids as text on one side and integers on the
        other; the join must not silently score zero because of that."""
        cache.put_sample(1, [{"cid": "1"}, {"cid": "2"}])
        cache.put_sample(2, [{"id": 1}, {"id": 2}])
        assert cache.overlap(1, "cid", 2, "id") == 1.0


class TestDistinctCount:
    def test_counts_distinct_non_null_values(self, cache):
        cache.put_sample(1, [{"c": 1}, {"c": 1}, {"c": 2}, {"c": None}])
        assert cache.distinct_count(1, "c") == 2

    def test_missing_returns_zero(self, cache):
        assert cache.distinct_count(404, "c") == 0


class TestEviction:
    def test_evicts_least_recently_used_when_over_budget(self, tmp_path):
        c = cache_module.SampleCache(path=str(tmp_path / "m.duckdb"), max_mb=0)
        try:
            c.put_sample(1, ROWS)
            c.put_sample(2, ROWS)
            # A zero budget means everything is over budget, so the older entry
            # goes and the just-written one survives.
            c.evict_if_over_budget()
            assert c.has_sample(2) is True
            assert c.has_sample(1) is False
        finally:
            c.close()

    def test_reading_a_sample_refreshes_its_recency(self, tmp_path):
        c = cache_module.SampleCache(path=str(tmp_path / "m.duckdb"), max_mb=0)
        try:
            c.put_sample(1, ROWS)
            c.put_sample(2, ROWS)
            c.get_sample(1)          # 1 is now the most recently used
            c.evict_if_over_budget()
            assert c.has_sample(1) is True
            assert c.has_sample(2) is False
        finally:
            c.close()

    def test_generous_budget_evicts_nothing(self, cache):
        cache.put_sample(1, ROWS)
        cache.put_sample(2, ROWS)
        cache.evict_if_over_budget()
        assert cache.has_sample(1) and cache.has_sample(2)

    def test_drop_removes_one_sample(self, cache):
        cache.put_sample(1, ROWS)
        cache.drop_sample(1)
        assert cache.has_sample(1) is False

    def test_dropping_something_absent_is_not_an_error(self, cache):
        cache.drop_sample(404)


class TestPersistence:
    def test_samples_survive_reopening_the_file(self, tmp_path):
        path = str(tmp_path / "m.duckdb")
        first = cache_module.SampleCache(path=path, max_mb=8)
        first.put_sample(1, ROWS)
        first.close()

        second = cache_module.SampleCache(path=path, max_mb=8)
        try:
            assert len(second.get_sample(1)) == 3
        finally:
            second.close()


class TestSatisfiesInferenceInterface:
    """The real cache must answer everything foreign-key inference asks.

    THIS TEST EXISTS BECAUSE THE ABSENCE OF ONE METHOD WENT UNNOTICED.

    `infer_keys` needed `row_count` to check that a candidate parent column is
    unique — the guard that stops a "foreign key" pointing at a column full of
    repeats, which silently multiplies rows on every join built from it. It
    asked defensively:

        cache.row_count(x) if hasattr(cache, "row_count") else parent_distinct

    SampleCache did not define `row_count`, so production took the fallback and
    the comparison became `parent_distinct < parent_distinct * 0.99` — never
    true. The guard did nothing. Every test passed, because the FakeCache used
    throughout the inference tests DID implement `row_count`, so the suite only
    ever exercised a path production never reached.

    The lesson is not "write more inference tests". It is that a test double
    must never be more capable than the thing it stands in for. This test binds
    the real object to the interface its consumer requires.
    """

    def test_the_real_cache_answers_every_call_inference_makes(self, cache):
        cache.put_sample(1, [{"cid": 1}, {"cid": 1}, {"cid": 2}])
        cache.put_sample(2, [{"id": 1}, {"id": 2}])

        # Exactly the calls infer_keys.infer_foreign_keys makes.
        assert cache.overlap(1, "cid", 2, "id") == 1.0
        assert cache.distinct_count(1, "cid") == 2
        assert cache.row_count(1) == 3
        assert cache.row_count(2) == 2

    def test_row_count_is_rows_not_distinct_values(self, cache):
        """The distinction the missing method collapsed. A column with 2
        distinct values across 3 rows is NOT unique, and the whole parent-side
        guard turns on being able to tell."""
        cache.put_sample(1, [{"c": "a"}, {"c": "a"}, {"c": "b"}])
        assert cache.row_count(1) == 3
        assert cache.distinct_count(1, "c") == 2

    def test_an_empty_sample_reports_zero_rows(self, cache):
        """An empty object is stored as a placeholder table with one marker
        column; counting that as a row would make the object look populated."""
        cache.put_sample(1, [])
        assert cache.row_count(1) == 0

    def test_a_missing_sample_reports_zero_rows(self, cache):
        assert cache.row_count(404) == 0

    def test_inference_runs_against_the_real_cache(self, cache):
        """End to end, with no fake anywhere: the parent-uniqueness guard must
        actually reject a non-unique parent."""
        from app.services.metadata import infer_keys

        # customers.id repeats, so it cannot be the parent side of a key.
        cache.put_sample(1, [{"customer_id": i % 5} for i in range(20)])
        cache.put_sample(2, [{"id": i % 5} for i in range(20)])

        tables = [
            {"dataset_id": 1, "name": "orders",
             "columns": [{"name": "customer_id", "dtype": "integer"}]},
            {"dataset_id": 2, "name": "customers",
             "columns": [{"name": "id", "dtype": "integer"}]},
        ]
        assert infer_keys.infer_foreign_keys(tables, cache) == []

    def test_a_genuinely_unique_parent_is_still_accepted(self, cache):
        from app.services.metadata import infer_keys

        cache.put_sample(1, [{"customer_id": i % 5} for i in range(20)])
        cache.put_sample(2, [{"id": i} for i in range(5)])

        tables = [
            {"dataset_id": 1, "name": "orders",
             "columns": [{"name": "customer_id", "dtype": "integer"}]},
            {"dataset_id": 2, "name": "customers",
             "columns": [{"name": "id", "dtype": "integer"}]},
        ]
        got = infer_keys.infer_foreign_keys(tables, cache)
        assert len(got) == 1
        # 5 distinct values across 20 rows on the child side — many-to-one, and
        # the label that was universally wrong while row_count was missing.
        assert got[0].cardinality == "many_to_one"


class TestSchemaMemo:
    """The cache memoises its own schema. These tests exist to keep it honest.

    WHY THE MEMO
    -------------
    `overlap()` makes five DuckDB round trips per candidate pair, and four are
    existence checks against information_schema. Measured: _table_exists 7.00ms
    and _has_column 3.26ms against 3.32ms for the overlap query itself — 20.5ms
    of every 23.8ms spent re-asking questions whose answers cannot change while
    a stage runs. Across ~12,650 pairs that was the bulk of a 239-second stage.

    THE RISK THE MEMO INTRODUCES
    -----------------------------
    Staleness. A cache that confidently reports the wrong schema is far worse
    than a slow one, so every writer must invalidate. These tests drive the
    cache through each mutation and check the memo agrees with reality
    afterwards.
    """

    def test_a_new_sample_becomes_visible(self, cache):
        assert cache.has_sample(1) is False          # builds the memo
        cache.put_sample(1, [{"a": 1}])
        assert cache.has_sample(1) is True, "put_sample did not invalidate the memo"

    def test_a_dropped_sample_stops_being_visible(self, cache):
        cache.put_sample(1, [{"a": 1}])
        assert cache.has_sample(1) is True
        cache.drop_sample(1)
        assert cache.has_sample(1) is False, "drop_sample did not invalidate the memo"

    def test_replacing_a_sample_updates_its_columns(self, cache):
        """The shape can change between syncs — a column added upstream, or a
        table re-read after an ALTER."""
        cache.put_sample(1, [{"old_column": 1}])
        assert cache.distinct_count(1, "old_column") == 1
        cache.put_sample(1, [{"new_column": "x"}])

        assert cache.distinct_count(1, "new_column") == 1
        assert cache.distinct_count(1, "old_column") == 0, "stale column still reported"

    def test_row_count_is_recomputed_after_a_rewrite(self, cache):
        """row_count is memoised too, so a rewrite must clear it or every later
        caller reads the previous sync's size."""
        cache.put_sample(1, [{"a": i} for i in range(10)])
        assert cache.row_count(1) == 10
        cache.put_sample(1, [{"a": i} for i in range(3)])
        assert cache.row_count(1) == 3, "row_count memo survived a rewrite"

    def test_distinct_count_is_recomputed_after_a_rewrite(self, cache):
        cache.put_sample(1, [{"a": 1}, {"a": 2}, {"a": 3}])
        assert cache.distinct_count(1, "a") == 3
        cache.put_sample(1, [{"a": 1}, {"a": 1}])
        assert cache.distinct_count(1, "a") == 1, "distinct_count memo survived a rewrite"

    def test_overlap_reflects_a_rewritten_sample(self, cache):
        """The end-to-end version: the measurement inference actually runs."""
        cache.put_sample(1, [{"cid": 1}, {"cid": 2}])
        cache.put_sample(2, [{"id": 1}, {"id": 2}])
        assert cache.overlap(1, "cid", 2, "id") == 1.0

        cache.put_sample(2, [{"id": 99}])
        assert cache.overlap(1, "cid", 2, "id") == 0.0, "overlap used a stale sample"

    def test_an_empty_sample_still_registers_as_existing(self, cache):
        """An empty object is stored as a placeholder table with one marker
        column. It must read as present-but-empty, not as absent — the two mean
        different things to the deprecation heuristic."""
        cache.put_sample(1, [])
        assert cache.has_sample(1) is True
        assert cache.row_count(1) == 0
        assert cache.get_sample(1) == []

    def test_the_memo_agrees_with_the_database_it_describes(self, cache):
        """Cross-checks the memo against live information_schema queries, so a
        divergence is caught here rather than as a wrong overlap ratio."""
        cache.put_sample(1, [{"a": 1, "b": 2}])
        cache.put_sample(2, [{"c": 3}])
        cache.drop_sample(1)
        cache.put_sample(3, [{"d": 4}])

        with cache._lock:
            memo = {t: set(c) for t, c in cache._schema().items()}
            live: dict[str, set] = {}
            for table, column in cache._conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns"
            ).fetchall():
                live.setdefault(table, set()).add(column)

        for table, columns in live.items():
            assert memo.get(table) == columns, f"memo disagrees about {table}"

    def test_the_memo_is_built_once_not_per_call(self, cache):
        """The whole point. Without this the change is decoration.

        Asserted on the memo's object identity rather than by counting queries:
        DuckDB's connection is a C object whose `execute` cannot be patched, and
        identity is the stronger claim anyway — the map is not merely cheap to
        rebuild, it is not rebuilt at all.
        """
        cache.put_sample(1, [{"cid": 1}])
        cache.put_sample(2, [{"id": 1}])

        cache.overlap(1, "cid", 2, "id")        # builds the memo
        built_once = cache._schema_map
        assert built_once is not None

        for _ in range(25):
            cache.overlap(1, "cid", 2, "id")

        # 25 overlaps used to mean 100 information_schema round trips, measured
        # at 20.5ms of every 23.8ms call.
        assert cache._schema_map is built_once, (
            "the schema memo was rebuilt during a run of overlap() calls"
        )

    def test_a_write_does_rebuild_it(self, cache):
        """The other half: cheap is worthless if it is also wrong."""
        cache.put_sample(1, [{"cid": 1}])
        cache.overlap(1, "cid", 1, "cid")
        before = cache._schema_map

        cache.put_sample(2, [{"id": 1}])
        assert cache._schema_map is not before, "a write left the memo in place"
