import os
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import create_engine, inspect, text
import httpx

from . import connectors
from .sql_safety import ensure_read_only


def _build_url(cfg: dict) -> str:
    """Kept as the module-level seam every SQL layer (and the tests) monkeypatch;
    the body now lives in the connector registry so all types share one path."""
    return connectors.build_url(cfg)


def _limit_sql(db_type: str, table: str, limit: int, schema: str | None = None) -> str:
    # An embedded quote is doubled, as SQL requires: interpolated raw, a table
    # named  x" UNION ...  would leave its identifier and become SQL.
    q = lambda name: '"' + str(name).replace('"', '""') + '"'  # noqa: E731
    full = f'{q(schema)}.{q(table)}' if schema else q(table)
    if db_type == 'sqlserver':
        return f"SELECT TOP {limit} * FROM {full}"
    elif db_type == 'oracle':
        return f"SELECT * FROM {full} FETCH FIRST {limit} ROWS ONLY"
    else:
        return f"SELECT * FROM {full} LIMIT {limit}"


def _safe_val(v):
    if v != v:  # NaN
        return None
    if hasattr(v, 'item'):
        return v.item()
    return v


def _access_path(cfg: dict) -> str:
    """The .mdb/.accdb this source points at.

    Access has no SQLAlchemy dialect on Linux (the ACE/Jet provider is
    Windows-only), so every function below special-cases it the same way `api`
    is special-cased: there is no engine and no URL, just a file read with the
    mdbtools CLIs.
    """
    return (cfg.get('filepath') or '').strip()


def _reject_access_query(query: str | None) -> None:
    """mdbtools has no usable SQL engine (`mdb-sql` is an interactive shell),
    so a custom query cannot be honoured. Saying so beats returning the whole
    table and quietly ignoring what the user asked for."""
    if query and query.strip():
        raise ValueError("Custom SQL is not supported for Microsoft Access "
                         "sources — choose a table instead")


class MissingDatabaseFile(Exception):
    """A file-based connection (SQLite, DuckDB) whose file is not there.

    5.3: SQLite's own text is "unable to open database file", which names no
    file and suggests no fix; Browse and Test showed it raw. Said once, with
    the path and what to do."""


def _check_file_source(cfg: dict) -> None:
    import os
    if cfg.get('type') not in ('sqlite', 'duckdb'):
        return
    path = (cfg.get('filepath') or '').strip()
    if cfg.get('type') == 'duckdb' and not path:
        return  # in-memory
    if not path or not os.path.exists(path):
        raise MissingDatabaseFile(
            f"Database file not found at {path or '(no path given)'} — edit the connection "
            f"and point it at the file.")


def test_connection(cfg: dict) -> dict:
    if cfg['type'] == 'api':
        return _test_api(cfg)
    if cfg['type'] == 'access':
        from . import mdb
        try:
            mdb.list_tables(_access_path(cfg))
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    try:
        _check_file_source(cfg)
        url = _build_url(cfg)
        engine = create_engine(url, connect_args=connectors.connect_args(cfg))
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _test_api(cfg: dict) -> dict:
    try:
        resp = _api_request(cfg, timeout=8)
        resp.raise_for_status()
        return {'ok': True, 'status': resp.status_code}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def list_tables(cfg: dict) -> list[dict]:
    if cfg['type'] == 'api':
        return []
    if cfg['type'] == 'access':
        from . import mdb
        return [{'name': t, 'kind': 'table'}
                for t in mdb.list_tables(_access_path(cfg))]
    _check_file_source(cfg)
    url = _build_url(cfg)
    engine = create_engine(url, connect_args=connectors.connect_args(cfg))
    try:
        insp   = inspect(engine)
        schema = cfg.get('schema') or None
        tables = [{'name': t, 'kind': 'table'} for t in insp.get_table_names(schema=schema)]
        views  = [{'name': v, 'kind': 'view'}  for v in insp.get_view_names(schema=schema)]
        return tables + views
    finally:
        engine.dispose()


def preview_table(cfg: dict, table: str | None, query: str | None, limit: int = 200) -> dict:
    if cfg['type'] == 'api':
        return _fetch_api(cfg, limit)
    if cfg['type'] == 'access':
        from . import mdb
        _reject_access_query(query)
        df = mdb.read_table(_access_path(cfg), table).head(limit)
        return {
            'columns': list(df.columns),
            'rows':    [[_safe_val(v) for v in row] for row in df.values.tolist()],
            'total':   len(df),
        }
    _check_file_source(cfg)
    url    = _build_url(cfg)
    engine = create_engine(url, connect_args=connectors.connect_args(cfg))
    try:
        # Hand-written SQL must be ONE read (sql_safety.ensure_read_only): the
        # SQL tab and custom-SQL imports went to the database unchecked.
        sql = (ensure_read_only(query, connectors.sql_family_of(cfg) or cfg['type']) if query and query.strip()
               else _limit_sql(connectors.sql_family_of(cfg) or cfg['type'], table, limit, cfg.get('schema')))
        df  = pd.read_sql(_driver_sql(sql, engine), engine)
        df  = df.head(limit)
        return {
            'columns': list(df.columns),
            'rows':    [[_safe_val(v) for v in row] for row in df.values.tolist()],
            'total':   len(df),
        }
    finally:
        engine.dispose()


class ImportTooLarge(ValueError):
    """The source has more rows than an import may hold (settings.import_row_cap).

    E07: a TABLE import used to stop silently at 100,000 rows and the dataset
    looked complete -- a partial dataset masquerading as ready. Refusing, with
    the way forward, is the same call the cap already makes everywhere else."""


def _too_large(cap: int) -> ImportTooLarge:
    return ImportTooLarge(
        f"The source returns more than {cap:,} rows, the import limit. Narrow it with a "
        "query (a filter or a date range), or ask an administrator to raise IMPORT_ROW_CAP.")


#: An import in memory at its worst, against the rows as they arrived: the
#: chunks and the joined table exist together, then the file is written.
#: Measured by scripts/bench_import.py: about three times the table.
IMPORT_PEAK = 3.0


def _import_cap() -> int:
    from ..core.config import settings
    return int(settings.import_row_cap or 0)


def _checked(df: pd.DataFrame, cap: int) -> pd.DataFrame:
    if cap and len(df) > cap:
        raise _too_large(cap)
    return df


def _driver_sql(sql: str, engine) -> str:
    """SQL text as the DB-API driver must receive it. psycopg2 and pymysql use
    %-placeholders, so a literal % (every LIKE '%x%') has to be written %%:
    without this, any hand-written query with a LIKE failed on PostgreSQL and
    MySQL with "immutabledict is not a sequence". Drivers with other
    placeholder styles (SQLite's ?) take the text as it is."""
    if getattr(engine.dialect, "paramstyle", "") in ("format", "pyformat"):
        return sql.replace("%", "%%")
    return sql


#: Rows fetched from a source at a time.
CHUNK_ROWS = 100_000


@dataclass
class Streamed:
    """An import that was written to disk as it arrived, instead of a frame:
    the parquet file, how many rows it holds, a random sample of them (for the
    column types and the profile), and how empty each column is -- counted on
    every row, not on the sample."""
    path: str
    rows: int
    columns: list[str]
    sample: pd.DataFrame
    missing: dict[str, float]


def _arrow_kind(t) -> str:
    import pyarrow.types as pt
    if pt.is_null(t):
        return "null"
    if pt.is_boolean(t):
        return "bool"
    if pt.is_integer(t):
        return "int"
    if pt.is_floating(t) or pt.is_decimal(t):
        return "float"
    if pt.is_timestamp(t) or pt.is_date(t):
        return "time"
    return "text"


#: The one type a column gets when its chunks disagreed, as DuckDB names it.
_WIDEST = {frozenset({"int"}): "BIGINT", frozenset({"float"}): "DOUBLE", frozenset({"int", "float"}): "DOUBLE",
           frozenset({"bool"}): "BOOLEAN", frozenset({"time"}): "TIMESTAMP"}


def _stream_to_parquet(first: list[pd.DataFrame], rest, cap: int, stream_dir: str, prepare, n: int) -> Streamed:
    """The rows already fetched (`first`) and every chunk still to come, written
    to one parquet file with memory at about one chunk.

    Each chunk is written as its own small file the moment it arrives. A column
    may come out differently from one chunk to the next -- numbers for a
    million rows, then a row with text in it -- and a file already written
    cannot change its mind, so the pieces are merged at the end by DuckDB with
    each column cast to the widest type any piece gave it: nothing is dropped
    and nothing is coerced to empty."""
    import duckdb
    import pyarrow.parquet as pq
    parts_dir = os.path.join(stream_dir, "parts")
    os.makedirs(parts_dir, exist_ok=True)
    parts: list[str] = []
    kinds: dict[str, set[str]] = {}
    columns: list[str] = []

    def write(chunk: pd.DataFrame) -> None:
        nonlocal columns
        if prepare is not None:
            chunk = prepare(chunk)
        if not columns:
            columns = [str(c) for c in chunk.columns]
        path = os.path.join(parts_dir, f"part_{len(parts):06d}.parquet")
        chunk.to_parquet(path, index=False)
        for field in pq.read_schema(path):
            kinds.setdefault(field.name, set()).add(_arrow_kind(field.type))
        parts.append(path)

    for chunk in first:
        write(chunk)
    for chunk in rest:
        n += len(chunk)
        if cap and n > cap:
            raise _too_large(cap)
        write(chunk)

    final = os.path.join(stream_dir, "import.parquet")
    quote = lambda c: '"' + str(c).replace('"', '""') + '"'                     # noqa: E731
    casts = []
    for c in columns:
        seen = frozenset(kinds.get(c, set()) - {"null"})
        target = _WIDEST.get(seen, "VARCHAR") if seen else "VARCHAR"
        casts.append(f"CAST({quote(c)} AS {target}) AS {quote(c)}")
    con = duckdb.connect()
    try:
        from ..core.config import settings
        con.execute(f"SET threads TO {max(1, int(getattr(settings, 'widget_duckdb_threads', 2)))}")
        con.execute("SET preserve_insertion_order TO true")
        source = "read_parquet(?, union_by_name=true)"
        con.execute(f"COPY (SELECT {', '.join(casts)} FROM {source}) TO '{final}' "
                    "(FORMAT parquet, ROW_GROUP_SIZE 1000000)", [parts])
        rows = int(con.execute(f"SELECT COUNT(*) FROM read_parquet('{final}')").fetchone()[0])
        counts = con.execute("SELECT " + ", ".join(f"COUNT({quote(c)})" for c in columns)
                             + f" FROM read_parquet('{final}')").fetchone() if columns else ()
        sample_rows = int(getattr(settings, "discovery_sample_rows", 200_000) or 200_000)
        sample = con.execute(f"SELECT * FROM read_parquet('{final}') USING SAMPLE reservoir({sample_rows} ROWS) "
                             "REPEATABLE (7)").fetch_df() if rows > sample_rows else \
            con.execute(f"SELECT * FROM read_parquet('{final}')").fetch_df()
    finally:
        con.close()
        for path in parts:
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(parts_dir)
        except OSError:
            pass
    missing = {c: round(100.0 * (rows - int(k)) / rows, 2) if rows else 0.0 for c, k in zip(columns, counts)}
    return Streamed(path=final, rows=rows, columns=columns, sample=sample, missing=missing)


def _capped_read(sql: str, engine, params: dict | None, cap: int, *, stream_dir: str | None = None,
                 prepare=None) -> "pd.DataFrame | Streamed":
    """read_sql, stopping as soon as the cap is passed. Chunked, so a custom
    query over a huge table is refused without first holding all of it in
    memory, and dialect-free: the query itself is never rewritten.

    With `stream_dir`, an import that passes `settings.import_stream_rows` is
    no longer gathered: what has arrived and everything still to come goes to
    a parquet file there (`Streamed`). `prepare(chunk)` is applied to each
    chunk before it is written -- the caller's type conversions."""
    # With parameters (incremental refresh's :cursor_val) the query goes
    # through SQLAlchemy text(), which binds :name on every driver and escapes
    # % itself; sent raw, psycopg2 could not bind :cursor_val, the refresh
    # failed and quietly fell back to a full reload. Without parameters the
    # text goes to the driver as written, % doubled where the driver needs it.
    sql = text(sql) if params else _driver_sql(sql, engine)
    from . import memory_guard
    share = memory_guard.share()
    from ..core.config import settings
    stream_from = int(getattr(settings, "import_stream_rows", 0) or 0) if stream_dir else 0
    if not cap and share <= 0 and not stream_from:
        return pd.read_sql(sql, engine, params=params)
    chunks, n = [], 0
    per_row, free = None, memory_guard.free_bytes() if share > 0 else None
    # A SERVER-side cursor: without it the common drivers (psycopg2, pymysql)
    # bring the WHOLE result into this process before the first chunk is
    # handed over, and "chunked" only describes how it is then sliced --
    # measured 2026-10-11: 50,000,000 rows took 11.9 GB that way. With it the
    # rows cross the wire as they are read. A driver without one ignores this.
    conn = engine.connect()
    try:
        try:
            stream = conn.execution_options(stream_results=True, max_row_buffer=CHUNK_ROWS)
        except Exception:                                   # noqa: BLE001 -- not supported: read as before
            stream = conn
        reader = iter(pd.read_sql(sql, stream, params=params, chunksize=min(cap + 1, CHUNK_ROWS) if cap else CHUNK_ROWS))
        for chunk in reader:
            chunks.append(chunk)
            n += len(chunk)
            if cap and n > cap:
                raise _too_large(cap)
            if stream_from and n > stream_from:
                # Large enough: from here on nothing is kept in memory.
                return _stream_to_parquet(chunks, reader, cap, stream_dir, prepare, n)
            # The same question as the row limit, asked of memory: what has
            # arrived so far, joined into one table and written out, against what
            # this server has free. Refused while it is still cheap to refuse --
            # the alternative was the server process ending mid-import.
            if free is not None and len(chunk):
                if per_row is None:
                    per_row = float(chunk.memory_usage(deep=True).sum()) / len(chunk)
                needed = int(n * per_row * IMPORT_PEAK)
                if needed > free * share and stream_from:
                    # Memory is short before the threshold was reached: the same
                    # answer as past it -- to disk from here on, not a refusal.
                    return _stream_to_parquet(chunks, reader, cap, stream_dir, prepare, n)
                if needed > free * share:
                    raise ImportTooLarge(
                        f"The source returns more than this server's memory can hold: stopped at {n:,} rows "
                        f"(about {needed / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free). Narrow it with a query "
                        "(a filter or a date range), or connect it live so it is not copied.")
    finally:
        conn.close()
    if not chunks:  # no rows: read once more for the column names
        return pd.read_sql(sql, engine, params=params)
    return pd.concat(chunks, ignore_index=True)


def import_to_dataframe(cfg: dict, table: str | None, query: str | None, params: dict | None = None, *,
                        stream_dir: str | None = None, prepare=None) -> "pd.DataFrame | Streamed":
    cap = _import_cap()
    if cfg['type'] == 'api':
        result = _fetch_api(cfg, limit=None)
        return _checked(pd.DataFrame(result['rows'], columns=result['columns']), cap)
    if cfg['type'] == 'access':
        from . import mdb
        _reject_access_query(query)
        return _checked(mdb.read_table(_access_path(cfg), table), cap)
    url    = _build_url(cfg)
    engine = create_engine(url, connect_args=connectors.connect_args(cfg))
    try:
        # A table read asks for ONE row past the cap: enough to know it is over,
        # never the whole table. (cap 0 = no limit, for an operator with disk.)
        sql = (ensure_read_only(query, connectors.sql_family_of(cfg) or cfg['type']) if query and query.strip()
               else _limit_sql(connectors.sql_family_of(cfg) or cfg['type'], table,
                               cap + 1 if cap else 10 ** 12, cfg.get('schema')))
        # F3: incremental refresh binds `:cursor_val` -- SQLAlchemy's text()
        # params rather than string formatting, so a cursor value can never
        # break out of its position regardless of type or content.
        return _capped_read(sql, engine, params, cap, stream_dir=stream_dir, prepare=prepare)
    finally:
        engine.dispose()


def _api_request(cfg: dict, timeout: int = 30) -> httpx.Response:
    from urllib.parse import urlparse
    from .net_guard import assert_host_allowed
    url     = cfg['url']
    assert_host_allowed(urlparse(url).hostname)
    method  = cfg.get('method', 'GET').upper()
    headers = dict(cfg.get('headers', {}))
    params  = dict(cfg.get('params', {}))

    # Secrets are stored encrypted; decrypt at the point the request is signed.
    from .secrets import decrypt_value
    auth_type = cfg.get('auth_type', 'none')
    auth = None
    if auth_type == 'bearer':
        headers['Authorization'] = f"Bearer {decrypt_value(cfg.get('token', ''))}"
    elif auth_type == 'api_key':
        headers[cfg.get('key_header', 'X-API-Key')] = decrypt_value(cfg.get('api_key', ''))
    elif auth_type == 'basic':
        auth = (cfg.get('username', ''), decrypt_value(cfg.get('password', '')))

    with httpx.Client(timeout=timeout) as client:
        if method == 'GET':
            return client.get(url, headers=headers, params=params, auth=auth)
        else:
            return client.post(url, headers=headers, params=params, json=cfg.get('body', {}), auth=auth)


def _fetch_api(cfg: dict, limit: int | None) -> dict:
    resp = _api_request(cfg)
    resp.raise_for_status()
    data = resp.json()

    # Navigate JSON path like "data.records"
    path = cfg.get('json_path', '').strip().lstrip('$').strip('.')
    if path:
        for part in path.split('.'):
            if isinstance(data, dict):
                data = data.get(part, data)

    if isinstance(data, list):
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        found = next((v for v in data.values() if isinstance(v, list)), None)
        df = pd.DataFrame(found) if found else pd.DataFrame([data])
    else:
        df = pd.DataFrame()

    if limit:
        df = df.head(limit)

    return {
        'columns': list(df.columns),
        'rows':    [[_safe_val(v) for v in row] for row in df.values.tolist()],
        'total':   len(df),
    }
