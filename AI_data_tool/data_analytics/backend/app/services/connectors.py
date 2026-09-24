"""The connector registry — the single source of truth for data-source types.

Most database "connectors" are wire-compatible with one of the handful of SQL
engines we already drive: Amazon Redshift / CockroachDB / TimescaleDB / Aurora
PostgreSQL all speak the PostgreSQL wire protocol (our installed psycopg2);
MariaDB / TiDB / SingleStore / PlanetScale speak MySQL (pymysql); Azure SQL /
Synapse speak T-SQL (pymssql). So a broad *named* catalog maps onto just five
SQL **families**, and each named connector inherits that family's import,
DirectQuery and query-builder behaviour with no new driver.

Each `ConnectorSpec` declares how to CONNECT (a SQLAlchemy dialect+driver and a
config-field shape) and which `sql_family` supplies its SQL traits. The three
SQL layers (`connections`, `direct_query`, `query_builder`) resolve a source's
`type` to its `sql_family` and then run their existing per-family logic
unchanged — so the five original types map to themselves and behave
byte-for-byte as before.

`sql_family = None` means import-only (no DirectQuery / no dialect functions),
exactly like the `api` source: the generic SQLAlchemy-URL connector when its
backend isn't one of the five, and the cloud-warehouse entries whose driver
isn't bundled.
"""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import quote_plus

# The five SQL trait-sets the SQL layers already implement. A connector's
# sql_family selects which one drives its limit clause, quoting, random fn,
# percentile and stat support.
SQL_FAMILIES = {"postgresql", "mysql", "sqlserver", "oracle", "sqlite", "clickhouse"}
DIRECTQUERY_FAMILIES = set(SQL_FAMILIES)
PERCENTILE_FAMILIES = {"postgresql", "oracle"}   # mirrors direct_query._DIALECTS_WITH_PERCENTILE_CONT
STAT_FAMILIES = {"postgresql"}                    # mirrors direct_query._STAT_DIALECTS

# SQLAlchemy backend name → our SQL family (drives DirectQuery/builder for a
# generic URL). A backend not listed here is import-only, like `api`.
_BACKEND_TO_FAMILY = {
    "postgresql": "postgresql", "mysql": "mysql", "mariadb": "mysql",
    "mssql": "sqlserver", "oracle": "oracle", "sqlite": "sqlite", "duckdb": "postgresql",
}


class UnknownConnector(ValueError):
    """Raised when a source `type` is not in the registry."""


@dataclass(frozen=True)
class ConfigField:
    name: str                              # key written into DataSource.config
    label: str
    kind: str = "text"                     # text | password | number | select
    required: bool = False
    default: Any = None
    placeholder: str = ""
    options: tuple[str, ...] = ()          # for kind == "select"
    secret: bool = False                   # password masking / future redaction
    show_if: tuple[str, Any] | None = None  # render only when cfg[show_if[0]] == show_if[1]


@dataclass(frozen=True)
class ConnectorSpec:
    key: str                               # DataSource.type value
    label: str
    icon: str
    category: str
    sql_family: str | None                 # a SQL_FAMILIES member, or None (import-only/api)
    dialect: str | None                    # SQLAlchemy dialect+driver, or None for api
    default_port: int | None
    config_fields: tuple[ConfigField, ...]
    driver_module: str | None = None       # probed for a helpful "install" error
    #: For a driver that is NOT a Python module. `driver_module` is probed with
    #: importlib, which can never find a command-line tool, so a connector
    #: backed by a binary (Access -> mdbtools) would otherwise report itself as
    #: installed on every host and the catalog card would lie.
    probe: "Callable[[], bool] | None" = None
    url_kind: str = "hostport"             # hostport | oracle_service | sqlite | duckdb | mdb | api | generic
    percentile_override: bool | None = None
    stat_override: bool | None = None

    @property
    def driver_installed(self) -> bool:
        if self.probe is not None:
            return self.probe()
        if not self.driver_module:
            return True
        # find_spec raises ModuleNotFoundError (not returns None) when a dotted
        # module's PARENT is absent, e.g. "snowflake.sqlalchemy" with no snowflake.
        try:
            return importlib.util.find_spec(self.driver_module) is not None
        except ModuleNotFoundError:
            return False

    @property
    def supports_directquery(self) -> bool:
        return self.sql_family in DIRECTQUERY_FAMILIES

    @property
    def supports_percentile(self) -> bool:
        if self.percentile_override is not None:
            return self.percentile_override
        return self.sql_family in PERCENTILE_FAMILIES

    @property
    def supports_stat(self) -> bool:
        if self.stat_override is not None:
            return self.stat_override
        return self.sql_family in STAT_FAMILIES


# ── field-group helpers (keep the catalog terse) ─────────────────────────────

def _hostport_fields(port: int, *, schema: bool = False) -> tuple[ConfigField, ...]:
    fields = [
        ConfigField("host", "Host", required=True, placeholder="localhost"),
        ConfigField("port", "Port", "number", default=port),
        ConfigField("database", "Database", required=True),
        ConfigField("username", "Username"),
        ConfigField("password", "Password", "password", secret=True),
    ]
    if schema:
        fields.append(ConfigField("schema", "Schema (optional)", placeholder="public"))
    return tuple(fields)


def _oracle_fields(port: int) -> tuple[ConfigField, ...]:
    return (
        ConfigField("host", "Host", required=True, placeholder="localhost"),
        ConfigField("port", "Port", "number", default=port),
        ConfigField("service_name", "Service Name", default="ORCL"),
        ConfigField("username", "Username"),
        ConfigField("password", "Password", "password", secret=True),
    )


_API_FIELDS = (
    ConfigField("url", "URL", required=True, placeholder="https://api.example.com/data"),
    ConfigField("method", "Method", "select", default="GET", options=("GET", "POST")),
    ConfigField("auth_type", "Auth", "select", default="none",
                options=("none", "bearer", "api_key", "basic")),
    ConfigField("token", "Bearer token", "password", secret=True, show_if=("auth_type", "bearer")),
    ConfigField("api_key", "API key", "password", secret=True, show_if=("auth_type", "api_key")),
    ConfigField("key_header", "Key header", default="X-API-Key", show_if=("auth_type", "api_key")),
    ConfigField("username", "Username", show_if=("auth_type", "basic")),
    ConfigField("password", "Password", "password", secret=True, show_if=("auth_type", "basic")),
    ConfigField("json_path", "JSON path (optional)", placeholder="data.records"),
)


# ── the catalog ──────────────────────────────────────────────────────────────
# Named SQL connectors map to an ALREADY-INSTALLED driver via wire-compatibility,
# so each inherits its family's import + DirectQuery + query-builder behaviour
# with no new driver. `_PG`/`_MY` mark Postgres-/MySQL-wire members whose engine
# lacks WIDTH_BUCKET/CORR/PERCENTILE_CONT — they carry overrides so a stat query
# fails cleanly (DirectQueryUnsupported) rather than silently wrong.

def _pg(key, label, icon, port, *, full_stats):
    """A PostgreSQL-wire connector. full_stats=False disables stat+percentile
    pushdown for engines that don't implement WIDTH_BUCKET/CORR/PERCENTILE_CONT."""
    return ConnectorSpec(
        key, label, icon, "PostgreSQL-compatible", "postgresql",
        "postgresql+psycopg2", port, _hostport_fields(port, schema=True), "psycopg2",
        stat_override=None if full_stats else False,
        percentile_override=None if full_stats else False)


def _my(key, label, icon, port):
    return ConnectorSpec(key, label, icon, "MySQL-compatible", "mysql",
                         "mysql+pymysql", port, _hostport_fields(port), "pymysql")


def _mssql(key, label, icon, port):
    return ConnectorSpec(key, label, icon, "SQL Server-compatible", "sqlserver",
                         "mssql+pymssql", port, _hostport_fields(port), "pymssql")


def _ora(key, label, icon, port):
    return ConnectorSpec(key, label, icon, "Oracle-compatible", "oracle",
                         "oracle+oracledb", port, _oracle_fields(port), "oracledb",
                         url_kind="oracle_service")


def _mdbtools_installed() -> bool:
    """Whether this host can read Access files.

    Imported inside the call, not at module scope: connectors.py is Layer 1 and
    so is services/mdb, but keeping the import lazy means the registry stays
    importable even if mdb.py grows a heavier dependency later.
    """
    from .mdb import mdbtools_available
    return mdbtools_available()


def _odbc_usable() -> bool:
    """Whether this host can actually open an ODBC connection.

    A `driver_module="pyodbc"` check would be a LIE here, and that distinction is
    the reason this probe exists. pyodbc imports successfully as soon as the
    wheel is present, but it is only a binding: without a driver manager
    (unixODBC) and at least one registered vendor driver there is nothing to
    connect to, so the catalog card would advertise a connector that fails at
    connect time for every host.

    `drivers()` asks the driver manager what is actually registered, which is the
    question a user reading the card is really asking. An empty list means the
    binding is installed and useless, which reports as not-installed.
    """
    try:
        import pyodbc
    except Exception:  # noqa: BLE001 -- ImportError, or a missing libodbc.so
        return False
    try:
        return bool(pyodbc.drivers())
    except Exception:  # noqa: BLE001 -- driver manager present but unusable
        return False


def _warehouse(key, label, icon, driver_module, placeholder):
    """A cloud warehouse: discoverable, but connects through a full SQLAlchemy
    URL once its driver is installed (enterprises pin their own). import-only."""
    return ConnectorSpec(
        key, label, icon, "Cloud warehouse", None, None, None,
        (ConfigField("url", "SQLAlchemy URL", required=True, placeholder=placeholder),),
        driver_module=driver_module, url_kind="generic")


_ALL_SPECS: list[ConnectorSpec] = [
    # ── PostgreSQL family (psycopg2, installed) ──
    _pg("postgresql", "PostgreSQL", "🐘", 5432, full_stats=True),
    _pg("timescaledb", "TimescaleDB", "⏱", 5432, full_stats=True),
    _pg("aurora_postgresql", "Aurora PostgreSQL", "🟠", 5432, full_stats=True),
    _pg("rds_postgresql", "RDS for PostgreSQL", "🟠", 5432, full_stats=True),
    _pg("cloudsql_postgresql", "Cloud SQL (PostgreSQL)", "☁", 5432, full_stats=True),
    _pg("azure_postgresql", "Azure DB for PostgreSQL", "🔷", 5432, full_stats=True),
    _pg("supabase", "Supabase", "⚡", 5432, full_stats=True),
    _pg("neon", "Neon", "🌩", 5432, full_stats=True),
    _pg("alloydb", "Google AlloyDB", "☁", 5432, full_stats=True),
    _pg("edb_postgres", "EnterpriseDB", "🐘", 5444, full_stats=True),
    _pg("redshift", "Amazon Redshift", "🟥", 5439, full_stats=False),
    _pg("cockroachdb", "CockroachDB", "🪳", 26257, full_stats=False),
    _pg("citus", "Citus", "🐘", 5432, full_stats=False),
    _pg("greenplum", "Greenplum", "🟩", 5432, full_stats=False),
    _pg("yugabytedb", "YugabyteDB", "🦎", 5433, full_stats=False),
    _pg("materialize", "Materialize", "🟣", 6875, full_stats=False),
    # ── MySQL family (pymysql, installed) ──
    _my("mysql", "MySQL", "🐬", 3306),
    _my("mariadb", "MariaDB", "🦭", 3306),
    _my("aurora_mysql", "Aurora MySQL", "🟠", 3306),
    _my("rds_mysql", "RDS for MySQL", "🟠", 3306),
    _my("cloudsql_mysql", "Cloud SQL (MySQL)", "☁", 3306),
    _my("azure_mysql", "Azure DB for MySQL", "🔷", 3306),
    _my("tidb", "TiDB", "🐯", 4000),
    _my("singlestore", "SingleStore", "🔶", 3306),
    _my("planetscale", "PlanetScale", "🪐", 3306),
    _my("vitess", "Vitess", "🧩", 15306),
    _my("oceanbase", "OceanBase", "🌊", 2881),
    # ── SQL Server family (pymssql, installed) ──
    _mssql("sqlserver", "SQL Server", "🪟", 1433),
    _mssql("azure_sql", "Azure SQL Database", "🔷", 1433),
    _mssql("azure_synapse", "Azure Synapse Analytics", "🔷", 1433),
    _mssql("rds_sqlserver", "RDS for SQL Server", "🟠", 1433),
    # ── Oracle family (oracledb, installed) ──
    _ora("oracle", "Oracle Database", "🔴", 1521),
    _ora("oracle_autonomous", "Oracle Autonomous DB", "🔴", 1522),
    _ora("rds_oracle", "RDS for Oracle", "🟠", 1521),
    # ── File engines ──
    ConnectorSpec("sqlite", "SQLite", "📁", "File", "sqlite", "sqlite", None,
                  (ConfigField("filepath", "File Path", required=True, placeholder="/data/mydb.db"),),
                  url_kind="sqlite"),
    ConnectorSpec("duckdb", "DuckDB", "🦆", "File", "postgresql", "duckdb", None,
                  (ConfigField("filepath", "File Path (blank = in-memory)", placeholder="/data/analytics.duckdb"),),
                  driver_module="duckdb_engine", url_kind="duckdb", stat_override=False),
    ConnectorSpec("access", "Microsoft Access", "🗄", "File",
                  None,      # no SQL family: Jet/ACE matches none of the five
                  None,      # no SQLAlchemy dialect -- read via the mdbtools CLIs
                  None,
                  (ConfigField("filepath", "File Path", required=True,
                               placeholder="/data/inventory.accdb"),),
                  url_kind="mdb", probe=_mdbtools_installed),
    # ── Cloud warehouses (driver installed by the operator; import-only) ──
    _warehouse("snowflake", "Snowflake", "❄", "snowflake.sqlalchemy",
               "snowflake://user:pw@account/db/schema?warehouse=WH"),
    _warehouse("bigquery", "Google BigQuery", "🔵", "sqlalchemy_bigquery",
               "bigquery://project/dataset"),
    _warehouse("databricks", "Databricks SQL", "🧱", "databricks.sqlalchemy",
               "databricks://token:***@host?http_path=/sql/1.0/..."),
    # ClickHouse is the one warehouse in this category that is NOT import-only.
    # It keeps its driver gate (clickhouse_sqlalchemy is operator-installed, like
    # every other warehouse driver) but carries a real sql_family, so DirectQuery
    # resolves for it. percentile/stat stay off: ClickHouse spells quantiles
    # quantile(0.5)(col), not PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col),
    # and has no WIDTH_BUCKET -- the same fail-closed call Redshift gets, rather
    # than SQL the server rejects at render time.
    ConnectorSpec(
        "clickhouse", "ClickHouse", "🟡", "Cloud warehouse", "clickhouse",
        "clickhouse+native", 9000, _hostport_fields(9000),
        driver_module="clickhouse_sqlalchemy", url_kind="hostport",
        percentile_override=False, stat_override=False),
    _warehouse("trino", "Trino", "🦌", "trino",
               "trino://user@host:8080/catalog/schema"),
    # ── Non-SQL / advanced ──
    ConnectorSpec("api", "Web API", "🌐", "API", None, None, None, _API_FIELDS, url_kind="api"),
    # ── ODBC: the escape hatch for backends with no SQLAlchemy dialect ──
    ConnectorSpec("odbc", "ODBC (generic)", "🔌", "Advanced",
                  None,      # no SQL family: what is behind the DSN is unknown,
                  None,      # so no dialect and no DirectQuery -- import only.
                  None,
                  (ConfigField("url", "SQLAlchemy ODBC URL", required=True,
                               placeholder="mssql+pyodbc://user:pw@host/db?driver=ODBC+Driver+18+for+SQL+Server"),),
                  probe=_odbc_usable, url_kind="generic"),
    ConnectorSpec("generic", "SQLAlchemy URL", "🔗", "Advanced", None, None, None,
                  (ConfigField("url", "SQLAlchemy URL", required=True,
                               placeholder="postgresql+psycopg2://user:pw@host:5432/db"),),
                  url_kind="generic"),
]

_REGISTRY: dict[str, ConnectorSpec] = {s.key: s for s in _ALL_SPECS}


# ── registry API ─────────────────────────────────────────────────────────────

def resolve(type_key: str) -> ConnectorSpec:
    spec = _REGISTRY.get(type_key)
    if spec is None:
        raise UnknownConnector(f"unknown connector type '{type_key}'")
    return spec


def secret_field_names(type_key: str | None) -> set[str]:
    """The config fields that hold secrets for this connector type (password, token,
    api_key). Used to encrypt-at-rest and redact on the wire. Unknown types fall back
    to the common secret names so an unrecognised config still isn't stored in clear."""
    spec = _REGISTRY.get(type_key)
    if spec is None:
        return {"password", "token", "api_key"}
    return {f.name for f in spec.config_fields if f.secret}


def is_known(type_key: str) -> bool:
    return type_key in _REGISTRY


def all_specs() -> list[ConnectorSpec]:
    return list(_ALL_SPECS)


def _generic_family(url: str) -> str | None:
    from sqlalchemy.engine.url import make_url
    try:
        backend = make_url(url).get_backend_name()
    except Exception:
        return None
    return _BACKEND_TO_FAMILY.get(backend)


def sql_family_of(cfg: dict) -> str | None:
    """The SQL family that drives this source's SQL behaviour, or None for
    import-only sources (api, generic-on-an-unknown-backend, driver-gated
    warehouses). For the five original types this is the type itself."""
    key = cfg.get("type")
    spec = _REGISTRY.get(key)
    if spec is None:
        return None
    if spec.url_kind == "generic":
        return _generic_family(cfg.get("url", "") or "")
    return spec.sql_family


def _backend_of(cfg: dict) -> str | None:
    """The SQLAlchemy backend name (e.g. 'postgresql', 'duckdb') that will
    actually connect — the real driver, not the SQL-behaviour family. DuckDB
    resolves to the 'postgresql' family for SQL building yet its backend is
    'duckdb', which is what decides driver-specific connect args."""
    key = cfg.get("type")
    spec = _REGISTRY.get(key)
    if spec is None:
        return None
    if spec.url_kind == "generic":
        from sqlalchemy.engine.url import make_url
        try:
            return make_url((cfg.get("url") or "").strip()).get_backend_name()
        except Exception:
            return None
    return spec.dialect.split("+", 1)[0] if spec.dialect else None


#: A schema name we are willing to put in a libpq options string. Deliberately
#: narrower than what Postgres accepts as a quoted identifier: the value is
#: interpolated into `-csearch_path=...`, where a comma adds a second entry and
#: a space ends the option, so anything outside this set is refused rather than
#: quietly repaired.
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def connect_args(cfg: dict) -> dict:
    """connect_args for create_engine. A network connect timeout applies only to
    the networked drivers that accept it (psycopg2/pymysql); in-process engines
    (duckdb, sqlite) reject the kwarg and the others simply do not use it.

    The Schema field has been on every PostgreSQL-family connection form since
    the connector registry was written, and nothing read it -- so a customer
    whose tables live in `sales` filled it in and still got "relation does not
    exist". It becomes a search_path here, which is the one place that applies
    to every query the source ever runs: DirectQuery, metadata sampling and
    import alike, without any of them having to know about it.

    Postgres only. `options` is libpq's; pymysql raises TypeError on it, and
    MySQL has no schema distinct from the database anyway.
    """
    backend = _backend_of(cfg)
    # clickhouse-driver takes connect_timeout as well, and an unreachable
    # warehouse must fail in seconds rather than hold a worker open. It has no
    # search_path, so it returns before the schema branch below.
    if backend == "clickhouse":
        return {"connect_timeout": 8}
    if backend not in ("postgresql", "mysql"):
        return {}
    args: dict = {"connect_timeout": 8}
    schema = (cfg.get("schema") or "").strip() if backend == "postgresql" else ""
    if schema:
        if not _SCHEMA_RE.match(schema):
            raise ValueError(
                f"{schema!r} is not a usable schema name -- letters, digits and "
                "underscores only, starting with a letter or underscore")
        # public stays on the path: extensions install there by default, and
        # anything already qualified against it must keep working.
        args["options"] = f"-csearch_path={schema},public"
    return args


def _guard_host(host: str | None) -> None:
    from .net_guard import assert_host_allowed
    assert_host_allowed(host)


def build_url(cfg: dict) -> str:
    """Build a SQLAlchemy URL for a source config. Replaces the body of
    connections._build_url; the five original types produce byte-identical URLs."""
    key = cfg.get("type")
    spec = resolve(key)

    if spec.driver_module and not spec.driver_installed:
        raise ValueError(
            f"{spec.label} driver is not installed in this environment "
            f"— pip install {spec.driver_module}")

    # Secrets are stored encrypted; decrypt them here, at the one point they become
    # part of a live connection URL. Marker-based, so a plaintext (legacy) value is
    # returned unchanged. This is also the DirectQuery engine-key input, so keys stay
    # consistent across reads.
    from . import secrets as _secrets
    secret_names = {f.name for f in spec.config_fields if f.secret}
    if secret_names:
        cfg = {**cfg, **{n: _secrets.decrypt_value(cfg.get(n))
                         for n in secret_names if cfg.get(n) is not None}}

    u = quote_plus(cfg.get("username", ""))
    pw = quote_plus(cfg.get("password", ""))
    h = cfg.get("host", "localhost")
    db = cfg.get("database", "")
    port = cfg.get("port")

    if spec.url_kind == "sqlite":
        return f"sqlite:///{cfg.get('filepath', '')}"
    if spec.url_kind == "oracle_service":
        _guard_host(h)
        sn = cfg.get("service_name", "ORCL")
        return f"{spec.dialect}://{u}:{pw}@{h}:{port or spec.default_port}/?service_name={sn}"
    if spec.url_kind == "duckdb":
        return f"duckdb:///{cfg.get('filepath') or ':memory:'}"
    if spec.url_kind == "generic":
        from sqlalchemy.exc import NoSuchModuleError
        from sqlalchemy.engine.url import make_url
        raw = (cfg.get("url") or "").strip()
        if not raw:
            raise ValueError("A SQLAlchemy URL is required")
        try:
            url_obj = make_url(raw)
        except Exception as e:
            raise ValueError(f"Not a valid SQLAlchemy URL: {e}") from e
        # Allow any backend whose driver is actually installed; a missing driver
        # gives a clear message instead of an obscure connect failure. This is
        # what makes the cloud-warehouse entries work once their driver is added.
        try:
            url_obj.get_dialect()
        except NoSuchModuleError as e:
            raise ValueError(
                f"Driver for backend '{url_obj.get_backend_name()}' is not installed "
                f"in this environment — install it, then use this URL. ({e})") from e
        _guard_host(url_obj.host)
        return raw
    if spec.url_kind == "api":
        raise ValueError("The API source type does not use a SQL connection URL")
    if spec.url_kind == "mdb":
        # Same shape as `api`: there is nothing to build. Access is read by
        # running mdbtools against the file, so connections.py special-cases it
        # rather than opening an engine.
        raise ValueError("The Microsoft Access source type does not use a SQL "
                         "connection URL — it is read directly with mdbtools")
    # hostport
    _guard_host(h)
    return f"{spec.dialect}://{u}:{pw}@{h}:{port or spec.default_port}/{db}"


def assert_valid(type_key: str, config: dict | None = None) -> None:
    """Router guard: reject an unknown connector type with a clear error."""
    if not is_known(type_key):
        raise UnknownConnector(f"unknown connector type '{type_key}'")


def catalog_payload(custom_connectors: list | None = None) -> list[dict]:
    """The catalog for the frontend — no secrets, no dialect internals.
    `custom_connectors`, when given, is a list of already-loaded
    CustomConnector rows (or anything with the same attributes) whose org
    the caller has already scoped -- this function does no DB access and no
    org filtering of its own."""
    out = []
    for s in _ALL_SPECS:
        out.append({
            "key": s.key, "label": s.label, "icon": s.icon, "category": s.category,
            "default_port": s.default_port,
            "driver_installed": s.driver_installed,
            "supports_directquery": s.supports_directquery,
            "is_custom": False,
            "config_fields": [
                {"name": f.name, "label": f.label, "kind": f.kind, "required": f.required,
                 "default": f.default, "placeholder": f.placeholder, "options": list(f.options),
                 "secret": f.secret, "show_if": list(f.show_if) if f.show_if else None}
                for f in s.config_fields
            ],
        })
    for cc in (custom_connectors or []):
        spec = _REGISTRY.get(cc.base_type)
        if spec is None:
            continue  # the preset's base type was removed from the registry -- skip, don't crash the catalog
        locked = set(cc.locked_fields or [])
        out.append({
            "key": f"custom:{cc.id}", "label": cc.label, "icon": spec.icon, "category": "Custom",
            "default_port": spec.default_port,
            "driver_installed": spec.driver_installed,
            "supports_directquery": spec.supports_directquery,
            "is_custom": True, "base_type": cc.base_type, "custom_connector_id": cc.id,
            "config_fields": [
                {"name": f.name, "label": f.label, "kind": f.kind, "required": f.required,
                 "default": f.default, "placeholder": f.placeholder, "options": list(f.options),
                 "secret": f.secret, "show_if": list(f.show_if) if f.show_if else None}
                for f in spec.config_fields if f.name not in locked
            ],
        })
    return out
