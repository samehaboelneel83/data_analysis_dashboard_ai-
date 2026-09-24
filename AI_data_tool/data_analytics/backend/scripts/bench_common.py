"""Shared pieces of the performance benchmark harness.

Seeds a deterministic synthetic dataset and defines the widget-config
battery every bench script and the equivalence gate run. Deterministic by
construction (seeded RNG, fixed column recipe) so two runs on the same
machine — or the same run with a lever toggled — see byte-identical input.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

SEED = 20260823


def seed_frame(rows: int) -> pd.DataFrame:
    """1M-scale synthetic frame: 3 date-string cols, 6 categoricals of varied
    cardinality, 8 numerics (~2% NaN), 2 free-text. ~20 columns."""
    rng = np.random.default_rng(SEED)
    n = rows

    def dates(start: str, span_days: int) -> np.ndarray:
        base = np.datetime64(start)
        offs = rng.integers(0, span_days, n)
        return (base + offs.astype("timedelta64[D]")).astype(str)

    def cat(card: int, prefix: str) -> np.ndarray:
        return np.char.add(prefix, rng.integers(0, card, n).astype(str))

    def num(scale: float, nan_frac: float = 0.02) -> np.ndarray:
        v = rng.normal(loc=scale, scale=scale / 3, size=n)
        mask = rng.random(n) < nan_frac
        v[mask] = np.nan
        return v

    df = pd.DataFrame({
        "order_date": dates("2024-01-01", 720),
        "ship_date": dates("2024-01-08", 720),
        "due_date": dates("2024-02-01", 720),
        "region": cat(5, "R"),
        "segment": cat(20, "S"),
        "city": cat(200, "C"),
        "sku": cat(2_000, "K"),
        "customer": cat(20_000, "U"),
        "order_ref": cat(200_000, "O"),
        "revenue": num(1000.0),
        "cost": num(600.0),
        "units": rng.integers(1, 50, n).astype(float),
        "discount": num(0.1, 0.02),
        "margin": num(400.0),
        "weight": num(12.0),
        "rating": rng.integers(1, 6, n).astype(float),
        "latency": num(3.0),
        "note": cat(50, "note-"),
        "channel": cat(3, "ch"),
    })
    return df


def seed_csv(path: str, rows: int) -> str:
    seed_frame(rows).to_csv(path, index=False)
    return path


def battery(aux_path: str | None = None) -> list[dict]:
    """The widget-config battery: one entry per pipeline feature the plan's
    levers may touch. Each is kwargs for get_widget_data (minus file_path)."""
    configs: list[dict] = [
        {"name": "bar_sum", "widget_type": "bar",
         "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}},
        {"name": "table_1000", "widget_type": "table",
         "config": {"columns": ["region", "segment", "revenue", "cost"], "limit": 1000}},
        {"name": "kpi", "widget_type": "kpi",
         "config": {"measure": "revenue", "aggregation": "avg"}},
        {"name": "line_month", "widget_type": "line",
         "config": {"dimension": "order_date", "measure": "revenue",
                    "aggregation": "sum", "dimension_granularity": "month"}},
        {"name": "calc_cols", "widget_type": "bar",
         "config": {"dimension": "segment", "measure": "profit", "aggregation": "sum"},
         "calculated_columns": [
             {"name": "profit", "expression": "revenue - cost"},
             {"name": "unit_price", "expression": "revenue / units"}]},
        {"name": "prep_steps", "widget_type": "bar",
         "config": {"dimension": "region", "measure": "revenue", "aggregation": "mean"},
         "prep_steps": [
             {"kind": "trim", "columns": ["region"]},
             {"kind": "fill_nulls", "column": "revenue", "method": "zero"},
             {"kind": "filter_rows", "expression": "units > 5"}]},
        {"name": "rls", "widget_type": "bar",
         "config": {"dimension": "segment", "measure": "revenue", "aggregation": "sum"},
         "rls_filter_expr": "region == 'R1'"},
        {"name": "crosstab", "widget_type": "crosstab",
         "config": {"dimension": "region", "dimension2": "channel",
                    "measure": "revenue", "aggregation": "sum"}},
        {"name": "heatmap", "widget_type": "heatmap",
         "config": {"roles": {"category": "region", "category2": "channel",
                              "measure": "units"}, "aggregation": "sum"}},
        {"name": "masked", "widget_type": "table",
         "config": {"columns": ["region", "revenue"], "limit": 100},
         "drop_columns": ["customer", "order_ref"]},
    ]
    if aux_path:
        configs.append(
            {"name": "joined", "widget_type": "bar",
             "config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
             "prep_steps": [{"kind": "join", "dataset_id": -1, "how": "left",
                             "left_on": "region", "right_on": "region"}],
             "aux_key": -1})
    return configs


def timeit(fn, repeat: int = 3, discard_first: bool = True) -> float:
    """min-of-N seconds after one discarded warm-up call."""
    if discard_first:
        fn()
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best
