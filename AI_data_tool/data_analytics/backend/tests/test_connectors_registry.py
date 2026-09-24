"""The connector registry: family resolution, URL building, capabilities."""
import pytest

from app.services import connectors as C


def test_five_original_types_map_to_themselves_byte_identically():
    # The refactor's core guarantee: existing types resolve to their own family
    # and build the exact URLs the old if/elif produced.
    assert C.build_url({"type": "postgresql", "host": "h", "database": "d",
                        "username": "u", "password": "p"}) == "postgresql+psycopg2://u:p@h:5432/d"
    assert C.build_url({"type": "mysql", "host": "h", "database": "d",
                        "username": "u", "password": "p"}) == "mysql+pymysql://u:p@h:3306/d"
    assert C.build_url({"type": "sqlserver", "host": "h", "database": "d",
                        "username": "u", "password": "p"}) == "mssql+pymssql://u:p@h:1433/d"
    assert C.build_url({"type": "oracle", "host": "h", "service_name": "ORCL",
                        "username": "u", "password": "p"}) == "oracle+oracledb://u:p@h:1521/?service_name=ORCL"
    assert C.build_url({"type": "sqlite", "filepath": "/x.db"}) == "sqlite:////x.db"
    for t in ("postgresql", "mysql", "sqlserver", "oracle", "sqlite"):
        assert C.sql_family_of({"type": t}) == t


def test_wire_compatible_aliases_reuse_a_family_and_driver():
    r = C.resolve("redshift")
    assert r.sql_family == "postgresql" and r.dialect == "postgresql+psycopg2"
    assert r.default_port == 5439 and r.driver_installed  # psycopg2 is bundled
    assert C.build_url({"type": "redshift", "host": "h", "database": "d",
                        "username": "u", "password": "p"}).startswith("postgresql+psycopg2://u:p@h:5439/d")
    assert C.resolve("mariadb").dialect == "mysql+pymysql"
    assert C.resolve("azure_synapse").sql_family == "sqlserver"
    assert C.build_url({"type": "oracle_autonomous", "host": "h", "service_name": "X",
                        "username": "u", "password": "p"}).endswith("?service_name=X")


def test_password_is_url_escaped():
    url = C.build_url({"type": "postgresql", "host": "h", "database": "d",
                       "username": "u", "password": "p@ss w/rd"})
    assert "p%40ss+w%2Frd" in url  # quote_plus, as before


def test_capability_overrides_prevent_silent_wrongness():
    # Full-Postgres members keep stat/percentile; wire-only members disable them.
    assert C.resolve("postgresql").supports_stat is True
    assert C.resolve("timescaledb").supports_stat is True
    assert C.resolve("redshift").supports_stat is False
    assert C.resolve("redshift").supports_percentile is False
    assert C.resolve("cockroachdb").supports_stat is False
    # DuckDB: percentile works, but no WIDTH_BUCKET → stat off.
    assert C.resolve("duckdb").sql_family == "postgresql"
    assert C.resolve("duckdb").supports_stat is False


def test_directquery_support_by_family():
    assert C.resolve("redshift").supports_directquery is True
    assert C.resolve("api").supports_directquery is False
    assert C.resolve("snowflake").supports_directquery is False  # sql_family None


def test_duckdb_url_defaults_to_in_memory():
    assert C.build_url({"type": "duckdb", "filepath": ""}) == "duckdb:///:memory:"
    assert C.build_url({"type": "duckdb", "filepath": "/a.duckdb"}) == "duckdb:////a.duckdb"


def test_connect_timeout_only_for_networked_drivers():
    """DuckDB maps to the postgresql SQL family but connects in-process; the
    network connect_timeout must key on the real driver, never the family, or
    duckdb.connect() raises on the unexpected kwarg."""
    assert C.connect_args({"type": "postgresql"}) == {"connect_timeout": 8}
    assert C.connect_args({"type": "redshift"}) == {"connect_timeout": 8}
    assert C.connect_args({"type": "mysql"}) == {"connect_timeout": 8}
    assert C.connect_args({"type": "duckdb", "filepath": ":memory:"}) == {}
    assert C.connect_args({"type": "sqlite", "filepath": "/x.db"}) == {}
    assert C.connect_args({"type": "oracle"}) == {}
    assert C.connect_args({"type": "generic", "url": "postgresql+psycopg2://a:b@h/d"}) == {"connect_timeout": 8}
    assert C.connect_args({"type": "generic", "url": "duckdb:///:memory:"}) == {}


def test_generic_url_infers_family_and_requires_installed_driver():
    assert C.sql_family_of({"type": "generic", "url": "postgresql+psycopg2://a:b@h/d"}) == "postgresql"
    assert C.sql_family_of({"type": "generic", "url": "mysql+pymysql://a:b@h/d"}) == "mysql"
    # a backend with no installed driver → import-only (None) and build_url errors clearly
    assert C.sql_family_of({"type": "generic", "url": "snowflake://a/b"}) is None
    with pytest.raises(ValueError, match="not installed"):
        C.build_url({"type": "generic", "url": "snowflake://a/b"})
    # a bundled backend passes through verbatim
    assert C.build_url({"type": "generic", "url": "sqlite:///x.db"}) == "sqlite:///x.db"


def test_warehouse_without_driver_gives_install_message():
    assert C.resolve("snowflake").driver_installed is False
    with pytest.raises(ValueError, match="not installed"):
        C.build_url({"type": "snowflake", "url": "snowflake://a/b"})


def test_unknown_type_raises():
    with pytest.raises(C.UnknownConnector):
        C.resolve("bogus")
    assert C.is_known("redshift") and not C.is_known("bogus")
    with pytest.raises(C.UnknownConnector):
        C.assert_valid("bogus")


def test_catalog_payload_has_no_secrets_and_covers_every_spec():
    payload = C.catalog_payload()
    assert {p["key"] for p in payload} == {s.key for s in C.all_specs()}
    # the SQLAlchemy dialect/driver internals are not exposed as fields
    for entry in payload:
        assert "dialect" not in entry and "driver_module" not in entry and "sql_family" not in entry
    # config fields are described, secrets flagged not valued
    pg = next(p for p in payload if p["key"] == "postgresql")
    pwd = next(f for f in pg["config_fields"] if f["name"] == "password")
    assert pwd["secret"] is True and pwd["kind"] == "password"


# ── ODBC ──────────────────────────────────────────────────────────────────────
# The escape hatch for backends with no SQLAlchemy dialect. What matters here is
# that its card tells the truth: pyodbc being importable is NOT the same as this
# host being able to open an ODBC connection, and a card that conflates the two
# advertises a connector that fails at connect time everywhere.

def test_odbc_is_registered_and_import_only():
    spec = C._REGISTRY["odbc"]
    assert spec.url_kind == "generic"
    # No family and no dialect on purpose: what sits behind a DSN is unknown, so
    # claiming a SQL family would push generated SQL at a backend that may not
    # speak it. Import-only is the honest position.
    assert spec.sql_family is None
    assert spec.supports_directquery is False


def test_odbc_reports_not_installed_when_no_driver_is_registered(monkeypatch):
    """A registered VENDOR DRIVER is the real requirement, not the wheel."""
    import types
    fake = types.SimpleNamespace(drivers=lambda: [])
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", fake)
    assert C._odbc_usable() is False


def test_odbc_reports_installed_only_with_a_driver(monkeypatch):
    import types
    fake = types.SimpleNamespace(drivers=lambda: ["ODBC Driver 18 for SQL Server"])
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", fake)
    assert C._odbc_usable() is True


def test_odbc_survives_a_broken_driver_manager(monkeypatch):
    """pyodbc imports but libodbc is missing or unusable: report not-installed
    rather than raising, so the whole catalog endpoint does not 500."""
    import types

    def boom():
        raise RuntimeError("libodbc.so.2: cannot open shared object file")

    monkeypatch.setitem(__import__("sys").modules, "pyodbc",
                        types.SimpleNamespace(drivers=boom))
    assert C._odbc_usable() is False
