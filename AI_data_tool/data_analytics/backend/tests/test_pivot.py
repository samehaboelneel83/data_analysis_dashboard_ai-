"""The nested crosstab: several fields on Rows, on Columns, several Measures.

Hand-computed cells on a small frame, through the dispatcher every surface uses
(get_widget_data_from_df), and through a DirectQuery source, which fetches the
rows and shapes them with the same code.
"""
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.direct_query import run_direct_query
from app.services.pivot import PIVOT_WIDGETS, is_multilevel
from app.services.widget_data import clear_widget_data_cache, get_widget_data_from_df
from app.services.widget_roles import InvalidWidget, validate_widget_payload

ROWS = [
    # continent, country, line, category, qty, cost
    ("Europe", "France", "Sports", "Golf", 10, 1.0),
    ("Europe", "France", "Sports", "Golf", 5, 2.0),
    ("Europe", "France", "Sports", "Swim", 7, 3.0),
    ("Europe", "Spain", "Sports", "Golf", 4, 4.0),
    ("Europe", "Spain", "Outdoors", "Tents", 2, 5.0),
    ("Asia", "China", "Sports", "Swim", 3, 6.0),
    ("Asia", None, "Sports", "Swim", 99, 99.0),          # no country: in no cell
]
COLS = ["continent", "country", "line", "category", "qty", "cost"]
df = pd.DataFrame(ROWS, columns=COLS)

CFG = {"dimension": "continent", "rows_extra": ["country"],
       "dimension2": "line", "columns_extra": ["category"],
       "measure": "qty", "extra_measures": ["cost"], "aggregation": "sum"}


def _cell(result, row_keys, col_keys, measure):
    ci = result["column_keys"].index(col_keys)
    mi = result["measures"].index(measure)
    row = next(r for r in result["rows"] if r["keys"] == row_keys)
    return row["values"][ci * len(result["measures"]) + mi]


class TestWhenItApplies:
    def test_only_a_crosstab_or_matrix_with_more_than_one_field_somewhere(self):
        assert is_multilevel("crosstab", CFG)
        assert is_multilevel("matrix", {"dimension": "a", "extra_measures": ["b"]})
        assert not is_multilevel("crosstab", {"dimension": "a", "dimension2": "b", "measure": "c"})
        assert not is_multilevel("bar", CFG)
        assert PIVOT_WIDGETS == {"crosstab", "matrix"}

    def test_a_one_level_crosstab_keeps_its_own_shape(self):
        out = get_widget_data_from_df(df, {"dimension": "continent", "dimension2": "line",
                                           "measure": "qty", "aggregation": "sum"}, "crosstab")
        assert out["type"] == "crosstab"


class TestTheCells:
    def test_nested_rows_and_columns_with_two_measures(self):
        out = get_widget_data_from_df(df, CFG, "crosstab")
        assert out["type"] == "pivot"
        assert out["row_fields"] == ["continent", "country"]
        assert out["column_fields"] == ["line", "category"]
        assert out["measures"] == ["qty", "cost"]
        # Groups in label order, outer level first.
        assert [r["keys"] for r in out["rows"]] == [["Asia", "China"], ["Europe", "France"], ["Europe", "Spain"]]
        assert out["column_keys"] == [["Outdoors", "Tents"], ["Sports", "Golf"], ["Sports", "Swim"]]
        # France / Sports / Golf: 10 + 5 units, 1 + 2 cost.
        assert _cell(out, ["Europe", "France"], ["Sports", "Golf"], "qty") == 15
        assert _cell(out, ["Europe", "France"], ["Sports", "Golf"], "cost") == 3.0
        assert _cell(out, ["Europe", "Spain"], ["Outdoors", "Tents"], "qty") == 2
        # No rows there: blank, not zero.
        assert _cell(out, ["Asia", "China"], ["Sports", "Golf"], "qty") is None

    def test_a_row_with_a_blank_field_is_in_no_cell_and_is_disclosed(self):
        out = get_widget_data_from_df(df, CFG, "crosstab")
        assert out["missing_category"]["rows"] == 1
        assert all(99 not in r["values"] for r in out["rows"])

    def test_no_measure_counts_rows(self):
        out = get_widget_data_from_df(df, {"dimension": "continent", "rows_extra": ["country"]}, "crosstab")
        assert out["measures"] == ["count"]
        assert _cell(out, ["Europe", "France"], [], "count") == 3

    def test_the_named_aggregations_other_charts_use(self):
        out = get_widget_data_from_df(df, {**CFG, "aggregation": "avg"}, "crosstab")
        assert _cell(out, ["Europe", "France"], ["Sports", "Golf"], "qty") == 7.5

    def test_filters_apply_first(self):
        out = get_widget_data_from_df(df, {**CFG, "filters": [{"column": "country", "op": "eq", "value": "Spain"}]},
                                      "crosstab")
        assert [r["keys"] for r in out["rows"]] == [["Europe", "Spain"]]

    def test_a_defined_measure_is_refused_by_name_not_read_as_a_column(self):
        out = get_widget_data_from_df(df, {**CFG, "extra_measures": ["Margin"]}, "crosstab",
                                      measures=[{"name": "Margin", "expression": "SUM(qty)"}])
        assert out["type"] == "error" and "defined measure" in out["message"]

    def test_an_unknown_field_is_an_error(self):
        out = get_widget_data_from_df(df, {**CFG, "rows_extra": ["nope"]}, "crosstab")
        assert out["type"] == "error" and out["code"] == "unknown_field"


class TestSaving:
    def test_more_levels_on_a_crosstab_or_matrix(self):
        validate_widget_payload("crosstab", CFG)
        validate_widget_payload("matrix", CFG)

    @pytest.mark.parametrize("key", ["rows_extra", "columns_extra"])
    def test_not_on_a_bar(self, key):
        with pytest.raises(InvalidWidget, match="crosstab or matrix"):
            validate_widget_payload("bar", {"dimension": "a", "measure": "b", key: ["c"]})

    def test_only_a_list_of_names(self):
        with pytest.raises(InvalidWidget):
            validate_widget_payload("crosstab", {**CFG, "rows_extra": "country"})


@pytest.fixture
def sqlite_source(tmp_path):
    clear_widget_data_cache()
    p = tmp_path / "pivot.db"
    conn = sqlite3.connect(str(p))
    conn.execute("CREATE TABLE sales (continent TEXT, country TEXT, line TEXT, category TEXT, qty INTEGER, cost REAL)")
    conn.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)", ROWS)
    conn.commit()
    conn.close()
    yield {"type": "sqlite", "filepath": str(p)}
    clear_widget_data_cache()


def test_a_directquery_source_gives_the_same_cells(sqlite_source):
    ds = SimpleNamespace(source_table="sales", source_query=None, columns=[SimpleNamespace(name=c) for c in COLS])
    out = run_direct_query(sqlite_source, ds, CFG, widget_type="crosstab", cache_ttl_seconds=0)
    assert out["type"] == "pivot"
    assert _cell(out, ["Europe", "France"], ["Sports", "Golf"], "qty") == 15
    assert _cell(out, ["Europe", "Spain"], ["Outdoors", "Tents"], "cost") == 5.0
    assert out["missing_category"]["rows"] == 1
