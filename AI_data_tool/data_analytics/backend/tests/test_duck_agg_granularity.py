"""Date bucketing (`dimension_granularity`) on the DuckDB path.

`line_month` -- a date dimension bucketed by month -- was 5.35s cold at 1M
rows, 4s above the frame load, because `dimension_granularity` was not on the
DuckDB allowlist and pandas parsed a million date strings. DuckDB's own date
functions are the same operation.

The contract is unchanged: identical to pandas, or DuckDB does not run. Two
places that is harder than it looks, both pinned:

  * pandas hands the column back UNTOUCHED when nothing in it parses as a date
    (a department name with a stale granularity left on it). DuckDB probes
    first and declines in that case.
  * pandas parses more formats than DuckDB's TRY_CAST ("01/02/2024" is
    January 2nd to pandas and NULL to DuckDB). If any non-null value fails to
    cast, DuckDB declines rather than silently dropping rows pandas would
    have bucketed.

And one shape detail: the shaper re-buckets whatever DuckDB returns, so every
label must survive a second pass unchanged -- which an integer year does not
(`pd.to_datetime(2024)` is 1970-01-01 plus 2024 ns). Year comes back as text.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import duck_agg
from app.services.duck_agg import Ineligible, plan
from app.services.widget_data import clear_widget_data_cache, get_widget_data

BASE = {"dimension": "order_date", "measure": "sales", "aggregation": "sum"}


@pytest.fixture
def csv(tmp_path):
    """ISO dates across two years and a year boundary that ISO weeks care
    about, one null, and a text column with a granularity that cannot apply."""
    rows = []
    dates = ["2024-01-05", "2024-01-20", "2024-03-31", "2024-06-15", "2024-12-30",
             "2025-01-02", "2025-04-01", None, "2025-12-29"]
    for i in range(180):
        rows.append({"order_date": dates[i % len(dates)], "sales": float(i % 37),
                     "department": ["ops", "sales", "hr"][i % 3]})
    p = tmp_path / "dates.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return str(p)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


@pytest.fixture
def spy(monkeypatch):
    seen = {"ran": False, "reason": "not consulted"}
    real = duck_agg.try_aggregate

    def _spy(*a, **kw):
        frame, reason = real(*a, **kw)
        seen["ran"], seen["reason"] = frame is not None, reason
        return frame, reason

    monkeypatch.setattr(duck_agg, "try_aggregate", _spy)
    return seen


def both(csv, monkeypatch, config):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    clear_widget_data_cache()
    p = get_widget_data(csv, dict(config), widget_type="line", use_cache=False)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    clear_widget_data_cache()
    d = get_widget_data(csv, dict(config), widget_type="line", use_cache=False)
    return p, d


def assert_same(p, d):
    assert [r["name"] for r in p["rows"]] == [r["name"] for r in d["rows"]]
    for a, b in zip(p["rows"], d["rows"]):
        assert b["value"] == pytest.approx(a["value"], rel=1e-9)
    assert p["total"] == d["total"]


class TestParity:
    @pytest.mark.parametrize("gran", ["month", "quarter", "year", "week", "day"])
    def test_every_granularity_matches_pandas(self, csv, monkeypatch, spy, gran):
        p, d = both(csv, monkeypatch, dict(BASE, dimension_granularity=gran))
        assert spy["ran"], spy["reason"]
        assert_same(p, d)

    def test_labels_are_the_documented_shapes(self, csv, monkeypatch, spy):
        _, d = both(csv, monkeypatch, dict(BASE, dimension_granularity="week"))
        names = [r["name"] for r in d["rows"]]
        # 2025-12-29 is ISO 2026-W01 -- the case the pandas comment is about.
        assert "2026-W01" in names
        assert all(len(n) == 8 and n[4:6] == "-W" for n in names), names

    def test_year_survives_the_shaper_second_pass(self, csv, monkeypatch, spy):
        """An integer year re-parses as 1970; text does not."""
        p, d = both(csv, monkeypatch, dict(BASE, dimension_granularity="year"))
        assert spy["ran"], spy["reason"]
        assert [r["name"] for r in d["rows"]] == [2024, 2025]
        assert_same(p, d)

    def test_a_null_date_is_dropped_from_groups_but_counted_in_total(self, csv, monkeypatch, spy):
        p, d = both(csv, monkeypatch, dict(BASE, dimension_granularity="month"))
        assert spy["ran"]
        assert d["total"] == 180                      # nulls counted, as pandas does
        assert all(r["name"] for r in d["rows"])      # but no NaN bucket

    def test_with_a_filter_and_an_rls_rule(self, csv, monkeypatch, spy):
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
        clear_widget_data_cache()
        cfg = dict(BASE, dimension_granularity="quarter",
                   filters=[{"column": "department", "op": "eq", "value": "ops"}])
        p = get_widget_data(csv, cfg, widget_type="line", use_cache=False,
                            rls_filter_expr="sales > 5")
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        clear_widget_data_cache()
        d = get_widget_data(csv, cfg, widget_type="line", use_cache=False,
                            rls_filter_expr="sales > 5")
        assert spy["ran"], spy["reason"]
        assert_same(p, d)


class TestDeclines:
    def test_a_column_with_no_dates_stays_on_pandas(self, csv, monkeypatch, spy):
        """pandas hands the raw column back; DuckDB would return nothing."""
        p, d = both(csv, monkeypatch, {"dimension": "department", "measure": "sales",
                                       "aggregation": "sum", "dimension_granularity": "month"})
        assert not spy["ran"]
        # The raw departments, untouched -- not one "<NA>-Q<NA>" bucket.
        assert sorted(r["name"] for r in p["rows"]) == ["hr", "ops", "sales"]
        assert_same(p, d)

    def test_a_format_pandas_parses_and_duckdb_does_not_stays_on_pandas(self, tmp_path, monkeypatch, spy):
        p = tmp_path / "us.csv"
        pd.DataFrame({"order_date": ["01/02/2024", "03/04/2024", "2024-05-06"],
                      "sales": [1.0, 2.0, 3.0]}).to_csv(p, index=False)
        pr, d = both(str(p), monkeypatch, dict(BASE, dimension_granularity="month"))
        assert not spy["ran"], "DuckDB dropped rows pandas would have bucketed"
        assert_same(pr, d)

    def test_an_unknown_granularity_is_ineligible(self):
        with pytest.raises(Ineligible, match="granularity"):
            plan(dict(BASE, dimension_granularity="fortnight"),
                 ["order_date", "sales"], "src")

    def test_an_empty_granularity_is_no_granularity(self):
        """Callers pass None/'' routinely; that is 'group by the raw column'."""
        p = plan(dict(BASE, dimension_granularity=""), ["order_date", "sales"], "src")
        assert "TRY_CAST" not in p.sql
