"""Phase 6.2: lattice rows/columns on the cartesian family."""
import pandas as pd
import pytest

from app.services.widget_data import LATTICE_MAX_CELLS, get_widget_data_from_df


@pytest.fixture
def df():
    rows = []
    for region, k in (("N", 3), ("S", 2), ("E", 1)):
        for channel in ("web", "store"):
            for month in ("2026-01-10", "2026-02-10", "2026-03-10"):
                rows.append({"region": region, "channel": channel, "d": month, "sales": 10.0 * k})
    return pd.DataFrame(rows)


def test_rows_by_columns_grid_with_shared_domain(df):
    cfg = {"dimension": "d", "measure": "sales", "aggregation": "sum",
           "lattice_rows": "region", "lattice_columns": "channel"}
    res = get_widget_data_from_df(df, cfg, "line")
    assert res["type"] == "lattice" and res["inner"] == "line"
    assert res["row_values"] == ["N", "S", "E"] or set(res["row_values"]) == {"N", "S", "E"}
    assert len(res["cells"]) == 6
    cell = next(c for c in res["cells"] if c["row"] == "N" and c["col"] == "web")
    assert [r["value"] for r in cell["result"]["rows"]] == [30.0, 30.0, 30.0]
    assert res["domain"] == [0.0, 30.0]
    assert res["lattice_truncation"] is None


def test_one_role_is_enough(df):
    res = get_widget_data_from_df(df, {"dimension": "channel", "measure": "sales",
                                       "lattice_columns": "region"}, "bar")
    assert res["type"] == "lattice" and res["row_values"] == [] and len(res["cells"]) == 3


def test_panels_are_capped_and_the_cut_is_worded():
    df = pd.DataFrame({"a": [f"a{i}" for i in range(20) for _ in range(20)],
                       "b": [f"b{j}" for _ in range(20) for j in range(20)], "v": 1.0, "x": "k"})
    res = get_widget_data_from_df(df, {"dimension": "x", "measure": "v",
                                       "lattice_rows": "a", "lattice_columns": "b"}, "bar")
    assert len(res["cells"]) <= LATTICE_MAX_CELLS
    assert "of 20 a values" in res["lattice_truncation"]["text"]


def test_other_widget_types_ignore_lattice_and_missing_columns_degrade(df):
    assert get_widget_data_from_df(df, {"dimension": "region", "measure": "sales",
                                        "lattice_rows": "channel"}, "pie")["type"] != "lattice"
    res = get_widget_data_from_df(df, {"dimension": "region", "measure": "sales",
                                       "lattice_rows": "gone"}, "bar")
    assert res["type"] != "lattice" and "gone" in res["lattice_note"]


def test_stacked_domain_spans_row_sums(df):
    res = get_widget_data_from_df(df, {"dimension": "d", "dimension2": "channel", "measure": "sales",
                                       "bar_mode": "stacked", "lattice_rows": "region"}, "bar")
    assert res["domain"][1] == pytest.approx(60.0)


def test_filters_decide_which_panels_exist(df):
    res = get_widget_data_from_df(df, {"dimension": "d", "measure": "sales", "lattice_rows": "region",
                                       "filters": [{"column": "region", "op": "neq", "value": "E"}]}, "bar")
    assert set(res["row_values"]) == {"N", "S"}
