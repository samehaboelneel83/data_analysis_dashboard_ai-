"""Fields an analyst would add before charting: rates of totals and durations.

The five-dataset gap review (2026-10-02) found the questions the platform
could not ask were the ones that need a field the data does not hold:

- a **rate of totals** -- canceled orders as a share of all orders is 0.55%
  on daily ops, while the average of the daily rates is 0.88%; a widget
  aggregates one column at a time, so it can only draw the second;
- a **duration** -- days from purchase to delivery, days late against the
  promised date. Averaging a date is (rightly) refused, so without a column
  for the difference there was no delivery-time chart at all.

`propose(df, roles)` measures the frame and returns what is worth adding:

  {"measures": [MeasureDef-shaped dicts],
   "calculated_columns": [CalcColumnDef-shaped dicts],
   "facts": ["one sentence per field, with its number"]}

Nothing here is a guess: a part/whole pair must hold part <= whole on
(almost) every row, and a duration must run forward on (almost) every row.
The fields use the platform's own expression grammars -- `measure_eval` for
measures (which `measure_sql` also writes for a live source) and the
calculated-column grammar (DATEDIFF) -- so a field drawn in a proposal is the
field the dashboard will compute. Nothing is written to the dataset here: the
person's acceptance creates them (SuggestDashboardsDialog).
"""
from __future__ import annotations

import re

import pandas as pd

#: Words that say nothing about WHAT a column counts.
_GENERIC = {"total", "sum", "count", "num", "number", "n", "all", "value", "amount", "daily",
            "per", "day", "qty", "quantity", "of"}
#: A date the record is promised or due by.
_PROMISE = ("estimated", "expected", "due", "deadline", "limit", "promised", "planned", "sla", "target")
#: A date something actually happened on.
_ACTUAL = ("delivered", "delivery", "completed", "closed", "resolved", "shipped", "carrier", "finished",
           "done", "actual", "returned", "paid", "approved")
MAX_DURATIONS = 3
MAX_RATES = 3


def _words(name: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z]+", str(name).lower()):
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def _short(date_col: str) -> str:
    s = str(date_col).lower()
    s = re.sub(r"^(order|record|item|case|ticket)_", "", s)
    s = re.sub(r"_(date|timestamp|time|at|on|dt)$", "", s)
    return s


def _numeric(df: pd.DataFrame, c: str) -> pd.Series:
    return pd.to_numeric(df[c], errors="coerce")


def rate_measures(df: pd.DataFrame, nums: list[str], taken: set[str]) -> list[dict]:
    """Part/whole pairs drawn as SUM(part) / SUM(whole) * 100."""
    from .semantic_guard import is_intensive, non_additive_kind
    cands = [c for c in nums if not is_intensive(c) and non_additive_kind(c) is None]
    out: list[dict] = []
    # A total, when there is one, is THE whole: canceled orders are a share
    # of total orders, not of delivered orders.
    totals = [c for c in cands if _words(c) & {"total", "all"}]
    done: set[str] = set()
    for whole in totals + [c for c in cands if c not in totals]:
        w = _numeric(df, whole)
        for part in cands:
            if part == whole or part in done or len(out) >= MAX_RATES:
                continue
            p = _numeric(df, part)
            both = p.notna() & w.notna()
            if both.sum() < 20:
                continue
            pp, ww = p[both], w[both]
            if (pp < 0).any() or (ww <= 0).mean() > 0.01:
                continue
            if (pp == ww).mean() >= 0.999 or (pp <= ww).mean() < 0.99:
                continue
            share = pp.sum() / ww.sum() if ww.sum() else 0
            if not 0.0001 <= share <= 0.95:
                continue
            # They count the same thing: a shared noun ("orders"), the whole
            # named as a total of it.
            if not ((_words(part) - _GENERIC) & (_words(whole) - _GENERIC)):
                continue
            name = f"{part}_pct_of_{whole}"
            if name in taken:
                continue
            done.add(part)
            out.append({"name": name, "expression": f"SUM({part}) / SUM({whole}) * 100",
                        "default_aggregation": "sum",
                        "format": {"type": "percent", "decimals": 2},
                        "kind": "rate", "part": part, "whole": whole,
                        "fact": (f"{part.replace('_', ' ')} as a share of {whole.replace('_', ' ')} "
                                 f"= {share * 100:.2f}% overall (a rate of totals, measure {name})")})
    return out


def _dates(df: pd.DataFrame, cols: list[str]) -> dict[str, pd.Series]:
    out = {}
    for c in cols:
        d = pd.to_datetime(df[c], errors="coerce")
        # A time of day read as today's date is not a date (CALL_TIME).
        if d.notna().mean() >= 0.3 and d.dropna().dt.normalize().nunique() >= 5:
            out[c] = d
    return out


def durations(df: pd.DataFrame, date_cols: list[str], taken: set[str]) -> list[dict]:
    """Days from the record's start date to each later event, and days late
    against a promised date."""
    from .insights import order_event_dates
    dates = _dates(df, order_event_dates(list(date_cols)))
    if len(dates) < 2:
        return []
    start = next(iter(dates))
    out: list[dict] = []

    def forward(a: str, b: str) -> pd.Series | None:
        both = dates[a].notna() & dates[b].notna()
        if both.sum() < 20:
            return None
        gap = (dates[b][both] - dates[a][both]).dt.total_seconds() / 86400
        # Half a day at least: an approval minutes after purchase is not a
        # duration anyone charts in days.
        if (gap >= 0).mean() < 0.95 or not 0.5 <= gap.median() <= 3650:
            return None
        return gap

    for b in dates:
        if b == start or len([f for f in out if f["kind"] == "duration"]) >= MAX_DURATIONS:
            continue
        low = b.lower()
        if any(k in low for k in _PROMISE):
            continue             # a promise is not an event that happened
        gap = forward(start, b)
        if gap is None:
            continue
        name = f"days_{_short(start)}_to_{_short(b)}"
        if name in taken:
            continue
        out.append({"name": name, "expression": f"DATEDIFF({start}, {b}, 'day')", "dtype": "number",
                    "format": {"type": "number", "decimals": 1}, "kind": "duration",
                    "start": start, "end": b,
                    "fact": f"{name.replace('_', ' ')}: median {gap.median():.1f} days (a duration column)"})

    # Lateness: each promise against the event it promises.
    for promise in dates:
        if not any(k in promise.lower() for k in _PROMISE):
            continue
        actuals = [a for a in dates if a != promise and any(k in a.lower() for k in _ACTUAL)
                   and not any(k in a.lower() for k in _PROMISE)]

        def distance(a: str) -> float:
            both = dates[promise].notna() & dates[a].notna()
            if both.sum() < 20:
                return float("inf")
            return abs(((dates[a][both] - dates[promise][both]).dt.total_seconds() / 86400).median())
        # The event the promise is about is the one that lands nearest it: the
        # carrier handover for a shipping limit, the customer's delivery for
        # an estimated delivery date.
        match = sorted(actuals, key=distance)
        for actual in match[:1]:
            both = dates[promise].notna() & dates[actual].notna()
            if both.sum() < 20:
                continue
            late = (dates[actual][both] > dates[promise][both]).mean()
            if not 0 < late < 1:
                continue
            col = f"days_late_vs_{_short(promise)}"
            rate = f"late_pct_vs_{_short(promise)}"
            if col not in taken:
                out.append({"name": col, "expression": f"DATEDIFF({promise}, {actual}, 'day')",
                            "dtype": "number", "format": {"type": "number", "decimals": 1},
                            "kind": "lateness", "start": promise, "end": actual,
                            "fact": (f"{col.replace('_', ' ')}: {actual.replace('_', ' ')} minus "
                                     f"{promise.replace('_', ' ')}, positive = late")})
            if rate not in taken:
                out.append({"name": rate, "kind": "late_rate", "default_aggregation": "sum",
                            "expression": (f"SUM(IF({actual} > {promise}, 1, 0)) / COUNT({actual}) * 100"),
                            "format": {"type": "percent", "decimals": 1},
                            "start": promise, "end": actual,
                            "fact": (f"{late * 100:.1f}% of rows with a {actual.replace('_', ' ')} came after "
                                     f"the {promise.replace('_', ' ')} (measure {rate})")})
    return out


def propose(df: pd.DataFrame | None, roles: dict[str, str],
            ineligible: set[str] | None = None, mixed: dict | None = None) -> dict:
    if df is None or len(df) < 20:
        return {"measures": [], "calculated_columns": [], "facts": []}
    blocked = {str(c).casefold() for c in (ineligible or set())}
    cols = [c for c in df.columns if c in roles and str(c).casefold() not in blocked]
    nums = [c for c in cols if roles.get(c) == "numeric" and c not in (mixed or {})]
    dates = [c for c in cols if roles.get(c) == "datetime"]
    taken = set(map(str, df.columns))
    fields = rate_measures(df, nums, taken) + durations(df, dates, taken)
    measures = [f for f in fields if f["kind"] in ("rate", "late_rate")]
    calc = [f for f in fields if f["kind"] in ("duration", "lateness")]
    return {"measures": measures, "calculated_columns": calc, "facts": [f["fact"] for f in fields]}


def as_definitions(fields: dict) -> dict:
    """The dataset-shaped definitions (what the dialog saves), without the
    proposer's bookkeeping."""
    keep_m = ("name", "expression", "default_aggregation", "format")
    keep_c = ("name", "expression", "dtype", "format")
    return {"measures": [{k: m[k] for k in keep_m if k in m} for m in fields.get("measures") or []],
            "calculated_columns": [{k: c[k] for k in keep_c if k in c}
                                   for c in fields.get("calculated_columns") or []]}


def used_by(widgets: list[dict], fields: dict) -> dict:
    """The derived fields these widgets name, as definitions."""
    names: set[str] = set()
    for w in widgets:
        stack = [w.get("config") or {}]
        while stack:
            node = stack.pop()
            if isinstance(node, str):
                names.add(node)
            elif isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    defs = as_definitions(fields)
    return {"measures": [m for m in defs["measures"] if m["name"] in names],
            "calculated_columns": [c for c in defs["calculated_columns"] if c["name"] in names]}


def widgets_for(fields: dict, profile: dict, dates: list[str]) -> list[dict]:
    """The charts each derived field exists for, as panel candidates."""
    cols = {c["name"]: c for c in profile.get("columns", [])}
    cats = [c for c, info in cols.items() if info.get("role") == "categorical"
            and not info.get("is_identifier") and not info.get("is_personal")
            and 3 <= (info.get("distinct") or 0) <= 12]
    out: list[dict] = []

    def add(wt, title, cfg, section, value, why):
        out.append({"widget_type": wt, "title": title, "config": cfg, "section": section,
                    "value": value, "source": "derived", "why": why})

    def axis_for(f) -> str | None:
        start = f.get("start")
        if start in dates and f.get("kind") in ("duration",):
            return start
        return dates[0] if dates else None

    for m in fields.get("measures") or []:
        label = m["name"].replace("_", " ")
        add("kpi", label.capitalize(), {"measure": m["name"]}, "summary", 5,
            "A rate of totals: every row weighs by its size, unlike an average of rates.")
        axis = dates[0] if dates else None
        if axis:
            add("line", f"{label.capitalize()} by month",
                {"dimension": axis, "dimension_granularity": "month", "measure": m["name"]},
                "time", 5, "How the rate moved, each month weighed by its volume.")
        if cats:
            add("bar", f"{label.capitalize()} by {cats[0].replace('_', ' ')}",
                {"dimension": cats[0], "measure": m["name"], "sort": "desc"},
                "measures", 4, "Where the rate is highest.")
    first = True
    for c in fields.get("calculated_columns") or []:
        label = c["name"].replace("_", " ")
        if c.get("kind") == "lateness":
            # Its rate measure carries the headline and the trend.
            add("histogram", f"Distribution of {label}", {"measure": c["name"]}, "measures", 4,
                "How early or late, and how long the late tail runs (positive = late).")
            continue
        if first:
            add("kpi", f"Median {label}", {"measure": c["name"], "aggregation": "median"}, "summary", 4,
                "The typical duration, robust to a few very long cases.")
        add("histogram", f"Distribution of {label}", {"measure": c["name"]}, "measures", 4,
            "How long it usually takes, and how long the tail is.")
        axis = axis_for(c)
        if axis:
            add("line", f"Average {label} by month",
                {"dimension": axis, "dimension_granularity": "month", "measure": c["name"],
                 "aggregation": "avg"}, "time", 4, "Whether it is getting faster or slower.")
        if cats and first:
            add("box_plot", f"{label.capitalize()} by {cats[0].replace('_', ' ')}",
                {"dimension": cats[0], "measure": c["name"]}, "measures", 3,
                "Which groups wait longest.")
        first = False
    return out


def augment_profile(profile: dict, fields: dict) -> dict:
    """The profile with each derived measure listed like a numeric column, so
    the analysts see it and the gate accepts it (it resolves as a measure)."""
    # Every key a profiled column carries (describe_for_prompt reads them
    # all: a missing "min" failed every lens of the live panel), then ours.
    template = {k: None for c in profile.get("columns", []) for k in c}
    extra = [{**template, "name": m["name"], "role": "numeric", "distinct": 100, "missing_pct": 0,
              "is_identifier": False, "is_personal": False, "is_flag": False, "top_values": [],
              "min": None, "max": None, "is_measure": True, "description": m.get("fact")}
             for m in fields.get("measures") or []]
    have = {c["name"] for c in profile.get("columns", [])}
    return {**profile, "columns": list(profile.get("columns", [])) + [e for e in extra if e["name"] not in have]}
