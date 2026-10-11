"""Two what-ifs side by side (docs/discovery/PLAN.md §N, scenarios).

`forecast_scenario` answers one "what if". A decision is usually between two:
this plan or that one. This runs the SAME fitted model once per named
scenario and sets them beside the projection with nothing moved -- period by
period, in total, and against each other.

Nothing new is fitted and nothing is optimised: each scenario is exactly what
`forecast_scenario` returns for its adjustments, with every caveat it carries
(association not intervention; a factor with no evidence; an extrapolation),
kept per scenario so one stretched what-if does not hide behind a sound one.
"""
from __future__ import annotations

import pandas as pd

from ..readback import _s, as_i18n
from .forecast_scenario import DEFAULT_HORIZON, ForecastScenarioError, forecast_scenario

MIN_SCENARIOS, MAX_SCENARIOS = 2, 4
#: Below this share of the variation explained, the scenarios differ by what
#: the model does not know: said first, before any total.
WEAK_FIT = 0.3


class CompareScenariosError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def compare_scenarios(df: pd.DataFrame, date_column: str, measure: str, factors: list[str],
                      scenarios: list[dict], periods: int = DEFAULT_HORIZON,
                      granularity: str = "month") -> dict:
    """`scenarios` is 2 to 4 of {"name": ..., "adjustments": {factor: fraction}}
    ({"spend": 0.1} is +10%). Names must differ; a scenario that moves nothing
    is the baseline and is refused, since the baseline is always shown."""
    if not isinstance(scenarios, list) or not (MIN_SCENARIOS <= len(scenarios) <= MAX_SCENARIOS):
        raise CompareScenariosError(f"give {MIN_SCENARIOS} to {MAX_SCENARIOS} scenarios to set side by side")
    seen: set[str] = set()
    cleaned = []
    for i, sc in enumerate(scenarios, start=1):
        if not isinstance(sc, dict):
            raise CompareScenariosError("each scenario is a name and its adjustments")
        name = str(sc.get("name") or f"Scenario {i}").strip()
        moves = {k: v for k, v in (sc.get("adjustments") or {}).items() if v}
        if name.casefold() in seen:
            raise CompareScenariosError(f"two scenarios are both called '{name}'")
        if not moves:
            raise CompareScenariosError(f"'{name}' moves nothing: that is the baseline, which is always shown")
        seen.add(name.casefold())
        cleaned.append((name, moves))

    runs = []
    for name, moves in cleaned:
        try:
            runs.append((name, moves, forecast_scenario(df, date_column, measure, factors, moves, periods, granularity)))
        except ForecastScenarioError as e:
            raise CompareScenariosError(str(e)) from e
    first = runs[0][2]
    base_total = first["baseline_total"]

    def pct(d):
        return round(d / abs(base_total) * 100, 2) if base_total else None

    table = [{"scenario": "Nothing moved", "baseline": True, "adjustments": {}, "total": base_total,
              "vs_baseline": 0.0, "vs_baseline_pct": 0.0 if base_total else None, "extrapolating": False}]
    for name, moves, r in runs:
        d = round(r["scenario_total"] - base_total, 4)
        table.append({"scenario": name, "baseline": False, "adjustments": r["adjustments"], "total": r["scenario_total"],
                      "vs_baseline": d, "vs_baseline_pct": pct(d), "extrapolating": bool(r["extrapolating"])})
    # Period by period: the baseline and every scenario on one axis.
    chart = []
    for i, point in enumerate(first["baseline"]):
        row = {"name": point["name"], "Nothing moved": point["value"]}
        for name, _moves, r in runs:
            row[name] = r["scenario"][i]["value"]
        chart.append(row)
    ranked = sorted(table[1:], key=lambda r: -r["total"])
    gap = round(ranked[0]["total"] - ranked[-1]["total"], 4)
    # Caveats said once, in the order met; the ones about one scenario carry its name.
    shared, own = [], []
    for name, _moves, r in runs:
        for c in r["caveats"]:
            if c.startswith("That scenario goes outside"):
                own.append(f"{name}: " + c[len("That scenario goes outside"):].replace(" anything observed", "goes outside anything observed", 1).lstrip())
            elif c not in shared:
                shared.append(c)
    weak = first["r2"] < WEAK_FIT
    if weak:
        shared.insert(0, _s("an.weakfit", "The model behind these scenarios explains only {r2} of how {m} has moved: "
                                          "the difference between them is mostly what it does not know.",
                            r2=f"{first['r2']:.0%}", m=measure))
    return {
        "kind": "compare_scenarios", "weak_fit": weak, "measure": measure, "factors": first["factors"],
        "history": first["history"], "horizon": first["horizon"], "r2": first["r2"],
        "periods_fitted": first["periods_fitted"],
        "table": table, "chart": chart, "series": ["Nothing moved", *[n for n, _m, _r in runs]],
        "highest": ranked[0]["scenario"], "lowest": ranked[-1]["scenario"], "gap": gap, "gap_pct": pct(gap),
        "caveats": [str(c) for c in shared + own],
        # Only this analysis' own lines carry keys; the single what-if's warnings are as it wrote them.
        "caveats_i18n": [as_i18n(c) for c in shared + own],
    }
