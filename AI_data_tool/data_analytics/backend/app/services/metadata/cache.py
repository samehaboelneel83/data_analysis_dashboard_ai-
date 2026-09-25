"""Stage 3 storage — the DuckDB sample cache.

WHY THIS EXISTS
----------------
ARCHITECTURE.md, on the two planes: "The agent iterates — profiles, guesses a
join, fails, retries. If every iteration hits the customer's production
database, you get blocked from their infrastructure within weeks."

So structure is learned once per sync and then interrogated locally. Stage 4 is
the demanding customer: it compares every plausible column pair, which is
quadratic in column count, and each comparison is a set-intersection over
distinct values. As a local DuckDB join that is milliseconds and costs the
customer nothing. As N queries against their warehouse it is a phone call.

DuckDB rather than pandas because these ARE joins and aggregations, and because
the file persists across restarts — a worker that comes back up does not need to
re-sample every source before it can infer anything.

WHAT THIS IS NOT
-----------------
Not a system of record. Everything here is reconstructible by re-sampling, which
is what makes LRU eviction under a byte budget safe: the worst case for evicting
too eagerly is a slower next sync, never lost data.
"""
from __future__ import annotations

import logging
import os
import threading

import duckdb

logger = logging.getLogger(__name__)

#: Bookkeeping for eviction. Separate from the sample tables so that dropping a
#: sample and forgetting its metadata cannot get out of step.
_META_TABLE = "_cache_meta"


def _table_name(entity_id: int, namespace: str = "s") -> str:
    """One cache table per entity.

    The namespace keeps two id spaces apart: source-catalog objects ("o") and
    user-created datasets ("s") both number from 1, so without it object 3 and
    dataset 3 would silently share a sample. The id is coerced to int and the
    namespace comes from code, never from a caller, so the name is structurally
    safe to interpolate.
    """
    return f"{namespace}_{int(entity_id)}"


def _quote(identifier: str) -> str:
    """Quote a column name for DuckDB.

    Sample column names come from a customer's catalog and routinely include
    spaces, reserved words and mixed case. Doubling any embedded quote is the
    standard SQL escape and keeps the name faithful rather than mangling it —
    these names have to match the catalog exactly for inference to line up.
    """
    return '"' + identifier.replace('"', '""') + '"'


class SampleCache:
    """A DuckDB-backed store of per-dataset row samples.

    Guarded by a lock: DuckDB connections are not thread-safe, and this is
    reached from the sync pipeline's worker threads.
    """

    def __init__(self, path: str, max_mb: int = 512, namespace: str = "s") -> None:
        self.path = path
        self.max_bytes = max_mb * 1024 * 1024
        self.namespace = namespace
        self._lock = threading.Lock()

        # The cache's own schema, memoised. See _schema() for why this is worth
        # a cache rather than a query: the four existence checks inside
        # overlap() measured 20.5ms of its 23.8ms, repeated for every candidate
        # pair, about a schema that cannot change mid-stage.
        #   {table name: {column names}} -- None until first built.
        self._schema_map: dict[str, set[str]] | None = None
        # Derived counts, memoised for the same reason: infer_keys recomputes
        # both sides of every pair in its innermost loop.
        self._row_counts: dict[str, int] = {}
        self._distinct_counts: dict[tuple[str, str], int] = {}

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._conn = duckdb.connect(path)
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_META_TABLE} ("
            " dataset_id BIGINT PRIMARY KEY,"
            " rows BIGINT,"
            " bytes BIGINT,"
            " last_used_at TIMESTAMP"
            ")"
        )

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # ── writing ────────────────────────────────────────────────────────────

    def put_sample(self, dataset_id: int, rows: list[dict]) -> None:
        """Store (replacing) the sample for one dataset.

        Replace rather than append: a nightly resync would otherwise double the
        sample every night until the budget evicted it, and the duplicate values
        would skew nothing but waste everything.

        Rows are normalised onto the union of their keys first. Sources return
        ragged rows more often than they should, and a missing key becomes NULL
        rather than shifting a row's values into the wrong columns.
        """
        table = _table_name(dataset_id, self.namespace)
        with self._lock:
            self._invalidate(dataset_id)
            self._conn.execute(f"DROP TABLE IF EXISTS {table}")

            if not rows:
                # An empty table is a fact worth recording — it is one of the
                # deprecation signals Stage 5 looks for.
                self._conn.execute(f"CREATE TABLE {table} (_empty BOOLEAN)")
                self._touch(dataset_id, rows=0, nbytes=0)
                return

            columns: list[str] = []
            for row in rows:
                for key in row:
                    if key not in columns:
                        columns.append(key)

            normalised = [[row.get(c) for c in columns] for row in rows]

            # Register as an Arrow-compatible relation via a parameterised
            # VALUES insert, so no cell value is ever interpolated into SQL.
            col_defs = ", ".join(f"{_quote(c)} VARCHAR" for c in columns)
            self._conn.execute(f"CREATE TABLE {table} ({col_defs})")
            placeholders = ", ".join("?" for _ in columns)
            self._conn.executemany(
                f"INSERT INTO {table} VALUES ({placeholders})",
                [[None if v is None else str(v) for v in values] for values in normalised],
            )

            nbytes = sum(
                len(str(v)) for values in normalised for v in values if v is not None
            )
            self._touch(dataset_id, rows=len(rows), nbytes=nbytes)

    def _meta_key(self, entity_id: int) -> int:
        """Bookkeeping rows share one table across namespaces, so object ids are
        offset to keep them from colliding with dataset ids."""
        return int(entity_id) + (10_000_000 if self.namespace == "o" else 0)

    def _touch(self, dataset_id: int, *, rows: int, nbytes: int) -> None:
        """Record size and recency. Caller holds the lock."""
        self._conn.execute(f"DELETE FROM {_META_TABLE} WHERE dataset_id = ?", [self._meta_key(dataset_id)])
        self._conn.execute(
            f"INSERT INTO {_META_TABLE} VALUES (?, ?, ?, now())",
            [self._meta_key(dataset_id), rows, nbytes],
        )

    # ── reading ────────────────────────────────────────────────────────────

    def has_sample(self, dataset_id: int) -> bool:
        with self._lock:
            return self._table_exists(_table_name(dataset_id, self.namespace))

    def _schema(self) -> dict[str, set[str]]:
        """Every cached table and its columns, read once. Caller holds the lock.

        One `information_schema.columns` scan replaces two per-table and two
        per-column point lookups on every single call that needs them. On the
        measured source that is one query in place of roughly fifty thousand.
        """
        if self._schema_map is None:
            found: dict[str, set[str]] = {}
            for table, column in self._conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns"
            ).fetchall():
                found.setdefault(table, set()).add(column)
            # A table with no columns cannot appear above, so tables are listed
            # separately too — the placeholder written for an empty object has
            # exactly one column, but an empty CREATE TABLE would otherwise
            # vanish from the map and read as "does not exist".
            for (table,) in self._conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall():
                found.setdefault(table, set())
            self._schema_map = found
        return self._schema_map

    def _invalidate(self, dataset_id: int | None = None) -> None:
        """Forget the memo. Caller holds the lock.

        Called by the only two methods that can change what the cache contains.
        Dropping the whole map rather than patching it: the map costs one query
        to rebuild, and a patch that misses a case would produce a cache that
        confidently reports the wrong schema — far worse than a rebuild.
        """
        self._schema_map = None
        if dataset_id is None:
            self._row_counts.clear()
            self._distinct_counts.clear()
            return
        table = _table_name(dataset_id, self.namespace)
        self._row_counts.pop(table, None)
        for key in [k for k in self._distinct_counts if k[0] == table]:
            del self._distinct_counts[key]

    def _table_exists(self, table: str) -> bool:
        """Caller holds the lock."""
        return table in self._schema()

    def get_sample(self, dataset_id: int) -> list[dict]:
        """Return the cached rows, and mark the sample as recently used."""
        table = _table_name(dataset_id, self.namespace)
        with self._lock:
            if not self._table_exists(table):
                return []
            cursor = self._conn.execute(f"SELECT * FROM {table}")
            names = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            self._conn.execute(
                f"UPDATE {_META_TABLE} SET last_used_at = now() WHERE dataset_id = ?",
                [self._meta_key(dataset_id)],
            )

        if names == ["_empty"]:
            return []
        return [dict(zip(names, row)) for row in rows]

    def row_count(self, dataset_id: int) -> int:
        """How many rows were cached for this entity.

        Required by foreign-key inference, which compares it against a column's
        distinct count to decide whether that column is unique enough to be the
        PARENT side of a key. Without it the uniqueness check silently passes
        for everything, and inference will happily propose a join onto a column
        full of repeats — which multiplies rows and quietly corrupts every
        aggregate downstream.
        """
        table = _table_name(dataset_id, self.namespace)
        with self._lock:
            memo = self._row_counts.get(table)
            if memo is not None:
                return memo
            if not self._table_exists(table):
                return 0
            # The placeholder written for a genuinely empty object. Read from
            # the memoised schema rather than a second query.
            if self._schema().get(table) == {"_empty"}:
                self._row_counts[table] = 0
                return 0
            got = self._conn.execute(f"SELECT count(*) FROM {table}").fetchone()
            count = int(got[0]) if got else 0
            self._row_counts[table] = count
        return count

    def distinct_count(self, dataset_id: int, column: str) -> int:
        """Distinct non-null values, for cardinality-direction decisions."""
        table = _table_name(dataset_id, self.namespace)
        key = (table, column)
        with self._lock:
            memo = self._distinct_counts.get(key)
            if memo is not None:
                return memo
            if not self._table_exists(table) or not self._has_column(table, column):
                return 0
            got = self._conn.execute(
                f"SELECT count(DISTINCT {_quote(column)}) FROM {table} "
                f"WHERE {_quote(column)} IS NOT NULL"
            ).fetchone()
            count = int(got[0]) if got else 0
            self._distinct_counts[key] = count
        return count

    def _has_column(self, table: str, column: str) -> bool:
        """Caller holds the lock."""
        return column in self._schema().get(table, ())

    # ── the measurement Stage 4 runs on ────────────────────────────────────

    def overlap(
        self, child_dataset_id: int, child_column: str,
        parent_dataset_id: int, parent_column: str,
    ) -> float:
        """Fraction of the child's distinct values that appear in the parent.

        DIRECTIONAL, deliberately. A foreign key asserts that every CHILD value
        exists in the parent, never the reverse. Measuring the parent side would
        score a small lookup table against a huge fact table near zero and throw
        away a real key.

        NULLs are excluded from the child side: a nullable foreign key is still a
        foreign key, and counting nulls as misses would push every optional
        relationship below the threshold.

        Values are compared as text because a source may hand back ids as VARCHAR
        on one side and BIGINT on the other; a type-strict join would score that
        pair zero and silently lose the relationship.

        A missing sample or column scores 0.0 rather than raising — Stage 4 asks
        about many pairs that do not exist, and that is a normal answer, not an
        error.
        """
        child_table = _table_name(child_dataset_id, self.namespace)
        parent_table = _table_name(parent_dataset_id, self.namespace)

        with self._lock:
            if not (self._table_exists(child_table) and self._table_exists(parent_table)):
                return 0.0
            if not (self._has_column(child_table, child_column)
                    and self._has_column(parent_table, parent_column)):
                return 0.0

            cc, pc = _quote(child_column), _quote(parent_column)
            got = self._conn.execute(
                f"WITH c AS ("
                f"  SELECT DISTINCT CAST({cc} AS VARCHAR) AS v FROM {child_table}"
                f"  WHERE {cc} IS NOT NULL"
                f"), p AS ("
                f"  SELECT DISTINCT CAST({pc} AS VARCHAR) AS v FROM {parent_table}"
                f"  WHERE {pc} IS NOT NULL"
                f") SELECT (SELECT count(*) FROM c), "
                f"         (SELECT count(*) FROM c WHERE c.v IN (SELECT v FROM p))"
            ).fetchone()

        if not got or not got[0]:
            return 0.0
        return round(int(got[1]) / int(got[0]), 6)

    # ── budget ─────────────────────────────────────────────────────────────

    def total_bytes(self) -> int:
        with self._lock:
            got = self._conn.execute(f"SELECT coalesce(sum(bytes), 0) FROM {_META_TABLE}").fetchone()
        return int(got[0]) if got else 0

    def drop_sample(self, dataset_id: int) -> None:
        """Remove one sample. Absent is not an error — eviction and an explicit
        drop can race, and both outcomes are the same."""
        with self._lock:
            self._invalidate(dataset_id)
            self._conn.execute(f"DROP TABLE IF EXISTS {_table_name(dataset_id, self.namespace)}")
            self._conn.execute(f"DELETE FROM {_META_TABLE} WHERE dataset_id = ?", [self._meta_key(dataset_id)])

    def evict_if_over_budget(self) -> list[int]:
        """Evict least-recently-used samples until under budget.

        Returns the evicted dataset ids so the sync run can record what it lost
        — a sample silently disappearing would make the next run's inference
        results look inexplicably different.

        The most recently touched entry is never evicted, even at a zero budget:
        evicting what was just written would make the cache useless rather than
        merely small.
        """
        evicted: list[int] = []
        while self.total_bytes() > self.max_bytes:
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT dataset_id FROM {_META_TABLE} ORDER BY last_used_at ASC"
                ).fetchall()
            if len(rows) <= 1:
                break
            victim = int(rows[0][0])
            if self.namespace == "o":
                victim -= 10_000_000
            self.drop_sample(victim)
            evicted.append(victim)

        if evicted:
            logger.info("metadata cache evicted %d sample(s): %s", len(evicted), evicted)
        return evicted


_default: SampleCache | None = None
_object_cache: SampleCache | None = None
_default_lock = threading.Lock()


def get_cache() -> SampleCache:
    """The process-wide cache, opened lazily.

    One DuckDB connection per process: the file is not safe to open twice from
    the same process, and the connection is cheap to hold open.
    """
    global _default
    with _default_lock:
        if _default is None:
            from ...core.config import settings
            _default = SampleCache(
                path=settings.duckdb_cache_path,
                max_mb=settings.metadata_cache_max_mb,
            )
        return _default


def get_object_cache() -> SampleCache:
    """The cache for SOURCE CATALOG objects, as opposed to user datasets.

    Same file, separate namespace. Both id spaces start at 1, so sharing one
    namespace would let a catalog object and an unrelated dataset overwrite each
    other's samples — and the foreign-key inference measured against them would
    reflect whichever wrote last.
    """
    global _object_cache
    with _default_lock:
        if _object_cache is None:
            from ...core.config import settings
            _object_cache = SampleCache(
                path=settings.duckdb_cache_path,
                max_mb=settings.metadata_cache_max_mb,
                namespace="o",
            )
        return _object_cache
