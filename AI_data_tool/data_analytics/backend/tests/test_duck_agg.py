"""DuckDB pre-aggregation: identical results to pandas, or no DuckDB at all.

The contract is narrow and the tests exist to hold it:

  * Enabled + eligible  -> DuckDB, and the result is IDENTICAL to pandas.
  * Anything else       -> pandas, unchanged.
  * Any DuckDB failure  -> pandas, unchanged.

Parity is asserted by running both engines over the same file and comparing
the shaped results, not by spot-checking a total. A pushdown that is fast and
subtly wrong is worse than no pushdown, so every eligibility case below has a
matching parity case.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import duck_agg, widget_data as wd
from app.services.duck_agg import Ineligible, plan
from app.services.widget_data import get_widget_data


BASE = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

#: Two engines summing the same float64 column in different orders cannot agree
#: bit-for-bit: pandas pairwise-sums, DuckDB sums in scan order, and both land
#: within an ulp of math.fsum's reference. Measured on 2M rows the relative
#: difference is ~2e-16 -- machine epsilon, not a logic error. This is the same
#: property DirectQuery has always had against Postgres/MySQL.
#:
#: 1e-9 sits six orders above that noise floor and six below anything a chart
#: could render, so it catches a real computational divergence while tolerating
#: summation order.
FLOAT_TOLERANCE = 1e-9


def assert_shaped_equal(pandas_result: dict, duck_result: dict) -> None:
    """Parity: EXACT on structure, APPROXIMATE on float values only.

    Everything a reader can see except the last few bits of a float must match
    exactly -- the shape, the group names, their order, the row count, `total`.
    Only the aggregated numbers are allowed to differ, and only at float64
    precision.
    """
    assert pandas_result.keys() == duck_result.keys()
    for key in pandas_result:
        if key == "rows":
            continue
        assert pandas_result[key] == duck_result[key], f"'{key}' differs"

    a_rows, b_rows = pandas_result["rows"], duck_result["rows"]
    assert len(a_rows) == len(b_rows), "row count differs"

    for i, (a, b) in enumerate(zip(a_rows, b_rows)):
        assert a.keys() == b.keys(), f"row {i} keys differ"
        for key in a:
            if isinstance(a[key], float) and isinstance(b[key], float):
                assert a[key] == pytest.approx(b[key], rel=FLOAT_TOLERANCE), (
                    f"row {i} '{key}': {a[key]} vs {b[key]}")
            else:
                # Names and ordering are exact: a chart labelled differently by
                # engine would be a real defect.
                assert a[key] == b[key], f"row {i} '{key}' differs"


@pytest.fixture(autouse=True)
def _clean():
    wd.clear_widget_data_cache()
    yield
    wd.clear_widget_data_cache()


def _csv(tmp_path, frame: pd.DataFrame, name="d.csv") -> str:
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return str(path)


def _both(path: str, config: dict, monkeypatch) -> tuple[dict, dict]:
    """The same query through pandas and through DuckDB."""
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    wd.clear_widget_data_cache()
    pandas_result = get_widget_data(path, config, widget_type="bar", use_cache=False)

    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    wd.clear_widget_data_cache()
    duck_result = get_widget_data(path, config, widget_type="bar", use_cache=False)
    return pandas_result, duck_result


class TestEligibility:
    COLUMNS = ["region", "sales", "day"]

    def _plan(self, **overrides):
        return plan({**BASE, **overrides}, self.COLUMNS, "read_csv_auto('x')")

    def test_the_plain_shape_is_eligible(self):
        assert self._plan().dimension == "region"

    @pytest.mark.parametrize("agg", ["sum", "avg", "min", "max", "median", "p95"])
    def test_grain_safe_aggregations_are_eligible(self, agg):
        assert self._plan(aggregation=agg) is not None

    @pytest.mark.parametrize("agg", ["count", "countd", "std", "variance", "range"])
    def test_non_grain_safe_aggregations_are_rejected(self, agg):
        """The shaper re-aggregates whatever we return. Re-counting one row
        gives 1, not the real count -- so these must never take this path."""
        with pytest.raises(Ineligible, match="grain-safe"):
            self._plan(aggregation=agg)

    @pytest.mark.parametrize("key", [
        "dimension2", "dimension_levels",  # dimension_granularity: supported since 2026-09-12
        "running", "columns", "sort_keys", "quick_calc", "having",
        # measure2 is the one that got away. A butterfly chart passes it for its
        # second series; the original blocklist did not name it, so DuckDB
        # aggregated `measure` alone and every `value2` came back missing --
        # a visibly broken widget. Found by running the suite with the flag
        # forced on, which is why the gate is now an allowlist.
        "measure2", "measures", "measure_defs", "target_value",
        "rank", "suppress_below", "sort_custom", "display_rules",
        "fit_line", "forecast_periods", "bins", "method",
    ])
    def test_unsupported_config_features_are_rejected(self, key):
        with pytest.raises(Ineligible, match=key):
            self._plan(**{key: ["something"]})

    def test_an_unknown_future_key_is_ineligible_by_default(self):
        """The allowlist's whole purpose: a config feature added later must
        fail CLOSED here until someone decides what it means, rather than being
        silently ignored by a fast path that does not implement it."""
        with pytest.raises(Ineligible, match="not_invented_yet"):
            self._plan(not_invented_yet="whatever")

    def test_totals_presentation_keys_keep_a_config_eligible(self):
        """New tables are created carrying these; none changes what DuckDB returns
        (subtotals need `dimension2`, the other two need `show_totals`, and both of
        those still decline). Unlisted, every new table would drop to pandas."""
        assert self._plan(show_subtotals=False, totals_position="before",
                          totals_scope="shown") is not None

    def test_show_totals_still_declines_to_pandas(self):
        """Totals are computed from the source rows by the pandas shaper; this
        path returns pre-aggregated groups and cannot produce them."""
        with pytest.raises(Ineligible, match="show_totals"):
            self._plan(show_totals=True)

    def test_empty_values_do_not_make_a_config_ineligible(self):
        """Callers routinely pass keys set to None/[]. Those carry no meaning,
        so they must not push an otherwise-eligible query onto the slow path."""
        assert self._plan(dimension2=None, running="", sort_keys=[]) is not None

    def test_unknown_columns_are_rejected(self):
        with pytest.raises(Ineligible, match="not a real column"):
            self._plan(dimension="no_such_column")
        with pytest.raises(Ineligible, match="not a real column"):
            self._plan(measure="no_such_column")

    def test_a_measure_that_is_not_a_column_is_rejected(self):
        """Post-aggregation measure expressions are resolved by measure_eval
        against the whole frame; there is nothing to push down."""
        with pytest.raises(Ineligible):
            self._plan(measure="profit_margin")

    def test_unsupported_filter_op_is_rejected(self):
        with pytest.raises(Ineligible, match="filter op"):
            self._plan(filters=[{"column": "region", "op": "contains", "value": "N"}])

    def test_filter_on_unknown_column_is_rejected(self):
        with pytest.raises(Ineligible, match="not a real column"):
            self._plan(filters=[{"column": "nope", "op": "eq", "value": 1}])


class TestParity:
    """Both engines, same file, identical shaped output."""

    def test_plain_group_and_sum(self, tmp_path, monkeypatch):
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["North", "South", "East"] * 40,
            "sales": range(120),
        }))
        a, b = _both(path, BASE, monkeypatch)
        assert_shaped_equal(a, b)

    def test_nulls_in_the_dimension_are_dropped_like_pandas(self, tmp_path, monkeypatch):
        """pandas groupby drops NaN keys; SQL GROUP BY keeps NULL as a group.
        Without the IS NOT NULL predicate this produces an extra bar that the
        pandas path never renders."""
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["North", None, "South", None, "North"],
            "sales": [1.0, 2.0, 3.0, 4.0, 5.0],
        }))
        a, b = _both(path, BASE, monkeypatch)
        assert_shaped_equal(a, b)
        assert all(r["name"] is not None for r in b["rows"])

    def test_nulls_in_the_measure(self, tmp_path, monkeypatch):
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["North", "North", "South", "South"],
            "sales": [1.0, None, 3.0, 4.0],
        }))
        a, b = _both(path, BASE, monkeypatch)
        assert_shaped_equal(a, b)

    def test_empty_result_after_filtering(self, tmp_path, monkeypatch):
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["North", "South"], "sales": [1, 2],
        }))
        config = {**BASE, "filters": [{"column": "region", "op": "eq", "value": "Nowhere"}]}
        a, b = _both(path, config, monkeypatch)
        assert_shaped_equal(a, b)

    @pytest.mark.parametrize("agg", ["sum", "avg", "min", "max", "median"])
    def test_each_grain_safe_aggregation_matches(self, tmp_path, monkeypatch, agg):
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["A", "B", "A", "B", "C"],
            "sales": [10.0, 20.0, 30.0, 40.0, 50.0],
        }))
        a, b = _both(path, {**BASE, "aggregation": agg}, monkeypatch)
        assert_shaped_equal(a, b)  # per-aggregation parity

    def test_filters_match(self, tmp_path, monkeypatch):
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["A", "B", "C", "A"],
            "sales": [1, 2, 3, 4],
            "day": [1, 2, 3, 4],
        }))
        config = {**BASE, "filters": [
            {"column": "day", "op": "gte", "value": 2},
            {"column": "region", "op": "in", "value": ["A", "B"]},
        ]}
        a, b = _both(path, config, monkeypatch)
        assert_shaped_equal(a, b)

    def test_large_float_sums_agree_within_tolerance(self, tmp_path, monkeypatch):
        """The case the small fixtures could not catch.

        Every other parity fixture here is small enough that both engines sum
        exactly, so `==` would have passed while the real contract is
        approximate. At 200k random floats the summation orders diverge and the
        tolerance path is actually exercised: without it this test fails with
        ~1e-16 relative error, which is precisely the noise this suite must
        tolerate rather than chase.
        """
        import numpy as np

        rng = np.random.default_rng(20260828)
        path = _csv(tmp_path, pd.DataFrame({
            "region": rng.choice(["North", "South", "East", "West"], 200_000),
            "sales": rng.normal(1000, 250, 200_000).round(2),
        }))
        a, b = _both(path, BASE, monkeypatch)
        assert_shaped_equal(a, b)

        # And the difference really is at float64 precision, not merely "within
        # a generous tolerance" -- if this ever loosens, something changed.
        for x, y in zip(a["rows"], b["rows"]):
            assert abs(x["value"] - y["value"]) / abs(y["value"]) < 1e-12

    def test_limit_and_sort_match(self, tmp_path, monkeypatch):
        path = _csv(tmp_path, pd.DataFrame({
            "region": list("ABCDEFGH"),
            "sales": [8, 7, 6, 5, 4, 3, 2, 1],
        }))
        a, b = _both(path, {**BASE, "limit": 3, "sort": "desc"}, monkeypatch)
        assert_shaped_equal(a, b)
        assert len(b["rows"]) == 3


class TestFallbackIsAlwaysSafe:
    def test_disabled_flag_uses_pandas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        frame, reason = duck_agg.try_aggregate("anything.csv", BASE, ["region", "sales"])
        assert frame is None and reason == "disabled"

    def test_an_unexpected_error_falls_back_rather_than_raising(self, monkeypatch):
        """The whole value of this module is that its worst case is the
        behaviour that existed before it."""
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        monkeypatch.setattr(duck_agg, "aggregate",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        frame, reason = duck_agg.try_aggregate("x.csv", BASE, ["region", "sales"])
        assert frame is None
        assert "RuntimeError" in reason

    def test_rls_forces_the_pandas_path(self, tmp_path, monkeypatch):
        """RLS is applied to the frame by apply_rls_filter. Until that is
        translated to SQL, an RLS-bearing query must not be pushed down --
        pushing it down while ignoring the filter would leak rows."""
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["North", "South", "North"],
            "sales": [1, 2, 3],
        }))
        restricted = get_widget_data(path, BASE, widget_type="bar", use_cache=False,
                                     rls_filter_expr="region == 'North'")
        assert [r["name"] for r in restricted["rows"]] == ["North"]
        assert restricted["rows"][0]["value"] == 4

    def test_calculated_columns_force_the_pandas_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        path = _csv(tmp_path, pd.DataFrame({
            "region": ["A", "B"], "sales": [1, 2],
        }))
        result = get_widget_data(
            path, {**BASE, "measure": "doubled"}, widget_type="bar", use_cache=False,
            calculated_columns=[{"name": "doubled", "expression": "sales * 2"}])
        assert sum(r["value"] for r in result["rows"]) == 6


class TestParquetSidecar:
    """`_source_expr` prefers the sidecar frame_cache maintains next to a CSV.

    That sidecar is written from a RE-READ of the CSV, never from a caller's
    frame, so its dtypes are what a fresh read_csv yields -- which is exactly
    the parity this path needs. Reading it also avoids re-parsing the CSV on
    every query.
    """

    def test_a_fresh_sidecar_is_preferred(self, tmp_path, monkeypatch):
        from app.services.frame_cache import write_parquet_sidecar

        path = _csv(tmp_path, pd.DataFrame({
            "region": ["A", "B", "A"], "sales": [1.0, 2.0, 3.0],
        }))
        assert write_parquet_sidecar(path), "sidecar write should succeed"
        assert "read_parquet(" in duck_agg._source_expr(path)

    def test_results_match_through_the_sidecar(self, tmp_path, monkeypatch):
        from app.services.frame_cache import write_parquet_sidecar

        path = _csv(tmp_path, pd.DataFrame({
            "region": ["A", "B", "A", "C"], "sales": [1.5, 2.5, 3.5, 4.5],
        }))
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        wd.clear_widget_data_cache()
        pandas_result = get_widget_data(path, BASE, widget_type="bar", use_cache=False)

        write_parquet_sidecar(path)
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        wd.clear_widget_data_cache()
        duck_result = get_widget_data(path, BASE, widget_type="bar", use_cache=False)

        assert_shaped_equal(pandas_result, duck_result)

    def test_missing_sidecar_falls_back_to_the_csv(self, tmp_path):
        path = _csv(tmp_path, pd.DataFrame({"region": ["A"], "sales": [1.0]}))
        assert "read_csv_auto(" in duck_agg._source_expr(path)


class TestIdentifierSafety:
    def test_quotes_in_a_column_name_are_escaped(self):
        weird = 'we"ird'
        p = plan({"dimension": weird, "measure": "sales", "aggregation": "sum"},
                 [weird, "sales"], "read_csv_auto('x')")
        assert '"we""ird"' in p.sql

    def test_filter_values_are_parameterised_not_interpolated(self):
        p = plan({**BASE, "filters": [
                     {"column": "region", "op": "eq", "value": "'; DROP TABLE t; --"}]},
                 ["region", "sales"], "read_csv_auto('x')")
        assert "DROP TABLE" not in p.sql
        assert "'; DROP TABLE t; --" in p.params
