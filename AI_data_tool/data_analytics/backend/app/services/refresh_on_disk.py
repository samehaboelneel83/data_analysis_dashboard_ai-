"""Adding new rows to a dataset that is too large to hold in memory.

An incremental refresh used to read the whole file, join the new rows to it
and write it back -- impossible once the file is larger than memory, so such a
dataset was reloaded whole on every run. Here the file never enters memory:
DuckDB reads the live file and the new rows from disk and writes the merged
file beside it. Same rules as the in-memory path (services/dataset_refresh):
an incoming row replaces the held row with its key, the last of two incoming
rows with one key wins, a row with no key is never matched, and the file keeps
its own columns.
"""
from __future__ import annotations

import os

import pandas as pd


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _lit(path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def schema(path) -> list[tuple[str, str]]:
    """(column, DuckDB type) of a parquet file, read from its footer."""
    import duckdb
    con = duckdb.connect()
    try:
        return [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({_lit(path)})").fetchall()]
    finally:
        con.close()


def key_sql(column: str, kind: str) -> str:
    """A key as comparable text -- `data_checks.key_text` in SQL: 7 and 7.0
    are one key, text is trimmed, an empty key stays empty."""
    c = _q(column)
    kind = kind.upper()
    if any(kind.startswith(p) for p in ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT",
                                        "USMALLINT", "UINTEGER", "UBIGINT")):
        return f"CAST({c} AS VARCHAR)"
    if any(kind.startswith(p) for p in ("DOUBLE", "FLOAT", "REAL", "DECIMAL")):
        return (f"CASE WHEN {c} IS NULL OR isnan(CAST({c} AS DOUBLE)) THEN NULL "
                f"WHEN CAST({c} AS DOUBLE) = floor(CAST({c} AS DOUBLE)) AND abs(CAST({c} AS DOUBLE)) < 9e15 "
                f"THEN CAST(CAST({c} AS BIGINT) AS VARCHAR) ELSE CAST({c} AS VARCHAR) END")
    return f"trim(CAST({c} AS VARCHAR))"


def summarise(con, path, columns: list[str]) -> tuple[int, dict[str, float], pd.DataFrame]:
    """(rows, how empty each column is in percent, a random sample) of a file."""
    from ..core.config import settings
    src = f"read_parquet({_lit(path)})"
    rows = int(con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0])
    counts = con.execute("SELECT " + ", ".join(f"COUNT({_q(c)})" for c in columns) + f" FROM {src}").fetchone() \
        if columns else ()
    take = int(getattr(settings, "discovery_sample_rows", 200_000) or 200_000)
    sample = con.execute(f"SELECT * FROM {src} USING SAMPLE reservoir({take} ROWS) REPEATABLE (7)").fetch_df() \
        if rows > take else con.execute(f"SELECT * FROM {src}").fetch_df()
    missing = {c: round(100.0 * (rows - int(k)) / rows, 2) if rows else 0.0 for c, k in zip(columns, counts)}
    return rows, missing, sample


def _memory_mb() -> int:
    """What a merge may hold in memory: half of what one dataset may take,
    between 1 and 4 GB."""
    from . import memory_guard
    free = memory_guard.free_bytes()
    allowed = memory_guard.share() or 0.6
    if free is None:
        return 2048
    return int(max(1024, min(free * allowed / 2 / 2**20, 4096)))


def merge(live, new, stage: str, *, key_column: str | None = None, alive_keys: pd.Series | None = None,
          cursor_column: str | None = None) -> dict:
    """The live file with `new` added, written to `<stage>/merged.parquet`.

    `new` is a frame, or the path of a parquet file of new rows, or None.
    `alive_keys` (with a key): rows whose key is not among them are removed.
    `path` is None when nothing changed: the live file stands as it is.
    Returns {path, rows, missing, sample, rows_new, rows_updated, rows_deleted,
    cursor}. Raises when a new value cannot be stored as the file's column
    type -- the caller reloads the whole table instead."""
    import duckdb
    from ..core.config import settings
    held = schema(live)
    names = [c for c, _ in held]
    new_path = None
    if isinstance(new, pd.DataFrame):
        if len(new):
            new_path = os.path.join(stage, "new_rows.parquet")
            new.to_parquet(new_path, index=False)
    elif new:
        new_path = str(new)
    out = os.path.join(stage, "merged.parquet")
    con = duckdb.connect()
    try:
        con.execute(f"SET threads TO {max(1, int(getattr(settings, 'widget_duckdb_threads', 2)))}")
        con.execute("SET preserve_insertion_order TO true")
        # Past this much it works from disk instead of memory: measured at
        # 200,000,000 rows, an unlimited merge took 10 GB.
        con.execute(f"SET memory_limit = '{_memory_mb()}MB'")
        con.execute(f"SET temp_directory = {_lit(os.path.join(stage, 'duck_tmp'))}")
        old_src = f"read_parquet({_lit(live)})"
        keyed = bool(key_column and key_column in names)
        kind = dict(held).get(key_column, "VARCHAR") if keyed else "VARCHAR"
        rows_new = rows_updated = rows_deleted = 0
        where: list[str] = []
        new_select = None
        if new_path:
            arrived = dict(schema(new_path))
            rows_new = int(con.execute(f"SELECT COUNT(*) FROM read_parquet({_lit(new_path)})").fetchone()[0])
            cols = ", ".join((f"CAST({_q(c)} AS {t}) AS {_q(c)}" if c in arrived else f"CAST(NULL AS {t}) AS {_q(c)}")
                             for c, t in held)
            con.execute(f"CREATE TEMP VIEW incoming AS SELECT {cols}, file_row_number AS __at FROM "
                        f"read_parquet({_lit(new_path)}, file_row_number = true)")
            new_select = "SELECT " + ", ".join(_q(c) for c in names) + " FROM incoming"
            if keyed and key_column in arrived:
                k = key_sql(key_column, kind)
                con.execute(f"CREATE TEMP TABLE incoming_keys AS SELECT DISTINCT {k} AS k FROM incoming WHERE {k} IS NOT NULL")
                rows_updated = int(con.execute(
                    f"SELECT COUNT(*) FROM incoming WHERE {k} IN (SELECT {k} FROM {old_src} WHERE {k} IS NOT NULL)"
                ).fetchone()[0])
                where.append(f"({k} IS NULL OR {k} NOT IN (SELECT k FROM incoming_keys))")
                # Two incoming rows with one key: the later one stands.
                new_select += (f" QUALIFY {k} IS NULL OR row_number() OVER (PARTITION BY {k} ORDER BY __at DESC) = 1"
                               " ORDER BY __at")
        if keyed and alive_keys is not None and len(alive_keys):
            from .data_checks import key_text
            alive = pd.DataFrame({"k": sorted(set(key_text(alive_keys)))})
            con.register("alive_frame", alive)
            con.execute("CREATE TEMP TABLE alive AS SELECT k FROM alive_frame")
            k = key_sql(key_column, kind)
            gone = f"({k} IS NOT NULL AND {k} NOT IN (SELECT k FROM alive))"
            rows_deleted = int(con.execute(f"SELECT COUNT(*) FROM {old_src} WHERE {gone}"
                                           + (" AND " + " AND ".join(where) if where else "")).fetchone()[0])
            where.append(f"NOT {gone}")
            if new_select:
                # An incoming row the source has since deleted goes too.
                gone_new = int(con.execute(f"SELECT COUNT(*) FROM ({new_select}) WHERE {gone}").fetchone()[0])
                rows_deleted += gone_new
                new_select = f"SELECT * FROM ({new_select}) WHERE NOT {gone}"
        if not new_select and not rows_deleted:
            # Nothing new and nothing gone -- the commonest run. The file is
            # left exactly as it is rather than written out again.
            out = None
        else:
            old_select = "SELECT " + ", ".join(_q(c) for c in names) + f" FROM {old_src}" \
                + (" WHERE " + " AND ".join(where) if where else "")
            both = old_select + (f" UNION ALL SELECT * FROM ({new_select})" if new_select else "")
            con.execute(f"COPY ({both}) TO {_lit(out)} (FORMAT parquet, ROW_GROUP_SIZE 1000000)")
        now = out or str(live)
        rows, missing, sample = summarise(con, now, names)
        cursor = None
        if cursor_column and cursor_column in names:
            cursor = con.execute(f"SELECT max({_q(cursor_column)}) FROM read_parquet({_lit(now)})").fetchone()[0]
    finally:
        con.close()
        import shutil
        shutil.rmtree(os.path.join(stage, "duck_tmp"), ignore_errors=True)
        if new_path and new_path.endswith("new_rows.parquet"):
            try:
                os.remove(new_path)
            except OSError:
                pass
    return {"path": out, "rows": rows, "missing": missing, "sample": sample, "rows_new": rows_new,
            "rows_updated": rows_updated, "rows_deleted": rows_deleted, "cursor": cursor}


def unique_faults(path, column: str) -> tuple[int, int]:
    """(repeated values beyond the first, distinct values that repeat) on every row."""
    import duckdb
    con = duckdb.connect()
    try:
        c = _q(column)
        return tuple(int(v or 0) for v in con.execute(
            f"SELECT COALESCE(SUM(n - 1), 0), COUNT(*) FROM (SELECT COUNT(*) AS n FROM read_parquet({_lit(path)}) "
            f"WHERE {c} IS NOT NULL GROUP BY {c} HAVING COUNT(*) > 1)").fetchone())
    finally:
        con.close()


def outside_list(path, column: str, allowed: list[str]) -> tuple[int, int]:
    """(rows whose value is not in the list, how many different such values) on every row."""
    import duckdb
    con = duckdb.connect()
    try:
        c = _q(column)
        con.register("allowed_frame", pd.DataFrame({"v": [str(a) for a in allowed]}))
        return tuple(int(v or 0) for v in con.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT CAST({c} AS VARCHAR)) FROM read_parquet({_lit(path)}) "
            f"WHERE {c} IS NOT NULL AND CAST({c} AS VARCHAR) NOT IN (SELECT v FROM allowed_frame)").fetchone())
    finally:
        con.close()
