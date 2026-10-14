"""Why did it change? -- which groups account for the difference between two
periods (docs/discovery/PLAN.md, phase 3 #14).

A total that moved between one period and the next moved SOMEWHERE: this
splits the difference by each category in turn and says which values carry
it. "Fees rose 30% in September" becomes "two thirds of the rise is one
service; the rest is spread".

It is arithmetic, not a model, and it says only WHERE the change sits. It
does not say what caused it: a group that carries the change is where to
look, not why.

For a total or a count the parts add up to the whole change, so each value
gets a share of it. For an average they do not (the change of an average is
part change within groups and part change of the mix), so each value is
given its own change and its share of rows -- and no share of the change.
"""
from __future__ import annotations

import pandas as pd

from ..analysis_contract import AnalysisContract
from ..readback import _s, as_i18n

#: A category with more values than this is not a breakdown anyone reads.
MAX_LEVELS = 50
#: Values listed per category, largest change first.
TOP_VALUES = 6
#: Categories reported, most concentrated first.
TOP_FACTORS = 5
#: When a category's values moved this many times more than the total did,
#: they mostly cancel: "748% of the change" is true and tells nobody anything,
#: so the shares are left out and the category says its values offset.
OFFSET_RATIO = 3.0
EMPTY = "(empty)"
_GRAIN = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}
_ADDITIVE = ("sum", "count", "countd")


class ChangeError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def _agg(series: pd.Series, how: str) -> float:
    if how == "count":
        return float(series.count())
    if how == "countd":
        return float(series.nunique())
    v = pd.to_numeric(series, errors="coerce")
    return float({"sum": v.sum, "avg": v.mean, "mean": v.mean, "median": v.median,
                  "min": v.min, "max": v.max}.get(how, v.sum)())


def explain_change(df: pd.DataFrame, date_column: str, measure: str, aggregation: str = "sum",
                   granularity: str = "month", period: str | None = None, baseline: str | None = None,
                   factors: list[str] | None = None, column_meta: dict | None = None) -> AnalysisContract:
    """Which values of which categories account for the change of `measure`
    between `baseline` and `period`.

    With no periods named: the last COMPLETE period against the one before it
    (the period the data stops inside is not compared). `factors` limits the
    categories looked at; omitted, every category of 2 to 50 values that is
    not an identifier and not hidden."""
    how = str(aggregation or "sum").lower()
    how = "avg" if how in ("mean", "average") else how
    for col in (date_column, measure):
        if col not in df.columns:
            raise ChangeError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=col))
    freq = _GRAIN.get(str(granularity or "month").lower())
    if not freq:
        raise ChangeError(_s("no.change_drivers.2", "granularity must be day, week, month, quarter or year", cap=False))
    dt = pd.to_datetime(df[date_column], errors="coerce")
    frame = df[dt.notna()].copy()
    if frame.empty:
        raise ChangeError(_s("no.change_drivers.3", "{a} holds no dates", cap=False, a=date_column))
    frame["__p__"] = dt[dt.notna()].dt.to_period(freq).astype(str)
    periods = sorted(frame["__p__"].unique())

    if period is None:
        from ..relative_dates import partial_period
        rows = [{"name": p, "value": 1} for p in periods]
        try:
            partial = partial_period(frame, date_column, str(granularity or "month").lower(), {"type": "series", "rows": rows})
        except Exception:                                       # noqa: BLE001
            partial = None
        usable = periods[:-1] if partial and len(periods) > 1 else periods
        if len(usable) < 2:
            raise ChangeError(_s("no.change_drivers.4", "needs at least two complete periods to compare", cap=False))
        period, baseline = usable[-1], baseline or usable[-2]
    period, baseline = str(period), str(baseline) if baseline is not None else None
    if baseline is None:
        earlier = [p for p in periods if p < period]
        if not earlier:
            raise ChangeError(_s("no.change_drivers.5", "there is no period before {a} to compare with", cap=False, a=period))
        baseline = earlier[-1]
    for p in (period, baseline):
        if p not in periods:
            raise ChangeError(_s("no.change_drivers.6", "no rows fall in {a}", cap=False, a=p))

    now, then = frame[frame["__p__"] == period], frame[frame["__p__"] == baseline]
    total_now, total_then = _agg(now[measure], how), _agg(then[measure], how)
    change = total_now - total_then
    additive = how in _ADDITIVE

    meta = column_meta or {}
    from .. import semantic_guard as guard
    if factors:
        missing = [c for c in factors if c not in df.columns]
        if missing:
            raise ChangeError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=missing[0]))
        candidates = list(factors)
    else:
        candidates = []
        for c in df.columns:
            if c in (date_column, measure) or str(c).startswith("__"):
                continue
            entry = meta.get(c) if isinstance(meta.get(c), dict) else {}
            if entry.get("hidden") or entry.get("eligible_for_suggestion") is False:
                continue
            s = df[c]
            if pd.api.types.is_datetime64_any_dtype(s) or guard.is_identifier(c, meta):
                continue
            if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                continue
            if 2 <= s.nunique(dropna=True) <= MAX_LEVELS:
                candidates.append(c)

    out_factors = []
    for c in candidates:
        key_now = now[c].astype(object).where(now[c].notna(), EMPTY).astype(str)
        key_then = then[c].astype(object).where(then[c].notna(), EMPTY).astype(str)
        a = now.groupby(key_now)[measure].apply(lambda s: _agg(s, how))
        b = then.groupby(key_then)[measure].apply(lambda s: _agg(s, how))
        both = pd.DataFrame({"now": a, "then": b}).fillna(0.0 if additive else float("nan"))
        both["delta"] = both["now"] - both["then"]
        both = both.dropna(subset=["delta"])
        if both.empty:
            continue
        ranked = both.reindex(both["delta"].abs().sort_values(ascending=False).index)
        moved = float(both["delta"].abs().sum())
        values = []
        rows_now = key_now.value_counts()
        offsetting = bool(additive and change and moved > OFFSET_RATIO * abs(change))
        for name, r in ranked.head(TOP_VALUES).iterrows():
            item = {"value": str(name), "now": float(r["now"]), "then": float(r["then"]), "delta": float(r["delta"])}
            if offsetting:
                pass
            elif additive and change:
                # Its part of the whole change; over 100% or negative when
                # other values moved the other way.
                item["share_of_change_pct"] = round(float(r["delta"]) / change * 100, 1)
            else:
                item["rows_share_pct"] = round(float(rows_now.get(name, 0)) / max(len(now), 1) * 100, 1)
            values.append(item)
        top = float(ranked["delta"].abs().iloc[0])
        out_factors.append({
            "column": c, "values": values, "levels": int(len(both)),
            # How much of all the movement in this category sits in ONE value:
            # near 1 = the change is one group's; near 1/levels = spread evenly.
            "concentration": round(top / moved, 3) if moved else 0.0,
            "top": str(ranked.index[0]), "offsetting": offsetting,
        })
    # A category whose values cancel is where rows moved between values, not
    # where the change sits: after the ones that do carry it.
    out_factors.sort(key=lambda f: (f["offsetting"], -f["concentration"]))
    out_factors = out_factors[:TOP_FACTORS]

    caveats = [_s("an.where", "This says WHERE the change sits, not what caused it.")]
    if not additive:
        caveats.append(_s("an.avgparts", "An average does not split into parts: each value shows its own change and its share of rows."))
    return AnalysisContract(
        kind="change_drivers",
        columns=[{"name": "column", "type": "text"}, {"name": "value", "type": "text"},
                 {"name": "then", "type": "number"}, {"name": "now", "type": "number"},
                 {"name": "delta", "type": "number"}],
        rows=[{"column": f["column"], **v} for f in out_factors for v in f["values"]],
        meta={"measure": measure, "aggregation": how, "date_column": date_column,
              "granularity": str(granularity or "month").lower(), "period": period, "baseline": baseline,
              "now": total_now, "then": total_then, "change": change,
              "change_pct": (change / abs(total_then) * 100) if total_then else None,
              "additive": additive, "factors": out_factors,
              "rows_now": int(len(now)), "rows_then": int(len(then)),
              "warnings_i18n": [as_i18n(c) for c in caveats]},
        warnings=[str(c) for c in caveats])


def explain_variance(df: pd.DataFrame, measure: str, reference: str, aggregation: str = "sum",
                     factors: list[str] | None = None, column_meta: dict | None = None) -> AnalysisContract:
    """Where the difference between two numbers of the same rows sits: one
    column against another (what was reached against what was expected, what
    was there against what was asked for), split by every usable category.

    The same arithmetic as `explain_change`, between two columns instead of
    two periods -- so the same reading: each value's part of the difference,
    no shares where the parts cancel, and never a cause."""
    how = str(aggregation or "sum").lower()
    how = "avg" if how in ("mean", "average") else how
    for col in (measure, reference):
        if col not in df.columns:
            raise ChangeError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=col))
    if measure == reference:
        raise ChangeError(_s("no.change_drivers.7", "the two numbers are the same column", cap=False))
    # Rows where either number is missing are in neither total: a difference
    # of a number against nothing is not a difference.
    frame = df[pd.to_numeric(df[measure], errors="coerce").notna()
               & pd.to_numeric(df[reference], errors="coerce").notna()]
    if frame.empty:
        raise ChangeError(_s("no.change_drivers.8", "no row holds both {a} and {b}", cap=False, a=measure, b=reference))
    total_now, total_then = _agg(frame[measure], how), _agg(frame[reference], how)
    change = total_now - total_then
    additive = how in _ADDITIVE

    meta = column_meta or {}
    from .. import semantic_guard as guard
    if factors:
        missing = [c for c in factors if c not in df.columns]
        if missing:
            raise ChangeError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=missing[0]))
        candidates = list(factors)
    else:
        candidates = []
        for c in df.columns:
            if c in (measure, reference) or str(c).startswith("__"):
                continue
            entry = meta.get(c) if isinstance(meta.get(c), dict) else {}
            if entry.get("hidden") or entry.get("eligible_for_suggestion") is False:
                continue
            s = df[c]
            if pd.api.types.is_datetime64_any_dtype(s) or guard.is_identifier(c, meta):
                continue
            if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                continue
            if 2 <= s.nunique(dropna=True) <= MAX_LEVELS:
                candidates.append(c)

    out_factors = []
    for c in candidates:
        key = frame[c].astype(object).where(frame[c].notna(), EMPTY).astype(str)
        a = frame.groupby(key)[measure].apply(lambda s: _agg(s, how))
        b = frame.groupby(key)[reference].apply(lambda s: _agg(s, how))
        both = pd.DataFrame({"now": a, "then": b})
        both["delta"] = both["now"] - both["then"]
        both = both.dropna(subset=["delta"])
        if both.empty:
            continue
        ranked = both.reindex(both["delta"].abs().sort_values(ascending=False).index)
        moved = float(both["delta"].abs().sum())
        offsetting = bool(additive and change and moved > OFFSET_RATIO * abs(change))
        rows = key.value_counts()
        values = []
        for name, r in ranked.head(TOP_VALUES).iterrows():
            item = {"value": str(name), "now": float(r["now"]), "then": float(r["then"]), "delta": float(r["delta"]),
                    "delta_pct": round(float(r["delta"]) / abs(float(r["then"])) * 100, 1) if r["then"] else None}
            if offsetting:
                pass
            elif additive and change:
                item["share_of_change_pct"] = round(float(r["delta"]) / change * 100, 1)
            else:
                item["rows_share_pct"] = round(float(rows.get(name, 0)) / max(len(frame), 1) * 100, 1)
            values.append(item)
        out_factors.append({"column": c, "values": values, "levels": int(len(both)),
                            "concentration": round(float(ranked["delta"].abs().iloc[0]) / moved, 3) if moved else 0.0,
                            "top": str(ranked.index[0]), "offsetting": offsetting})
    out_factors.sort(key=lambda f: (f["offsetting"], -f["concentration"]))
    out_factors = out_factors[:TOP_FACTORS]

    caveats = [_s("an.where.diff", "This says WHERE the difference sits, not what caused it.")]
    if not additive:
        caveats.append(_s("an.avgparts.diff", "An average does not split into parts: each value shows its own difference "
                                              "and its share of rows."))
    left_out = len(df) - len(frame)
    if left_out:
        caveats.append(_s("an.oneonly", "{n} rows hold only one of the two numbers and are in neither total.", n=f"{left_out:,}"))
    return AnalysisContract(
        kind="change_drivers",
        columns=[{"name": "column", "type": "text"}, {"name": "value", "type": "text"},
                 {"name": "then", "type": "number"}, {"name": "now", "type": "number"},
                 {"name": "delta", "type": "number"}],
        rows=[{"column": f["column"], **v} for f in out_factors for v in f["values"]],
        meta={"mode": "measures", "measure": measure, "reference": reference, "aggregation": how,
              "now": total_now, "then": total_then, "change": change,
              "change_pct": (change / abs(total_then) * 100) if total_then else None,
              "additive": additive, "factors": out_factors, "rows_used": int(len(frame)), "rows_left_out": int(left_out),
              "warnings_i18n": [as_i18n(c) for c in caveats]},
        warnings=[str(c) for c in caveats])
