import pandas as pd
from sqlalchemy import create_engine, inspect, text
import httpx

from . import connectors


def _build_url(cfg: dict) -> str:
    """Kept as the module-level seam every SQL layer (and the tests) monkeypatch;
    the body now lives in the connector registry so all types share one path."""
    return connectors.build_url(cfg)


def _limit_sql(db_type: str, table: str, limit: int, schema: str | None = None) -> str:
    full = f'"{schema}"."{table}"' if schema else f'"{table}"'
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
    url    = _build_url(cfg)
    engine = create_engine(url, connect_args=connectors.connect_args(cfg))
    try:
        sql = query.strip() if query else _limit_sql(connectors.sql_family_of(cfg) or cfg['type'], table, limit, cfg.get('schema'))
        df  = pd.read_sql(sql, engine)
        df  = df.head(limit)
        return {
            'columns': list(df.columns),
            'rows':    [[_safe_val(v) for v in row] for row in df.values.tolist()],
            'total':   len(df),
        }
    finally:
        engine.dispose()


def import_to_dataframe(cfg: dict, table: str | None, query: str | None, params: dict | None = None) -> pd.DataFrame:
    if cfg['type'] == 'api':
        result = _fetch_api(cfg, limit=None)
        return pd.DataFrame(result['rows'], columns=result['columns'])
    if cfg['type'] == 'access':
        from . import mdb
        _reject_access_query(query)
        return mdb.read_table(_access_path(cfg), table)
    url    = _build_url(cfg)
    engine = create_engine(url, connect_args=connectors.connect_args(cfg))
    try:
        sql = query.strip() if query else _limit_sql(connectors.sql_family_of(cfg) or cfg['type'], table, 100_000, cfg.get('schema'))
        # F3: incremental refresh binds `:cursor_val` -- SQLAlchemy's text()
        # params rather than string formatting, so a cursor value can never
        # break out of its position regardless of type or content.
        return pd.read_sql(sql, engine, params=params)
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
