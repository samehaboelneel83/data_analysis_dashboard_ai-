"""A wire-compatible alias lights up DirectQuery through family resolution.

DuckDB proves it end-to-end with a REAL engine (in-process, no server): a
`duckdb` source resolves to the postgresql family and its DirectQuery result
must equal import-mode. A Postgres-wire alias (`redshift`) is proven by
redirecting the driver to the same DuckDB file — showing family resolution,
not the literal type, drives the SQL.
"""
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services import connectors
from app.services.direct_query import DirectQueryUnsupported, run_direct_query
from app.services.widget_data import clear_widget_data_cache, get_widget_data_from_df

ROWS = [("east", 100.0), ("east", 50.0), ("west", 200.0), ("north", 5.0)]


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


def _dataset(cols=("region", "revenue")):
    return SimpleNamespace(source_table="sales", source_query=None,
                           columns=[SimpleNamespace(name=c) for c in cols])


@pytest.fixture
def duckdb_source(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE sales (region VARCHAR, revenue DOUBLE)")
    con.executemany("INSERT INTO sales VALUES (?, ?)", ROWS)
    con.close()
    return {"type": "duckdb", "filepath": str(path)}


@pytest.mark.parametrize("agg", ["sum", "avg", "min", "max"])
def test_duckdb_directquery_matches_import(duckdb_source, agg):
    config = {"dimension": "region", "measure": "revenue", "aggregation": agg}
    direct = run_direct_query(duckdb_source, _dataset(), config, widget_type="bar")
    imported = get_widget_data_from_df(pd.DataFrame(ROWS, columns=["region", "revenue"]),
                                       config, widget_type="bar")
    assert direct == imported


def test_duckdb_percentile_works_but_stat_widgets_are_refused(duckdb_source):
    # DuckDB has PERCENTILE_CONT (postgres family, percentile inherited)...
    med = run_direct_query(duckdb_source, _dataset(),
                           {"dimension": "region", "measure": "revenue", "aggregation": "median"},
                           widget_type="bar")
    assert med["type"] != "error"
    # ...but no WIDTH_BUCKET, so histogram pushdown is cleanly refused (stat_override=False)
    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(duckdb_source, _dataset(),
                         {"measure": "revenue", "bins": 5}, widget_type="histogram")


def test_a_postgres_wire_alias_resolves_to_the_postgres_family(duckdb_source, monkeypatch):
    """`redshift` is Postgres-wire. Point its engine at the DuckDB file (both
    postgres family) and DirectQuery must run — proving sql_family_of('redshift'),
    not the raw type, selects the SQL builder."""
    assert connectors.sql_family_of({"type": "redshift"}) == "postgresql"
    real_build = connectors.build_url

    def fake_build(cfg):
        if cfg.get("type") == "redshift":
            return f"duckdb:///{duckdb_source['filepath']}"
        return real_build(cfg)

    monkeypatch.setattr("app.services.connections.connectors.build_url", fake_build)
    # The engine is hijacked to DuckDB, which rejects psycopg2's connect_timeout — so
    # neutralize the (postgres-keyed) connect args alongside the URL. In real use a
    # redshift source connects via psycopg2 and keeps its connect_timeout.
    real_connect_args = connectors.connect_args
    monkeypatch.setattr("app.services.connectors.connect_args",
                        lambda cfg: {} if cfg.get("type") == "redshift" else real_connect_args(cfg))

    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
    result = run_direct_query({"type": "redshift", "host": "x", "database": "d"},
                              _dataset(), config, widget_type="bar")
    imported = get_widget_data_from_df(pd.DataFrame(ROWS, columns=["region", "revenue"]),
                                       config, widget_type="bar")
    assert result == imported


def test_import_only_types_reject_directquery():
    for cfg in ({"type": "snowflake"}, {"type": "api"},
                {"type": "generic", "url": "snowflake://a/b"}):
        with pytest.raises(DirectQueryUnsupported):
            run_direct_query(cfg, _dataset(), {"dimension": "region", "measure": "revenue"},
                             widget_type="bar")
