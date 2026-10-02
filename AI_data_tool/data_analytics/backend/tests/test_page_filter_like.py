"""The "contains" filter the page filter bar sends for text columns.

It must work on every data path (live SQL, DuckDB, pandas), ignore case, and
never put the reader's text into SQL -- it is always a bound parameter.
"""
import duckdb
import pandas as pd

from app.services.direct_query import _build_where, like_pattern, plan_query
from app.services.widget_data import _apply_filters


def test_like_is_a_supported_live_filter():
    plan_query({"dimension": "region", "measure": "revenue",
                "filters": [{"column": "region", "op": "like", "value": "East"}]}, "bar")


def test_like_binds_the_value_and_folds_case():
    sql, params = _build_where([{"column": "region", "op": "like", "value": "EaSt"}])
    assert "LOWER(" in sql and "LIKE :f0" in sql
    assert params == {"f0": "%east%"}
    # The reader's text never lands in the SQL string itself.
    hostile = "x'; DROP TABLE t; --"
    sql, params = _build_where([{"column": "region", "op": "like", "value": hostile}])
    assert "DROP" not in sql and params["f0"] == like_pattern(hostile)


def test_like_in_duckdb_matches_pandas():
    df = pd.DataFrame({"region": ["North East", "south", "EAST end", None], "v": [1, 2, 3, 4]})
    kept = _apply_filters(df, [{"column": "region", "op": "like", "value": "east"}])
    assert list(kept["v"]) == [1, 3]
    con = duckdb.connect()
    con.register("t", df)
    got = con.execute("SELECT v FROM t WHERE lower(CAST(region AS VARCHAR)) LIKE ? ORDER BY v",
                      [like_pattern("east")]).fetchall()
    assert [r[0] for r in got] == [1, 3]


def test_pandas_contains_is_plain_text_not_a_pattern():
    df = pd.DataFrame({"name": ["a(b", "ab", "a.b"], "v": [1, 2, 3]})
    assert list(_apply_filters(df, [{"column": "name", "op": "like", "value": "a(b"}])["v"]) == [1]
    assert list(_apply_filters(df, [{"column": "name", "op": "like", "value": "a.b"}])["v"]) == [3]
