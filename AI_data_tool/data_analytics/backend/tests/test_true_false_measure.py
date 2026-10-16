"""UAT-9 follow-up: the widget-data result says when its measure is the
average of a true/false column, so every surface (builder, viewer, shared
link, embed, print) can show the share that is true as a percent -- 51.4%,
not 0.51 -- without the dataset ever having been profiled.

The server is the one place that knows: detect_types files a pandas bool
under 'numeric', so the column metadata cannot tell `on_time` from a rate
spread over 0..1, but the source file (its parquet sidecar, or the CSV
read the way the pandas path reads it) still holds a bool.
"""
import pandas as pd
import pytest

from app.core.config import settings
from app.services import duck_agg
from app.services.frame_cache import write_parquet_sidecar
from app.services.widget_data import clear_widget_data_cache, get_widget_data

KPI = {"measure": "on_time", "aggregation": "avg"}


@pytest.fixture
def csv(tmp_path):
    rows = []
    for i in range(1000):
        rows.append({"carrier": ["A", "B", "C"][i % 3],
                     "on_time": (i * 7919) % 1000 < 514,
                     "rate": round((i % 97) / 96, 4),
                     "flag01": i % 2})
    p = tmp_path / "ship.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return str(p)


@pytest.fixture(autouse=True)
def _clean():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


@pytest.fixture
def spy(monkeypatch):
    seen = {"ran": False}
    real = duck_agg.try_aggregate

    def _spy(*a, **kw):
        frame, reason = real(*a, **kw)
        seen["ran"] = frame is not None
        return frame, reason

    monkeypatch.setattr(duck_agg, "try_aggregate", _spy)
    return seen


def _kpi(csv, config=KPI, widget_type="kpi", **kw):
    return get_widget_data(csv, dict(config), widget_type=widget_type, use_cache=False, **kw)


def test_kpi_avg_of_bool_carries_the_hint_on_the_pandas_path(csv, monkeypatch, spy):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    r = _kpi(csv)
    assert not spy["ran"]
    assert r["rows"][0]["value"] == pytest.approx(0.514)
    assert r.get("measure_true_false") is True


def test_kpi_avg_of_bool_carries_the_hint_with_duckdb_pushdown_on(csv, monkeypatch, spy):
    # The parquet sidecar every upload gets; DuckDB reads it. (DuckDB has no
    # AVG(BOOLEAN) and declines, so pandas answers -- the hint must not
    # depend on which engine did: it is attached after either.)
    assert write_parquet_sidecar(csv)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    r = _kpi(csv)
    assert r["rows"][0]["value"] == pytest.approx(0.514)
    assert r.get("measure_true_false") is True


def test_the_hint_survives_the_result_cache(csv, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    first = get_widget_data(csv, dict(KPI), widget_type="kpi")
    again = get_widget_data(csv, dict(KPI), widget_type="kpi")
    assert first.get("measure_true_false") is True and again.get("measure_true_false") is True


def test_a_pre_aggregated_duckdb_answer_carries_it_too(csv, monkeypatch):
    """When DuckDB answers the average itself, the shaper sees one value per
    group and no bool is left in it; the hint still comes from the source
    column. (DuckDB has no AVG(BOOLEAN) today, so the plan is fed the 0/1
    twin of the column and its frame renamed back.)"""
    assert write_parquet_sidecar(csv)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    real, ran = duck_agg.try_aggregate, []

    def _as_number(file_path, config, *a, **kw):
        frame, reason = real(file_path, {**config, "measure": "flag01"}, *a, **kw)
        ran.append(frame is not None)
        return (frame.rename(columns={"flag01": "on_time"}) if frame is not None else None), reason

    monkeypatch.setattr(duck_agg, "try_aggregate", _as_number)
    r = _kpi(csv, {"dimension": "carrier", **KPI}, widget_type="bar")
    assert ran == [True], "the render must come from the DuckDB pre-aggregated frame"
    assert r["type"] == "series" and len(r["rows"]) == 3
    assert r.get("measure_true_false") is True


def test_bar_avg_of_bool_by_group_carries_the_hint(csv, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    r = _kpi(csv, {"dimension": "carrier", **KPI}, widget_type="bar")
    assert r.get("measure_true_false") is True


@pytest.mark.parametrize("pushdown", [False, True])
def test_a_rate_or_a_0_1_number_does_not(csv, monkeypatch, pushdown):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", pushdown)
    for col in ("rate", "flag01"):
        r = _kpi(csv, {"measure": col, "aggregation": "avg"})
        assert r["type"] != "error"
        assert "measure_true_false" not in r, col


@pytest.mark.parametrize("agg", ["sum", "count", "max"])
def test_other_aggregations_of_bool_do_not(csv, monkeypatch, agg):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    r = _kpi(csv, {"measure": "on_time", "aggregation": agg})
    assert "measure_true_false" not in r


def test_a_calculated_column_of_the_same_name_does_not(csv, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    calc = [{"name": "score", "expression": "rate * 2"}]
    r = _kpi(csv, {"measure": "score", "aggregation": "avg"}, calculated_columns=calc)
    assert "measure_true_false" not in r
