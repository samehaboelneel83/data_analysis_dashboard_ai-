"""E07: a database connection can require TLS, and no source query runs forever.

Before this nothing set TLS -- a source across an untrusted network got the
password and the rows in clear unless the server insisted -- and an import
query had no ceiling at all: a runaway one held a worker until a restart."""
import ssl

import pytest

from app.core.config import settings
from app.services import connectors as C

PG = {"type": "postgresql", "host": "h", "database": "d"}
MY = {"type": "mysql", "host": "h", "database": "d"}


@pytest.fixture
def limit(monkeypatch):
    monkeypatch.setattr(settings, "source_statement_timeout_s", 120)


class TestStatementCeiling:
    def test_postgres_enforces_it_server_side(self, limit):
        assert C.connect_args(PG)["options"] == "-cstatement_timeout=120000"

    def test_it_joins_the_schema_search_path_in_one_options_string(self, limit):
        args = C.connect_args({**PG, "schema": "sales"})
        assert args["options"] == "-cstatement_timeout=120000 -csearch_path=sales,public"

    def test_every_postgres_wire_connector_gets_it(self, limit):
        assert "statement_timeout" in C.connect_args({"type": "redshift"})["options"]

    def test_mysql_and_clickhouse_get_a_read_timeout(self, limit):
        assert C.connect_args(MY)["read_timeout"] == 120
        assert C.connect_args({"type": "clickhouse"})["send_receive_timeout"] == 120

    def test_zero_turns_it_off(self, monkeypatch):
        monkeypatch.setattr(settings, "source_statement_timeout_s", 0)
        assert C.connect_args(PG) == {"connect_timeout": 8}
        assert "read_timeout" not in C.connect_args(MY)

    def test_in_process_engines_are_untouched(self, limit):
        """sqlite/duckdb reject unknown connect kwargs outright."""
        assert C.connect_args({"type": "sqlite", "filepath": "x"}) == {}
        assert C.connect_args({"type": "duckdb", "filepath": "x"}) == {}

    def test_the_default_is_generous_but_set(self):
        assert settings.source_statement_timeout_s == 900


class TestTls:
    def test_a_connection_saved_before_this_changes_nothing(self):
        for cfg in (PG, MY, {**PG, "ssl_mode": "default"}):
            args = C.connect_args(cfg)
            assert not {"sslmode", "ssl", "ssl_ca", "ssl_disabled"} & set(args)

    def test_postgres_modes_are_libpq_sslmode(self):
        assert C.connect_args({**PG, "ssl_mode": "require"})["sslmode"] == "require"
        args = C.connect_args({**PG, "ssl_mode": "verify-full", "ssl_root_cert": "/certs/ca.pem"})
        assert (args["sslmode"], args["sslrootcert"]) == ("verify-full", "/certs/ca.pem")

    def test_verifying_without_a_ca_is_refused_by_name(self):
        with pytest.raises(ValueError, match="verify-ca needs the CA certificate"):
            C.connect_args({**PG, "ssl_mode": "verify-ca"})

    def test_an_unknown_mode_is_refused(self):
        with pytest.raises(ValueError, match="not a TLS mode"):
            C.connect_args({**MY, "ssl_mode": "strict"})

    def test_mysql_modes_in_pymysqls_words(self):
        req = C.connect_args({**MY, "ssl_mode": "require"})["ssl"]
        assert req == {"check_hostname": False, "verify_mode": ssl.CERT_NONE}
        full = C.connect_args({**MY, "ssl_mode": "verify-full", "ssl_root_cert": "/c.pem"})
        assert (full["ssl_ca"], full["ssl_verify_cert"], full["ssl_verify_identity"]) == ("/c.pem", True, True)
        ca = C.connect_args({**MY, "ssl_mode": "verify-ca", "ssl_root_cert": "/c.pem"})
        assert ca["ssl_verify_identity"] is False
        assert C.connect_args({**MY, "ssl_mode": "disable"})["ssl_disabled"] is True

    def test_pymysql_actually_accepts_those_keywords(self):
        """A kwarg the driver does not know fails every connection at runtime,
        which a dict comparison never shows."""
        import inspect
        import pymysql
        params = inspect.signature(pymysql.connections.Connection.__init__).parameters
        for mode, extra in (("require", {}), ("disable", {}), ("verify-full", {"ssl_root_cert": "/c"})):
            args = C.connect_args({**MY, "ssl_mode": mode, **extra})
            assert set(args) <= set(params), mode

    def test_the_form_offers_it_on_postgres_and_mysql_family_connectors(self):
        def fields(key):
            return {f.name for f in C.resolve(key).config_fields}
        for key in ("postgresql", "redshift", "mysql", "mariadb"):
            assert {"ssl_mode", "ssl_root_cert"} <= fields(key), key
        assert "ssl_mode" not in fields("sqlite")
