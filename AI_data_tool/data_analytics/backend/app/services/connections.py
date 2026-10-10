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


def _capped_read(sql: str, engine, params: dict | None, cap: int) -> pd.DataFrame:
    """read_sql, stopping as soon as the cap is passed. Chunked, so a custom
    query over a huge table is refused without first holding all of it in
    memory, and dialect-free: the query itself is never rewritten."""
    # With parameters (incremental refresh's :cursor_val) the query goes
    # through SQLAlchemy text(), which binds :name on every driver and escapes
    # % itself; sent raw, psycopg2 could not bind :cursor_val, the refresh
    # failed and quietly fell back to a full reload. Without parameters the
    # text goes to the driver as written, % doubled where the driver needs it.
    sql = text(sql) if params else _driver_sql(sql, engine)
    if not cap:
        return pd.read_sql(sql, engine, params=params)
    chunks, n = [], 0
    for chunk in pd.read_sql(sql, engine, params=params, chunksize=min(cap + 1, 100_000)):
        chunks.append(chunk)
        n += len(chunk)
        if n > cap:
            raise _too_large(cap)
    if not chunks:  # no rows: read once more for the column names
        return pd.read_sql(sql, engine, params=params)
    return pd.concat(chunks, ignore_index=True)


def import_to_dataframe(cfg: dict, table: str | None, query: str | None, params: dict | None = None) -> pd.DataFrame:
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
        return _capped_read(sql, engine, params, cap)
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
