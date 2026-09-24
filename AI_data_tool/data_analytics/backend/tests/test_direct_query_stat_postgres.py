"""
Equivalence tests for the sql_stat strategy (histogram, correlation_matrix)
against a REAL Postgres instance -- the project's dev docker-compose Postgres
container, reachable at localhost:5433 with the docker-compose.yml defaults.

Unlike every other test in this suite, these need a live external service, so
they're skipped (not failed) when that service isn't reachable -- keeping the
rest of the suite fully self-contained while still giving genuine dialect
verification (WIDTH_BUCKET boundary clamping, CORR null-pairwise behavior) when
run in an environment that has the container up.
"""
import uuid
from types import SimpleNamespace

import pandas as pd
import pytest

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from app.services.direct_query import run_direct_query
from app.services.widget_data import clear_widget_data_cache, shape_correlation_matrix, shape_histogram


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()

PG_CFG = {
    "type": "postgresql", "host": "localhost", "port": 5433,
    "username": "datalytics", "password": "datalytics_secret", "database": "datalytics",
}

ROWS = [
    ("east", 100.0, 10.0), ("east", 50.0, 5.0), ("east", 25.0, 30.0),
    ("west", 200.0, 15.0), ("west", 10.0, None), ("west", 175.0, 22.0),
    ("north", 5.0, 40.0), ("north", 90.0, 12.0), ("north", 60.0, 18.0),
    ("south", 300.0, 2.0),
]


def _pg_reachable() -> bool:
    if psycopg2 is None:
        return False
    try:
        conn = psycopg2.connect(connect_timeout=2, host="localhost", port=5433,
                                 user="datalytics", password="datalytics_secret", dbname="datalytics")
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _pg_reachable(), reason="live Postgres container not reachable at localhost:5433")


@pytest.fixture
def sales_table():
    table = f"direct_query_test_{uuid.uuid4().hex[:12]}"
    conn = psycopg2.connect(host="localhost", port=5433, user="datalytics", password="datalytics_secret", dbname="datalytics")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f'CREATE TABLE "{table}" (region TEXT, revenue DOUBLE PRECISION, cost DOUBLE PRECISION)')
    cur.executemany(f'INSERT INTO "{table}" (region, revenue, cost) VALUES (%s, %s, %s)', ROWS)
    try:
        yield table
    finally:
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
        cur.close()
        conn.close()


def _dataset(table, columns=("region", "revenue", "cost")):
    return SimpleNamespace(
        source_table=table, source_query=None,
        columns=[SimpleNamespace(name=c) for c in columns],
    )


def test_histogram_matches_import_mode(sales_table):
    config = {"measure": "revenue", "bins": 4}

    direct_result = run_direct_query(PG_CFG, _dataset(sales_table), config, widget_type="histogram")

    df = pd.DataFrame(ROWS, columns=["region", "revenue", "cost"])
    import_result = shape_histogram(df, config)

    assert direct_result == import_result


def test_histogram_boundary_value_lands_in_last_bin(sales_table):
    """Regression check for the WIDTH_BUCKET clamping fix: the max value must
    land in the last bin, not get dropped into an out-of-range bucket."""
    config = {"measure": "revenue", "bins": 3}

    direct_result = run_direct_query(PG_CFG, _dataset(sales_table), config, widget_type="histogram")

    assert sum(r["value"] for r in direct_result["rows"]) == direct_result["total"]


def test_correlation_matrix_matches_import_mode(sales_table):
    """Includes a NULL in the cost column (west, 10.0, None) specifically to
    verify SQL's pairwise-NULL-skipping in CORR matches pandas' pairwise
    (not listwise) deletion in .corr()."""
    config = {"measures": ["revenue", "cost"]}

    direct_result = run_direct_query(PG_CFG, _dataset(sales_table), config, widget_type="correlation_matrix")

    df = pd.DataFrame(ROWS, columns=["region", "revenue", "cost"])
    import_result = shape_correlation_matrix(df, config)

    assert direct_result["measures"] == import_result["measures"]
    assert direct_result["total"] == import_result["total"]
    for direct_row, import_row in zip(direct_result["matrix"], import_result["matrix"]):
        for d, i in zip(direct_row, import_row):
            assert d == pytest.approx(i, abs=1e-9)
