"""Suggestions in the shape the data asks for, not only bar / line / scatter.

The suggestions panel offered four widget types out of seventy-five: a finding
was mapped to one fixed chart by its KIND (a standout is a bar, a trend a
line). HR re-test 2026-10-02: a workforce dataset was never offered a bubble,
a box plot, a share, a mix -- although its data has exactly those shapes.

Here each candidate is chosen by the SHAPE of the data and offered only when
that shape is really there, so variety never means decoration:

  KPI         the headline count and the main measure
  stacked bar two categories that travel together (association rules), e.g.
              Finance is 77% Senior Staff against 34% overall; a pair with no
              rule (gender x department) is never charted as a mix -- every
              bar would show the same split
  heatmap     the same, when the second category has too many values to stack
  box plot    a measure whose spread differs by group (the group explains a
              real share of the variation, eta-squared >= 5%)
  bubble      groups compared on two numbers at once, sized by how many
  donut       a share of the whole across 2-6 parts
  treemap     a count across many parts
  multi-line  a count over time split by a group whose MIX changes over time
  rules       the Association Rules widget, when there are rules to show

Every candidate is drawn on the secured frame before it is offered
(`draws`); `diversify` keeps at most two of a kind in the list.
Titles are built from column names only, never from a value the reader may
not be allowed to see; values appear in the REASON, which is computed from the
frame this reader is allowed to see.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

#: The most of one widget type in a suggestion list (stacked and plain bars
#: count separately: they answer different questions).
PER_TYPE = 2
#: Cost bound for rule mining in the panel: the most categorical columns mined.
RULE_COLUMNS = 8
#: A pair of categories is worth a mix chart only above this lift.
MIX_MIN_LIFT = 1.5
#: Box plot / bubble: the group must explain at least this share of variation.
MIN_ETA2 = 0.05
#: Multi-line: the group mix must change over time at least this much (Cramer's V).
MIN_TREND_V = 0.1


def _h(col: str) -> str:
    return " ".join(str(col).replace("_", " ").split())


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def _num(v: float) -> str:
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:,.1f}".rstrip("0").rstrip(".")
    return f"{v:,.2f}".rstrip("0").rstrip(".")


class _Profile:
    """The frame's columns sorted by what they can be: id, category, number, date."""

    def __init__(self, df: pd.DataFrame, roles: dict[str, str],
                 column_meta: dict | None, ineligible: set[str] | None):
        from .insights import _NOT_START_DATE, order_event_dates
        from .semantic_guard import default_summary, is_identifier
        from .widget_data import _is_id_like_column
        self.df = df
        blocked = {c.casefold() for c in (ineligible or set())}
        cols = [c for c in df.columns if c in roles and str(c).casefold() not in blocked]
        self.card = {c: self._nunique(c) for c in cols}
        n = len(df)
        self.ids = [c for c in cols if (is_identifier(c, column_meta) or _is_id_like_column(c, column_meta))
                    and self.card[c] >= 0.5 * n]
        self.id_col = self.ids[0] if self.ids else None
        self.cats = [c for c in cols if roles.get(c) == "categorical" and c not in self.ids
                     and 2 <= self.card[c] <= 50]
        self.nums = [c for c in cols if roles.get(c) == "numeric" and c not in self.ids
                     and not _is_id_like_column(c, column_meta) and not is_identifier(c, column_meta)
                     and self.card[c] > 2]
        from .insights import drop_duplicate_measures
        self.nums = drop_duplicate_measures(df, self.nums)
        self.dates = [c for c in cols if roles.get(c) == "datetime"
                      and not any(k in str(c).lower() for k in _NOT_START_DATE)]
        self.dates = order_event_dates(self.dates, df)
        self.summary = {m: (default_summary(m, column_meta) if default_summary(m, column_meta)
                            in ("avg", "median", "sum") else "avg") for m in self.nums}
        if self.id_col:
            from .insights import counted_as
            self.count_word = counted_as(self.id_col)
            self.entity = _h(self.id_col)
        else:
            self.count_word, self.entity = "Rows", "rows"

    def _nunique(self, c) -> int:
        try:
            return int(self.df[c].nunique(dropna=True))
        except Exception:                                    # noqa: BLE001
            return 0

    def count(self, fallback: str) -> dict:
        """How to count: distinct ids when there is one, else rows."""
        return ({"measure": self.id_col, "aggregation": "countd"} if self.id_col
                else {"measure": fallback, "aggregation": "count"})


def _eta2(values: pd.Series, groups: pd.Series) -> float:
    """Share of the variation in `values` that the groups explain (0..1)."""
    v = pd.to_numeric(values, errors="coerce")
    ok = v.notna() & groups.notna()
    v, g = v[ok], groups[ok].astype(str)
    if len(v) < 20:
        return 0.0
    total = float(((v - v.mean()) ** 2).sum())
    if not total:
        return 0.0
    means = v.groupby(g).transform("mean")
    return float(((means - v.mean()) ** 2).sum()) / total


def _cramers_v(a: pd.Series, b: pd.Series) -> float:
    t = pd.crosstab(a, b)
    if t.shape[0] < 2 or t.shape[1] < 2:
        return 0.0
    n = float(t.to_numpy().sum())
    expected = np.outer(t.sum(axis=1), t.sum(axis=0)) / n
    chi2 = float((((t.to_numpy() - expected) ** 2) / np.where(expected == 0, 1, expected)).sum())
    return math.sqrt(chi2 / (n * (min(t.shape) - 1))) if n else 0.0


def _item(wt: str, title: str, reason: str, config: dict, score: float, kind: str) -> dict:
    return {"widget_type": wt, "title": _cap(title)[:120], "reason": reason, "config": config,
            "score": round(score, 3), "kind": kind, "aligned": False,
            "keep_granularity": "dimension_granularity" in config}


# ── candidates ───────────────────────────────────────────────────────────────

def _kpis(p: _Profile) -> list[dict]:
    out = []
    df = p.df
    if p.id_col:
        out.append(_item("kpi", p.count_word, f"How many {p.entity} there are in total.",
                         {"measure": p.id_col, "aggregation": "countd"}, 9.9, "kpi"))
    if p.nums:
        m = p.nums[0]
        summ = p.summary[m]
        word = {"avg": "Average", "median": "Median", "sum": "Total"}[summ]
        out.append(_item("kpi", f"{word} {_h(m)}", f"The {word.lower()} {_h(m)} across all {len(df):,} rows.",
                         {"measure": m, "aggregation": summ}, 9.2, "kpi"))
    return out


def _mixes(p: _Profile) -> tuple[list[dict], list[dict]]:
    """Mix charts from association rules, and the rules widget itself."""
    from .analysis.patterns import PatternError, association_rules
    cats = sorted([c for c in p.cats if p.card[c] <= 30], key=lambda c: p.card[c])[:RULE_COLUMNS]
    if len(cats) < 2:
        return [], []
    try:
        rules = association_rules(p.df[cats].astype(object).where(p.df[cats].notna()),
                                  cats).to_dict().get("rows") or []
    except PatternError:
        return [], []
    # One rule of one value each side is a statement about a PAIR of columns.
    best: dict[frozenset, dict] = {}
    for r in rules:
        if len(r.get("if_items") or []) != 1 or len(r.get("then_items") or []) != 1:
            continue
        a, b = r["if_items"][0][0], r["then_items"][0][0]
        key = frozenset((a, b))
        if r["lift"] >= MIX_MIN_LIFT and (key not in best or r["lift"] > best[key]["lift"]):
            best[key] = r
    mixes = []
    for key, r in sorted(best.items(), key=lambda kv: -kv[1]["lift"])[:2]:
        a, b = sorted(key, key=lambda c: -p.card[c])     # bars = the column with more values
        # Say it as "<a value> is X% <b value>": the rule from a to b, either way round.
        ra = next((x for x in rules if len(x["if_items"]) == 1 and len(x["then_items"]) == 1
                   and x["if_items"][0][0] == a and x["then_items"][0][0] == b), None) or r
        (ca, va), (cb, vb) = ra["if_items"][0], ra["then_items"][0]
        reason = (f"{va} ({_h(ca)}) is {_pct(ra['confidence'])} {vb}, against {_pct(ra['base_rate'])} "
                  f"overall -- {ra['lift']:.1f}x what chance predicts.")
        cfg = {"dimension": a, "dimension2": b, **p.count(a)}
        score = 9.0 + min(r["lift"] - 1, 2) * 0.2
        if p.card[b] <= 8:
            mixes.append(_item("bar", f"{_h(b)} mix by {_h(a)}", reason,
                               {**cfg, "bar_mode": "stacked100"}, score, "mix"))
        else:
            mixes.append(_item("heatmap", f"{_h(a)} by {_h(b)}", reason, cfg, score - 0.1, "mix"))
    widget = []
    if len(rules) >= 3:
        top = rules[0]
        widget.append(_item(
            "model_rules", "What goes together in this data",
            f"{len(rules)} combinations of values appear together more often than chance; the "
            f"strongest: {top['if']} -> {top['then']} ({top['lift']:.1f}x).",
            {"predictors": cats}, 8.0, "rules"))
    return mixes, widget


def _box(p: _Profile) -> list[dict]:
    if not p.nums:
        return []
    m = p.nums[0]
    best = None
    for c in p.cats:
        if 2 <= p.card[c] <= 15:
            e = _eta2(p.df[m], p.df[c])
            if best is None or e > best[1]:
                best = (c, e)
    if not best or best[1] < MIN_ETA2:
        return []
    c, e = best
    med = pd.to_numeric(p.df[m], errors="coerce").groupby(p.df[c].astype(str)).median().dropna()
    lo, hi = med.idxmin(), med.idxmax()
    reason = (f"Median {_h(m)} runs from {_num(med[lo])} ({lo}) to {_num(med[hi])} ({hi}); "
              f"{_h(c)} explains {_pct(e)} of the variation in {_h(m)}.")
    return [_item("box_plot", f"{_h(m)} range by {_h(c)}", reason,
                  {"dimension": c, "measure": m, "limit": 15}, 8.6, "spread")]


def _bubble(p: _Profile) -> list[dict]:
    """Groups on two numbers at once. The second number may be a start date,
    read as years since it (average years of service per title)."""
    if not p.nums:
        return []
    x = p.nums[0]
    y = p.nums[1] if len(p.nums) > 1 else (p.dates[0] if p.dates else None)
    if not y:
        return []
    from .widget_data import _is_date_like, _years_before_latest
    ys = _years_before_latest(p.df[y]) if _is_date_like(p.df[y]) else p.df[y]
    best = None
    for c in p.cats:
        if 3 <= p.card[c] <= 30:
            e = min(_eta2(p.df[x], p.df[c]), _eta2(ys, p.df[c]))
            if best is None or e > best[1]:
                best = (c, e)
    if not best or best[1] < MIN_ETA2:
        return []                          # one of the two axes does not vary by group
    c = best[0]
    y_date = _is_date_like(p.df[y])
    y_name = f"years since {_h(y)}" if y_date else _h(y)
    size = {"size": p.id_col, "size_aggregation": "countd"} if p.id_col \
        else {"size": c, "size_aggregation": "count"}
    cfg = {"dimension": c, "measure": x, "measure2": y, **size, "aggregation": "avg",
           "x_axis_label": f"Average {_h(x)}", "y_axis_label": f"Average {y_name}"}
    reason = (f"One bubble per {_h(c)}: average {_h(x)} across, average {y_name} up, "
              f"size = {p.count_word.lower()}.")
    return [_item("bubble", f"{_h(x)} and {y_name} by {_h(c)}", reason, cfg, 8.4, "bubble")]


def _shares(p: _Profile, used_dims: set[str]) -> list[dict]:
    out = []
    small = [c for c in p.cats if 2 <= p.card[c] <= 6]
    if small:
        c = small[0]
        shares = p.df[c].astype(str).value_counts(normalize=True)
        reason = ", ".join(f"{k} {_pct(v)}" for k, v in shares.head(4).items()) + "."
        out.append(_item("donut", f"{p.count_word} share by {_h(c)}", reason,
                         {"dimension": c, **p.count(c), "sort": "desc", "sort_by": "value"},
                         7.6, "share"))
    many = [c for c in p.cats if 7 <= p.card[c] <= 40 and c not in used_dims]
    if many:
        c = many[0]
        out.append(_item("treemap", f"{p.count_word} by {_h(c)} (treemap)",
                         f"All {p.card[c]} values of {_h(c)} at once, sized by {p.count_word.lower()}.",
                         {"dimension": c, **p.count(c), "sort": "desc", "sort_by": "value", "limit": 40},
                         7.2, "share"))
    return out


def _split_trend(p: _Profile) -> list[dict]:
    if not p.dates:
        return []
    d = p.dates[0]
    dt = pd.to_datetime(p.df[d], errors="coerce")
    if dt.isna().all() or (dt.max() - dt.min()).days < 2 * 365:
        return []
    year = dt.dt.year
    best = None
    for c in p.cats:
        if 3 <= p.card[c] <= 8:
            v = _cramers_v(p.df[c].astype(str)[year.notna()], year[year.notna()])
            if best is None or v > best[1]:
                best = (c, v)
    if not best or best[1] < MIN_TREND_V:
        return []                          # the mix is the same every year: one line says it
    c, v = best
    title = f"{p.count_word} per year of {_h(d)} by {_h(c)}"
    return [_item("line", title,
                  f"The mix of {_h(c)} changes over time (Cramer's V {v:.2f}), so one line per value.",
                  {"dimension": d, "dimension2": c, **p.count(d), "dimension_granularity": "year"},
                  8.2, "trend_split")]


# ── the rest of the catalogue ────────────────────────────────────

#: Two numbers are "the same kind of amount" when their totals are within
#: this factor of each other and they move together row by row at least this much.
SAME_SIZE = 2.0
SAME_MOVE = 0.5
#: A date must cover at least this many days before a chart over time is offered.
MIN_DAYS = 90


def _alike(p: _Profile) -> tuple[str, str] | None:
    """Two numbers that add up, of one size, that move together: one can be
    read against the other (an amount and the amount it was meant to be)."""
    sums = [m for m in p.nums if p.summary[m] == "sum"]
    for i, a in enumerate(sums):
        for b in sums[i + 1:]:
            x, y = pd.to_numeric(p.df[a], errors="coerce"), pd.to_numeric(p.df[b], errors="coerce")
            ta, tb = float(x.sum()), float(y.sum())
            if ta <= 0 or tb <= 0 or max(ta, tb) / min(ta, tb) > SAME_SIZE:
                continue
            ok = x.notna() & y.notna()
            if ok.sum() < 30 or not x[ok].std() or not y[ok].std():
                continue
            r = float(np.corrcoef(x[ok], y[ok])[0, 1])
            if np.isfinite(r) and r >= SAME_MOVE:
                return a, b
    return None


def _share_like(p: _Profile) -> str | None:
    """A number that is a share: averaged, and every value between 0 and 1.
    (0 to 100 is not taken as one: a score or an age lies there too.)"""
    for m in p.nums:
        if p.summary[m] == "sum":
            continue
        v = pd.to_numeric(p.df[m], errors="coerce").dropna()
        if len(v) >= 20 and float(v.min()) >= 0 and 0 < float(v.max()) <= 1:
            return m
    return None


def catalogue_suggestions(p: _Profile) -> list[dict]:
    """One idea for each further widget type this data has the shape for, so
    the panel is not limited to the handful of types the findings map to.
    Each states, in its reason, what in the data makes it fit; the caller
    still draws every one before offering it. Types whose fit cannot be told
    from the columns alone (a map, a hierarchy, a funnel's order) are left to
    the person."""
    df, out = p.df, []
    word = {"avg": "Average", "median": "Median", "sum": "Total"}
    sums = [m for m in p.nums if p.summary[m] == "sum"]
    levels = [m for m in p.nums if p.summary[m] != "sum"]
    small = [c for c in p.cats if 2 <= p.card[c] <= 6]
    mid = [c for c in p.cats if 3 <= p.card[c] <= 12]
    many = [c for c in p.cats if 7 <= p.card[c] <= 50]
    date = None
    if p.dates:
        dt = pd.to_datetime(df[p.dates[0]], errors="coerce")
        if dt.notna().any() and (dt.max() - dt.min()).days >= MIN_DAYS:
            date = p.dates[0]
    main = (sums or p.nums or [None])[0]

    def named(m):
        return f"{word[p.summary[m]]} {_h(m)}"

    def add(wt, title, reason, config, score):
        out.append(_item(wt, title, reason, config, score, "catalogue"))

    pair = _alike(p)
    if pair:
        a, b = pair
        add("gauge", f"{_h(a)} against {_h(b)}",
            f"{_cap(_h(a))} and {_h(b)} are the same kind of amount and move together, so one is read against the other.",
            {"measure": a, "aggregation": "sum", "target": b, "gauge_shape": "bullet"}, 7.9)
        if mid:
            add("butterfly", f"{_h(a)} and {_h(b)} by {_h(mid[0])}",
                f"The two amounts back to back for each {_h(mid[0])}.",
                {"dimension": mid[0], "measure": a, "measure2": b, "aggregation": "sum", "aggregation2": "sum"}, 7.3)
        if date:
            add("comparative_time_series", f"{_h(a)} and {_h(b)} over time",
                "The two amounts on one scale, period by period.",
                {"start": date, "measure": a, "measure2": b, "aggregation": "sum", "aggregation2": "sum",
                 "dimension_granularity": "month"}, 7.2)
    share = _share_like(p)
    if share:
        top = 1
        add("gauge", f"Average {_h(share)}",
            f"{_cap(_h(share))} is a share (it runs from 0 to {top}), so it is shown as how far along it is.",
            {"measure": share, "aggregation": "avg", "gauge_shape": "progress", "target_value": top}, 7.8)
    if len(p.nums) >= 3:
        kind = max(("sum", "avg", "median"), key=lambda k: sum(1 for m in p.nums if p.summary[m] == k))
        same = [m for m in p.nums if p.summary[m] == kind][:5]
        if len(same) >= 3:
            add("card", f"{word[kind]} of {len(same)} numbers",
                f"{len(same)} numbers that are each read as one figure, in one list.",
                {"measures": same, "aggregation": kind}, 7.7)
    if levels and mid:
        m, c = levels[0], mid[0]
        add("dot_plot", f"{named(m)} by {_h(c)}",
            f"{_cap(_h(m))} is averaged, not added up, so each {_h(c)} is a point on one scale rather than a bar from zero.",
            {"dimension": c, "measure": m, "aggregation": p.summary[m], "sort": "desc", "sort_by": "value"}, 7.6)
    if len(p.nums) >= 2 and mid:
        a, b, c = p.nums[0], p.nums[1], mid[0]
        add("dual_axis_bar", f"{named(a)} and {named(b).lower()} by {_h(c)}",
            f"Two numbers for each {_h(c)}, each on its own scale.",
            {"dimension": c, "measure": a, "measure2": b, "aggregation": p.summary[a], "aggregation2": p.summary[b]}, 7.5)
    if date and main:
        if sums:
            add("area", f"Total {_h(sums[0])} over time",
                f"{_cap(_h(sums[0]))} adds up, so the filled area is the amount in each month of {_h(date)}.",
                {"dimension": date, "dimension_granularity": "month", "measure": sums[0], "aggregation": "sum"}, 7.45)
        if levels:
            add("step", f"{named(levels[0])} over time",
                f"{_cap(_h(levels[0]))} is a level: it holds through each month and changes at the next.",
                {"dimension": date, "dimension_granularity": "month", "measure": levels[0],
                 "aggregation": p.summary[levels[0]]}, 7.1)
        if len(p.nums) >= 2:
            a, b = p.nums[0], p.nums[1]
            add("dual_axis_time_series", f"{named(a)} and {named(b).lower()} over time",
                "Two numbers month by month, each on its own scale, to see whether they rise and fall together.",
                {"start": date, "measure": a, "measure2": b, "aggregation": p.summary[a],
                 "aggregation2": p.summary[b], "dimension_granularity": "month"}, 7.0)
        ranked = [c for c in p.cats if 3 <= p.card[c] <= 8]
        if ranked and sums:
            add("ribbon", f"Total {_h(sums[0])} by {_h(ranked[0])} over time",
                f"Which {_h(ranked[0])} leads in each month, and when the order changes.",
                {"dimension": date, "dimension_granularity": "month", "dimension2": ranked[0],
                 "measure": sums[0], "aggregation": "sum"}, 6.9)
    if sums and mid:
        add("waterfall", f"How {_h(mid[0])} adds up to total {_h(sums[0])}",
            f"Each {_h(mid[0])} as a step towards the total.",
            {"dimension": mid[0], "measure": sums[0], "aggregation": "sum", "sort": "desc", "sort_by": "value"}, 7.05)
    if p.nums:
        add("histogram", f"How {_h(p.nums[0])} is spread",
            f"How many rows fall in each range of {_h(p.nums[0])}.", {"measure": p.nums[0], "bins": 20}, 6.95)
    if len(p.nums) >= 2:
        add("numeric_series", f"{_h(p.nums[1])} against {_h(p.nums[0])}",
            "One number against another, to see whether they move together.",
            {"measure": p.nums[0], "measure2": p.nums[1]}, 6.8)
    if len(p.nums) >= 3:
        add("correlation_matrix", "Which numbers move together",
            f"Every pair of {min(len(p.nums), 8)} numbers at once.", {"measures": p.nums[:8]}, 6.85)
        add("parallel_coordinates", f"{min(len(p.nums), 6)} numbers side by side",
            "Each row drawn across all the numbers, to see which go high or low together.",
            {"measures": p.nums[:6], **({"color": small[0]} if small else {})}, 6.5)
    two = [c for c in p.cats if 2 <= p.card[c] <= 15]
    if len(two) >= 2:
        a, b = two[0], two[1]
        add("crosstab", f"{p.count_word} by {_h(a)} and {_h(b)}",
            f"A table of every {_h(a)} against every {_h(b)}.", {"dimension": a, "dimension2": b, **p.count(a)}, 6.75)
        add("sankey", f"{_h(a)} to {_h(b)}", f"How the rows of each {_h(a)} divide among {_h(b)}.",
            {"dimension": a, "dimension2": b, **p.count(a)}, 6.6)
    if mid and small and main and mid[0] != small[0]:
        add("small_multiples", f"{named(main)} by {_h(mid[0])}, one panel per {_h(small[0])}",
            f"The same chart repeated for each {_h(small[0])}, on one scale.",
            {"dimension": mid[0], "measure": main, "aggregation": p.summary[main], "facet_by": small[0]}, 6.7)
    if many:
        c = many[0]
        add("list", f"Top {_h(c)} by {p.count_word.lower()}", f"The {_h(c)} values with the most {p.entity}, as a ranked list.",
            {"dimension": c, **p.count(c), "sort": "desc", "sort_by": "value", "limit": 10}, 6.65)
        add("word_cloud", f"{_h(c)} sized by {p.count_word.lower()}",
            f"All {p.card[c]} values of {_h(c)} at once; the larger the word, the more {p.entity}.",
            {"dimension": c, **p.count(c), "limit": 50}, 6.4)
    return out


def variety_suggestions(df: pd.DataFrame | None, roles: dict[str, str],
                        column_meta: dict | None = None,
                        ineligible: set[str] | None = None) -> list[dict]:
    from .insights import BASELINE_MIN_ROWS
    if df is None or len(df) < BASELINE_MIN_ROWS:
        return []
    p = _Profile(df, roles, column_meta, ineligible)
    out = _kpis(p)
    mixes, rules_widget = _mixes(p)
    out += mixes + _box(p) + _bubble(p)
    used = {s["config"].get("dimension") for s in out} | {s["config"].get("dimension2") for s in out}
    out += _shares(p, used) + _split_trend(p) + rules_widget
    return out


# ── honesty gates ────────────────────────────────────────────────────────────

def draws(widget_type: str, config: dict, df: pd.DataFrame) -> bool:
    """Shape it on the frame; offer it only if there is something to draw."""
    from .suggest_dataset_dashboard import _RESULT_METADATA
    from .widget_data import SHAPERS
    from .widget_roles import InvalidWidget, missing_roles, validate_widget_payload
    if missing_roles(widget_type, config):
        return False
    # The same check "Add" runs: a suggestion the server would refuse to save
    # (an axis title on a box plot) is not a suggestion.
    try:
        validate_widget_payload(widget_type, config)
    except InvalidWidget:
        return False
    shaper = SHAPERS.get(widget_type)
    if shaper is None:
        return False
    try:
        r = shaper(df, dict(config))
    except Exception:                                        # noqa: BLE001
        return False
    if not isinstance(r, dict) or r.get("type") in ("empty", "error"):
        return False
    if r.get("type") == "model":
        return r.get("status") == "ok"
    if r.get("type") == "sankey":
        return bool(r.get("links"))
    if r.get("type") == "small_multiples":
        return len(r.get("panels") or []) > 1
    if isinstance(r.get("rows"), list):
        return len(r["rows"]) > 0
    if r.get("value") is not None:
        return True
    return any(isinstance(v, (list, dict)) and len(v) for k, v in r.items()
               if k not in _RESULT_METADATA)


def _type_key(s: dict) -> str:
    c = s.get("config") or {}
    if s["widget_type"] == "bar" and c.get("dimension2"):
        return "bar_mix"
    if s["widget_type"] == "pie":
        return "donut"
    return s["widget_type"]


def diversify(items: list[dict], limit: int, per_type: int = PER_TYPE) -> list[dict]:
    """At most `per_type` of each kind, in the order given."""
    seen: dict[str, int] = {}
    out = []
    for s in items:
        k = _type_key(s)
        if seen.get(k, 0) >= per_type:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(s)
        if len(out) >= limit:
            break
    return out
