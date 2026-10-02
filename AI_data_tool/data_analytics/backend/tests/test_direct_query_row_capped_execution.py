import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.direct_query import DirectQueryUnsupported, run_direct_query
from app.services.widget_data import clear_widget_data_cache, get_widget_data_from_df


@pytest.fixture(autouse=True)
def _clear_cache():
    # Same rationale as test_direct_query_execution.py's fixture: these tests
    # share a dataset/config/table shape (and a data_source_id-less fixture),
    # so without clearing, one test's cached result -- crucially including
    # `sampled`, which varies only by row_cap -- can leak into another.
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


ROWS = [(float(i), float(i) * 2) for i in range(1, 21)]  # 20 rows, x=1..20, y=2x


@pytest.fixture
def xy_sqlite_source(tmp_path):
    db_path = tmp_path / "row_capped_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE points (x REAL, y REAL)")
    conn.executemany("INSERT INTO points (x, y) VALUES (?, ?)", ROWS)
    conn.commit()
    conn.close()
    return {"type": "sqlite", "filepath": str(db_path)}


def _dataset(source_table="points", columns=("x", "y")):
    return SimpleNamespace(
        source_table=source_table, source_query=None,
        columns=[SimpleNamespace(name=c) for c in columns],
    )


def test_row_capped_under_cap_matches_import_mode_exactly(xy_sqlite_source):
    """When every row fits under the cap, no sampling happens -- the result must
    be byte-for-byte identical to import mode (a real pass-through, not merely
    'close enough'). This is the row_capped strategy's version of the grain
    invariant: the equivalence guarantee that survives at all only holds below
    the cap, so it must hold exactly there."""
    config = {"roles": {"measure": "x", "measure2": "y"}}

    direct_result = run_direct_query(xy_sqlite_source, _dataset(), config, widget_type="numeric_series")

    df = pd.DataFrame(ROWS, columns=["x", "y"])
    import_result = get_widget_data_from_df(df, config, widget_type="numeric_series")

    assert direct_result["rows"] == import_result["rows"]
    assert direct_result["sampled"] is False
    assert direct_result["total"] == import_result["total"] == 20


def test_row_capped_over_cap_samples_and_reports_indicator(xy_sqlite_source):
    config = {"roles": {"measure": "x", "measure2": "y"}}

    result = run_direct_query(
        xy_sqlite_source, _dataset(), config, widget_type="numeric_series", row_cap=5,
    )

    assert result["sampled"] is True
    assert result["sample_size"] == 5
    assert result["total_rows"] == 20
    # the widget's own `total` must still report the TRUE total, not the sample size --
    # a "20 points" widget must not silently relabel itself "5 points" just because
    # it's rendering a sample.
    assert result["total"] == 20
    assert len(result["rows"]) <= 5


def test_row_capped_rejects_unsupported_widget_type(xy_sqlite_source):
    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(xy_sqlite_source, _dataset(), {"dimension": "x"}, widget_type="bar_that_is_not_row_capped")


def test_row_capped_applies_rls_filter(xy_sqlite_source):
    config = {"roles": {"measure": "x", "measure2": "y"}}

    result = run_direct_query(
        xy_sqlite_source, _dataset(), config, widget_type="numeric_series", rls_filter_expr="x <= 5",
    )

    assert result["total"] == 5
    assert all(row["x"] <= 5 for row in result["rows"])


def test_row_capped_rls_is_fail_closed_on_untranslatable_expression(xy_sqlite_source, monkeypatch):
    import app.services.direct_query as direct_query_module

    def _spy_get_engine(cfg):
        raise AssertionError("engine should never be created for an untranslatable RLS expression")

    monkeypatch.setattr(direct_query_module, "get_engine", _spy_get_engine)

    config = {"roles": {"measure": "x", "measure2": "y"}}

    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(
            xy_sqlite_source, _dataset(), config, widget_type="numeric_series",
            rls_filter_expr="SUM(x) > 100",
        )


def test_row_capped_drops_denied_columns_before_shaping(xy_sqlite_source):
    # The fetch is SELECT *; a table with no column list draws whatever it gets.
    result = run_direct_query(xy_sqlite_source, _dataset(), {}, widget_type="table",
                              drop_columns=["y"])
    assert result["columns"] == ["x"]
    assert result["total"] == 20


def test_a_warm_unrestricted_entry_is_not_served_to_a_restricted_role(xy_sqlite_source):
    run_direct_query(xy_sqlite_source, _dataset(), {}, widget_type="table", cache_ttl_seconds=60)
    restricted = run_direct_query(xy_sqlite_source, _dataset(), {}, widget_type="table",
                                  cache_ttl_seconds=60, drop_columns=["y"])
    assert restricted["columns"] == ["x"]


@pytest.mark.parametrize("agg,expected", [
    ("sum", 210.0), ("avg", 10.5), ("min", 1.0), ("max", 20.0),
    ("count", 20), ("countd", 20),
])
def test_a_sampled_kpi_is_remeasured_over_every_row(xy_sqlite_source, agg, expected):
    """HR re-test 2026-10-01: "Total Headcount" read 10,000 on a 240,124-row
    live dataset -- the KPI aggregated the 10k sample. Above the cap the plain
    aggregates are now computed in SQL over the real rows and not flagged."""
    result = run_direct_query(xy_sqlite_source, _dataset(),
                              {"measure": "x", "aggregation": agg},
                              widget_type="kpi", row_cap=5)
    assert result["rows"][0]["value"] == pytest.approx(expected)
    assert result["sampled"] is False
    assert result["total"] == 20


def test_a_sampled_kpi_respects_its_filters(xy_sqlite_source):
    result = run_direct_query(
        xy_sqlite_source, _dataset(),
        {"measure": "x", "aggregation": "count",
         "filters": [{"column": "x", "op": "gt", "value": 10}]},
        widget_type="kpi", row_cap=3)
    assert result["rows"][0]["value"] == 10


def test_a_median_kpi_reads_every_row_not_the_drawing_cap(xy_sqlite_source):
    """A median cannot be re-measured in portable SQL, so it used to stay a
    sample of the 10,000-row drawing cap -- 69,934 then 69,915 on two loads
    for a true 69,805 (HR analyst panel, 2026-10-02). It now takes the
    analysis cap, like every other aggregate fetched for computing."""
    import statistics
    result = run_direct_query(xy_sqlite_source, _dataset(),
                              {"measure": "x", "aggregation": "median"},
                              widget_type="kpi", row_cap=5)
    assert not result.get("sampled")
    assert result["rows"][0]["value"] == statistics.median(r[0] for r in ROWS)


def test_a_sampled_multi_row_card_is_remeasured_row_by_row(xy_sqlite_source):
    """Analyst panel dashboard 2026-10-02: a "Workforce snapshot" card read a
    headcount of 10,000 -- the cap -- on a 240,124-row live dataset."""
    result = run_direct_query(xy_sqlite_source, _dataset(),
                              {"measures": ["x", "y"], "aggregation": "countd"},
                              widget_type="card", row_cap=5)
    assert [r["value"] for r in result["rows"]] == [20, 20]
    assert result["sampled"] is False
