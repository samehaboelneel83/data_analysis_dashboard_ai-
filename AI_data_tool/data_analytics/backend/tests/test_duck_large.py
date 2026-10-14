"""On a dataset too large to load, a count by month, a number with its
history, a second split and a spread are answered by DuckDB from the file
(duck_agg.large_aggregate / daily_frame) -- and must say exactly what the
ordinary path says on a dataset that fits."""
import numpy as np
import pandas as pd
import pytest

from app.services import frame_cache, widget_data as wd
from app.services import memory_guard as mg

N = 6000

CHARTS = [
    ("count by month", "line", {"dimension": "when", "dimension_granularity": "month"}),
    ("count by week, filtered", "line", {"dimension": "when", "dimension_granularity": "week",
                                         "filters": [{"column": "kind", "op": "eq", "value": "x"}]}),
    ("number with its history", "kpi", {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"}),
    ("highest with its history by month", "kpi", {"measure": "amount", "aggregation": "max", "sparkline_date": "when",
                                                  "sparkline_granularity": "month"}),
    ("how many with its history", "kpi", {"measure": "amount", "aggregation": "count", "sparkline_date": "when"}),
    ("second split", "bar", {"dimension": "grp", "dimension2": "kind", "measure": "amount", "aggregation": "sum"}),
    ("second split, counted", "bar", {"dimension": "grp", "dimension2": "kind"}),
    ("second split by month", "line", {"dimension": "when", "dimension_granularity": "month", "dimension2": "kind",
                                       "measure": "amount", "aggregation": "max"}),
    ("spread", "bar", {"dimension": "grp", "measure": "amount", "aggregation": "std"}),
    ("variance", "bar", {"dimension": "grp", "measure": "amount", "aggregation": "var"}),
    ("different values", "bar", {"dimension": "grp", "measure": "code", "aggregation": "countd"}),
]


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    rng = np.random.default_rng(11)
    df = pd.DataFrame({
        # ends part-way through a month, so the partial-period note is in play
        "when": pd.date_range("2023-01-01", periods=N, freq="3h"),
        "grp": rng.choice(["a", "b", "c", None], N, p=[.4, .3, .25, .05]),
        "kind": rng.choice(["x", "y", None], N, p=[.5, .45, .05]),
        "amount": np.where(rng.random(N) < .03, np.nan, rng.uniform(1, 100, N).round(2)),
        "code": rng.integers(0, 40, N), "note": ["t" * 30] * N})
    path = tmp_path_factory.mktemp("big") / "big.parquet"
    df.to_parquet(path, index=False)
    want = {name: wd.get_widget_data(str(path), cfg, wt, use_cache=False) for name, wt, cfg in CHARTS}
    return str(path), want


@pytest.fixture
def too_large(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True, raising=False)
    monkeypatch.setattr(mg, "free_bytes", lambda: 100)
    monkeypatch.setattr(mg, "share", lambda: 1.0)
    monkeypatch.setattr(mg, "estimate", lambda p, columns=None: (10 ** 9, N))      # nothing fits, not even a column
    with frame_cache._LOCK:
        frame_cache._CACHE.clear()


def _close(a, b, path="result"):
    if isinstance(a, dict) and isinstance(b, dict):
        assert set(a) == set(b), f"{path}: keys {sorted(set(a) ^ set(b))}"
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        assert len(a) == len(b), f"{path}: {len(a)} against {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        if a is None or b is None or (a != a and b != b):
            assert (a is None or a != a) and (b is None or b != b), f"{path}: {a!r} against {b!r}"
        else:
            assert a == pytest.approx(b, rel=1e-9, abs=1e-9), f"{path}: {a!r} against {b!r}"
    else:
        assert a == b, f"{path}: {a!r} against {b!r}"


@pytest.mark.parametrize("name,wt,cfg", CHARTS)
def test_it_says_what_the_ordinary_path_says(data, too_large, name, wt, cfg, monkeypatch):
    path, want = data
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rows were loaded")))
    got = wd.get_widget_data(path, cfg, wt, use_cache=False)
    _close(got, want[name])


def test_the_partial_period_note_is_kept(data, too_large):
    path, want = data
    assert want["count by month"].get("partial_period")
    assert wd.get_widget_data(path, CHARTS[0][2], "line", use_cache=False)["partial_period"] \
        == want["count by month"]["partial_period"]


def test_what_cannot_be_regrouped_is_not_answered_this_way(data, too_large):
    path, _ = data
    for wt, cfg in [("bar", {"dimension": "grp", "dimension2": "kind", "measure": "amount", "aggregation": "avg"}),
                    ("kpi", {"measure": "amount", "aggregation": "median", "sparkline_date": "when"}),
                    ("table", {})]:
        with pytest.raises(mg.TooLargeToLoad):
            wd.get_widget_data(path, cfg, wt, use_cache=False)
