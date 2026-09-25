"""Index recommendations from what the platform has watched itself run.

DirectQuery latency on a large table is the customer's index situation, not
anything in this codebase. Measured 2026-09-12 at 10M rows: an index on the
FILTERED column cut a governed query 0.95s -> 0.71s; an index on the GROUPED
column changed nothing (1.08s -> 1.10s), because a full aggregation scans
either way. So the advice is built from the filter and RLS columns recorded
with each run (`QueryRun.filter_columns`), ranked by how often and how slowly
they ran, and it never says "index what you group by".

Recommendations only. Nothing here creates an index on a customer database;
the statement is offered for the customer's DBA to paste.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from . import engines

#: Below this many runs the recommender says nothing about a column: one slow
#: widget somebody opened once is not a pattern.
DEFAULT_MIN_RUNS = 3

#: The leading column of every index on the named tables, from the catalog.
#: `indkey[0]` is the first indexed attribute; 0 means an expression index,
#: which has no plain leading column and is left out by the WHERE. Read this
#: way rather than parsed from `pg_indexes.indexdef`: a regex read
#: `(region DESC)` as a column called "region DESC" and reported an index
#: that existed as missing.
_CATALOG_SQL = (
    "SELECT n.nspname, c.relname, a.attname "
    "FROM pg_index i "
    "JOIN pg_class c ON c.oid = i.indrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0] "
    "WHERE c.relname = ANY(:names) AND i.indkey[0] <> 0"
)


def _pairs_from_catalog(rows, tables: set[str]) -> set[tuple[str, str]]:
    """(table as the dataset names it, leading column) from catalog rows of
    (schema, table, attname). A dataset's `orders` matches any schema's
    `orders`; its `sales.orders` matches only that schema's."""
    out: set[tuple[str, str]] = set()
    for schema, table, col in rows:
        if not col:
            continue
        for t in tables:
            if t == table or t == f"{schema}.{table}":
                out.add((t, col))
    return out


def leading_index_columns(cfg: dict, tables: set[str]) -> set[tuple[str, str]] | None:
    """Every (table, leading column) indexed on the customer's side.

    None means it could not be asked at all -- the source is not the Postgres
    family, the only dialect this reads (and the one the measurement was made
    on). The caller reports that as `unsupported`, distinct from `unavailable`
    (a Postgres source that did not answer), and offers no statement: a
    Postgres CREATE INDEX is wrong syntax on MySQL.
    """
    if engines.connectors.sql_family_of(cfg) != "postgresql":
        return None
    if not tables:
        return set()
    engine = engines.get_metadata_engine(cfg)
    with engine.connect() as conn:
        rows = conn.execute(text(_CATALOG_SQL),
                            {"names": [t.split(".")[-1] for t in tables]}).fetchall()
    return _pairs_from_catalog(rows, tables)

def create_index_statement(table: str, column: str) -> str:
    qualified = ".".join(f'"{part}"' for part in table.split("."))
    return f'CREATE INDEX ON {qualified} ("{column}");'


def advise(runs: list[dict], indexed: set[tuple[str, str]] | None,
           min_runs: int = DEFAULT_MIN_RUNS) -> dict:
    """Rank (table, filter column) pairs from recorded runs.

    `runs` are dicts with source_table, filter_columns, group_column and
    duration_ms -- QueryRun rows, or anything shaped like them. `group_column`
    is deliberately never read: see the module docstring.
    """
    stats: dict[tuple[str, str], list[int]] = defaultdict(list)
    for r in runs:
        table = r.get("source_table")
        if not table:
            continue
        for col in r.get("filter_columns") or []:
            stats[(table, col)].append(int(r.get("duration_ms") or 0))

    by_table: dict[str, list[dict]] = defaultdict(list)
    for (table, col), durations in stats.items():
        n = len(durations)
        if n < min_runs:
            continue
        avg = sum(durations) / n
        # `indexed is None`: the dialect could not be asked. The column is still
        # hot, so it is still recommended -- but with no index flag and no
        # statement, which would be Postgres syntax on a database that is not.
        is_indexed = None if indexed is None else (table, col) in indexed
        by_table[table].append({
            "column": col, "runs": n, "avg_ms": round(avg),
            "score": round(n * avg),
            "indexed": is_indexed, "recommended": not is_indexed,
            "statement": (create_index_statement(table, col)
                          if indexed is not None and not is_indexed else None),
        })
    tables = []
    for table, cols in by_table.items():
        cols.sort(key=lambda c: -c["score"])
        tables.append({"table": table, "columns": cols})
    tables.sort(key=lambda t: -max(c["score"] for c in t["columns"]))
    return {"tables": tables, "min_runs": min_runs}
