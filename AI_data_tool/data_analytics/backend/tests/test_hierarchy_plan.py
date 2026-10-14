"""Hierarchies across widgets (2026-10-10): the slicer tree and its exact
"paths" filter, in the import engine and in DirectQuery SQL."""
import pandas as pd
import pytest

from app.services.direct_query import (DirectQueryUnsupported, _build_where, _is_bucket_filter, _needs_rows,
                                       _validate_known_columns)
from app.services.widget_data import _apply_filters, shape_slicer

DF = pd.DataFrame({
    "country": ["Egypt", "Egypt", "Egypt", "US", "US", None],
    "city": ["Cairo", "Alexandria", "Cairo", "Alexandria", "Boston", "x"],
    "d": pd.to_datetime(["2024-01-05", "2024-02-01", "2025-03-01", "2025-03-02", "2025-07-01", None]),
    "v": [1, 2, 3, 4, 5, 6],
})


def paths(*ps, columns=("country", "city"), grains=None):
    return {"column": columns[0], "op": "paths",
            "value": {"columns": list(columns), "paths": [list(p) for p in ps],
                      "granularities": grains or [None] * len(columns)}}


class TestThePathsFilter:
    def test_it_is_exact_per_path(self):
        out = _apply_filters(DF, [paths(("Egypt", "Alexandria"), ("US", "Boston"))])
        assert out[["country", "city"]].values.tolist() == [["Egypt", "Alexandria"], ["US", "Boston"]]

    def test_a_short_path_is_a_whole_branch(self):
        assert sorted(_apply_filters(DF, [paths(("Egypt",))])["v"]) == [1, 2, 3]

    def test_date_levels_compare_bucket_labels(self):
        f = paths(("2025", "2025-Q1"), columns=("d", "d"), grains=["year", "quarter"])
        assert sorted(_apply_filters(DF, [f])["v"]) == [3, 4]

    def test_a_widget_without_the_deeper_level_is_filtered_on_what_it_has(self):
        only_country = DF[["country", "v"]]
        assert sorted(_apply_filters(only_country, [paths(("US", "Boston"))])["v"]) == [4, 5]

    def test_a_widget_without_the_top_level_is_not_filtered(self):
        assert len(_apply_filters(DF[["v"]], [paths(("US",))])) == len(DF)


class TestTheSlicerTree:
    def test_nested_values_with_counts_after_other_filters(self):
        t = shape_slicer(DF, {"slicer_levels": ["country", "city"],
                              "filters": [{"column": "v", "op": "lte", "value": 4}]})
        assert t["type"] == "slicer_tree" and t["total"] == 4
        assert [(n["value"], n["count"], [c["value"] for c in n["children"]]) for n in t["nodes"]] == \
            [("Egypt", 3, ["Alexandria", "Cairo"]), ("US", 1, ["Alexandria"])]

    def test_a_date_chain(self):
        t = shape_slicer(DF, {"slicer_levels": [{"column": "d", "granularity": "year"},
                                                {"column": "d", "granularity": "quarter"}]})
        assert [(n["value"], [c["value"] for c in n["children"]]) for n in t["nodes"]] == \
            [("2024", ["2024-Q1"]), ("2025", ["2025-Q1", "2025-Q3"])]

    def test_an_unknown_level_says_so(self):
        assert shape_slicer(DF, {"slicer_levels": ["nope"]})["type"] == "error"


class TestDirectQuery:
    def test_paths_become_bound_sql(self):
        sql, params = _build_where([paths(("Egypt", "Alexandria"), ("US",))])
        assert sql == '(("country" = :f0_0_0 AND "city" = :f0_0_1) OR ("country" = :f0_1_0))'
        assert params == {"f0_0_0": "Egypt", "f0_0_1": "Alexandria", "f0_1_0": "US"}

    def test_no_paths_matches_nothing(self):
        assert _build_where([paths()])[0] == "1 = 0"

    def test_every_path_column_is_allow_listed(self):
        class Ds:
            columns = [type("C", (), {"name": n})() for n in ("country", "city")]
        _validate_known_columns(Ds(), [], [paths(("Egypt",))])
        with pytest.raises(DirectQueryUnsupported):
            _validate_known_columns(Ds(), [], [paths(("Egypt",), columns=("country", 'x"; DROP TABLE t; --'))])

    def test_date_bucket_paths_and_the_tree_are_computed_from_rows(self):
        assert _is_bucket_filter(paths(("2025",), columns=("d",), grains=["year"]))
        assert not _is_bucket_filter(paths(("Egypt",)))
        assert _needs_rows({"slicer_levels": ["country", "city"]})


class TestTheHierarchicalCrosstab:
    """Step 3: every group's value from its own rows, subtotals and grand totals."""

    def grid(self, **extra):
        from app.services.hier_pivot import shape_hier_pivot
        cfg = {"hierarchy_rows": [{"column": "country"}, {"column": "city"}],
               "hierarchy_columns": [{"column": "d", "granularity": "year"}],
               "measure": "v", "aggregation": "avg", **extra}
        out = shape_hier_pivot(DF, cfg)
        return out, {(tuple(r), tuple(c)): v for r, c, v in out["cells"]}

    def test_subtotals_of_an_average_are_the_groups_own_average(self):
        out, cells = self.grid()
        assert out["type"] == "hier_pivot"
        assert cells[(("Egypt",), ())] == 2           # (1+2+3)/3, not the average of city averages
        assert cells[(("Egypt", "Cairo"), ())] == 2   # (1+3)/2
        assert cells[((), ())] == 3                   # rows with a blank level are left out, and said so
        assert out["missing_category"]["rows"] == 1

    def test_every_row_and_column_level_has_cells(self):
        _, cells = self.grid()
        assert cells[(("Egypt",), ("2024",))] == 1.5
        assert cells[(("US", "Boston"), ("2025",))] == 5
        assert cells[((), ("2025",))] == 4            # (3+4+5)/3

    def test_the_trees_list_each_level(self):
        out, _ = self.grid()
        assert [n["value"] for n in out["row_tree"]] == ["Egypt", "US"]
        assert [c["value"] for c in out["row_tree"][0]["children"]] == ["Alexandria", "Cairo"]
        assert [n["value"] for n in out["column_tree"]] == ["2024", "2025"]

    def test_no_measure_counts_rows_and_no_columns_is_one_total_column(self):
        from app.services.hier_pivot import shape_hier_pivot
        out = shape_hier_pivot(DF, {"hierarchy_rows": [{"column": "country"}]})
        cells = {(tuple(r), tuple(c)): v for r, c, v in out["cells"]}
        assert cells == {(("Egypt",), ()): 3, (("US",), ()): 2, ((), ()): 5}

    def test_a_filter_applies_before_the_grid(self):
        _, cells = self.grid(filters=[paths(("US",))])
        assert cells[((), ())] == 4.5

    def test_an_unknown_column_is_an_error(self):
        from app.services.hier_pivot import shape_hier_pivot
        out = shape_hier_pivot(DF, {"hierarchy_rows": [{"column": "nope"}]})
        assert out["type"] == "error" and out["code"] == "unknown_field"


def test_a_column_level_with_too_many_values_is_left_out_not_cut(monkeypatch):
    """A date chain down to Day across the top: Day is dropped, every year stays."""
    from app.services import hier_pivot
    monkeypatch.setattr(hier_pivot, "MAX_COLUMN_PATHS", 3)
    out = hier_pivot.shape_hier_pivot(DF, {
        "hierarchy_rows": [{"column": "country"}],
        "hierarchy_columns": [{"column": "d", "granularity": "year"}, {"column": "d", "granularity": "month"}]})
    assert [n["value"] for n in out["column_tree"]] == ["2024", "2025"]
    assert all(not n["children"] for n in out["column_tree"])
    assert out["levels_dropped"]["columns"] == ["d (month)"]
    assert out["truncation"]["applied"] is False
