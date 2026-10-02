"""Measured facts about a dataset, for anyone who has to propose charts of it.

The dashboard designer (a model) used to see column SHAPES: "salary, numeric,
min/max", "dept_name, 9 values". The HR analyst panel (2026-10-02) proposed
far better visuals when it was handed the measured facts instead -- pay by
department, hires per year, which categories travel together, and which
comparisons are FLAT (gender share is ~40% in every department) -- because a
chart is only worth proposing for a difference that exists.

`build_facts(df, roles, ...)` measures them on the secured frame (the frame
this reader may see, so no fact can leak a row they could not) and returns:

  {"facts": [{"kind", "text", "columns", "strength"}], "text": "<prompt block>"}

Kinds: overview, measure, groups (a measure by a category, with how much the
category explains), flat (a comparison with no real difference), shares,
trend, mix_over_time, link (association rules), independent.

Every number is computed here; nothing is a model's estimate. Bounded: at most
RULE_COLUMNS categories are mined and the text is capped at MAX_CHARS.
"""
from __future__ import annotations

import pandas as pd

MAX_CHARS = 3500
#: A category explains "a real share" of a measure at or above this eta-squared.
REAL_EFFECT = 0.05
#: ...and is FLAT below this (and within 2% of the mean, see readback).
FLAT_EFFECT = 0.005
#: Group medians this many times apart mean the groups are measured in
#: different units (data bytes against call seconds), not that one is bigger.
MIXED_UNITS_RATIO = 1000


def mixed_units(df: pd.DataFrame, nums: list[str], cats: list[str], card: dict) -> dict:
    """{measure: {"by", "high", "high_median", "low", "low_median"}} for each
    measure whose typical value differs by MIXED_UNITS_RATIO or more between
    the values of one category.

    The call-records panel (2026-10-02) summed ROUNDED_VOLUME across services:
    GPRS sessions in bytes beside voice calls in seconds, so "GPRS carries
    100% of the volume". Such a measure can be compared within one value of
    that category, never added up across them."""
    out: dict = {}
    for m in nums:
        v = pd.to_numeric(df[m], errors="coerce")
        for c in cats:
            if not 2 <= card.get(c, 0) <= 30:
                continue
            pos = v[v > 0]
            if len(pos) < 20:
                break
            g = pos.groupby(df.loc[pos.index, c].astype(str))
            med = g.median()[g.size() >= max(5, int(len(pos) * 0.01))]
            if len(med) < 2 or med.min() <= 0:
                continue
            if med.max() / med.min() >= MIXED_UNITS_RATIO:
                common = df[c].astype(str).value_counts()
                out[m] = {"by": c, "high": str(med.idxmax()), "high_median": float(med.max()),
                          "low": str(med.idxmin()), "low_median": float(med.min()),
                          "common": str(common.index[0]) if len(common) else None}
                break
    return out


def one_to_one(df: pd.DataFrame, columns: list[str], max_values: int = 50) -> dict:
    """{column: [columns it pairs with one-to-one]} among low-cardinality
    columns of any type: each value of one always comes with the same value of
    the other, and back.

    Enrolments (2026-10-02): every faculty has one tuition fee, so the panel
    offered faculty-by-fee treemaps and "Faculty > Fee" rings -- one breakdown
    under two names. A city inside a country is NOT one-to-one (a country has
    many cities) and stays a legitimate nesting."""
    cols = []
    for c in columns:
        try:
            k = int(df[c].nunique(dropna=True))
        except Exception:                                    # noqa: BLE001
            continue
        if 2 <= k <= max_values:
            cols.append(c)
    out: dict = {}
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            sub = df[[a, b]].dropna()
            if len(sub) < 20:
                continue
            if sub.groupby(a)[b].nunique().max() == 1 and sub.groupby(b)[a].nunique().max() == 1:
                out.setdefault(a, []).append(b)
                out.setdefault(b, []).append(a)
    return out


def identical_columns(df: pd.DataFrame, columns: list[str]) -> dict:
    """{column: [columns holding the same value on (almost) every row]}.

    Daily ops (2026-10-02): unique_customers equalled total_orders on all 616
    days, and both engines drew "Orders vs Customers" -- one line twice --
    and correlated the pair at 1.0."""
    nums = [c for c in columns if pd.api.types.is_numeric_dtype(df[c])]
    out: dict = {}
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            both = df[[a, b]].dropna()
            if len(both) >= 20 and (both[a] == both[b]).mean() >= 0.999:
                out.setdefault(a, []).append(b)
                out.setdefault(b, []).append(a)
    return out


#: A leading or trailing period with fewer rows than this share of the
#: typical period is a stub (a test month, an extract cut off mid-period).
STUB_SHARE = 0.10


def edge_periods(df: pd.DataFrame, date_cols: list[str]) -> dict:
    """{date column: {grain: {"from": ISO, "before": ISO}}} -- the span of
    whole, representative periods for each time grain.

    Five-dataset review (2026-10-02): every monthly trend opened on Olist's
    2016 test months ("late deliveries fall from 100% in 2016-09") or closed on
    a cut-off month, and the HR hire trend ended on a year 2000 with 9 hires.
    The analysts trimmed both ends. A period is trimmed from an end when it is
    partial (the data starts after or stops before its edges) or a stub (under
    STUB_SHARE of the median period's rows); trimming stops at the first whole
    period, so a real dip in the middle is never touched."""
    out: dict = {}
    for c in date_cols:
        d = pd.to_datetime(df[c], errors="coerce").dropna()
        if len(d) < 50 or d.dt.normalize().nunique() < 20:
            continue
        lo, hi = d.min().normalize(), d.max().normalize()
        spans = {}
        for grain, freq in (("week", "W"), ("month", "M"), ("quarter", "Q"), ("year", "Y")):
            per = d.dt.to_period(freq)
            counts = per.value_counts().sort_index()
            if len(counts) < 4:
                continue
            full = counts.reindex(pd.period_range(counts.index.min(), counts.index.max(), freq=freq), fill_value=0)
            keep = list(full.index)

            def bad(p, inner) -> bool:
                # Partial: the data starts after, or stops before, the period's
                # edge by more than a tenth of it (enrolments ending 29 Dec is
                # a whole December).
                slack = (p.end_time - p.start_time) * 0.1
                partial = p.start_time < lo - slack or p.end_time > hi + slack + pd.Timedelta(days=1)
                # A stub: far smaller than the periods next to it -- an abrupt
                # edge, not a trend that tails off (hires per year falling is
                # the data; 9 hires in 2000 is where the extract stops).
                near = full[inner].median() if len(inner) else 0
                return partial or (near > 0 and full[p] < STUB_SHARE * near)
            while len(keep) > 3 and bad(keep[0], keep[1:4]):
                keep.pop(0)
            while len(keep) > 3 and bad(keep[-1], keep[-4:-1]):
                keep.pop()
            # A run cut off from the bulk by an empty or stub period (Olist's
            # 2016 test months: 363 orders, then 0, then 1) goes too -- but
            # only within the outer quarter of the span.
            if len(keep) > 8:
                typical = full[keep].median()
                quarter = max(1, len(keep) // 4)
                def gap(i: int, inward: int) -> bool:
                    # Small overall AND a cliff against its inner neighbour:
                    # hires falling year on year to 1,204 is a trend; 9 after
                    # 1,204, or 1 before 955, is where the data breaks.
                    q, n = keep[i], keep[i + inward] if 0 <= i + inward < len(keep) else None
                    small = full[q] < STUB_SHARE * typical
                    cliff = n is None or full[q] == 0 or full[q] < STUB_SHARE * full[n]
                    return small and cliff
                head = [i for i in range(quarter) if gap(i, 1)]
                if head:
                    keep = keep[head[-1] + 1:]
                n0 = len(keep)
                tail = [i for i in range(n0 - quarter, n0) if gap(i, -1)]
                if tail:
                    keep = keep[:tail[0]]
            if len(keep) < 3 or (keep[0] == full.index[0] and keep[-1] == full.index[-1]):
                continue
            spans[grain] = {"from": keep[0].start_time.strftime("%Y-%m-%d"),
                            "before": (keep[-1] + 1).start_time.strftime("%Y-%m-%d")}
        if spans:
            out[c] = spans
    return out


def quality_findings(df: pd.DataFrame, cats: list[str], limit: int = 6) -> list[dict]:
    """The data's own faults, worst first, as {kind, text, column, values}.

    Call records (2026-10-02): 104 exact duplicate rows, " Catch All Zone"
    with a leading space, and "Mobile to Mobile" / "Mobile To Mobile" as two
    destinations -- the analysts flagged all three, the platform none. Read
    by the analysts' lenses (to avoid splitting by a broken label), shown to
    the person beside the facts, and drawn on a "Data quality" page."""
    from .suggest_variety import _h
    out: list[dict] = []
    try:
        dups = int(df.duplicated().sum())
    except TypeError:
        dups = 0
    if dups:
        out.append({"kind": "duplicates", "column": None, "values": [], "count": dups,
                    "text": f"{dups:,} rows are exact duplicates of another row ({dups / len(df):.1%}); "
                            f"totals count them twice."})
    for c in cats:
        vals = df[c].dropna().astype(str)
        if vals.empty or vals.nunique() > 200:
            continue
        uniq = vals.unique()
        padded = [v for v in uniq if v != v.strip()]
        if padded:
            out.append({"kind": "spaces", "column": c, "values": [str(v) for v in padded[:3]],
                        "text": f"{_h(c)} has values with stray spaces "
                                f"({', '.join(repr(v) for v in padded[:3])})."})
        groups: dict = {}
        for v in uniq:
            groups.setdefault(" ".join(v.strip().lower().split()), []).append(v)
        same = [g for g in groups.values() if len(g) > 1]
        if same:
            out.append({"kind": "variants", "column": c,
                        "values": [str(v) for g in same[:2] for v in g[:3]],
                        "text": f"{_h(c)} spells one value several ways: " +
                                "; ".join(" / ".join(repr(v) for v in g[:3]) for g in same[:2]) +
                                " -- they are split into separate groups."})
    for c in df.columns:
        miss = float(df[c].isna().mean())
        if 0.2 <= miss < 1:
            out.append({"kind": "missing", "column": c, "values": [], "share": round(miss, 4),
                        "text": f"{_h(c)} is missing on {miss:.0%} of rows; charts of it describe the rest only."})
    return out[:limit]


def quality_issues(df: pd.DataFrame, cats: list[str], limit: int = 6) -> list[str]:
    """Plain sentences about the data's own faults, worst first."""
    return [f["text"] for f in quality_findings(df, cats, limit)]


def _fmt(v: float) -> str:
    from .readback import _num
    return _num(v)


def build_facts(df: pd.DataFrame | None, roles: dict[str, str],
                column_meta: dict | None = None,
                ineligible: set[str] | None = None) -> dict:
    from .suggest_variety import _cramers_v, _eta2, _h, _Profile
    if df is None or len(df) < 20:
        return {"facts": [], "text": ""}
    p = _Profile(df, roles, column_meta, ineligible)
    facts: list[dict] = []

    def add(kind: str, text: str, columns: list[str], strength: float = 0.0) -> None:
        facts.append({"kind": kind, "text": text, "columns": columns, "strength": round(strength, 4)})

    mixed = mixed_units(df, p.nums, p.cats, p.card)
    n = len(df)
    who = f"{n:,} rows" + (f", one per {_h(p.id_col)}" if p.id_col else "")
    add("overview", who + ".", [p.id_col] if p.id_col else [])

    # ── columns that are one fact twice: never split by both ─────────────────
    blocked = {c.casefold() for c in (ineligible or set())}
    visible = [c for c in df.columns if c != p.id_col and str(c).casefold() not in blocked]
    pairs = one_to_one(df, visible)
    # Not stated as a fact: the measures pool already drops a copy
    # (insights.drop_duplicate_measures), and naming it would put it back in
    # the prompt. The gate uses the pairs (analyst_panel.same_number_twice).
    twins = identical_columns(df, visible)
    done: set[frozenset] = set()
    for a, bs in pairs.items():
        for b in bs:
            if frozenset((a, b)) in done:
                continue
            done.add(frozenset((a, b)))
            add("same", f"{_h(a)} and {_h(b)} always go together (each {_h(a)} has one {_h(b)}): they are "
                        f"one breakdown, so use one of them, never both as a split.", [a, b], 1.0)

    # ── measures on different scales per group: never added across them ─────
    for m, u in mixed.items():
        # Name what stays free: told only "volume is in different units by
        # service", the call-records panel stopped splitting ANYTHING by
        # service -- revenue by service per month went missing in every run.
        free = [x for x in p.nums if x not in mixed][:3]
        also = (f" Other measures ({', '.join(_h(x) for x in free)}) are one unit throughout: split and "
                f"total them by {_h(u['by'])} freely." if free else "")
        add("units", f"{_h(m)} is on different scales by {_h(u['by'])} (median {_fmt(u['high_median'])} "
                     f"for {u['high']}, {_fmt(u['low_median'])} for {u['low']}): almost certainly different "
                     f"units. Show it for one {_h(u['by'])} at a time, with a filter; never total, average "
                     f"or set it side by side across {_h(u['by'])} values. Counting rows is fine." + also,
            [m, u["by"]], 1.0)

    # ── the data's own faults ───────────────────────────────────────────────
    quality = quality_findings(df, list(p.cats))
    for q in quality:
        add("quality", q["text"], [], 0.9)

    # ── measures ────────────────────────────────────────────────────────────
    for m in p.nums[:3]:
        v = pd.to_numeric(df[m], errors="coerce").dropna()
        if len(v) < 20:
            continue
        q = v.quantile([0.1, 0.5, 0.9])
        skew = " (right-skewed: mean above median)" if v.mean() > q[0.5] * 1.02 else ""
        add("measure", f"{_h(m)}: median {_fmt(q[0.5])}, mean {_fmt(v.mean())}, "
                       f"p10 {_fmt(q[0.1])}, p90 {_fmt(q[0.9])}, range {_fmt(v.min())}–{_fmt(v.max())}{skew}.", [m])

    # ── a measure by each category: who is high, who is low, does it matter ──
    if p.nums:
        m = p.nums[0]
        summ = p.summary[m]
        word = {"avg": "average", "median": "median", "sum": "total"}[summ]
        for c in p.cats:
            if not 2 <= p.card[c] <= 30:
                continue
            e = _eta2(df[m], df[c])
            g = pd.to_numeric(df[m], errors="coerce").groupby(df[c].astype(str))
            vals = (g.median() if summ == "median" else g.mean()).dropna().sort_values()
            if len(vals) < 2:
                continue
            spread = (vals.iloc[-1] - vals.iloc[0]) / abs(vals.mean()) if vals.mean() else 0
            if e < FLAT_EFFECT and spread < 0.02:
                add("flat", f"{word.capitalize()} {_h(m)} is the same for every {_h(c)} "
                            f"({_fmt(vals.iloc[0])}–{_fmt(vals.iloc[-1])}); {_h(c)} explains {e:.1%} of it.",
                    [m, c], 0.0)
            else:
                add("groups", f"{word.capitalize()} {_h(m)} by {_h(c)}: highest {vals.index[-1]} "
                              f"{_fmt(vals.iloc[-1])}, lowest {vals.index[0]} {_fmt(vals.iloc[0])}; "
                              f"{_h(c)} explains {e:.0%} of the variation.", [m, c], e)

    # ── shares: how the rows split, and whether a small split is uniform ────
    for c in p.cats:
        if not 2 <= p.card[c] <= 30:
            continue
        sh = df[c].astype(str).value_counts(normalize=True)
        top = ", ".join(f"{k} {v:.0%}" for k, v in sh.head(3).items())
        add("shares", f"{_h(c)} ({p.card[c]} values): {top}" + (", …" if len(sh) > 3 else ".") , [c],
            float(sh.iloc[0]))
    small = [c for c in p.cats if 2 <= p.card[c] <= 4]
    for s in small:
        lead = df[s].astype(str).value_counts().index[-1]          # the minority value
        for c in p.cats:
            if c == s or not 3 <= p.card[c] <= 30:
                continue
            share = (df[s].astype(str) == lead).groupby(df[c].astype(str)).mean()
            if len(share) >= 3 and share.max() - share.min() < 0.03:
                add("flat", f"{_h(s)} = {lead} is {share.min():.1%}–{share.max():.1%} in every {_h(c)}: "
                            f"the {_h(s)} mix does not differ by {_h(c)}.", [s, c], 0.0)

    # ── time ────────────────────────────────────────────────────────────────
    if p.dates:
        d = p.dates[0]
        dt = pd.to_datetime(df[d], errors="coerce")
        if dt.notna().sum() >= 20 and (dt.max() - dt.min()).days >= 2 * 365:
            per = dt.dt.year.value_counts().sort_index()
            peak = per.idxmax()
            add("trend", f"Rows per year of {_h(d)}: {per.index[0]} {per.iloc[0]:,} → peak {peak} "
                         f"{per.max():,} → {per.index[-1]} {per.iloc[-1]:,} "
                         f"({dt.min():%Y-%m-%d} to {dt.max():%Y-%m-%d}).", [d], 0.5)
            if p.nums:
                m = p.nums[0]
                by = pd.to_numeric(df[m], errors="coerce").groupby(dt.dt.year).mean().dropna()
                if len(by) >= 2:
                    add("trend", f"Average {_h(m)} by year of {_h(d)}: {by.index[0]} {_fmt(by.iloc[0])} → "
                                 f"{by.index[-1]} {_fmt(by.iloc[-1])}.", [m, d], 0.5)
            year = dt.dt.year
            for c in p.cats:
                if 3 <= p.card[c] <= 12:
                    v = _cramers_v(df[c].astype(str)[year.notna()], year[year.notna()])
                    if v >= 0.1:
                        add("mix_over_time", f"The {_h(c)} mix changes over {_h(d)} (Cramér's V {v:.2f}).",
                            [c, d], v)
                    else:
                        add("flat", f"The {_h(c)} mix is stable across years of {_h(d)} (Cramér's V {v:.2f}).",
                            [c, d], 0.0)

    # ── links between categories ────────────────────────────────────────────
    from .suggest_variety import RULE_COLUMNS
    cats = sorted([c for c in p.cats if p.card[c] <= 30], key=lambda c: p.card[c])[:RULE_COLUMNS]
    if len(cats) >= 2:
        try:
            from .analysis.patterns import association_rules
            rules = association_rules(df[cats].astype(object).where(df[cats].notna()), cats).to_dict()["rows"]
        except Exception:                                    # noqa: BLE001
            rules = []
        seen: set[frozenset] = set()
        for r in rules:
            cols = frozenset(c for c, _ in r.get("if_items", []) + r.get("then_items", []))
            if len(cols) != 2 or cols in seen:
                continue
            seen.add(cols)
            add("link", f"{r['if']} → {r['then']}: {r['confidence']:.0%} vs {r['base_rate']:.0%} overall "
                        f"({r['lift']:.1f}×).", sorted(cols), r["lift"])
            if len(seen) >= 4:
                break
        for i, a in enumerate(cats):
            for b in cats[i + 1:]:
                if frozenset((a, b)) in seen:
                    continue
                if _cramers_v(df[a].astype(str), df[b].astype(str)) < 0.05:
                    add("independent", f"{_h(a)} and {_h(b)} are independent: a mix of one by the other "
                                       f"would show the same split everywhere.", [a, b], 0.0)

    lines, size = [], 0
    for f in facts:
        line = f"- {f['text']}"
        if size + len(line) > MAX_CHARS:
            break
        lines.append(line)
        size += len(line) + 1
    edges = edge_periods(df, list(p.dates))
    return {"facts": facts, "text": "\n".join(lines), "mixed_units": mixed, "one_to_one": pairs,
            "identical": twins, "edges": edges, "quality": quality}
