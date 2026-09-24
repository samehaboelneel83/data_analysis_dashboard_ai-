"""What if spend rose 10%? — a projection with factors you can move.

`shape_forecast` is AutoETS: univariate, no exogenous inputs. It answers "where
is this heading" and cannot answer "where would it head if we changed
something", which is what a plan is actually made of. This is that second
question, and it is the last analysis in the SAS comparison this catalogue did
not have.

**OLS on period totals — `measure ~ time + factors` — rather than SARIMAX with
exogenous regressors**, though SARIMAX is available and would be the textbook
choice. SARIMAX needs FUTURE values for every factor, which is a second
forecasting problem hidden inside the first: the answer would quietly depend on
a forecast of spend that nobody asked for and nobody sees. Asking for the
adjustment directly is the honest shape, because the adjustment is the thing
the user actually knows and the model is the thing they do not.

Three properties decide whether this produces a plan or a plausible-looking
number:

  * **Association, not intervention.** Moving a factor inside a fitted model is
    not the same as changing it in the world -- the model has only ever seen the
    two move together, and a factor that rises when revenue rises may be an
    effect, a cause, or neither. Said every time, not as a footnote.

  * **Each factor's evidence travels with it.** A coefficient at p = 0.6 must
    not lend a scenario the same weight as one at p = 0.001, and nobody can tell
    them apart unless both are on screen.

  * **Extrapolation is named.** "What if spend doubled" is unanswerable from
    data where it never moved more than 20%, and answering anyway with a
    confident number is the failure this catalogue is built against. The same
    rule `goal_seek` already applies to its own answers.
"""
from __future__ import annotations

import pandas as pd

#: Enough periods that a fit over a trend plus factors is not drawing a line
#: through its own degrees of freedom.
MIN_PERIODS = 8
#: Extra periods needed per factor, for the same reason.
PERIODS_PER_FACTOR = 3
DEFAULT_HORIZON = 6
MAX_HORIZON = 36
MAX_FACTORS = 8
#: Factors are held at the mean of this many recent periods -- long enough not
#: to hang the whole projection on one unusual month, short enough to mean
#: "where we are now" rather than "where we have been".
RECENT_PERIODS = 3


class ForecastScenarioError(ValueError):
    """Not something a factor model can be fitted to, with the reason."""


def forecast_scenario(df: pd.DataFrame, date_column: str, measure: str,
                      factors: list[str], adjustments: dict | None = None,
                      periods: int = DEFAULT_HORIZON,
                      granularity: str = "month") -> dict:
    """Project a measure forward with its factors held or moved."""
    import numpy as np
    import statsmodels.api as sm

    for column in (date_column, measure):
        if column not in df.columns:
            raise ForecastScenarioError(f"Column '{column}' not found")
    factors = [f for f in (factors or [])]
    if not factors:
        raise ForecastScenarioError(
            "A scenario needs at least one factor to move. Without one this is "
            "an ordinary forecast -- use `forecast_ets`.")
    if len(factors) > MAX_FACTORS:
        raise ForecastScenarioError(
            f"At most {MAX_FACTORS} factors; more than that and the fit "
            f"describes the noise as readily as the signal.")
    for f in factors:
        if f not in df.columns:
            raise ForecastScenarioError(f"Factor '{f}' not found")
        if not pd.api.types.is_numeric_dtype(df[f]):
            raise ForecastScenarioError(
                f"Factor '{f}' is not numeric. A scenario moves a quantity by a "
                f"percentage; a category has no percentage to move.")

    dates = pd.to_datetime(df[date_column], errors="coerce")
    freq = {"day": "D", "week": "W", "month": "MS",
            "quarter": "QS", "year": "YS"}.get(granularity, "MS")
    frame = (df.assign(__p__=dates.dt.to_period(
                 {"day": "D", "week": "W", "month": "M",
                  "quarter": "Q", "year": "Y"}.get(granularity, "M")))
               .dropna(subset=["__p__"]))
    grouped = frame.groupby("__p__")[[measure, *factors]].sum().sort_index()
    grouped = grouped.dropna()

    needed = MIN_PERIODS + PERIODS_PER_FACTOR * len(factors)
    if len(grouped) < needed:
        raise ForecastScenarioError(
            f"Only {len(grouped)} periods of history; {needed} are needed to fit "
            f"a trend plus {len(factors)} factor(s) without simply tracing the "
            f"data back.")

    horizon = max(1, min(int(periods or DEFAULT_HORIZON), MAX_HORIZON))
    y = grouped[measure].astype(float)
    # A time index alongside the factors: without it a factor that merely grows
    # over time inherits the whole trend and looks far more powerful than it is.
    design = grouped[factors].astype(float).copy()
    design.insert(0, "__t__", np.arange(len(grouped), dtype=float))
    fitted = sm.OLS(y.to_numpy(), sm.add_constant(design.to_numpy())).fit()

    names = ["const", "__t__", *factors]
    per_factor = []
    for i, name in enumerate(names):
        if name in ("const", "__t__"):
            continue
        series = grouped[name].astype(float)
        per_factor.append({
            "column": name,
            "coefficient": round(float(fitted.params[i]), 6),
            "p_value": round(float(fitted.pvalues[i]), 6),
            "observed_min": round(float(series.min()), 4),
            "observed_max": round(float(series.max()), 4),
            "recent_level": round(float(series.tail(RECENT_PERIODS).mean()), 4),
        })

    recent = {f["column"]: f["recent_level"] for f in per_factor}
    moves = {k: float(v) for k, v in (adjustments or {}).items() if k in recent}

    def project(level: dict[str, float]) -> list[dict]:
        out = []
        last_period = grouped.index[-1]
        for step in range(1, horizon + 1):
            t = float(len(grouped) - 1 + step)
            row = [1.0, t] + [level[f] for f in factors]
            value = float(np.dot(fitted.params, row))
            out.append({"name": str(last_period + step), "value": round(value, 4)})
        return out

    baseline_level = dict(recent)
    scenario_level = {f: recent[f] * (1.0 + moves.get(f, 0.0)) for f in factors}
    baseline = project(baseline_level)
    scenario = project(scenario_level)

    # An adjusted factor outside anything ever observed is a question this data
    # cannot answer; the fit will still produce a number, which is the problem.
    extrapolating = False
    stretched = []
    for f in per_factor:
        target = scenario_level[f["column"]]
        if target < f["observed_min"] or target > f["observed_max"]:
            extrapolating = True
            stretched.append(f["column"])

    baseline_total = round(sum(p["value"] for p in baseline), 4)
    scenario_total = round(sum(p["value"] for p in scenario), 4)

    caveats = [
        "This is association, not intervention. The model has only seen these "
        "columns move together -- moving one inside the model is not the same "
        "as changing it in the world, and a factor that rises with the measure "
        "may be an effect of it rather than a cause.",
        f"Factors you did not adjust are held at their average over the last "
        f"{RECENT_PERIODS} periods.",
        f"Fitted over {len(grouped)} periods; the fit explains "
        f"{round(float(fitted.rsquared), 4)} of the variation.",
    ]
    weak = [f["column"] for f in per_factor if f["p_value"] > 0.05]
    if weak:
        caveats.append(
            f"There is no strong evidence that {', '.join(weak)} moves this "
            f"measure at all (p > 0.05) -- a scenario built on it is a guess "
            f"wearing a number.")
    if stretched:
        ranges = "; ".join(
            f"{f['column']} has only ever been between {f['observed_min']:,} and "
            f"{f['observed_max']:,}" for f in per_factor if f["column"] in stretched)
        caveats.append(
            f"That scenario goes outside anything observed -- {ranges}. The "
            f"projection is an extrapolation, not evidence.")

    return {
        "kind": "forecast_scenario",
        "measure": measure,
        "factors": per_factor,
        "adjustments": {k: round(v, 6) for k, v in moves.items()},
        "history": [{"name": str(p), "value": round(float(v), 4)}
                    for p, v in y.items()],
        "baseline": baseline,
        "scenario": scenario,
        "baseline_total": baseline_total,
        "scenario_total": scenario_total,
        "difference": round(scenario_total - baseline_total, 4),
        "r2": round(float(fitted.rsquared), 4),
        "periods_fitted": int(len(grouped)),
        "horizon": horizon,
        "extrapolating": extrapolating,
        "caveats": caveats,
    }
