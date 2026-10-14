"""A chart on a dataset too large to load whole is drawn from only the
columns it names (services/widget_data._load_file_named_columns): the same answer
as on a small dataset, for the shapes the DuckDB path does not take."""
import numpy as np
import pandas as pd
import pytest

from app.services import frame_cache, widget_data as wd
from app.services import memory_guard as mg

N = 4000


@pytest.fixture
def big(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    df = pd.DataFrame({
        "when": pd.date_range("2023-01-01", periods=N, freq="6h"),
        "grp": rng.choice(["a", "b", "c"], N), "kind": rng.choice(["x", "y"], N),
        "amount": rng.uniform(1, 100, N).round(2), "note": ["t" * 40] * N,
        **{f"extra{i}": rng.normal(size=N) for i in range(6)}})
    path = tmp_path / "big.parquet"
    df.to_parquet(path, index=False)
    want = {}
    for name, wt, cfg in CHARTS:
        want[name] = wd.get_widget_data(str(path), cfg, wt, use_cache=False)
    # From here on the whole file "does not fit"; a few columns of it do.
    real = mg.estimate
    monkeypatch.setattr(mg, "free_bytes", lambda: 100)
    monkeypatch.setattr(mg, "share", lambda: 1.0)
    monkeypatch.setattr(mg, "estimate", lambda p, columns=None: (10 if columns is not None else 10 ** 9, N))
    frame_cache.invalidate(str(path)) if hasattr(frame_cache, "invalidate") else None
    with frame_cache._LOCK:
        frame_cache._CACHE.clear()
    return path, df, want, real


CHARTS = [
    ("number with its history", "kpi", {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"}),
    ("count by month", "line", {"dimension": "when", "dimension_granularity": "month"}),
    ("second split", "bar", {"dimension": "grp", "dimension2": "kind", "measure": "amount", "aggregation": "sum"}),
    ("spread", "bar", {"dimension": "grp", "measure": "amount", "aggregation": "std"}),
    ("filtered", "bar", {"dimension": "grp", "measure": "amount", "aggregation": "std",
                         "filters": [{"column": "kind", "op": "eq", "value": "x"}]}),
]


@pytest.mark.parametrize("name,wt,cfg", CHARTS)
def test_the_chart_is_the_same_as_on_a_dataset_that_fits(big, name, wt, cfg, monkeypatch):
    path, df, want, _ = big
    read = []
    real = pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda p, columns=None, **k: (read.append(columns), real(p, columns=columns, **k))[1])
    got = wd.get_widget_data(str(path), cfg, wt, use_cache=False)
    assert got == want[name]
    # Only the named columns were read -- never the whole file.
    assert read and all(c is not None and "note" not in c and len(c) <= 3 for c in read), read


def test_whole_rows_and_preparation_steps_are_still_refused_in_words(big):
    path, *_ = big
    with pytest.raises(mg.TooLargeToLoad):
        wd.get_widget_data(str(path), {}, "table", use_cache=False)
    with pytest.raises(mg.TooLargeToLoad):
        wd.get_widget_data(str(path), {"dimension": "grp", "measure": "amount", "aggregation": "std"}, "bar",
                           use_cache=False, prep_steps=[{"op": "rename", "from": "grp", "to": "g"}])


def test_when_the_named_columns_do_not_fit_either_it_is_refused(big, monkeypatch):
    path, *_ = big
    monkeypatch.setattr(mg, "estimate", lambda p, columns=None: (10 ** 9, N))
    with pytest.raises(mg.TooLargeToLoad):
        wd.get_widget_data(str(path), {"dimension": "grp", "measure": "amount", "aggregation": "std"}, "bar",
                           use_cache=False)


def test_a_column_named_only_in_a_rule_or_a_calculation_is_read_too():
    names = ["when", "grp", "amount", "region code", 'odd"name', "unused"]
    got = wd.named_columns(names, {"dimension": "grp"}, "[region code] = 'N'", None,
                           [{"name": "x", "formula": 'amount * 2 + [odd"name]'}], None)
    assert got == ["grp", "amount", "region code", 'odd"name']


def test_a_sample_is_the_same_every_time_and_says_how_many_rows_there_are(big):
    path, df, *_ = big
    a, total = frame_cache.load_sample(str(path), 500)
    b, _ = frame_cache.load_sample(str(path), 500)
    assert total == N and len(a) == 500 and a.equals(b) and list(a.columns) == list(df.columns)
    whole, total = frame_cache.load_sample(str(path), 10 ** 6)
    assert len(whole) == N


def test_an_analysis_or_a_spread_chart_runs_on_a_sample_and_says_so_but_a_total_never_does(big, monkeypatch):
    from app.core.config import settings
    path, df, *_ = big
    monkeypatch.setattr(mg, "estimate", lambda p, columns=None: (10 ** 9, N))      # nothing fits
    monkeypatch.setattr(settings, "analysis_row_cap", 1000, raising=False)
    got = wd.get_widget_data(str(path), {"measure": "amount", "dimension": "amount"}, "histogram", use_cache=False)
    assert got["sampled"] is True and got["sample_size"] == 1000 and got["total_rows"] == N
    with pytest.raises(mg.TooLargeToLoad):
        wd.get_widget_data(str(path), {"dimension": "grp", "measure": "amount", "aggregation": "std"}, "bar",
                           use_cache=False)
    whole = frame_cache.load_or_sample(str(path))
    assert len(whole) == 1000 and whole.attrs["sampled_of"] == N
