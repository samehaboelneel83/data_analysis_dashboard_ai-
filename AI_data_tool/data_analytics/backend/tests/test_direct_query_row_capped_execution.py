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
