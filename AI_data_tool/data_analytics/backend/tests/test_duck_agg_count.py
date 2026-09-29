"""Count charts ("rows per value", no measure) on an uploaded file run in DuckDB.

They used to decline ("no measure") and load the whole file into pandas --
the most common chart there is, on the slowest path. The DuckDB answer must
be the pandas answer, field for field.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.services import duck_agg
from app.services.widget_data import clear_widget_data_cache, get_widget_data


@pytest.fixture
def csv(tmp_path):
    rng = np.random.default_rng(5)
    n = 4000
    df = pd.DataFrame({
        "region": rng.choice(["north", "south", "east", "west", None], n),
        "d": pd.date_range("2024-01-01", periods=n, freq="3h").strftime("%Y-%m-%d %H:%M:%S"),
        "amount": np.round(rng.uniform(1, 100, n), 2),
    })
    p = tmp_path / "c.csv"
    df.to_csv(p, index=False)
    return str(p)


CASES = [
    {"dimension": "region"},
    {"dimension": "region", "aggregation": "count"},
    {"dimension": "region", "sort_by": "name", "sort": "asc", "limit": 2},
    {"dimension": "region", "filters": [{"column": "amount", "op": "gt", "value": 50}]},
    {"dimension": "region", "show_totals": True, "limit": 2},
]


def _strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("executor", "timing")}


@pytest.mark.parametrize("cfg", CASES, ids=[str(i) for i in range(len(CASES))])
@pytest.mark.parametrize("wt", ["bar", "donut", "table"])
def test_duckdb_count_equals_pandas(csv, cfg, wt, monkeypatch):
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", False)
    clear_widget_data_cache()
    want = get_widget_data(csv, cfg, widget_type=wt, use_cache=False)
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    calls = []
    real = duck_agg.aggregate
    monkeypatch.setattr(duck_agg, "aggregate", lambda *a, **k: calls.append(1) or real(*a, **k))
    got = get_widget_data(csv, cfg, widget_type=wt, use_cache=False)
    assert calls, "DuckDB was not used"
    assert _strip(got) == _strip(want)


def test_a_count_by_month_keeps_its_partial_period_note_on_pandas():
    with pytest.raises(duck_agg.Ineligible):
        duck_agg.plan({"dimension": "d", "dimension_granularity": "month"}, ["d"], "t")


def test_pct_without_a_measure_stays_pandas(csv):
    with pytest.raises(duck_agg.Ineligible):
        duck_agg.plan({"dimension": "region", "aggregation": "pct"}, ["region", "d", "amount"], "t")
