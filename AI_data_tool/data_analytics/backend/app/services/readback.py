"""What a drawn widget actually says, in one sentence, from its own numbers.

A suggestion used to carry the sentence it was PROPOSED with: the model's
expectation ("shows the gender pay gap by title") or a finding's text. The HR
analyst panel (2026-10-02) drew 80 proposals on live data and had to correct
seven of their takeaways against what the charts returned -- an "expected
gap" that was 0.1%, a cohort effect that held for some titles and not others.

`takeaway(widget_type, config, result)` reads the SHAPED result -- the same
payload the browser draws -- and states what it shows: the largest and the
smallest, the first and the last, the winner and by how much. Nothing is
inferred that the numbers do not say, and a comparison whose values are all
within `FLAT_SPREAD` of each other is said to be flat, because "no difference"
is a finding too and the one a reader most often misses.

Every function returns None rather than guessing when the result is a shape it
does not know; a missing sentence is better than a wrong one.
"""
from __future__ import annotations

import math
import re
from typing import Any

#: Values within this share of their mean are "essentially the same".
FLAT_SPREAD = 0.02


class Said(str):
    """A sentence that also knows how to be said in another language.

    It IS the English string (every caller that wanted a str still gets one);
    `key` names the sentence and `vars` holds the pieces that go into it --
    numbers already formatted, names as drawn, and nested phrases ("average
    salary") as Said values of their own. `as_i18n()` is what the browser
    renders with its own catalogue (`rb.<key>`), so a reader in Arabic reads
    the same finding in Arabic (2026-10-02)."""
    key: str
    vars: dict

    def as_i18n(self) -> dict:
        return {"key": self.key,
                "vars": {k: (v.as_i18n() if isinstance(v, Said) else str(v)) for k, v in self.vars.items()}}


def _s(key: str, template: str, cap: bool = True, **vars) -> Said:
    """English `template` filled with `vars`; the first letter capitalised
    unless the sentence is a piece of another (`cap=False`)."""
    text = template.format(**{k: str(v) for k, v in vars.items()})
    out = Said(text[:1].upper() + text[1:] if text and cap else text)
    out.key, out.vars = key, vars
    return out


def as_i18n(text) -> dict | None:
    return text.as_i18n() if isinstance(text, Said) else None

_AGG_WORD = {"sum": "total", "avg": "average", "mean": "average", "median": "median",
             "min": "lowest", "max": "highest", "count": "number of rows",
             "countd": "count", "cv": "spread (CV%)", "std": "spread"}


def _h(col: Any) -> str:
    return " ".join(str(col).replace("_", " ").split())


def _num(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f):
        return "—"
    a = abs(f)
    if a >= 1e15:
        return f"{f:.2e}"
    if a >= 1e12:
        return f"{f / 1e12:,.2f}T"
    if a >= 1e9:
        return f"{f / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{f / 1e6:,.2f}M"
    if a >= 100:
        return f"{f:,.0f}"
    if a >= 1:
        return f"{f:,.1f}".rstrip("0").rstrip(".")
    return f"{f:.3g}"


def _pct(v) -> str:
    """A share; one decimal near the ends, where 99.6% vs 99.7% is the point."""
    f = float(v)
    return f"{f:.1%}" if f >= 0.95 or f <= 0.05 else f"{f:.0%}"


def _is_num(v: Any) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return not math.isnan(f) and not math.isinf(f)


def _agg(agg: str) -> Said:
    word = _AGG_WORD.get(agg, agg)
    out = Said(word)
    out.key, out.vars = (f"agg.{agg}" if agg in _AGG_WORD else "agg.other"), {"agg": agg}
    return out


def _what(config: dict) -> Said:
    """'average salary', 'headcount', 'number of rows' -- lower case, a phrase."""
    m = config.get("measure") or (config.get("roles") or {}).get("measure")
    agg = str(config.get("aggregation") or ("sum" if m else "count")).lower()

    def phrase(key, text, **v):
        out = Said(text)
        out.key, out.vars = key, v
        return out
    if not m or agg in ("count", "frequency"):
        return phrase("what.rows", "number of rows")
    if agg == "countd":
        from .insights import _PERSON_ID
        if any(k in str(m).lower() for k in _PERSON_ID):
            return phrase("what.headcount", "headcount")
        # "student_id" counts students: "number of students", not "distinct
        # student id" (enrolments panel, 2026-10-02).
        stem = re.sub(r"[_ ]?(id|no|num|number|code|key|ref)$", "", str(m), flags=re.I).strip("_ ")
        if stem and stem.lower() != str(m).lower():
            noun = _h(stem) + ("" if _h(stem).endswith("s") else "s")
            return phrase("what.countOf", f"number of {noun}", m=noun)
        return phrase("what.distinct", f"distinct {_h(m)}", m=_h(m))
    # A derived rate measure (derived_fields) computes its own roll-up: its
    # aggregation is ignored, so no word is put in front of it.
    if re.search(r"_pct_of_|^late_pct_vs_", str(m)):
        return phrase("what.plain", _h(m), m=_h(m))
    # A column already named for its roll-up ("total_orders", "avg_price")
    # is not said twice: "total total orders" (daily-ops panel).
    word = _AGG_WORD.get(agg, agg)
    first = _h(m).lower().split(" ")[0]
    same = {"sum": ("total", "sum"), "avg": ("avg", "mean", "average"), "mean": ("avg", "mean", "average"),
            "median": ("median",), "min": ("min", "lowest"), "max": ("max", "highest")}.get(agg, ())
    if first in same:
        return phrase("what.plain", _h(m), m=_h(m))
    return phrase("what.agg", f"{word} {_h(m)}", agg=_agg(agg), m=_h(m))


def _additive(config: dict) -> bool:
    return str(config.get("aggregation") or "sum").lower() in ("sum", "count", "countd")


def _flat(values: list[float]) -> bool:
    vals = [v for v in values if _is_num(v)]
    if len(vals) < 2:
        return False
    mean = sum(vals) / len(vals)
    return bool(mean) and (max(vals) - min(vals)) / abs(mean) < FLAT_SPREAD


def _is_time(config: dict, rows: list[dict]) -> bool:
    if config.get("dimension_granularity") or any("bin_start" in r for r in rows[:1]):
        return True
    # Raw dates on the axis (no grain): ISO strings. Ranking them as categories
    # read "1985-01-20T00:00:00 leads with 100" on the live HR panel.
    names = [r.get("name") for r in rows[:5]]
    return bool(names) and all(isinstance(n, str) and len(n) >= 10 and n[4] == "-" and n[7] == "-"
                               and n[:4].isdigit() for n in names)


def _label(v: Any) -> Any:
    """A whole-number float label is a year or a count: 1985.0 reads as 1985;
    an ISO timestamp reads as its date."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and len(v) > 10 and v[4:5] == "-" and v[10:11] == "T":
        return v[:10]
    return v


def _series(widget_type: str, config: dict, rows: list[dict]) -> str | None:
    pts = [(_label(r.get("name")), r.get("value")) for r in rows if _is_num(r.get("value"))]
    if not pts:
        return None
    what = _what(config)
    dim = _h(config.get("dimension") or "")
    if widget_type == "histogram":
        peak_row = max((r for r in rows if _is_num(r.get("value"))), key=lambda r: float(r["value"]))
        where = (f"{_num(peak_row['bin_start'])}–{_num(peak_row['bin_end'])}"
                 if _is_num(peak_row.get("bin_start")) and _is_num(peak_row.get("bin_end"))
                 else str(peak_row.get("name")))
        return _s("hist", "the most common range is {range} ({n} rows).", range=where, n=_num(peak_row["value"]))
    if _is_time(config, rows):
        first, last = pts[0], pts[-1]
        peak = max(pts, key=lambda p: float(p[1]))
        if _flat([p[1] for p in pts]):
            return _s("time.flat", "{what} stays about {v} from {a} to {b}.",
                      what=what, v=_num(first[1]), a=first[0], b=last[0])
        trend = "rises" if float(last[1]) > float(first[1]) else "falls"
        parts = dict(what=what, v1=_num(first[1]), a=first[0], v2=_num(last[1]), b=last[0])
        if peak not in (first, last):
            return _s(f"time.{trend}Peak", "{what} " + trend + " from {v1} ({a}) to {v2} ({b}), "
                      "peaking at {p} in {c}.", p=_num(peak[1]), c=peak[0], **parts)
        return _s(f"time.{trend}", "{what} " + trend + " from {v1} ({a}) to {v2} ({b}).", **parts)
    ranked = sorted(pts, key=lambda p: float(p[1]), reverse=True)
    top, bottom = ranked[0], ranked[-1]
    if len(ranked) == 1:
        return _s("one", "{name}: {v}.", name=top[0], v=_num(top[1]))
    if _flat([p[1] for p in pts]):
        if dim:
            return _s("flat", "{what} is essentially the same for every {dim} ({lo}–{hi}).",
                      what=what, dim=dim, lo=_num(bottom[1]), hi=_num(top[1]))
        return _s("flatGroups", "{what} is essentially the same for every group ({lo}–{hi}).",
                  what=what, lo=_num(bottom[1]), hi=_num(top[1]))
    if _additive(config) and len(pts) == 2:
        total = sum(float(p[1]) for p in pts)
        return _s("two", "{a} {pa}, {b} {pb}.", a=top[0], pa=f"{float(top[1]) / total:.0%}",
                  b=bottom[0], pb=f"{float(bottom[1]) / total:.0%}")
    if _additive(config):
        total = sum(float(p[1]) for p in pts)
        share = float(top[1]) / total if total else 0
        return _s("leads", "{top} leads with {v} ({share} of the total); {bottom} has the fewest at {vb}.",
                  top=top[0], v=_num(top[1]), share=f"{share:.0%}", bottom=bottom[0], vb=_num(bottom[1]))
    return _s("highest", "{top} is highest at {v} and {bottom} lowest at {vb} ({what}).",
              top=top[0], v=_num(top[1]), bottom=bottom[0], vb=_num(bottom[1]), what=_what(config))


def _card(config: dict, rows: list[dict]) -> Said | None:
    """Each figure on a card, named by how it is rolled up: "average price 121;
    average freight value 20" -- not a ranking of unlike numbers."""
    items = [r for r in rows if _is_num(r.get("value"))]
    if not items:
        return None
    agg = str(config.get("aggregation") or "sum").lower()
    pieces = {f"i{n}": _s("cardItem", "{what} {v}", cap=False, what=_what({"measure": r.get("name"), "aggregation": agg}),
                          v=_num(r["value"]))
              for n, r in enumerate(items[:4])}
    template = "; ".join("{%s}" % k for k in pieces) + "."
    return _s(f"card{len(pieces)}", template, **pieces)


def _xy(config: dict, rows: list[dict]) -> Said | None:
    """Two measures row by row: how closely one moves with the other."""
    pts = [(float(r["x"]), float(r["y"])) for r in rows if _is_num(r.get("x")) and _is_num(r.get("y"))]
    if len(pts) < 10:
        return None
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxy = sum((a - mx) * (b - my) for a, b in pts)
    sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pts))
    sy = math.sqrt(sum((b - my) ** 2 for _, b in pts))
    if not sx or not sy:
        return None
    r = sxy / (sx * sy)
    x, y = _h(config.get("measure")), _h(config.get("measure2"))
    if abs(r) < 0.1:
        return _s("xy.none", "{x} and {y} do not move together (r = {r}).", x=x, y=y, r=f"{r:.2f}")
    key = "xy.up" if r > 0 else "xy.down"
    word = "rises" if r > 0 else "falls"
    return _s(key, "as {x} rises, {y} " + word + " (r = {r}, {n} rows).", x=x, y=y, r=f"{r:.2f}", n=f"{n:,}")


def _cramers_v(table: list[list[float]]) -> float:
    rows = [r for r in table if sum(r)]
    if len(rows) < 2 or len(rows[0]) < 2:
        return 0.0
    col_tot = [sum(c) for c in zip(*rows)]
    n = sum(col_tot)
    if not n:
        return 0.0
    chi2 = 0.0
    for r in rows:
        rt = sum(r)
        for v, ct in zip(r, col_tot):
            e = rt * ct / n
            if e:
                chi2 += (v - e) ** 2 / e
    k = min(len(rows), len([c for c in col_tot if c])) - 1
    return math.sqrt(chi2 / (n * k)) if k > 0 else 0.0


def _crosstab(config: dict, result: dict) -> str | None:
    """Bars split by a second column: is the split the same in every bar?"""
    cols = result.get("columns") or []
    rows = result.get("rows") or []
    if len(cols) < 3 or not rows:
        return None
    series = [c for c in cols[1:] if str(c) not in ("__total__", "Total")]
    d1, d2 = _h(config.get("dimension")), _h(config.get("dimension2"))
    mode = config.get("bar_mode")
    if mode == "stacked100" or (_additive(config) and mode in (None, "stacked")):
        # Each series' share of each bar; the mix is judged by the series
        # whose share varies MOST. Judging by the first series called a
        # department x title mix "the same everywhere" because Assistant
        # Engineer was 0-3% in every bar, while Senior Engineer ran 0-63%.
        per_series: dict[str, list] = {str(sname): [] for sname in series}
        for r in rows:
            vals = [float(v) if _is_num(v) else 0.0 for v in r[1:1 + len(series)]]
            tot = sum(vals)
            if not tot:
                continue
            for sname, v in zip(series, vals):
                per_series[str(sname)].append((r[0], v / tot))
        spreads = [(sname, min(sh, key=lambda x: x[1]), max(sh, key=lambda x: x[1]))
                   for sname, sh in per_series.items() if sh]
        if not spreads:
            return None
        sname, lo, hi = max(spreads, key=lambda t: t[2][1] - t[1][1])
        # Counts carry their own noise: 750 people per bar move a 40% share by
        # ~4 points by chance alone. With counts, "the same" is judged by the
        # strength of the association (Cramer's V), which allows for size.
        counted = str(config.get("aggregation") or "").lower() in ("count", "countd", "frequency")
        if counted:
            table = [[float(v) if _is_num(v) else 0.0 for v in r[1:1 + len(series)]] for r in rows]
            same = _cramers_v(table) < 0.05
        else:
            same = hi[1] - lo[1] < 0.03
        if same:
            # State the range itself: "moves no more than 6%" read as a contradiction
            # beside "the same" when the call came from the association strength.
            return _s("mix.same", "the {d2} mix is about the same in every {d1}: {s} is {lo}–{hi} "
                      "of each, with no real link between them.",
                      d2=d2, d1=d1, s=sname, lo=f"{lo[1]:.0%}", hi=f"{hi[1]:.0%}")
        return _s("mix.differs", "the {d2} mix differs by {d1}: {s} is {hi} of {a} but {lo} of {b}.",
                  d2=d2, d1=d1, s=sname, hi=f"{hi[1]:.0%}", a=hi[0], lo=f"{lo[1]:.0%}", b=lo[0])
    # Side by side (an average per pair): the gap between the series in each bar.
    gaps = []
    for r in rows:
        vals = [v for v in r[1:1 + len(series)] if _is_num(v)]
        if len(vals) >= 2 and float(vals[0]):
            gaps.append((r[0], (float(vals[1]) - float(vals[0])) / abs(float(vals[0]))))
    if not gaps:
        return None
    widest = max(gaps, key=lambda g: abs(g[1]))
    if abs(widest[1]) < FLAT_SPREAD:
        return _s("gap.none", "no real difference between {a} and {b} in any {d1}: "
                  "the widest gap is {g} ({w}).", a=series[0], b=series[1], d1=d1,
                  g=f"{abs(widest[1]):.1%}", w=widest[0])
    # How many groups show no gap comes first: one tiny group (9 managers)
    # with a 4.6% gap must not read as the headline of a flat comparison.
    close = sum(1 for g in gaps if abs(g[1]) < FLAT_SPREAD)
    if close:
        return _s("gap.mostly", "{a} and {b} differ by under {f} in {close} of {n} {d1} values; "
                  "the widest gap is in {w}: {g}.", a=series[0], b=series[1], f=f"{FLAT_SPREAD:.0%}",
                  close=close, n=len(gaps), d1=d1, w=widest[0], g=f"{abs(widest[1]):.1%}")
    return _s("gap.widest", "the widest gap is in {w}: {g}.", w=widest[0], g=f"{abs(widest[1]):.1%}")


def _over_represented(table: list[list[float]], min_cell: float = 30) -> tuple | None:
    """(row, col, observed/expected) of the most over-represented cell with at
    least `min_cell` rows -- a 1-row cell at 5x is noise, not a finding."""
    total = sum(map(sum, table))
    if not total:
        return None
    rt = [sum(r) for r in table]
    ct = [sum(r[j] for r in table if j < len(r)) for j in range(max(map(len, table)))]
    best = None
    for i, r in enumerate(table):
        for j, v in enumerate(r):
            exp = rt[i] * ct[j] / total
            if v >= min_cell and exp:
                ratio = v / exp
                if best is None or ratio > best[2]:
                    best = (i, j, ratio)
    return best if best and best[2] >= 1.2 else None


def _heatmap(config: dict, result: dict) -> str | None:
    rows, cols, cells = result.get("rows_axis") or [], result.get("cols_axis") or [], result.get("cells") or []
    found = [(rows[i], cols[j], v) for i, line in enumerate(cells) for j, v in enumerate(line or [])
             if i < len(rows) and j < len(cols) and _is_num(v)]
    if not found:
        return None
    counted = str(config.get("aggregation") or "").lower() in ("count", "countd", "frequency")
    if counted and len(rows) >= 2 and len(cols) >= 2:
        # A count grid's biggest cell is mostly the biggest row times the
        # biggest column: "Development × M" headlined a gender grid in which
        # gender is independent of department (live HR panel, 2026-10-02).
        # So it is read for the LINK: none, or the most over-represented pair.
        table = [[float(v) if _is_num(v) else 0.0 for v in (line or [])][:len(cols)] for line in cells[:len(rows)]]
        d1, d2 = _h(config.get("dimension") or "rows"), _h(config.get("dimension2") or "columns")
        if _cramers_v(table) < 0.05:
            total = sum(map(sum, table)) or 1
            col_tot = [sum(r[j] for r in table if j < len(r)) for j in range(len(cols))]
            minor = min(range(len(cols)), key=lambda j: col_tot[j])
            shares = [r[minor] / sum(r) for r in table if sum(r)]
            return _s("grid.independent", "{d2} does not depend on {d1}: {c} is {lo}–{hi} in every "
                      "{d1} ({all} overall).", d2=d2, d1=d1, c=cols[minor], lo=f"{min(shares):.0%}",
                      hi=f"{max(shares):.0%}", all=f"{col_tot[minor] / total:.0%}")
        lift = _over_represented(table)
        if lift:
            i, j, ratio = lift
            big = max(found, key=lambda c: float(c[2]))
            return _s("grid.lift", "{r} × {c} is {x}× as common as the two would be by chance; "
                      "the largest cell is {br} × {bc}.", r=rows[i], c=cols[j], x=f"{ratio:.1f}",
                      br=big[0], bc=big[1])
    hi = max(found, key=lambda c: float(c[2]))
    # An empty combination (a count of 0) is an absence, not the "lowest".
    present = [c for c in found if float(c[2]) != 0] if _additive(config) else found
    lo = min(present or found, key=lambda c: float(c[2]))
    return _s("grid.range", "highest: {hr} × {hc} at {hv}; lowest: {lr} × {lc} at {lv} ({what}).",
              hr=hi[0], hc=hi[1], hv=_num(hi[2]), lr=lo[0], lc=lo[1], lv=_num(lo[2]), what=_what(config))


def _box(config: dict, rows: list[dict]) -> str | None:
    meds = [(r.get("name"), r.get("median")) for r in rows if _is_num(r.get("median"))]
    if len(meds) < 2:
        return None
    hi = max(meds, key=lambda m: float(m[1]))
    lo = min(meds, key=lambda m: float(m[1]))
    m = _h(config.get("measure"))
    if _flat([v[1] for v in meds]):
        return _s("box.flat", "median {m} is about the same in every group ({lo}–{hi}).",
                  m=m, lo=_num(lo[1]), hi=_num(hi[1]))
    return _s("box.range", "median {m} runs from {lo} ({a}) to {hi} ({b}).",
              m=m, lo=_num(lo[1]), a=lo[0], hi=_num(hi[1]), b=hi[0])


def _bubble(config: dict, rows: list[dict], derived: dict | None = None) -> str | None:
    pts = [r for r in rows if _is_num(r.get("x")) and _is_num(r.get("y"))]
    if len(pts) < 2:
        return None
    big = max(pts, key=lambda r: float(r.get("size") or 0))
    hx = max(pts, key=lambda r: float(r["x"]))
    hy = max(pts, key=lambda r: float(r["y"]))
    derived = derived or {}
    def name(c):
        if c in derived:
            out = Said(f"years since {_h(c)}")
            out.key, out.vars = "yearsSince", {"m": _h(c)}
            return out
        return _h(c)
    x, y = name(config.get("measure")), name(config.get("measure2"))
    return _s("bubble", "{big} is the largest ({s}); {hx} is highest on {x} ({vx}) and {hy} on {y} ({vy}).",
              big=big["name"], s=_num(big.get("size")), hx=hx["name"], x=x, vx=_num(hx["x"]),
              hy=hy["name"], y=y, vy=_num(hy["y"]))


def _model(result: dict) -> str | None:
    if result.get("status") != "ok":
        return None
    kind = result.get("model")
    fit = result.get("fit") or {}
    if kind == "compare":
        models = [m for m in result.get("models") or [] if m.get("score") is not None]
        win = next((m for m in models if m.get("id") == result.get("winner")), None)
        if not win:
            return None
        parts = dict(w=win["title"], metric=result.get("metric"), v=_num(win["score"]))
        if result.get("winner_beats_baseline"):
            return _s("model.best", "{w} predicts best ({metric}: {v}).", **parts)
        return _s("model.bestNoBetter", "{w} predicts best ({metric}: {v}) -- and it does not beat guessing.",
                  **parts)
    if kind == "rules":
        rules = result.get("rules") or []
        if not rules:
            return _s("rules.none", "no values appear together more often than chance.")
        r = rules[0]
        return _s("rules.top", "strongest pattern: {a} → {b}, {conf} of the time against {base} overall "
                  "({lift}×).", a=r["if"], b=r["then"], conf=f"{r['confidence']:.0%}",
                  base=f"{r['base_rate']:.0%}", lift=f"{r['lift']:.1f}")
    if kind == "cluster":
        return _s("cluster", "{n} segments (silhouette {v}).",
                  n=(fit.get("secondary") or {}).get("segments"), v=_num(fit.get("value")))
    if fit.get("value") is None:
        return None
    sec = fit.get("secondary") or {}
    if kind == "logistic":
        auc = float(fit["value"])
        if auc < 0.55:
            return _s("logit.coin", "AUC {v}: no better than a coin toss -- these predictors do not tell "
                      "the outcome apart.", v=_num(auc))
        acc = next((v for k, v in sec.items() if k.startswith("accuracy at")), None)
        base = next((v for k, v in sec.items() if k.startswith("accuracy of always")), None)
        if _is_num(acc) and _is_num(base):
            return _s("logit.acc", "AUC {v}; {acc} correct vs {base} by always guessing.",
                      v=_num(auc), acc=_pct(acc), base=_pct(base))
        return _s("logit.plain", "AUC {v}.", v=_num(auc))
    if kind == "linear":
        return _linear(result, fit)
    base = sec.get("accuracy of always guessing the commoner outcome")
    if kind == "tree" and str(fit.get("name")).lower() == "accuracy" and _is_num(base):
        acc = float(fit["value"])
        if acc - float(base) < 0.02:
            return _s("tree.noBetter", "accuracy {acc} -- no better than always guessing the commonest "
                      "value ({base}).", acc=_pct(acc), base=_pct(base))
        return _s("tree.acc", "accuracy {acc} vs {base} by always guessing the commonest value.",
                  acc=_pct(acc), base=_pct(base))
    return _s("fit", "{name} {v}.", name=fit.get("name"), v=_num(fit["value"]))


def _linear(result: dict, fit: dict) -> str:
    """How much is explained, then the biggest real effect in the measure's units."""
    target = str(result.get("target") or "the measure").replace("_", " ")
    r2 = float(fit["value"])
    head = dict(r2=f"{r2:.0%}", t=target)
    coefs = [c for c in ((result.get("result") or {}).get("detail") or {}).get("coefficients") or []
             if c.get("term") != "const" and c.get("significant") and _is_num(c.get("coefficient"))]
    if not coefs:
        return _s("linear.none", "these predictors explain {r2} of {t}; none of them has a clear effect.",
                  **head)
    # A level's coefficient and a per-unit slope are in different units, so they
    # are not ranked against each other: the largest level gap leads if there is
    # one, otherwise the slope that is most certain.
    levels = [c for c in coefs if "=" in str(c["term"])]
    top = (max(levels, key=lambda c: abs(float(c["coefficient"]))) if levels
           else max(coefs, key=lambda c: abs(float(c.get("t") or 0))))
    term, b = str(top["term"]), float(top["coefficient"])
    sign = "+" if b >= 0 else "−"
    if "=" in term:
        col, level = term.split("=", 1)
        ref = ((result.get("encodings") or {}).get(col) or {}).get("reference")
        parts = dict(level=level, col=col.replace("_", " "), b=f"{sign}{_num(abs(b))}", **head)
        if ref:
            return _s("linear.levelVs", "these predictors explain {r2} of {t}; the biggest effect is "
                      "{level} ({col}): {b} vs {ref}.", ref=ref, **parts)
        return _s("linear.level", "these predictors explain {r2} of {t}; the biggest effect is "
                  "{level} ({col}): {b}.", **parts)
    parts = dict(b=f"{sign}{_num(abs(b))}", term=term.replace("_", " "), **head)
    if (result.get("derived") or {}).get(term):
        return _s("linear.perYear", "these predictors explain {r2} of {t}; {b} per year since {term}.", **parts)
    return _s("linear.perUnit", "these predictors explain {r2} of {t}; {b} per unit of {term}.", **parts)


def takeaway(widget_type: str, config: dict, result: dict | None) -> Said | None:
    """One sentence stating what this drawn widget shows, or None."""
    if not isinstance(result, dict):
        return None
    try:
        t = result.get("type")
        if t in ("empty", "error"):
            return None
        if str(widget_type).startswith("map_") or widget_type in ("table", "list"):
            # Places, not a ranking: "None leads with ..." read the unnamed
            # points of a density map as a category (call-records panel).
            return None
        if t == "model" or str(widget_type).startswith("model_"):
            return _model(result)
        if t == "scalar":
            row = (result.get("rows") or [{}])[0]
            if not _is_num(row.get("value")):
                return None
            if (result.get("derived") or {}).get(config.get("measure")):
                return _s("scalar.years", "{agg} years since {m}: {v}.",
                          agg=_agg(str(config.get("aggregation") or "avg").lower()),
                          m=_h(config.get("measure")), v=_num(row["value"]))
            return _s("scalar", "{what}: {v}.", what=_what(config), v=_num(row["value"]))
        if t == "gauge" and _is_num(result.get("value")):
            tgt = result.get("target")
            if _is_num(tgt):
                return _s("gauge.target", "{v} against a target of {t}.", v=_num(result["value"]), t=_num(tgt))
            return _s("gauge", "{v}.", v=_num(result["value"]))
        if widget_type == "card" and isinstance(result.get("rows"), list):
            return _card(config, result["rows"])
        if t == "xy_series":
            return _xy(config, result.get("rows") or [])
        if t == "crosstab":
            return _crosstab(config, result)
        if t in ("heatmap", "ribbon"):
            return _heatmap(config, result)
        if t == "box_plot":
            return _box(config, result.get("rows") or [])
        if t == "bubble_series":
            return _bubble(config, result.get("rows") or [], result.get("derived"))
        if t == "sankey":
            links, nodes = result.get("links") or [], result.get("nodes") or []
            if not links:
                return None
            big = max(links, key=lambda l: float(l.get("value") or 0))
            name = lambda i: nodes[i]["name"] if i < len(nodes) else "?"  # noqa: E731
            return _s("sankey", "biggest flow: {a} → {b} ({v}).", a=name(big["source"]),
                      b=name(big["target"]), v=_num(big["value"]))
        if t == "decomposition":
            kids = [c for c in result.get("children") or [] if _is_num(c.get("value"))]
            if not kids:
                return None
            top = max(kids, key=lambda c: float(c["value"]))
            return _s("decomposition", "{what} {total}; {top} is highest at {v}.", what=_what(config),
                      total=_num(result.get("total")), top=top["name"], v=_num(top["value"]))
        if t == "waterfall":
            bars = result.get("bars") or []
            if not bars:
                return None
            big = max(bars, key=lambda b: abs(float(b.get("delta") or 0)))
            return _s("waterfall", "builds to {total}; the biggest step is {name} ({d}).",
                      total=_num(result.get("grand_total")), name=big["name"], d=_num(big["delta"]))
        if isinstance(result.get("root"), dict):
            root = result["root"]
            kids = [c for c in root.get("children") or [] if _is_num(c.get("value"))]
            if not kids:
                return None
            top = max(kids, key=lambda c: float(c["value"]))
            return _s("hierarchy", "{v} in all; {top} is the largest branch ({tv}).",
                      v=_num(root.get("value")), top=top["name"], tv=_num(top["value"]))
        if t == "custom_graph":
            rows = result.get("rows") or []
            if len(rows) < 2:
                return None
            a, b = rows[0], rows[-1]
            keys = [k for k in a if k != "name"]
            parts = [f"{_num(a.get(k))} → {_num(b.get(k))}" for k in keys[:2]]
            return _s("custom", "from {a} to {b}: {parts}.", a=a["name"], b=b["name"], parts="; ".join(parts))
        if t == "small_multiples":
            panels = result.get("panels") or []
            return (_s("multiples", "{n} panels, one per {f}.", n=len(panels), f=_h(config.get("facet_by")))
                    if panels else None)
        rows = result.get("rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "value" in rows[0]:
            return _series(widget_type, config, rows)
    except Exception:                                        # noqa: BLE001 -- never break a suggestion
        return None
    return None
