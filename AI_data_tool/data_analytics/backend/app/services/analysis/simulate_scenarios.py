"""How sure is a what-if? Each named scenario as a RANGE of outcomes, and the
chance it ends below doing nothing (docs/discovery/PLAN.md §D-15, phase 5).

`compare_scenarios` sets what-ifs side by side as single lines. A single line
hides that the model behind it is uncertain twice over: it does not know its
own coefficients exactly, and each period lands off the line by some amount.
This runs the same model many times with both drawn at random:

  * the coefficients from their estimated distribution (their covariance),
  * each projected period's own noise from the size of the fit's misses,

and reports, for the total over the horizon of each scenario: the middle, the
range most outcomes fall in, the chance of ending below the "nothing moved"
projection, and -- when a floor is given -- the chance of ending below it.

The same random draws are used for every scenario and for the baseline, so
two scenarios differ by what was moved, never by luck of the draw; the seed
is fixed, so the same data and scenarios give the same answer every time.

It carries every warning of the what-if it rests on: this is association,
not intervention, and a range around a guess is still a guess.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..readback import _s, as_i18n
from .compare_scenarios import MAX_SCENARIOS, WEAK_FIT, CompareScenariosError
from .forecast_scenario import (DEFAULT_HORIZON, MAX_HORIZON, RECENT_PERIODS, ForecastScenarioError,
                                forecast_scenario)

DEFAULT_RUNS = 2000
MAX_RUNS = 20000
SEED = 1618
#: Bars of the outcome histogram.
BINS = 24
_PERIOD = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}


class SimulateScenariosError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def _fit(df: pd.DataFrame, date_column: str, measure: str, factors: list[str], granularity: str):
    """The what-if's own model, refitted: a constant, a time index and the
    factors, on one row per period (forecast_scenario fits exactly this)."""
    import statsmodels.api as sm
    dates = pd.to_datetime(df[date_column], errors="coerce")
    frame = df.assign(__p__=dates.dt.to_period(_PERIOD.get(granularity, "M"))).dropna(subset=["__p__"])
    grouped = frame.groupby("__p__")[[measure, *factors]].sum().sort_index().dropna()
    design = grouped[factors].astype(float).copy()
    design.insert(0, "__t__", np.arange(len(grouped), dtype=float))
    fitted = sm.OLS(grouped[measure].astype(float).to_numpy(), sm.add_constant(design.to_numpy())).fit()
    recent = {f: float(grouped[f].astype(float).tail(RECENT_PERIODS).mean()) for f in factors}
    return grouped, fitted, recent


def simulate_scenarios(df: pd.DataFrame, date_column: str, measure: str, factors: list[str],
                       scenarios: list[dict] | None = None, periods: int = DEFAULT_HORIZON,
                       granularity: str = "month", runs: int = DEFAULT_RUNS, floor: float | None = None,
                       change_pct: float | None = None, seed: int = SEED) -> dict:
    """`scenarios` is 1 to 4 of {"name": ..., "adjustments": {factor: fraction}}.
    Without it, `change_pct` (default 10) makes two: every factor up by that
    much, and every factor down by it -- what a form with one number can ask."""
    if not scenarios:
        pct = abs(float(change_pct if change_pct not in (None, "") else 10.0))
        if not pct:
            raise SimulateScenariosError("give a change other than 0%, or name the scenarios")
        scenarios = [{"name": f"+{pct:g}%", "adjustments": {f: pct / 100.0 for f in factors or []}},
                     {"name": f"-{pct:g}%", "adjustments": {f: -pct / 100.0 for f in factors or []}}]
    if floor in ("",):
        floor = None
    if not isinstance(scenarios, list) or not (1 <= len(scenarios) <= MAX_SCENARIOS):
        raise SimulateScenariosError(f"give 1 to {MAX_SCENARIOS} scenarios to simulate")
    runs = max(200, min(int(runs or DEFAULT_RUNS), MAX_RUNS))
    horizon = max(1, min(int(periods or DEFAULT_HORIZON), MAX_HORIZON))
    seen: set[str] = set()
    cleaned: list[tuple[str, dict, dict]] = []
    for i, sc in enumerate(scenarios, start=1):
        if not isinstance(sc, dict):
            raise SimulateScenariosError("each scenario is a name and its adjustments")
        name = str(sc.get("name") or f"Scenario {i}").strip()
        moves = {k: float(v) for k, v in (sc.get("adjustments") or {}).items() if v}
        if name.casefold() in seen:
            raise SimulateScenariosError(f"two scenarios are both called '{name}'")
        if not moves:
            raise SimulateScenariosError(f"'{name}' moves nothing: that is the baseline, which is always shown")
        seen.add(name.casefold())
        try:
            # The single what-if validates the columns and history, and writes the warnings.
            single = forecast_scenario(df, date_column, measure, factors, moves, horizon, granularity)
        except (ForecastScenarioError, CompareScenariosError) as e:
            raise SimulateScenariosError(str(e)) from e
        cleaned.append((name, moves, single))

    grouped, fitted, recent = _fit(df, date_column, measure, list(factors), granularity)
    rng = np.random.default_rng(seed)
    k = len(fitted.params)
    cov = np.asarray(fitted.cov_params(), dtype=float)
    # Coefficients as the fit is unsure of them; a covariance that is not
    # usable (a perfect fit, a degenerate design) leaves them at their estimate.
    try:
        betas = rng.multivariate_normal(np.asarray(fitted.params, dtype=float), cov, size=runs, method="svd")
    except Exception:                                               # noqa: BLE001
        betas = np.tile(np.asarray(fitted.params, dtype=float), (runs, 1))
    sigma = float(np.sqrt(max(float(fitted.scale), 0.0)))
    noise = rng.normal(0.0, sigma, size=(runs, horizon)) if sigma > 0 else np.zeros((runs, horizon))
    steps = np.arange(1, horizon + 1, dtype=float) + (len(grouped) - 1)

    def totals(level: dict[str, float]) -> np.ndarray:
        rows = np.column_stack([np.ones(horizon), steps, *[np.full(horizon, level[f]) for f in factors]])
        assert rows.shape[1] == k
        return (betas @ rows.T + noise).sum(axis=1)

    base = totals(recent)
    out_rows, all_totals = [], [base]
    for name, moves, single in cleaned:
        level = {f: recent[f] * (1.0 + moves.get(f, 0.0)) for f in factors}
        t = totals(level)
        all_totals.append(t)
        row = {"scenario": name, "adjustments": moves, "extrapolating": bool(single.get("extrapolating")),
               "expected": round(float(single["scenario_total"]), 4),
               "p05": round(float(np.percentile(t, 5)), 4), "p25": round(float(np.percentile(t, 25)), 4),
               "median": round(float(np.percentile(t, 50)), 4),
               "p75": round(float(np.percentile(t, 75)), 4), "p95": round(float(np.percentile(t, 95)), 4),
               # Same draws for both: the difference is what was moved.
               "chance_below_baseline": round(float((t < base).mean()), 4),
               "median_gain": round(float(np.percentile(t - base, 50)), 4),
               "gain_p05": round(float(np.percentile(t - base, 5)), 4),
               "gain_p95": round(float(np.percentile(t - base, 95)), 4)}
        if floor is not None:
            row["chance_below_floor"] = round(float((t < float(floor)).mean()), 4)
        out_rows.append(row)
    baseline = {"scenario": "Nothing moved", "expected": round(float(cleaned[0][2]["baseline_total"]), 4),
                "p05": round(float(np.percentile(base, 5)), 4), "p25": round(float(np.percentile(base, 25)), 4),
                "median": round(float(np.percentile(base, 50)), 4),
                "p75": round(float(np.percentile(base, 75)), 4), "p95": round(float(np.percentile(base, 95)), 4)}
    if floor is not None:
        baseline["chance_below_floor"] = round(float((base < float(floor)).mean()), 4)

    # One set of bins for every scenario, so the shapes can be laid over each other.
    lo = float(min(a.min() for a in all_totals))
    hi = float(max(a.max() for a in all_totals))
    edges = np.linspace(lo, hi, BINS + 1) if hi > lo else np.array([lo, lo + 1.0])
    names = ["Nothing moved", *[n for n, _m, _s in cleaned]]
    histogram = []
    for i in range(len(edges) - 1):
        cell = {"from": round(float(edges[i]), 4), "to": round(float(edges[i + 1]), 4)}
        for name, arr in zip(names, all_totals):
            last = i == len(edges) - 2
            inside = (arr >= edges[i]) & ((arr <= edges[i + 1]) if last else (arr < edges[i + 1]))
            cell[name] = round(100.0 * float(inside.mean()), 2)
        histogram.append(cell)

    r2 = float(cleaned[0][2].get("r2", fitted.rsquared))
    caveats: list = []
    if r2 < WEAK_FIT:
        caveats.append(_s("sim.weakfit", "The model behind these ranges explains only {r2} of how {m} has moved: "
                                         "the ranges are wide because it knows little, and may still be too narrow.",
                          r2=f"{r2:.0%}", m=measure))
    caveats.append(_s("sim.what", "Each range comes from {n} runs of the same model with its coefficients and each "
                                  "period's noise drawn at random; it shows what the model is unsure of, not what "
                                  "it has never seen.", n=f"{runs:,}"))
    caveats.append(_s("sim.same", "The same draws are used for every scenario: they differ by what was moved, "
                                  "not by chance."))
    seen_text: set[str] = set()
    shared, shared_i18n = [], []
    for name, _moves, single in cleaned:
        for c, key in zip(single.get("caveats") or [], single.get("caveats_i18n") or [None] * 99):
            if key and key.get("key") == "fs.outside":
                c = _s("an.outside.named", "{name}: goes outside anything observed -- {ranges}. The "
                                           "projection is an extrapolation, not evidence.", cap=False,
                       name=name, ranges=key["vars"]["ranges"])
                key = as_i18n(c)
            if str(c) in seen_text:
                continue
            seen_text.add(str(c))
            shared.append(str(c))
            shared_i18n.append(key)
    best = max(out_rows, key=lambda r: r["median"])
    return {
        "kind": "simulate_scenarios", "measure": measure, "factors": list(factors), "horizon": horizon,
        "granularity": granularity, "runs": runs, "seed": seed, "r2": round(r2, 4), "weak_fit": r2 < WEAK_FIT,
        "periods_fitted": int(len(grouped)), "floor": float(floor) if floor is not None else None,
        "baseline": baseline, "table": out_rows, "series": names, "histogram": histogram,
        "highest": best["scenario"],
        "caveats": [str(c) for c in caveats] + shared,
        "caveats_i18n": [as_i18n(c) for c in caveats] + shared_i18n,
    }
