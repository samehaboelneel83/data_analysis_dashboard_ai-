"""How long the discovery engine and the analyses take as a table grows.

    python scripts/bench_discovery.py [--rows 100000,500000,2000000] [--json out.json]

One made-up table per size -- a start date with times of day, a finish date
that is empty on the newest rows, a due date, four categories (3 to 200
values), a two-valued flag, an outcome, five numbers (two of one unit that
move together), an identifier -- and each step timed once on it, in this
process, with nothing cached. The numbers are what a REQUEST would wait for
on this machine; they are for choosing thresholds (which analyses belong in
a background job from how many rows), not for comparing machines.

Nothing here touches the database or any dataset: the frame is built in
memory and thrown away.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def table(n: int, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    began = pd.Timestamp("2023-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 3 * 365 * 24 * 60, n)), unit="m")
    took = rng.gamma(2.0, 1.5, n)
    done = began + pd.to_timedelta(took, unit="D")
    still = np.arange(n) >= int(n * 0.97)
    size = rng.gamma(2.0, 40.0, n)
    kind = rng.choice(["a", "b", "c", "d", "e"], n, p=[.4, .25, .2, .1, .05])
    df = pd.DataFrame({
        "row_id": np.arange(n), "began": began, "due": (began + pd.Timedelta(days=4)).normalize(),
        "finished": done, "kind": kind,
        "place": rng.choice([f"p{i:03d}" for i in range(200)], n),
        "band": rng.choice(["low", "mid", "high"], n),
        "state": np.where(still, "going", np.where(took > 4, "late", "ended")),
        "flag": rng.choice(["yes", "no"], n, p=[.3, .7]),
        "size": size, "amount": size * 2.5 + rng.normal(0, 8, n) + np.where(kind == "e", 40.0, 0.0),
        "planned": size * 2.6 + rng.normal(0, 6, n),
        "wait": took, "score": rng.normal(50, 10, n),
    })
    df.loc[still, "finished"] = pd.NaT
    return df


META = {"amount": {"number": "amount", "unit": "u"}, "planned": {"number": "amount", "unit": "u"},
        "size": {"number": "amount"}, "wait": {"number": "duration"}, "score": {"number": "score"},
        "row_id": {"number": "code"}, "state": {"outcome": True}}


def steps(df: pd.DataFrame):
    from app.services import analytics, insights
    from app.services import widget_data as wd
    from app.services.analysis import registry
    from app.services.discovery import engine, evidence, profile as store

    types = analytics.detect_types(df) if hasattr(analytics, "detect_types") else None
    kept: dict = {}

    def run(name, params):
        return lambda: registry.run_analysis(name, df, params, column_meta=META)

    def draw(wt, cfg):
        return lambda: wd.get_widget_data_from_df(df, cfg, wt)

    def profile():
        kept["profile"] = store.compute(df, types)

    def cards():
        base = engine.tier0(kept["profile"], META)
        kept["cards"] = base["cards"]

    yield "profile (measured once per version of the data)", profile, "engine"
    yield "cards from the stored profile (no row read)", cards, "engine"
    yield "insight detectors", lambda: insights.generate_insights(df, types or {}, META), "engine"
    yield "look at the rows for the shape cards", lambda: evidence.look(list(kept["cards"]), df, META), "engine"
    yield "why did it change", run("explain_change", {"date_column": "began", "measure": "amount"}), "quick"
    yield "one number against another", run("explain_variance", {"measure": "amount", "reference": "planned"}), "quick"
    yield "two groups", run("compare_two_groups", {"group_col": "flag", "outcome": "amount"}), "quick"
    yield "stage board", run("stage_board", {"stage_col": "state", "start_date": "began", "done_date": "finished",
                                             "due_date": "due"}), "quick"
    yield "scenarios side by side", run("compare_scenarios", {
        "date_column": "began", "measure": "amount", "factors": ["size"],
        "scenarios": [{"name": "up", "adjustments": {"size": 0.1}}, {"name": "down", "adjustments": {"size": -0.1}}]}), "quick"
    yield "groups of similar rows", run("segment", {"columns": ["size", "amount", "wait", "score"]}), "slow"
    yield "what goes with an outcome", run("key_influencers", {"target": "state", "factors": ["kind", "band", "flag", "size"]}), "slow"
    yield "values that appear together", run("association_rules", {"columns": ["kind", "band", "flag", "state"]}), "slow"
    yield "rules that separate an outcome", run("decision_tree", {"target": "state", "predictors": ["kind", "band", "size", "wait"]}), "slow"
    yield "prediction comparison + importance", run("automated_prediction", {"target": "state", "predictors": ["kind", "band", "size", "wait"]}), "slow"
    yield "line by week, read (band, shift, notes)", draw("line", {
        "dimension": "began", "dimension_granularity": "week", "measure": "amount", "aggregation": "sum",
        "anomaly_band": True, "change_point": True}), "widget"
    yield "weekday x hour grid", draw("heatmap", {"dimension": "began", "dimension_granularity": "weekday",
                                                 "dimension2": "began", "dimension2_granularity": "hour_of_day",
                                                 "measure": "amount", "aggregation": "sum"}), "widget"
    yield "headline number with history", draw("kpi", {"measure": "amount", "aggregation": "sum",
                                                      "sparkline_date": "began"}), "widget"
    yield "bridge between two numbers", draw("waterfall", {"dimension": "place", "measure": "amount", "aggregation": "sum",
                                                          "bridge_from": "planned"}), "widget"
    yield "influencers tile", draw("model_influencers", {"response": "state", "predictors": ["kind", "band", "flag"]}), "widget"
    yield "cluster tile", draw("model_cluster", {"measures": ["size", "amount", "wait", "score"]}), "widget"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="100000,500000,2000000")
    ap.add_argument("--json")
    args = ap.parse_args()
    sizes = [int(x) for x in args.rows.split(",") if x.strip()]
    out: dict[str, dict] = {}
    for n in sizes:
        t0 = time.perf_counter()
        df = table(n)
        print(f"\n== {n:,} rows ({df.memory_usage(deep=True).sum() / 1e6:,.0f} MB, built in {time.perf_counter() - t0:.1f}s)", flush=True)
        for label, fn, group in steps(df):
            t = time.perf_counter()
            try:
                fn()
                took, note = time.perf_counter() - t, ""
            except Exception as exc:                        # noqa: BLE001 -- a refusal is a result too
                took, note = time.perf_counter() - t, f"  [{type(exc).__name__}: {str(exc)[:70]}]"
            out.setdefault(label, {"group": group})[str(n)] = round(took, 2)
            print(f"  {took:7.2f}s  {group:<6} {label}{note}", flush=True)
        del df
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    print("\n" + "| step | " + " | ".join(f"{n:,}" for n in sizes) + " |")
    print("|---|" + "---:|" * len(sizes))
    for label, row in out.items():
        print(f"| {label} | " + " | ".join(f"{row.get(str(n), '')}" for n in sizes) + " |")


if __name__ == "__main__":
    main()
