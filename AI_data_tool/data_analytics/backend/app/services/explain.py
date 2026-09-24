"""Automated explanation of a response variable: which columns move it, ranked.

SAS's "explain" produces a relative-importance chart (top factor = 1, the rest
proportional) and a type-dependent relationship plot. Same here, same scale:

  * numeric factor  -> |Pearson correlation| with the response
  * category factor -> sqrt(eta-squared): the share of response variance the
    grouping explains, on the same 0-1 scale as |r| so the two kinds of factor
    are comparable in ONE ranked list -- the point of the chart

The relationship payload depends on the top factor's type: sampled x/y pairs
for a numeric factor, group means for a categorical one. Everything computes on
the frame the caller secured (RLS, prep, column masks) -- this module never
loads data itself.
"""
from __future__ import annotations

import pandas as pd

MAX_FACTORS = 20
MAX_LEVELS = 30          # a 5,000-level "category" is an id column, not a factor
SAMPLE_POINTS = 300


def _eta_sq(groups: pd.Series, response: pd.Series) -> float | None:
    """Share of response variance explained by the grouping (correlation ratio)."""
    df = pd.DataFrame({"g": groups, "y": response}).dropna()
    if df.empty or df["g"].nunique() < 2 or df["g"].nunique() > MAX_LEVELS:
        return None
    grand = df["y"].mean()
    ss_total = ((df["y"] - grand) ** 2).sum()
    if ss_total == 0:
        return None
    ss_between = df.groupby("g")["y"].agg(["mean", "count"]).pipe(
        lambda t: (t["count"] * (t["mean"] - grand) ** 2).sum())
    return float(ss_between / ss_total)


def explain_response(df: pd.DataFrame, response: str) -> dict:
    """Rank every other usable column by influence on `response`."""
    y = pd.to_numeric(df[response], errors="coerce")
    if y.dropna().nunique() < 2:
        return {"response": response, "factors": [], "relationship": None,
                "note": "The response needs at least two distinct numeric values."}

    factors = []
    for col in df.columns:
        if col == response:
            continue
        s = df[col]
        as_num = pd.to_numeric(s, errors="coerce")
        if as_num.notna().mean() > 0.8:
            r = as_num.corr(y)
            if pd.notna(r) and abs(r) > 1e-9:
                factors.append({"column": col, "kind": "numeric",
                                "score": abs(float(r)), "direction": "+" if r > 0 else "-"})
        else:
            eta = _eta_sq(s.astype(str), y)
            if eta is not None and eta > 1e-9:
                factors.append({"column": col, "kind": "category", "score": float(eta) ** 0.5})

    factors.sort(key=lambda f: f["score"], reverse=True)
    factors = factors[:MAX_FACTORS]
    if not factors:
        return {"response": response, "factors": [], "relationship": None,
                "note": "No column shows a measurable relationship."}

    # SAS's scale: the top factor is 1.0, the rest proportional to it.
    top_score = factors[0]["score"]
    for f in factors:
        f["relative"] = round(f["score"] / top_score, 4)
        f["score"] = round(f["score"], 4)

    top = factors[0]
    if top["kind"] == "numeric":
        pair = pd.DataFrame({"x": pd.to_numeric(df[top["column"]], errors="coerce"), "y": y}).dropna()
        if len(pair) > SAMPLE_POINTS:
            pair = pair.sample(SAMPLE_POINTS, random_state=7)
        relationship = {"kind": "scatter", "column": top["column"],
                        "points": [{"x": float(r.x), "y": float(r.y)} for r in pair.itertuples()]}
    else:
        means = (pd.DataFrame({"g": df[top["column"]].astype(str), "y": y}).dropna()
                 .groupby("g")["y"].mean().sort_values(ascending=False).head(12))
        relationship = {"kind": "group_means", "column": top["column"],
                        "groups": [{"name": g, "mean": round(float(v), 4)} for g, v in means.items()]}
    return {"response": response, "factors": factors, "relationship": relationship, "note": None}
