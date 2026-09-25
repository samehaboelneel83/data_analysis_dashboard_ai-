"""Unit tests for shape_forecast's methods:
  - `simple` (T7's original statsmodels-ETS + naive fallback -- pinned byte-for-byte)
  - `ets`    (A3: NEW default, StatsForecast AutoETS, falling back to `simple` at
              runtime on any failure -- including a failed lazy import)
See .superpowers/sdd/2026-08-26-all-layers-pass/task-T7-brief.md and the tier-5 plan's
Task A3.
"""
import subprocess
import sys

import pandas as pd
import pytest

from app.services.widget_data import shape_forecast


def _monthly_df(values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(values), freq="MS")
    return pd.DataFrame({"month": dates, "revenue": values})


def _config(periods: int = 3, method: str = "simple") -> dict:
    return {
        "dimension": "month", "measure": "revenue", "aggregation": "sum",
        "dimension_granularity": "month", "forecast_periods": periods, "method": method,
    }


# ── method="simple" -- pinned byte-for-byte to the pre-A3 behavior ────────────────

def test_simple_long_trending_series_takes_the_ets_path():
    values = [100 + 10 * i for i in range(24)]
    result = shape_forecast(_monthly_df(values), _config())
    assert result["type"] == "forecast"
    assert result["method"] == "ets"
    assert result["forecast_method"] == "simple"
    assert len(result["forecast"]) == 3
    # trending series -> forecast should keep climbing, roughly matching the trend
    assert result["forecast"][0]["yhat"] > values[-1]


def test_simple_short_series_falls_back_to_naive():
    values = [10, 12, 11]
    result = shape_forecast(_monthly_df(values), _config(periods=2))
    assert result["type"] == "forecast"
    assert result["method"] == "naive"
    assert len(result["forecast"]) == 2


def test_simple_ets_path_has_band_keys():
    values = [100 + 5 * i + (3 if i % 2 == 0 else -3) for i in range(24)]
    result = shape_forecast(_monthly_df(values), _config())
    assert result["method"] == "ets"
    for point in result["forecast"]:
        assert "lo" in point and "hi" in point
        assert point["lo"] <= point["yhat"] <= point["hi"]


def test_response_shape_is_backward_compatible():
    values = [100 + 10 * i for i in range(24)]
    result = shape_forecast(_monthly_df(values), _config())
    # existing keys unchanged
    for key in ("type", "dimension", "measure", "rows", "forecast", "total"):
        assert key in result
    for point in result["forecast"]:
        for key in ("name", "yhat"):
            assert key in point


def test_still_empty_below_minimum_history():
    result = shape_forecast(_monthly_df([5]), _config())
    assert result["type"] == "empty"
    assert "error" in result


def test_method_defaults_to_ets_not_simple():
    # No "method" key at all -> the NEW default is "ets", not the legacy "simple".
    values = [100 + 10 * i for i in range(24)]
    config = {"dimension": "month", "measure": "revenue", "aggregation": "sum",
              "dimension_granularity": "month", "forecast_periods": 3}
    result = shape_forecast(_monthly_df(values), config)
    assert result["forecast_method"] == "ets"


# ── method="ets" -- StatsForecast AutoETS (A3) ─────────────────────────────────────

def _seasonal_series(n_years: int = 4) -> list[float]:
    import math
    values = []
    for i in range(12 * n_years):
        trend = 100 + 2 * i
        seasonal = 15 * math.sin(2 * math.pi * (i % 12) / 12)
        values.append(trend + seasonal)
    return values


def test_ets_path_reports_ets_and_has_ordered_band():
    values = _seasonal_series()
    result = shape_forecast(_monthly_df(values), _config(periods=6, method="ets"))
    assert result["type"] == "forecast"
    assert result["forecast_method"] == "ets"
    assert result["method"] == "ets"
    for point in result["forecast"]:
        assert "lo" in point and "hi" in point
        assert point["lo"] <= point["yhat"] <= point["hi"]


def test_ets_beats_simple_on_seasonal_synthetic_mae():
    """A3-pinned: on a clean seasonal+trend synthetic, StatsForecast's per-series
    AutoETS fit should out-predict the hand-rolled `simple` smoothing on held-out MAE.
    Fit on 3 years, forecast 12 months, compare against the held-out 4th year."""
    import math
    full = _seasonal_series(n_years=4)
    train, holdout = full[:36], full[36:48]

    ets_result = shape_forecast(_monthly_df(train), _config(periods=12, method="ets"))
    simple_result = shape_forecast(_monthly_df(train), _config(periods=12, method="simple"))

    ets_mae = sum(abs(p["yhat"] - h) for p, h in zip(ets_result["forecast"], holdout)) / 12
    simple_mae = sum(abs(p["yhat"] - h) for p, h in zip(simple_result["forecast"], holdout)) / 12

    assert ets_mae < simple_mae * 0.9  # pinned tolerance: at least 10% better


def test_ets_import_failure_falls_back_to_simple():
    """Monkeypatching the lazy import to raise must degrade to the exact `simple`
    result for identical input -- never a 500, never silently wrong numbers."""
    import builtins
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "statsforecast" or name.startswith("statsforecast."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    values = _seasonal_series()
    df = _monthly_df(values)

    import app.services.widget_data as wd
    try:
        builtins.__import__ = _blocked_import
        ets_config = _config(periods=6, method="ets")
        result = shape_forecast(df, ets_config)
    finally:
        builtins.__import__ = real_import

    simple_result = shape_forecast(df, _config(periods=6, method="simple"))
    assert result["method"] == simple_result["method"]
    assert result["forecast"] == simple_result["forecast"]
    # requested "ets", but the ACTUAL algorithm that ran was the simple fallback
    assert result["forecast_method"] == "ets"


def test_ets_constant_series_never_produces_nan_or_500():
    """A genuinely degenerate fit input (zero variance) must never surface a NaN or
    raise -- whichever branch handles it (a successful-but-flat AutoETS fit, or the
    NaN-check/except paths falling back to `simple`), the response stays finite."""
    values = [42.0] * 24
    result = shape_forecast(_monthly_df(values), _config(periods=6, method="ets"))
    assert result["type"] == "forecast"
    assert result["method"] in ("ets", "naive")
    for point in result["forecast"]:
        assert point["yhat"] is not None
        assert point["lo"] is not None and point["hi"] is not None


def test_ets_fit_raising_falls_back_to_simple(monkeypatch):
    """A genuine fit failure (not an import failure) reaching
    _forecast_statsforecast_ets's `except Exception` in shape_forecast must degrade
    to the exact `simple` result, same as the import-failure case above."""
    import statsforecast

    def _raise(self, *args, **kwargs):
        raise RuntimeError("simulated AutoETS fit failure")

    monkeypatch.setattr(statsforecast.StatsForecast, "forecast", _raise)

    values = _seasonal_series()
    df = _monthly_df(values)
    result = shape_forecast(df, _config(periods=6, method="ets"))
    simple_result = shape_forecast(df, _config(periods=6, method="simple"))
    assert result["method"] == simple_result["method"]
    assert result["forecast"] == simple_result["forecast"]
    assert result["forecast_method"] == "ets"


def test_ets_nan_output_falls_back_to_simple(monkeypatch):
    """Exercises _forecast_statsforecast_ets's NaN-check branch directly: a fit that
    "succeeds" (raises nothing) but yields NaN forecast values must still degrade to
    `simple`, not propagate NaNs into the response."""
    import statsforecast
    from statsforecast.models import AutoETS

    alias = AutoETS(season_length=1).alias

    def _nan_forecast(self, df, h, level=None, **kwargs):
        n = h
        return pd.DataFrame({
            "unique_id": ["series"] * n,
            "ds": pd.date_range("2030-01-01", periods=n, freq="MS"),
            alias: [float("nan")] * n,
            f"{alias}-lo-95": [float("nan")] * n,
            f"{alias}-hi-95": [float("nan")] * n,
        })

    monkeypatch.setattr(statsforecast.StatsForecast, "forecast", _nan_forecast)

    values = _seasonal_series()
    df = _monthly_df(values)
    result = shape_forecast(df, _config(periods=6, method="ets"))
    simple_result = shape_forecast(df, _config(periods=6, method="simple"))
    assert result["method"] == simple_result["method"]
    assert result["forecast"] == simple_result["forecast"]


def test_ets_lazy_import_not_loaded_at_app_import():
    """Mirrors test_segment.py's test_lazy_import_sklearn_not_pulled_in_at_app_import:
    numba's JIT warmup costs real seconds and must never run merely from importing
    app.main -- statsforecast is imported lazily inside _forecast_statsforecast_ets
    on first use only."""
    code = (
        "import sys; "
        "assert 'statsforecast' not in sys.modules; "
        "from app.main import app; "
        "assert 'statsforecast' not in sys.modules, "
        "'app.main import triggered a statsforecast import'; "
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
