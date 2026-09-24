import sqlite3
from types import SimpleNamespace

import pytest

from app.services.direct_query import run_direct_query
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


ROWS = [("North", 10.0), ("South", 20.0), ("East", 30.0)]


@pytest.fixture
def sales_sqlite_source(tmp_path):
    db_path = tmp_path / "table_preview_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany("INSERT INTO sales (region, revenue) VALUES (?, ?)", ROWS)
    conn.commit()
    conn.close()
    return {"type": "sqlite", "filepath": str(db_path)}


def _dataset(source_table="sales", columns=("region", "revenue")):
    return SimpleNamespace(
        source_table=source_table, source_query=None,
        columns=[SimpleNamespace(name=c) for c in columns],
    )


def test_table_widget_type_returns_raw_rows_for_preview(sales_sqlite_source):
    result = run_direct_query(sales_sqlite_source, _dataset(), {}, widget_type="table")

    assert result["columns"] == ["region", "revenue"]
    assert sorted(result["rows"]) == sorted([list(r) for r in ROWS])
    assert result["total"] == 3
    assert result["sampled"] is False
