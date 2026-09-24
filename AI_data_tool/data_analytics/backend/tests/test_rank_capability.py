"""Ranking as a cross-widget capability: the newly covered shapers.

`shape_series` had Top/Bottom-N for a while (`test_rank_modes.py` pins it);
`shape_dual_series` (six widget types) and `shape_heatmap` (heatmap + ribbon)
silently ignored the same config -- the panel offered a control those shapers
never read. Selection now goes through ONE helper (`_rank_selection`) so ties,
percent mode and bottom-N cannot drift between shapers; the "All Other" bucket
stays per-shaper because an honest residual is shape-specific, and each one
here must RECONCILE -- a breakdown whose parts stop summing to the whole is
worse than no breakdown.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.widget_data import (_rank_selection, shape_dual_series,
                                      shape_heatmap)


@pytest.fixture
def frame():
    rng = np.random.default_rng(0)
    n = 210
    return pd.DataFrame({
        "cat": list("ABCDEFG") * 30,
        "v1": rng.integers(1, 100, n).astype(float),
        "v2": rng.integers(1, 50, n).astype(float),
        "col": rng.choice(["X", "Y", "Z"], n),
    })


class TestTheSharedSelection:
    def test_ties_at_the_boundary_are_kept(self):
        # SAS keeps them: "top 3" over values with a tie at third shows 4.
        vals = pd.Series([10.0, 9.0, 8.0, 8.0, 1.0])
        keep = _rank_selection(vals, {"rank": {"mode": "top", "n": 3}})
        assert int(keep.sum()) == 4

    def test_bottom_flips_the_boundary(self):
        vals = pd.Series([10.0, 9.0, 8.0, 1.0])
        keep = _rank_selection(vals, {"rank": {"mode": "bottom", "n": 2}})
        assert list(vals[keep]) == [8.0, 1.0]

    def test_percent_reads_n_as_a_share_of_categories(self):
        vals = pd.Series(range(10), dtype=float)
        keep = _rank_selection(vals, {"rank": {"mode": "top", "n": 30, "percent": True}})
        assert int(keep.sum()) == 3

    def test_no_rank_config_means_no_mask(self):
        assert _rank_selection(pd.Series([1.0, 2.0]), {}) is None

    def test_fewer_categories_than_n_means_no_mask(self):
        assert _rank_selection(pd.Series([1.0, 2.0]),
                               {"rank": {"mode": "top", "n": 5}}) is None


class TestDualSeriesRanks:
    CFG = {"roles": {"category": "cat", "measure": "v1", "measure2": "v2"},
           "aggregation": "sum"}

    def test_top_n_keeps_the_largest_by_primary_measure(self, frame):
        out = shape_dual_series(frame, {**self.CFG, "rank": {"mode": "top", "n": 3}})
        names = {r["name"] for r in out["rows"]}
        top3 = set(frame.groupby("cat")["v1"].sum().nlargest(3).index)
        assert names == top3

    def test_the_other_bucket_reconciles_both_measures(self, frame):
        # THE property. The residual is re-aggregated from the excluded
        # categories' RAW rows, so parts + Other == whole for BOTH axes.
        out = shape_dual_series(frame, {**self.CFG,
                                        "rank": {"mode": "top", "n": 3, "other": True}})
        rows = out["rows"]
        assert any(r["name"] == "All Other" for r in rows)
        assert sum(r["value"] for r in rows) == pytest.approx(frame["v1"].sum())
        assert sum(r["value2"] for r in rows) == pytest.approx(frame["v2"].sum())

    def test_an_avg_other_is_honest_not_an_average_of_averages(self, frame):
        out = shape_dual_series(frame, {**self.CFG, "aggregation": "avg",
                                        "rank": {"mode": "top", "n": 3, "other": True}})
        other = next(r for r in out["rows"] if r["name"] == "All Other")
        kept = {r["name"] for r in out["rows"]} - {"All Other"}
        raw_other = frame[~frame["cat"].isin(kept)]
        assert other["value"] == pytest.approx(raw_other["v1"].mean())

    def test_without_rank_config_nothing_changes(self, frame):
        assert len(shape_dual_series(frame, self.CFG)["rows"]) == 7


class TestHeatmapRanks:
    CFG = {"roles": {"category": "cat", "category2": "col", "measure": "v1"},
           "aggregation": "sum"}

    def test_top_n_keeps_the_largest_rows(self, frame):
        out = shape_heatmap(frame, {**self.CFG, "rank": {"mode": "top", "n": 2}})
        top2 = set(frame.groupby("cat")["v1"].sum().nlargest(2).index)
        assert set(out["rows_axis"]) == {str(v) for v in top2}

    def test_the_other_row_reconciles_the_grid_to_the_total(self, frame):
        out = shape_heatmap(frame, {**self.CFG,
                                    "rank": {"mode": "top", "n": 2, "other": True}})
        assert out["rows_axis"][-1] == "All Other"
        grid_total = sum(c for row in out["cells"] for c in row if c is not None)
        assert grid_total == pytest.approx(frame["v1"].sum())

    def test_every_other_cell_is_the_same_kind_of_number(self, frame):
        # Re-aggregated from raw per column, never a sum of the excluded rows'
        # aggregates -- pinned via avg, where the two disagree.
        out = shape_heatmap(frame, {**self.CFG, "aggregation": "avg",
                                    "rank": {"mode": "top", "n": 2, "other": True}})
        kept = set(out["rows_axis"]) - {"All Other"}
        raw_other = frame[~frame["cat"].astype(str).isin(kept)]
        expect = raw_other.groupby("col")["v1"].mean()
        other_cells = dict(zip(out["cols_axis"], out["cells"][-1]))
        for col, val in expect.items():
            assert other_cells[str(col)] == pytest.approx(val)

    def test_without_rank_config_nothing_changes(self, frame):
        assert len(shape_heatmap(frame, self.CFG)["rows_axis"]) == 7
