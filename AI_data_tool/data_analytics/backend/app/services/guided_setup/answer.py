"""Step 4 of the guided setup: a dashboard that answers what was asked
(docs/guided-setup/PLAN_V2.md, part 4).

The app's dashboard designer is asked for three *different* dashboards with
*varied shapes*: right for someone browsing a dataset, wrong for someone who
said what they want. Here the Demand (demand.py) decides:

* every chart answers one of the person's QUESTIONS and says which;
* the part of the data they asked for is applied to every chart -- they are
  never handed everything and a filter to find their subject;
* SIMPLE charts first (a number, a sorted bar, a line over time, a table).
  An advanced chart is offered only for the kind of question a simple one
  cannot answer, and must say why;
* a chart is kept for what it SHOWS, not for drawing: one bar, the same
  value everywhere, a headline of zero are refused and replaced;
* each page opens with the answer in words, written from the charts' own
  results; a number that is not in those results is not shown.

Several pages are proposed, each a different ANGLE on the same request; the
ones the person ticks become the pages of one dashboard.

The catalogue, the field checks, the repairs and the probe are the app
designer's own (suggest_dataset_dashboard, analyst_panel), so a chart
offered here is drawn exactly as the builder will draw it.
"""
from __future__ import annotations

from ..llm import data_block as _data_block

import asyncio
import json
import logging
import re

from . import demand as demand_service

logger = logging.getLogger(__name__)

#: What any question can usually be answered with.
SIMPLE = ("kpi", "card", "bar", "line", "donut", "table")
#: Offered only for the kind of question named beside each.
ADVANCED = {
    "numeric_series": "ONLY when a question asks how two NUMBERS relate (does one fall as the other rises?)",
    "heatmap": "ONLY when a question needs two categories at once (which kind goes with which group?)",
    "histogram": "ONLY when a question asks how values are SPREAD (what is the usual range?)",
    "box_plot": "ONLY when a question compares the SPREAD between groups, not their typical value",
    "dual_axis_bar_line": "ONLY when a question compares two different kinds of number over the same groups "
                          "or periods (a count against an average)",
    "map_choropleth": "ONLY when a question asks WHERE, and a column holds country names",
}
MAX_ADVANCED_PER_PAGE = 1
#: Further charts, each for the kind of question it answers better than a bar
#: or a line (settings.setup_dashboard_richness: balanced or rich). The
#: condition is about the SHAPE of the question, never about a subject.
EXTRA = {
    "treemap": "when a question asks how a whole splits across MORE than 5 parts",
    "area": "when a question is about a TOTAL building up over time -- the volume, not only the direction",
    "dot_plot": "when a handful of groups sit close together and the exact values matter",
    "crosstab": "when a question needs the exact numbers across two categories",
    "funnel": "ONLY when a category holds ordered stages that rows pass through, and a question asks how many "
              "reach each stage",
    "sankey": "ONLY when a question asks how one category flows into another (`dimension` to `dimension2`)",
    "comparative_time_series": "ONLY when a question compares two numbers over the same periods",
    "forecast": "ONLY when a question asks what comes NEXT for a number with at least a year of history",
}
#: Charts beyond the common ones a page may hold, by richness.
ADVANCED_PER_PAGE = {"basic": 1, "balanced": 2, "rich": 3}
RICHNESS = ("basic", "balanced", "rich")


def richness_now(richness: str | None = None) -> str:
    """basic | balanced | rich, as set now (settings.setup_dashboard_richness)."""
    if richness in RICHNESS:
        return richness
    from ...core.config import settings
    mode = str(getattr(settings, "setup_dashboard_richness", "balanced") or "balanced")
    return mode if mode in RICHNESS else "balanced"


def advanced_for(richness: str) -> dict[str, str]:
    """The charts beyond the common ones, with the condition each is offered under."""
    return dict(ADVANCED) if richness == "basic" else {**ADVANCED, **EXTRA}
#: A value rows are only passing through: at least this share of its rows were
#: begun in the newest periods, which hold at most this share of all rows.
OPEN_INSIDE = 0.8
OPEN_RECENT_PERIODS = 2
OPEN_RECENT_MAX_SHARE = 0.25
OPEN_MIN_PERIODS = 6
OPEN_MIN_ROWS = 20
#: Slices a donut can carry before a bar reads better; bars before a top list does.
DONUT_MAX = 5
BAR_MAX = 12
TOP_N = 10
#: Points a line carries before it is drawn by month instead.
TIME_POINTS_MAX = 80
#: Values closer together than this share of their size say "the same everywhere".
FLAT_SHARE = 0.03
#: Groups whose highest and lowest differ by at most this share are "about the same".
CLOSE_SHARE = 0.10
#: A chart mostly made of "unknown" describes the gap, not the subject.
UNKNOWN_SHARE = 0.6
PROBE_CONCURRENCY = 4
PAGE_WIDGETS = (3, 6)

_UNKNOWN = {"", "unknown", "none", "nan", "null", "n/a", "na", "غير معروف", "(blank)", "other"}
_CHANGE = re.compile(r"(change|chg|growth|delta|diff|return|pct|percent)", re.I)
_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}

#: What a chart's number IS, declared by the model beside its title and checked
#: against the chart's query -- in any language, with no list of title words.
SHOWS = ("share", "average", "total", "count", "distinct", "change", "level", "list", "other")
#: The summaries each declared kind accepts (kinds not listed are not checked).
_SHOWS_AGGS = {"average": {"avg", "mean", "median"}, "total": {"sum", "count", "countd"},
               "count": {"count", "countd", "sum"}, "distinct": {"countd"}}

PAGES_SCHEMA = {
    "type": "object",
    "properties": {"pages": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "rationale": {"type": "string"},
            "widgets": {"type": "array", "items": {
                "type": "object",
                "properties": {"question": {"type": "string"}, "widget_type": {"type": "string"},
                               "title": {"type": "string"}, "why": {"type": "string"},
                               "shows": {"type": "string", "enum": list(SHOWS)},
                               "config": {"type": "object"}},
                "required": ["question", "widget_type", "title", "why", "shows", "config"]}},
        },
        "required": ["title", "rationale", "widgets"]}},
        # Each column the pages use, named for a reader in the person's language.
        "names": {"type": "object", "additionalProperties": {"type": "string"}}},
    "required": ["pages"],
}
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {
        "type": "object",
        "properties": {"page": {"type": "integer"}, "text": {"type": "string"}},
        "required": ["page", "text"]}}},
    "required": ["answers"],
}

T = {
    "en": {"high": "Highest: {a} ({x}); lowest: {b} ({y})", "one": "{a}: {x}",
           "trend": "{a}: {x} → {b}: {y} ({pct})", "rows": "{n} records",
           "latest": "{b}: {y} ({pct} on {ref}); highest: {p} ({pv})",
           "scope": "Showing only {what} — {n} of {total} rows. Remove the dashboard's filter to see everything.", "scoped": "This data holds only {what}.",
           "apart": "Left out: {what} in “{col}” — unlike the rest of that column. Remove the dashboard's filter to bring them back.",
           "change": "{pct} (from {a} on {x} to {b} on {y})",
           "fewrank": "{n} groups, most with fewer than {min} rows each: too few to say which is highest or lowest",
           "onerow": "— one single row gives {pct} of the leader's total",
           "unanswered": "This data could not answer: {q}",
           "unansweredWhy": "This data could not answer: {q} -- the chart for it was left out: {why}",
           "unansweredNone": "This data could not answer: {q} -- no chart of these columns answers it",
           "nomatch": "This data has nothing called “{what}”, so this page shows everything it holds.",
           "nobase": "These are counts of {events}, not rates: this data does not hold the {base} they are counted "
                     "against, and a bigger group has more of everything. Go back to Choose data and take the "
                     "suggestion that includes the {base} to compare groups fairly.",
           "rate": "{title} — share of each group (%)",
           "ratewhy": "The share within each group, so that big groups do not lead only because they are big.",
           "small": " Groups with fewer than {n} rows are left out.",
           "bysize": " (follows the size of each group)",
           "same": "{x} — about the same for every {dim} ({lo} to {hi})",
           "sameExact": "{x} for every {dim}",
           "sameRange": "About the same for every {dim}: {lo} to {hi}",
           "close": "Highest: {a} ({x}); lowest: {b} ({y}) -- only {pct} apart, so about the same",
           "open": "Shares of “{col}” leave out the rows still at {values}: what becomes of them is not known yet.",
           "flat": "it shows the same value everywhere", "single": "it has only one group to show",
           "unknown": "most of it is “unknown”", "zero": "its number is exactly zero",
           "tied": "its top values are all the same", "empty": "it has nothing to show",
           "advanced": "a simpler chart answers this", "noq": "it does not say which question it answers"},
    "ar": {"high": "الأعلى: {a} ({x})؛ الأدنى: {b} ({y})", "one": "{a}: {x}",
           "trend": "{a}: {x} ← {b}: {y} ({pct})", "rows": "{n} سجل",
           "latest": "{b}: {y} ({pct} مقارنة بـ {ref})؛ الأعلى: {p} ({pv})",
           "scope": "المعروض فقط: {what} — {n} من {total} صف. احذف فلتر اللوحة لعرض كل شيء.", "scoped": "هذه البيانات تحتوي فقط على {what}.",
           "apart": "مستبعد: {what} في «{col}» — لا تشبه بقية العمود. احذف فلتر اللوحة لإعادتها.",
           "change": "{pct} (من {a} في {x} إلى {b} في {y})",
           "fewrank": "{n} مجموعة، معظمها أقل من {min} صفًا: عدد قليل لا يكفي للقول أيها الأعلى أو الأدنى",
           "onerow": "— صف واحد فقط يعطي {pct} من مجموع الأول",
           "unanswered": "تعذّر على هذه البيانات الإجابة عن: {q}",
           "unansweredWhy": "تعذّر على هذه البيانات الإجابة عن: {q} -- استُبعد الرسم الخاص به: {why}",
           "unansweredNone": "تعذّر على هذه البيانات الإجابة عن: {q} -- لا يجيب عنه أي رسم من هذه الأعمدة",
           "nomatch": "لا يوجد في هذه البيانات ما يسمى «{what}»، لذلك تعرض هذه الصفحة كل ما فيها.",
           "nobase": "هذه أعداد {events} وليست نسبًا: هذه البيانات لا تحتوي على {base} التي تُحسب نسبةً إليها، "
                     "والمجموعة الأكبر لديها أكثر من كل شيء. ارجع إلى «اختيار البيانات» واختر الاقتراح الذي يتضمن "
                     "{base} لمقارنة عادلة.",
           "rate": "{title} — النسبة داخل كل مجموعة (٪)",
           "ratewhy": "النسبة داخل كل مجموعة، حتى لا تتصدر المجموعات الكبيرة لمجرد أنها كبيرة.",
           "same": "{x} — متقارب جدًا لكل {dim} (من {lo} إلى {hi})",
           "sameExact": "{x} لكل {dim}",
           "sameRange": "متقارب جدًا لكل {dim}: من {lo} إلى {hi}",
           "close": "الأعلى: {a} ({x})؛ الأدنى: {b} ({y}) -- الفرق {pct} فقط، فهي متقاربة",
           "open": "نِسَب «{col}» تستثني الصفوف التي ما زالت عند {values}: ما ستؤول إليه غير معروف بعد.",
           "small": " استُبعدت المجموعات التي تقل عن {n} صفًا.",
           "bysize": " (يتبع حجم كل مجموعة)",
           "flat": "it shows the same value everywhere", "single": "it has only one group to show",
           "unknown": "most of it is “unknown”", "zero": "its number is exactly zero",
           "tied": "its top values are all the same", "empty": "it has nothing to show",
           "advanced": "a simpler chart answers this", "noq": "it does not say which question it answers"},
}


def _t(lang: str, key: str, **kw) -> str:
    return (T.get(lang, T["en"]).get(key) or T["en"][key]).format(**kw)


def _fmt(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:
        return "—"
    if abs(f) >= 1000 or f == int(f):
        return f"{f:,.0f}"
    return f"{f:,.2f}" if abs(f) >= 1 else f"{f:.3g}"


_YES_NO = {"en": {"true": "Yes", "false": "No"}, "ar": {"true": "نعم", "false": "لا"}}


def _label(name, lang: str = "en") -> str:
    """A group's name as a person reads it: a period without its midnight,
    a yes/no column's True and False as words."""
    s = str(name)
    if s.casefold() in ("true", "false"):
        return _YES_NO.get(lang, _YES_NO["en"])[s.casefold()]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T00:00:00", s)
    if m:
        return m.group(1) if (m.group(2), m.group(3)) == ("01", "01") else s[:7] if m.group(3) == "01" else s[:10]
    return s


# ── what a drawn chart shows ────────────────────────────────────────────────

def _series(result: dict, lang: str = "en") -> list[tuple[str, float]] | None:
    """(name, value) pairs of a result that is one number per group, else None."""
    rows = result.get("rows")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or "value" not in rows[0]:
        return None
    out = []
    for r in rows:
        try:
            v = float(r.get("value"))
        except (TypeError, ValueError):
            continue
        if v == v:
            out.append((_label(r.get("name"), lang), v))
    return out


def is_time(widget: dict, dates: set[str]) -> bool:
    return (widget.get("config") or {}).get("dimension") in dates


def worth(widget: dict, result: dict, dates: set[str]) -> str | None:
    """Why this drawn chart says nothing, as a T key -- or None when it does."""
    wt, cfg = widget.get("widget_type"), widget.get("config") or {}
    series = _series(result)
    if wt in ("table", "list", "crosstab", "matrix"):
        return None if result.get("rows") else "empty"
    if series is None:
        return None                       # a shape this gate does not read: the probe's word stands
    if not series:
        return "empty"
    values = [v for _n, v in series]
    if wt in ("kpi", "gauge"):
        counted = str(cfg.get("aggregation") or "").startswith("count")
        if values[0] == 0 and (not counted or _CHANGE.search(str(cfg.get("measure") or ""))):
            return "zero"
        return None
    if wt == "card":
        return "zero" if all(v == 0 for v in values) else None
    if len(values) < 2:
        return "single"
    spread, size = max(values) - min(values), max(abs(v) for v in values)
    if size == 0 or spread <= FLAT_SHARE * size:
        return "flat"
    if is_time(widget, dates):
        return None
    ranked = sorted(values, reverse=True)
    if cfg.get("limit") and len(ranked) >= 3 and ranked[0] == ranked[2]:
        return "tied"                     # a "top" whose leaders are level ranks nothing
    additive = str(cfg.get("aggregation") or "count") in ("count", "sum", "countd", "frequency")
    total = sum(abs(v) for v in values)
    if additive and total:
        unknown = sum(abs(v) for n, v in series if str(n).strip().casefold() in _UNKNOWN)
        if unknown / total > UNKNOWN_SHARE:
            return "unknown"
    return None


def finding(widget: dict, result: dict, dates: set[str], lang: str, percent: set[str] | None = None) -> str:
    """What the chart shows, in one line with its own numbers."""
    wt = widget.get("widget_type")
    fmt = _fmt
    if percent and (widget.get("config") or {}).get("measure") in percent:
        def fmt(v):                                                 # a share reads "17.4%"
            try:
                return f"{float(v):.1f}%"
            except (TypeError, ValueError):
                return _fmt(v)
    series = _series(result, lang)
    if wt in ("table", "list") or series is None:
        n = result.get("total") if isinstance(result.get("total"), int) else len(result.get("rows") or [])
        return _t(lang, "rows", n=f"{n:,}") if n else ""
    if not series:
        return ""
    small = result.get("small_groups") if isinstance(result.get("small_groups"), dict) else {}
    if small.get("too_few") and wt not in ("kpi", "gauge", "card"):
        # Every group is under the floor (the data is small): the bars are
        # drawn, but no group is called the highest or the lowest.
        return _t(lang, "fewrank", n=f"{len(series):,}", min=f"{small.get('min_rows', 0):,}")
    if wt in ("kpi", "gauge"):
        ch = result.get("change") if isinstance(result.get("change"), dict) else None
        if ch:                                   # a level's change over the period shown
            return _t(lang, "change", pct=f"{float(ch['pct']):+.1f}%", a=_fmt(ch["from"]), b=_fmt(ch["to"]),
                      x=str(ch["first"])[:10], y=str(ch["last"])[:10])
        return fmt(series[0][1])
    if wt == "card":
        return "; ".join(_t(lang, "one", a=n.replace("_", " "), x=fmt(v)) for n, v in series[:4])
    if is_time(widget, dates):
        # A last period still filling up is not where the trend ends.
        if result.get("partial_period") and len(series) > 2:
            series = series[:-1]
        if len(series) <= 2:
            (a, x), (b, y) = series[0], series[-1]
            pct = f"{(y - x) / abs(x) * 100:+.0f}%" if x else "—"
            return _t(lang, "trend", a=a, x=fmt(x), b=b, y=fmt(y), pct=pct)
        # Like with like: the latest period against the same one a year before
        # when the history has it, else against the period before -- never the
        # first period of the data (persona test 2026-10-12: "+83%" from the
        # first month to a seasonal peak; the year itself was 4.5% down).
        b, y = series[-1]
        ref, was = series[-2]
        year_ago = _year_before_label(str(b))
        if year_ago is not None:
            hit = next(((n, v) for n, v in series if str(n) == year_ago), None)
            if hit is not None:
                ref, was = hit
        pct = f"{(y - was) / abs(was) * 100:+.0f}%" if was else "—"
        p, pv = max(series, key=lambda t: t[1])
        return _t(lang, "latest", b=b, y=fmt(y), pct=pct, ref=ref, p=p, pv=fmt(pv))
    hi, lo = max(series, key=lambda p: p[1]), min(series, key=lambda p: p[1])
    if hi[1] > 0 and lo[1] > 0 and (hi[1] - lo[1]) / hi[1] <= CLOSE_SHARE and len(series) >= 2:
        # "Online leads" when four channels are within 5% of each other is not
        # an answer; "about the same" is (persona test 2026-10-12, plan 2.3).
        return _t(lang, "close", a=hi[0], x=fmt(hi[1]), b=lo[0], y=fmt(lo[1]),
                  pct=f"{(hi[1] - lo[1]) / hi[1] * 100:.0f}%")
    return _t(lang, "high", a=hi[0], x=fmt(hi[1]), b=lo[0], y=fmt(lo[1]))


def _year_before_label(label: str) -> str | None:
    """'2011-11' -> '2010-11', '2011-Q3' -> '2010-Q3', '2011' -> '2010'; else None."""
    m = re.fullmatch(r"(\d{4})(-(?:\d{2}|Q[1-4]|W\d{2}))?", label.strip())
    if not m:
        return None
    return f"{int(m.group(1)) - 1}{m.group(2) or ''}"


PREVIEW_BARS = 12
PREVIEW_POINTS = 48
PREVIEW_ROWS = 4
PREVIEW_COLUMNS = 5


def preview_of(widget: dict, result: dict, dates: set[str], lang: str, percent: bool = False) -> dict | None:
    """What the chart drew, small enough to keep with the suggestion, so the
    person SEES the page before making it -- not only reads its titles."""
    wt = widget.get("widget_type")
    series = _series(result, lang)
    if series is None:
        rows = result.get("rows")
        cols = result.get("columns")
        if wt in ("table", "list") and isinstance(rows, list) and isinstance(cols, list):
            keep = list(range(min(len(cols), PREVIEW_COLUMNS)))
            return {"kind": "table", "columns": [str(cols[i]) for i in keep],
                    "rows": [[None if r[i] is None else str(r[i])[:40] for i in keep]
                             for r in rows[:PREVIEW_ROWS] if isinstance(r, list)],
                    "total": result.get("total") if isinstance(result.get("total"), int) else len(rows)}
        return None
    if not series:
        return None
    if wt in ("kpi", "gauge", "card"):
        return {"kind": "number", "percent": percent,
                "rows": [[n.replace("_", " "), round(v, 4)] for n, v in series[:4]]}
    if is_time(widget, dates):
        step = max(1, -(-len(series) // PREVIEW_POINTS))
        return {"kind": "line", "percent": percent, "rows": [[n, round(v, 4)] for n, v in series[::step]]}
    kind = "parts" if wt in ("donut", "pie") else "bars"
    return {"kind": kind, "percent": percent, "rows": [[n, round(v, 4)] for n, v in series[:PREVIEW_BARS]],
            "more": max(0, len(series) - PREVIEW_BARS)}


def numbers_of(widget: dict, result: dict, dates: set[str], percent: bool = False) -> list[float]:
    """Every number a sentence about this chart may honestly use."""
    series = _series(result)
    if series is None:
        n = result.get("total") if isinstance(result.get("total"), int) else len(result.get("rows") or [])
        return [float(n)]
    values = [v for _n, v in series]
    out = list(values) + [float(len(values))]
    if len(values) >= 2:
        first, last = values[0], values[-1]
        if first:
            out.append((last - first) / abs(first) * 100)
        total = sum(values)
        if total:
            out += [v / total * 100 for v in values[:8]]
        hi, lo = max(values), min(values)
        if lo:
            out += [hi / lo, (hi - lo) / abs(lo) * 100]
        out.append(hi - lo)
    if isinstance(result.get("total"), (int, float)):
        out.append(float(result["total"]))
    if percent:
        out += [100 - v for v in values]          # "32% late" may be said as "68% on time"
    return out


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?\s*(%|[KkMmBb]\b|thousand|million|billion|ألف|مليون|مليار)?")
_SCALE = {"k": 1e3, "thousand": 1e3, "ألف": 1e3, "m": 1e6, "million": 1e6, "مليون": 1e6,
          "b": 1e9, "billion": 1e9, "مليار": 1e9}


def _honest(n: float, allowed: list[float]) -> bool:
    """`n` is one of the charts' numbers, as a person would round or scale it."""
    if n == int(n) and (0 <= n <= 12 or 1900 <= n <= 2100):
        return True                       # "the top 3", "since 2020"
    for v in allowed:
        # As it is, or a fraction said as a percentage. "1.3M" for 1,300,000 is
        # checked by its unit; a bare 1,299 must not pass for 1,299,400.
        for scaled in (v, v * 100):
            if abs(n - scaled) <= max(0.5 if abs(scaled) >= 10 else 0.05, 0.02 * abs(scaled)):
                return True
    return False


def honest_text(text: str, allowed: list[float]) -> str:
    """The sentences of `text` whose every number is one of the charts' own.
    A sentence with a number that is not is dropped, not corrected: a wrong
    figure at the top of a dashboard is worse than a shorter answer."""
    kept = []
    for sentence in re.split(r"(?<=[.!?؟۔])\s+|\n+", (text or "").strip()):
        s = sentence.strip()
        if not s:
            continue
        ok = True
        for m in _NUMBER.finditer(s.translate(_DIGITS)):
            raw = re.sub(r"[^\d.\-+]", "", m.group(0).split("%")[0].replace(",", ""))
            try:
                n = float(raw)
            except ValueError:
                continue
            unit = (m.group(1) or "").strip().casefold()
            if not (_honest(n * _SCALE.get(unit, 1), allowed) or (unit and _honest(n, allowed))):
                ok = False
                break
        if ok:
            kept.append(s)
    return " ".join(kept)


# ── the prompt ──────────────────────────────────────────────────────────────

#: Options a chart takes only when the question calls for them.
OPTIONS = {"kpi": "\n    option: `change_over`: a date column -- the number becomes the percent change of the measure "
                  "(a level: a value at one moment, such as a price or a balance) from the first date to the last; for "
                  "'how much did it go up or down'. Never the average of a column of daily changes for that",
           "bar": "\n    option: \"pareto\": true adds the running share of the whole -- only when the person asks how "
                  "concentrated a total is (how few groups carry most of it); never on a plain ranking"
                  "\n    option: NO dimension and `measures` listing 2+ columns on one scale (with one `aggregation`) "
                  "draws one bar per column -- to compare items such as the columns of a score group"}


def menu(profile: dict, richness: str = "basic") -> tuple[list[str], str]:
    """(types that may be used, the menu text): the common charts, then the
    others, each with the kind of question it is for."""
    from ..suggest_dataset_dashboard import REQUIRED_ROLES, WIDGET_GUIDE, usable_widgets
    from ..widget_roles import config_key_for_role
    usable = set(usable_widgets(profile))

    def line(wt: str, note: str = "") -> str:
        keys = ", ".join(config_key_for_role(r) for r in REQUIRED_ROLES.get(wt, ())) or "no required fields"
        return f"- {wt}: {WIDGET_GUIDE[wt]}{note}\n    requires: {keys}{OPTIONS.get(wt, '')}"

    simple = [wt for wt in SIMPLE if wt in usable]
    others = advanced_for(richness)
    advanced = [wt for wt in others if wt in usable and wt in WIDGET_GUIDE]
    if richness == "basic":
        text = "SIMPLE CHARTS -- use these for almost everything:\n" + "\n".join(line(wt) for wt in simple)
        if advanced:
            text += ("\n\nADVANCED CHARTS -- at most one per page, and only under its condition:\n"
                     + "\n".join(line(wt, f" {others[wt]}.") for wt in advanced))
        return simple + advanced, text
    text = "COMMON CHARTS -- right for most questions:\n" + "\n".join(line(wt) for wt in simple)
    if advanced:
        text += (f"\n\nOTHER CHARTS -- at most {ADVANCED_PER_PAGE[richness]} per page. Use one when its condition "
                 "holds: it then answers that kind of question better than a bar or a line. A dashboard that is "
                 "all bars reads as one chart repeated -- when two charts answer a question equally well, take "
                 "the kind the dashboard does not have yet.\n"
                 + "\n".join(line(wt, f" {others[wt]}.") for wt in advanced))
    return simple + advanced, text


def _hard_rules() -> str:
    from ..suggest_dataset_dashboard import SYSTEM
    return "Hard rules" + SYSTEM.split("Hard rules", 1)[1]


def _demand_text(dem: dict, scope: list[str], scoped_rows: int, lang: str) -> str:
    lines = [f"WHAT THE PERSON WANTS\n{dem.get('sentence') or '(they did not say; serve whoever owns this data)'}"]
    if dem.get("who"):
        lines.append(f"Who they are: {dem['who']}")
    qs = dem.get("questions") or []
    if qs:
        lines.append("Their questions, most important first:\n" + "\n".join(f"{q['id']}. {q['text']}" for q in qs))
    if dem.get("exclude"):
        lines.append("Leave out: " + "; ".join(dem["exclude"]))
    missing = demand_service.missing_words(dem)
    if missing:
        lines.append("NOT IN THIS DATA: " + "; ".join(missing) + ". The data has nothing of that kind, so this "
                     "dashboard shows what the data DOES hold. Never use those words in a title, a rationale or "
                     "a why, and never present the rows as if they were that.")
    if scope:
        lines.append(f"THE DATA BELOW IS ALREADY ONLY: {'; '.join(scope)} ({scoped_rows:,} rows). Every chart is "
                     "about that and nothing else: do not add a filter for it, do not compare it with the rest, "
                     "do not break down by a column that now holds one value.")
    return "\n".join(lines)


def _groups_note(groups: list[dict]) -> str:
    from .groups import describe
    return describe(groups)


def build_messages(profile: dict, dem: dict, scope: list[str], scoped_rows: int, notes: list[str],
                   count: int, lang: str, knowledge=None, facts: str | None = None,
                   shares: list[dict] | None = None, reading: str = "",
                   richness: str = "basic", groups: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    from ..dataset_profile import describe_for_prompt
    allowed, menu_text = menu(profile, richness)
    system = (
        "You build the pages of ONE dashboard for one person who said what they want. They do not know "
        "data or charts: the dashboard must hand them their answer, not a tool to look for it.\n\n"
        "- Every widget answers ONE of their questions; `question` is that question's id (q1, q2...). "
        "A widget that answers none of them does not belong.\n"
        "- The first widget of the first page answers q1. The first page also says HOW MUCH there is "
        "of what they asked about -- the number of records as a kpi -- unless a question's own "
        "headline number already does.\n"
        "- A question answered by a share, a rate or an average gets that ONE number as a kpi on the first "
        "page -- never only as a line over time or a breakdown.\n"
        "- Choose the SIMPLEST chart that answers the question:\n"
        "    one number -> kpi (several related numbers -> card)\n"
        "    a number per group -> bar, sorted from high to low (many groups -> the top 10, `limit`: 10)\n"
        "    a number over time -> line\n"
        "    parts of a whole, 5 parts or fewer -> donut; more parts -> bar\n"
        "    the records themselves, to look one up -> table\n"
        "  A chart from the second list only under the condition written beside it; when in doubt, simple.\n"
        "- 'How many are X' (late, returned, cancelled...) is answered by the COUNT and by its "
        "SHARE of the whole, shown as a kpi beside the count. And when comparing groups on X, "
        "compare the SHARE per group: the biggest group always has the biggest count, which tells "
        "them nothing about where the problem is. A share is the `avg` of the column's percent "
        "twin when one is listed under SHARES below (never a filter on that column as well); "
        "otherwise the `avg` of the yes/no column.\n"
        "- Titles say what the chart shows in the person's own vocabulary, never column names. "
        "`why` is one short sentence: what they learn from it.\n"
        "- `names`: for every column the pages use, the name a reader of this language would give it, in a few "
        "plain words (the column's meaning, never its spelling).\n"
        "- `shows` says what the chart's NUMBER is: share (a part of the whole, as a percentage), average, "
        "total, count, distinct (how many different ones), change (a difference or a percent change), level "
        "(a value at one moment, such as a balance), list (the records themselves) or other. Build the query "
        "that gives that number.\n"
        "- Prefer the typical value (median) to the average when the notes say values are extreme.\n"
        "- Never a chart of how many rows there are unless counting is what they asked.\n\n"
        + _hard_rules())
    user = (
        f"{_demand_text(dem, scope, scoped_rows, lang)}\n\n"
        + ("NOTES ABOUT THIS DATA\n" + "\n".join(f"- {n}" for n in notes[:6]) + "\n\n" if notes else "")
        + (f"HOW TO READ THIS DATA (measured on the database)\n{reading}\n"
           "Respect it: total only amounts and counts; average levels, durations and scores; say 'best' and "
           "'worst' by each number's direction; and never rank groups by a count of events alone when the "
           "share per group can be drawn -- a `has_...` yes/no column gives it (the `avg` of its percent "
           "column).\n\n" if reading else "")
        + f"THE DATA\n{_data_block(describe_for_prompt(profile, knowledge))}\n"
        + (f"\nMEASURED FACTS (exact, computed on these rows)\n{facts}\n" if facts else "")
        + ("\nSHARES (percent columns; use only with `avg`)\n" + "\n".join(
            f"- `{c['name']}`: its avg is the share of rows where `{c['of']}` is "
            + (f"“{c.get('value')}”" if c.get("is") == "value" else "TRUE" if c.get("is") == "yes" else "FALSE")
            + ", in percent."
            for c in shares if c.get("is") != "label")
           + "\nPick the column for what the TITLE says: a title about the outcome being true (late, "
             "returned, active) takes the TRUE column; a title about the opposite (on time, kept, "
             "inactive) takes the FALSE column. A title must never promise the opposite of its column.\n"
           if shares else "")
        + ("\nSCORE GROUPS (found from the values)\n" + _groups_note(groups) + "\n" if groups else "")
        + f"\nWIDGETS YOU MAY USE\n{menu_text}\n\n"
        f"Propose {count} pages. Each page is a different ANGLE on the same request -- for example the "
        "overview (the headline numbers and the main comparison), the comparison in depth, how it changed "
        "over time, the records to look through -- whichever angles these questions and columns support. "
        "Never the same page reordered, and never a page about something they did not ask. Each page: a "
        "title naming its angle in two to four words (it is the page's tab), a one-sentence rationale "
        "saying which questions it answers, and "
        f"{PAGE_WIDGETS[0]} to {PAGE_WIDGETS[1]} widgets, the headline number first. A chart appears on one "
        f"page only. Write every title, rationale and why in {_LANGUAGE.get(lang, 'English')}.")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], allowed


# ── the gate ────────────────────────────────────────────────────────────────

def with_scope(config: dict, scope_filters: list[dict]) -> dict:
    """The widget's config with the person's scope in front of its own filters
    (the scope wins on a column both name)."""
    if not scope_filters:
        return config
    scoped = {f["column"] for f in scope_filters}
    own = [f for f in (config.get("filters") or []) if isinstance(f, dict) and f.get("column") not in scoped]
    return {**config, "filters": [dict(f) for f in scope_filters] + own}


def _key(widget: dict) -> str:
    return widget.get("widget_type", "") + "|" + json.dumps(widget.get("config"), sort_keys=True, default=str)


def _reading(widget: dict) -> str:
    """What a widget measures, whatever its shape: the same measure, by the
    same groups, under the same filters is one reading. Raw tables (no
    measure) are each their own."""
    c = widget.get("config") or {}
    if not c.get("measure") and not c.get("measures"):
        return _key(widget)
    return "reading|" + json.dumps([c.get("measure"), c.get("measures"), c.get("aggregation"), c.get("dimension"),
                                    c.get("dimension2"), c.get("filters")], sort_keys=True, default=str)


#: A title word and a column-name part are the same word when they share this many first letters.
_STEM = 5
_NAME_NOISE = {"is", "has", "was", "flag", "count", "total", "value", "amount", "date", "time", "name", "type"}


def _stems(text: str) -> set[str]:
    return {w[:_STEM] for w in re.findall(r"\w+", str(text or "").casefold()) if len(w) >= 4}


def _config_columns(config, df_columns: set[str]) -> set[str]:
    """Every column a widget's config names, wherever it names it."""
    out: set[str] = set()
    if isinstance(config, dict):
        for v in config.values():
            out |= _config_columns(v, df_columns)
    elif isinstance(config, (list, tuple)):
        for v in config:
            out |= _config_columns(v, df_columns)
    elif isinstance(config, str) and config in df_columns:
        out.add(config)
    return out


#: Quick calculations and modes that show each part as a share of the whole.
_SHARE_CALCS = {"percent_of_total", "percent_of_column", "percent_of_row", "percent_change"}


def _one_to_one(df, a: str, b: str) -> bool:
    """Whether two columns are one fact written twice (each value of one
    always comes with one value of the other, and back): "Late" / 1."""
    try:
        pair = df[[a, b]].dropna()
        return bool(len(pair)) and int(pair.groupby(a)[b].nunique().max()) == 1 \
            and int(pair.groupby(b)[a].nunique().max()) == 1
    except Exception:                                               # noqa: BLE001
        return False


def _gives_share(config: dict, df, percent: set[str] | None = None, column_meta: dict | None = None) -> bool:
    """Whether a chart's number is a share: the average of a yes/no column,
    a column that holds shares (measured, or classified as one), or parts
    shown as a share of their whole."""
    import pandas as pd
    from ..semantic_guard import recorded_number
    if config.get("quick_calc") in _SHARE_CALCS or config.get("bar_mode") == "stacked100":
        return True
    measures = [config.get("measure")] + list(config.get("measures") or [])
    for m in [x for x in measures if isinstance(x, str)]:
        if m in (percent or set()) or recorded_number(m, column_meta) == "share":
            return True
        if m in df.columns and str(config.get("aggregation") or "").lower() in ("avg", "mean"):
            vals = pd.to_numeric(df[m], errors="coerce").dropna()
            if len(vals) and set(vals.unique().tolist()) <= {0, 1}:
                return True
    return False


def _keeps_everything(f, df) -> bool:
    """Whether an `in` filter lists every value its column holds."""
    if not isinstance(f, dict) or f.get("op") != "in" or f.get("column") not in getattr(df, "columns", []):
        return False
    try:
        held = {str(v) for v in df[f["column"]].dropna().unique()[:1000]}
        wanted = {str(v) for v in (f.get("value") if isinstance(f.get("value"), list) else [f.get("value")])}
        return bool(held) and held <= wanted
    except Exception:                                               # noqa: BLE001
        return False


def title_promises(widget: dict, df, aliases: dict | None = None,
                   elsewhere: set[str] | None = None, percent: set[str] | None = None,
                   context: str | None = None) -> str | None:
    """What a chart's title promises that its query does not do, or None.

    Persona test 2026-10-12: "Review score: late orders" showed the average of
    ALL orders -- the number was real, the title was not. A title that names a
    yes/no column, a number column or a value of a category must be about a
    chart that uses that column (as its measure, its split or its filter).
    Words that also name a column the chart uses never count, nor do columns
    that are one fact with a column it uses (`delivery_performance` "Late" and
    `is_late` 1). A title naming a column that only another dataset of the
    analysis holds is about that one
    (named by two words or more: "review score", never "trip" alone). Words of
    the dataset's own name (`context`: "All deliveries with ...") describe
    every row, so a title repeating them promises nothing."""
    import pandas as pd
    title = str(widget.get("title") or "")
    if not title.strip() or df is None:
        return None
    cols = {str(c) for c in df.columns}
    # A filter that keeps every value of its column ("is_late in [0, 1]")
    # narrows nothing: it does not "use" the column (Olist: a one-number card
    # titled "Late vs. On Time" over every row).
    cfg_used = dict(widget.get("config") or {})
    if cfg_used.get("filters"):
        cfg_used["filters"] = [f for f in cfg_used["filters"] if not _keeps_everything(f, df)]
    used = _config_columns(cfg_used, cols | set((aliases or {}).keys()))
    used |= {aliases[u] for u in list(used) if aliases and u in aliases}
    # Words of the dataset's own name, compared by prefix so "trip" and
    # "trips" (or any word and its ending) are the same word.
    ctx = _stems(context or "")
    words = {w for w in _stems(title) if not any(c.startswith(w) or w.startswith(c) for c in ctx)}
    taken = set().union(*(_stems(u.replace("_", " ")) for u in used)) if used else set()
    heard = re.sub(r"\s+", " ", title.casefold())
    for c in sorted((elsewhere or set()) - cols):
        parts = {p for p in _stems(c.replace("_", " ")) if p not in {w[:_STEM] for w in _NAME_NOISE}}
        if len(parts) >= 2 and parts <= words - taken:
            return f"the title names “{c}”, which another dataset of this analysis holds, not this one"
    computes_change = bool(cfg_used.get("change_over")) or cfg_used.get("quick_calc") in ("percent_change", "difference")
    for c in cols - used:
        if any(_one_to_one(df, c, u) for u in used if u in cols):
            continue
        s = df[c]
        try:
            distinct = int(s.nunique(dropna=True))
        except TypeError:
            continue
        numeric = pd.api.types.is_numeric_dtype(s) and s.dtype != bool
        if numeric and computes_change:
            # The chart computes a change itself (a level's change over the
            # period, a percent change): a title saying "change" is its own,
            # not a promise of a change column (EGX: "COMI price change" over
            # `close` was refused for naming `change_pct`).
            continue
        if distinct <= 2 or numeric:
            parts = {p for p in _stems(c.replace("_", " ")) if p not in {w[:_STEM] for w in _NAME_NOISE}} - taken
            hit = parts & words
            if hit and not (numeric and str(c).casefold().endswith("_id")):
                return f"the title names “{c}” but the chart does not use it"
        elif 3 <= distinct <= 60:
            for v in s.dropna().unique().tolist():
                key = re.sub(r"\s+", " ", str(v).casefold()).strip()
                if len(key) >= 4 and _stems(key) - taken and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", heard):
                    return f"the title names “{v}” (a value of “{c}”) but the chart does not use that column"
    return None


def shows_mismatch(widget: dict, df, percent: set[str] | None = None,
                   column_meta: dict | None = None) -> str | None:
    """Why a chart's query does not give the number its `shows` declares, or
    None. Fresh benchmark run 2026-10-13: "Share of late deliveries" was the
    average days late and read "9.55%". Checked from the declaration, so a
    title in any language is held to what its number is."""
    shows = str(widget.get("shows") or "").lower()
    cfg = widget.get("config") or {}
    measure = cfg.get("measure") or ", ".join(m for m in cfg.get("measures") or [] if isinstance(m, str))
    if not measure or shows not in SHOWS or df is None:
        return None
    agg = str(cfg.get("aggregation") or cfg.get("agg") or "").lower()
    if shows == "share":
        ok = _gives_share(cfg, df, percent, column_meta)
    elif shows in _SHOWS_AGGS and agg:
        ok = agg in _SHOWS_AGGS[shows]
    else:
        return None
    return None if ok else f"it is meant to show {shows_word(shows)}, but its query gives the {agg or 'sum'} of “{measure}”"


def shows_word(shows: str) -> str:
    return {"share": "a share of the whole", "average": "an average", "total": "a total", "count": "a count",
            "distinct": "how many different ones"}.get(shows, shows)


class Gate:
    """Checks, draws and judges proposed widgets for one dataset."""

    def __init__(self, inputs, facts: dict, allowed: list[str], question_ids: set[str],
                 scope_filters: list[dict], lang: str, given: set[str] | None = None, richness: str = "basic"):
        #: The charts beyond the common ones, and how many a page may hold.
        self.richness = richness
        #: Columns only the analysis's OTHER datasets hold, and the dataset's
        #: own name (set by design()).
        self.elsewhere: set[str] = set()
        self.context: str = ""
        #: Each column's display name in the person's language (set by design()).
        self.names: dict[str, str] = {}
        #: Values only another dataset of the analysis is kept to, and each
        #: question's text (set by design()).
        self.foreign: set[str] = set()
        self.asked_text: dict[str, str] = {}
        #: The kind of number each question's answer rests on (demand `wants`),
        #: and the columns it rests on (demand `about`).
        self.wants: dict[str, str] = {}
        self.about: dict[str, list[str]] = {}
        #: On a summary dataset, the column saying how many rows each row stands for.
        self.group_size: str | None = None
        self.advanced = advanced_for(richness)
        self.max_advanced = ADVANCED_PER_PAGE.get(richness, 1)
        #: Values the dataset is ALREADY narrowed to by its own query.
        self.given = given or set()
        self.inputs, self.facts, self.allowed = inputs, facts, set(allowed)
        self.question_ids, self.scope_filters, self.lang = question_ids, scope_filters, lang
        self.dates = {c["name"] for c in inputs.profile.get("columns", []) if c.get("role") == "datetime"}
        shares = getattr(inputs, "shares", None) or []
        self.percent = {c["name"] for c in shares if c.get("is") != "label"}
        self.twins = {c["of"]: c["name"] for c in shares if c.get("is") == "yes"}
        #: A 0/1 number's percent twin: its average is drawn as that percentage.
        self.ones = {c["of"]: c["name"] for c in shares if c.get("is") == "value" and c.get("value") == 1}
        self.labels = {c["of"]: c["name"] for c in shares if c.get("is") == "label"}
        self.flag_of = {c["name"]: c["of"] for c in shares if c.get("is") != "label"}
        self.scoped = {f.get("column") for f in scope_filters}
        #: Percent columns made on the way for "the share that is <value>".
        self.made: list[dict] = []
        self.results: dict[str, dict] = {}
        self.captions: dict[str, str] = {}
        #: What is already on a page of this design: a chart, or the same
        #: numbers in another shape (a table of what a bar already shows).
        self.seen: set[str] = set()
        #: Values rows only pass through, per column; and what was left out for them.
        self._open: dict[str, list[str]] = {}
        self.open_notes: dict[str, list[str]] = {}
        #: A comparison that came out level, said as one number: its sentence.
        self.level: dict[str, str] = {}
        self._sem = asyncio.Semaphore(PROBE_CONCURRENCY)
        #: Why each asked question's chart was refused (question id -> reason), for the page.
        self.refusals: dict[str, str] = {}

    def _check(self, widget: dict) -> tuple[dict | None, str]:
        from ..analyst_panel import repair_and_check
        from ..suggest_dataset_dashboard import polish_widget
        title = widget.get("title") or widget.get("widget_type")
        wt = widget.get("widget_type")
        if wt == "pie":
            widget = {**widget, "widget_type": "donut"}
            wt = "donut"
        cfg0 = widget.get("config") or {}
        if (wt == "table" and cfg0.get("dimension") and cfg0.get("measure") and cfg0.get("aggregation")
                and not cfg0.get("columns") and "bar" in self.allowed):
            # One number per group is a ranking: bars, not a table of two columns.
            widget = {**widget, "widget_type": "bar", "config": {**cfg0, "sort": cfg0.get("sort") or "desc"}}
            wt = "bar"
        if wt not in self.allowed:
            return None, f"'{title}': {wt} is not on the menu -- {_t(self.lang, 'advanced')}"
        if self.question_ids and widget.get("question") not in self.question_ids and not widget.get("_unlinked"):
            return None, f"'{title}': {_t(self.lang, 'noq')}"
        cfg1 = widget.get("config") or {}
        if cfg1.get("filters") and self.twins:
            # "has_x = 1", "= 'yes'", "= 'true'" all mean the yes/no column's True.
            words = {"1": True, "true": True, "yes": True, "y": True, "0": False, "false": False, "no": False, "n": False}

            def truth(v):
                return words.get(str(v).strip().casefold(), v) if not isinstance(v, bool) else v
            fixed = [{**f, "value": [truth(v) for v in f["value"]] if isinstance(f.get("value"), list)
                      else truth(f.get("value"))}
                     if isinstance(f, dict) and f.get("column") in self.twins else f for f in cfg1["filters"]]
            cfg1 = {**cfg1, "filters": fixed}
            widget = {**widget, "config": cfg1}
        if self.given and cfg1.get("filters"):
            # A filter for what the whole dataset already is ("status = Returned"
            # on a dataset of returns that did not keep `status`) adds nothing.
            df = self.inputs.df
            kept = [f for f in cfg1["filters"] if not (
                isinstance(f, dict) and f.get("column") not in df.columns
                and {demand_service._norm(v) for v in (f["value"] if isinstance(f.get("value"), list)
                                                       else [f.get("value")])} <= self.given)]
            if len(kept) != len(cfg1["filters"]):
                widget = {**widget, "config": {**cfg1, "filters": kept}}
        widget = self._retarget_filters(widget)
        widget, compared = self._set_aside_comparisons(widget)
        bad = self._bad_filter(widget.get("config") or {})
        if bad:
            return None, f"'{title}': {bad}"
        cfg = widget.get("config") or {}
        averaged = str(cfg.get("aggregation") or "") in ("avg", "mean", "average")
        if cfg.get("measure") in self.twins and averaged:
            # The share of a yes/no column, drawn as a percentage a person reads.
            flag = cfg["measure"]
            # Rows where it is not known (a parcel still on its way) are in
            # neither the yes nor the no: left out of the share.
            known = [f for f in cfg.get("filters") or [] if not (isinstance(f, dict) and f.get("column") == flag)]
            cfg = {**cfg, "measure": self.twins[flag], "aggregation": "avg",
                   "filters": known + [{"column": flag, "op": "in", "value": [True, False]}]}
            widget = {**widget, "config": cfg}
        elif cfg.get("measure") in getattr(self, "ones", {}) and averaged:
            cfg = {**cfg, "measure": self.ones[cfg["measure"]], "aggregation": "avg"}
            widget = {**widget, "config": cfg}
        elif cfg.get("measure") in self.percent and not averaged:
            cfg = {**cfg, "aggregation": "avg"}
            widget = {**widget, "config": cfg}
        flag = self.flag_of.get(cfg.get("measure"))
        # A text column's share (one twin per value) has no "unknown" side: the
        # known-rows filter below is for yes/no columns only -- on text it
        # kept no row at all.
        if flag:
            # A share of an outcome is over ALL rows where the outcome is known:
            # a filter to "yes" (or "no") would make it 100% (or 0%) -- for any
            # share (Olist: "average days late" drawn as is_late_pct over the
            # late rows read 100%). Rows where a yes/no outcome is not known
            # yet count for neither side.
            same = {flag, self.labels.get(flag), self.twins.get(flag), f"{flag}{NOT_SUFFIX}"}
            rest = [f for f in cfg.get("filters") or [] if not (isinstance(f, dict) and f.get("column") in same)]
            known = [{"column": flag, "op": "in", "value": [True, False]}] if flag in self.twins else []
            widget = {**widget, "config": {**cfg, "filters": rest + known}}
        keep = {k: widget.get(k) for k in ("question", "why")}
        fixed, ok, why = repair_and_check(
            {**widget, "source": "model"}, self.inputs.profile, self.inputs.column_meta,
            self.facts.get("mixed_units"), self.facts.get("one_to_one"), self.facts.get("identical"),
            self.facts.get("edges"))
        if not ok:
            return None, str(why)
        fixed = polish_widget({k: v for k, v in fixed.items() if k != "source"}, self.inputs.profile)
        if compared:
            fixed = self._compare_columns({**fixed, "config": {**(fixed.get("config") or {}),
                                           "filters": list((fixed.get("config") or {}).get("filters") or [])
                                           + compared}})
        fixed = self._as_share(fixed)
        cfg = fixed.get("config") or {}
        of_label = {v: k for k, v in self.labels.items()}
        for key in ("dimension", "dimension2"):
            flag = of_label.get(cfg.get(key), cfg.get(key))     # the flag, or its label column used directly
            if flag in self.labels:
                # Split by a yes/no column: its groups in words, the unknown left out.
                cfg = {**cfg, key: self.labels[flag],
                       "filters": [f for f in cfg.get("filters") or []
                                   if not (isinstance(f, dict) and f.get("column") == flag)]
                       + [{"column": flag, "op": "in", "value": [True, False]}]}
        fixed = {**fixed, "config": cfg}
        return {**fixed, **keep, "config": with_scope(fixed.get("config") or {}, self.scope_filters)}, ""

    def _as_share(self, widget: dict) -> dict:
        """A chart meant as a share drawn as a COUNT of the rows where a
        column holds one value ("Share returned": count, status = Returned)
        shows a count. Drawn instead as what it says: the average of a
        percent column that is 100 on those rows -- made here, created on the
        dataset when the page is built."""
        cfg = widget.get("config") or {}
        # Whether a share is meant is what the chart DECLARES (`shows`); the
        # title's words decide only for a chart that declares nothing (a
        # design kept from before `shows`, or a platform-built card).
        shows = str(widget.get("shows") or "").lower()
        meant = shows == "share" if shows else bool(_SHARE_WORD.search(str(widget.get("title") or "")))
        if not meant or cfg.get("measure") in self.percent \
                or not str(cfg.get("aggregation") or "").startswith("count"):
            return widget
        df = self.inputs.df
        for f in cfg.get("filters") or []:
            col, op, val = (f.get("column"), f.get("op"), f.get("value")) if isinstance(f, dict) else (None,) * 3
            val = val[0] if isinstance(val, list) and len(val) == 1 else val
            if (op not in ("eq", "in") or isinstance(val, (list, dict)) or col not in df.columns
                    or col == cfg.get("dimension") or "`" in str(col) or '"' in str(val)):
                continue
            if col in self.twins and str(val).casefold() in ("true", "false"):
                name = self.twins[col] if str(val).casefold() == "true" else f"{col}{NOT_SUFFIX}"
            else:
                name = f"{col}_{_slug(val)}{SHARE_SUFFIX}"
                if name not in df.columns:
                    from ..widget_data import apply_calculated_columns
                    literal = str(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else f'"{val}"'
                    calc = {"name": name, "expression": f"IF(`{col}` == {literal}, 100, 0)", "dtype": "numeric",
                            "format": {"type": "percent", "decimals": 1}}
                    made = apply_calculated_columns(df, [calc])
                    if name not in made.columns:
                        continue
                    self.inputs.df = df = made
                    self.made.append(calc)
                self.percent.add(name)
            rest = [x for x in cfg["filters"] if x is not f]
            return {**widget, "config": {**cfg, "measure": name, "aggregation": "avg", "filters": rest}}
        return widget

    def _count_whom(self, widget: dict) -> dict:
        """A question that wants a COUNT of something its columns name (people:
        `emp_no`), on rows where that column repeats (one person per
        assignment), is counted by distinct values, never by rows (persona
        benchmark: "the current workforce is 489,903" counted assignment rows
        of 240,124 people)."""
        qid = str(widget.get("question") or "")
        cfg = widget.get("config") or {}
        df = getattr(self.inputs, "df", None)
        if df is None or getattr(self, "wants", {}).get(qid) != "count" or str(cfg.get("aggregation") or "") != "count":
            return widget
        about = [c for c in getattr(self, "about", {}).get(qid, []) if c in df.columns]
        if not about:
            return widget
        who = about[0]
        try:
            distinct, filled = int(df[who].nunique(dropna=True)), int(df[who].notna().sum())
        except TypeError:
            return widget
        # Only a column that names the things counted (most values its own: an
        # employee number), never a category (a status: its distinct values
        # are its few kinds).
        if not filled or distinct >= filled or distinct < IDENTIFIES_SHARE * filled or cfg.get("dimension") == who:
            return widget
        return {**widget, "config": {**cfg, "measure": who, "aggregation": "countd"}}

    def _about_question(self, widget: dict) -> bool:
        """Whether the chart uses a column its question rests on (demand
        `about`), directly or through a column made from it (a share, a group
        average, a comparison). Not judged when the question names none of
        this dataset's columns. Persona benchmark (Olist): days late over time
        stood under "do late deliveries get lower review SCORES"."""
        df = getattr(self.inputs, "df", None)
        about = [c for c in getattr(self, "about", {}).get(str(widget.get("question") or ""), [])
                 if df is not None and c in df.columns]
        if not about:
            return True
        cols = {str(c) for c in df.columns}
        used = _config_columns(widget.get("config") or {}, cols | set(getattr(self, "percent", set()) or set()))
        made = list(getattr(self.inputs, "shares", None) or []) + list(getattr(self.inputs, "groups", None) or []) \
            + list(getattr(self, "made", None) or [])
        sources = set(used)
        for m in made:
            if m.get("name") in used:
                sources |= {c for c in about if c == m.get("of") or c in (m.get("columns") or [])
                            or f"`{c}`" in str(m.get("expression") or "")}
        return bool(sources & set(about))

    def _data_only(self):
        """The rows without the columns the setup made itself (shares, a score
        group's average, comparisons): their names are the platform's words,
        not the data's, so a title cannot "name" them."""
        df = getattr(self.inputs, "df", None)
        if df is None:
            return None
        made = {c.get("name") for c in list(getattr(self.inputs, "shares", None) or [])
                + list(getattr(self.inputs, "groups", None) or []) + list(self.made or [])}
        drop = [c for c in df.columns if c in made]
        return df.drop(columns=drop) if drop else df

    _COMPARE = {"gt": ">", "lt": "<", "gte": ">=", "lte": "<=", "eq": "==", "neq": "!="}

    def _retarget_filters(self, widget: dict) -> dict:
        """An `eq`/`in` filter on a column that never holds its value, when
        exactly ONE other text column holds every value of it, moves to that
        column ("branch = Returned" -> "status = Returned"). Decided from the
        values alone, in any language; with no such column, or several, the
        filter stays and is refused as before."""
        import pandas as pd
        cfg = widget.get("config") or {}
        df = self.inputs.df
        changed, out = False, []
        holds: dict[str, set[str]] = {}

        def held(c: str) -> set[str]:
            if c not in holds:
                s = df[c]
                holds[c] = ({str(v).strip().casefold() for v in s.dropna().unique()[:5000]}
                            if not (pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s))
                            else set())
            return holds[c]
        for f in cfg.get("filters") or []:
            col, op, val = (f.get("column"), f.get("op"), f.get("value")) if isinstance(f, dict) else (None,) * 3
            values = [str(v).strip().casefold() for v in (val if isinstance(val, list) else [val]) if v is not None]
            if (op in ("eq", "in") and values and col in df.columns and not (set(values) & held(col))
                    and not any(v in df.columns for v in values)):
                owners = [c for c in df.columns if c != col and set(values) <= held(c)]
                if len(owners) == 1:
                    out.append({**f, "column": owners[0]})
                    changed = True
                    continue
            out.append(f)
        return {**widget, "config": {**cfg, "filters": out}} if changed else widget

    def _set_aside_comparisons(self, widget: dict) -> tuple[dict, list[dict]]:
        """(the widget without its column-against-column filters, those filters):
        they are applied after the checks, as a derived column (`_compare_columns`)."""
        cfg = widget.get("config") or {}
        df = self.inputs.df
        aside, keep = [], []
        for f in cfg.get("filters") or []:
            other = f.get("value") if isinstance(f, dict) else None
            other = other[0] if isinstance(other, list) and len(other) == 1 else other
            if (isinstance(f, dict) and f.get("op") in self._COMPARE and isinstance(other, str)
                    and other in df.columns and other != f.get("column") and f.get("column") in df.columns):
                aside.append(f)
            else:
                keep.append(f)
        return ({**widget, "config": {**cfg, "filters": keep}}, aside) if aside else (widget, [])

    def _compare_columns(self, widget: dict) -> dict:
        """A filter comparing a column with ANOTHER column ("delivery days >
        promised days") cannot be applied by any engine: it becomes a derived
        1/0 column -- made here, created on the dataset when a page uses it --
        and a filter `= 1` on it. Held-out benchmark 2026-10-13: "how many
        shipments were late" was refused for exactly this."""
        import pandas as pd
        cfg = widget.get("config") or {}
        df = self.inputs.df
        changed, filters = False, []
        for f in cfg.get("filters") or []:
            col, op, other = (f.get("column"), f.get("op"), f.get("value")) if isinstance(f, dict) else (None,) * 3
            other = other[0] if isinstance(other, list) and len(other) == 1 else other
            if (op in self._COMPARE and isinstance(other, str) and other != col and col in df.columns
                    and other in df.columns and pd.api.types.is_numeric_dtype(df[col])
                    and pd.api.types.is_numeric_dtype(df[other]) and "`" not in col + other):
                name = f"{col}_{op}_{other}"
                if name not in df.columns:
                    from ..widget_data import apply_calculated_columns
                    calc = {"name": name, "dtype": "numeric",
                            "expression": f"IF(`{col}` {self._COMPARE[op]} `{other}`, 1, 0)"}
                    made = apply_calculated_columns(df, [calc])
                    if name not in made.columns:
                        filters.append(f)
                        continue
                    self.inputs.df = df = made
                    self.made.append(calc)
                filters.append({"column": name, "op": "eq", "value": 1})
                changed = True
            else:
                filters.append(f)
        return {**widget, "config": {**cfg, "filters": filters}} if changed else widget

    def _bad_filter(self, config: dict) -> str | None:
        """A filter the engine would silently skip: an unknown column, another
        column where a value belongs, a value the column does not hold. Such a
        chart draws -- unfiltered -- under a title that promises the filter."""
        import pandas as pd
        df = self.inputs.df
        for f in config.get("filters") or []:
            if not isinstance(f, dict):
                return "a filter must be {column, op, value}"
            col, op, val = f.get("column"), f.get("op"), f.get("value")
            if op in ("date_range", "paths"):
                continue
            if col not in df.columns:
                return f"filter column '{col}' is not in this data"
            values = val if isinstance(val, list) else [val]
            if any(isinstance(v, str) and v in df.columns and v != col for v in values):
                return (f"the filter on '{col}' compares it with another column ('{values[0]}'); a filter "
                        "compares a column with a VALUE -- use a column that already holds the answer, "
                        "or leave the filter out")
            s = df[col]
            if op in ("gt", "gte", "lt", "lte"):
                ok = (pd.api.types.is_numeric_dtype(s) and isinstance(val, (int, float))
                      and not isinstance(val, bool)) or (
                    pd.api.types.is_datetime64_any_dtype(s) and isinstance(val, str)
                    and not pd.isna(pd.to_datetime(val, errors="coerce")))
                if not ok:
                    return f"the filter on '{col}' needs a number (or a date for a date column) as its value"
            elif op in ("eq", "in") and not pd.api.types.is_datetime64_any_dtype(s):
                have = {str(v).strip().casefold() for v in s.dropna().unique()[:5000]}
                if len(have) < 5000 and not any(str(v).strip().casefold() in have for v in values):
                    shown = ", ".join(sorted(str(v) for v in s.dropna().unique()[:8]))
                    logger.info("guided setup: filter refused, %r never holds %r (columns: %s)",
                                col, values, ", ".join(map(str, df.columns))[:400])
                    return f"'{col}' never holds {values!r}; it holds: {shown}"
        return None

    async def _draw(self, widget: dict) -> tuple[dict | None, str]:
        from ..suggest_dataset_dashboard import _probe
        async with self._sem:
            drew, rows, why = await _probe(widget, self.inputs.probe)
            if not drew:
                return None, why or "returned nothing to draw"
            from ..suggest_inputs import drawn_key
            return self.inputs.drawn.get(drawn_key(widget["widget_type"], widget["config"])) or {}, ""

    async def _ladder(self, widget: dict, result: dict) -> tuple[dict, dict]:
        """A chart with more groups than its shape reads: a donut becomes a
        bar, a long bar becomes the top ten."""
        series = _series(result)
        if series is not None and is_time(widget, self.dates) and len(series) > TIME_POINTS_MAX:
            # One point a day over years is noise: by month the shape shows.
            coarse = {**widget, "config": {**widget["config"], "dimension_granularity": "month"}}
            again, _why = await self._draw(coarse)
            if again is not None and 1 < len(_series(again) or []) < len(series):
                return coarse, again
        if series is None or is_time(widget, self.dates):
            return widget, result
        changed = widget
        if widget["widget_type"] == "donut" and len(series) > DONUT_MAX:
            changed = {**widget, "widget_type": "bar", "config": {**widget["config"], "sort": "desc"}}
        if changed["widget_type"] == "bar" and len(series) > BAR_MAX:
            changed = {**changed, "config": {**changed["config"], "limit": TOP_N, "sort": "desc"}}
        if changed is widget:
            return widget, result
        again, _why = await self._draw(changed)
        return (changed, again) if again is not None else (widget, result)

    def _share_of(self, measure) -> tuple[str, str] | None:
        """(column, value) when `measure` is a share made here for "the rows where column is value"."""
        for calc in self.made:
            if calc.get("name") == measure:
                m = re.match(r'^IF\((\w+) == "?(.*?)"?, 100, 0\)$', str(calc.get("expression") or ""))
                return (m.group(1), m.group(2)) if m else None
        return None

    def open_values(self, column: str) -> list[str]:
        """Values of `column` that rows are only PASSING THROUGH: nearly all of
        the rows holding one were begun in the newest periods, where older rows
        have moved on to something else. What becomes of such a row is not
        known yet, so it belongs on neither side of a share of an outcome.
        Read from the dates and the counts; no value's name is consulted."""
        import pandas as pd
        if column in self._open:
            return self._open[column]
        out: list[str] = []
        df = self.inputs.df
        from ..insights import order_event_dates
        dates = [d for d in order_event_dates(sorted(self.dates)) if d in df.columns]
        if dates and column in df.columns:
            when = pd.to_datetime(df[dates[0]], errors="coerce").dt.to_period("M")
            periods = sorted(when.dropna().unique())
            if len(periods) >= OPEN_MIN_PERIODS:
                recent = when.isin(periods[-OPEN_RECENT_PERIODS:])
                if 0 < recent.mean() <= OPEN_RECENT_MAX_SHARE:
                    values = df[column].astype(object)
                    for value, n in values[when.notna()].value_counts().items():
                        if n < OPEN_MIN_ROWS:
                            continue
                        inside = float((recent & (values == value)).sum()) / float(n)
                        if inside >= OPEN_INSIDE:
                            out.append(str(value))
        self._open[column] = out
        return out

    def _known_outcomes(self, widget: dict) -> dict:
        """A share of one outcome is over the rows whose outcome is known: rows
        still passing through a temporary value are left out, or the newest
        months read as a collapse ("delivered fell to 70%": the rest were on
        their way). Said once under the page (`self.open_notes`)."""
        cfg = widget.get("config") or {}
        made = self._share_of(cfg.get("measure"))
        if not made:
            return widget
        column, value = made
        still = [v for v in self.open_values(column) if v != str(value)]
        if not still or any(isinstance(f, dict) and f.get("column") == column for f in cfg.get("filters") or []):
            return widget
        self.open_notes[column] = still
        return {**widget, "config": {**cfg, "filters": list(cfg.get("filters") or [])
                                     + [{"column": column, "op": "neq", "value": v} for v in still]}}

    async def _same_everywhere(self, widget: dict, result: dict) -> tuple[dict, dict] | None:
        """A comparison of groups that comes out level IS an answer -- "it does
        not differ" -- so it is said as the one number with its range, instead
        of the chart being thrown away and the question left hanging."""
        cfg = widget.get("config") or {}
        series = _series(result) or []
        if (widget.get("widget_type") != "bar" or not widget.get("question") or not cfg.get("dimension")
                or is_time(widget, self.dates) or len(series) < 2):
            return None
        number = {"widget_type": "kpi", "title": widget.get("title"), "question": widget.get("question"),
                  "why": widget.get("why"),
                  "config": {k: v for k, v in cfg.items() if k not in ("dimension", "sort", "limit", "dimension2")}}
        drawn, _why = await self._draw(number)
        if drawn is None or not _series(drawn):
            return None
        share = cfg.get("measure") in self.percent
        fmt = (lambda v: f"{float(v):.1f}%") if share else _fmt
        values = [v for _n, v in series]
        overall = _series(drawn)[0][1]
        dim = display_name(cfg["dimension"], getattr(self, "names", None))
        # The number over every row can fall outside the groups' range (rows
        # with no group): then the range alone is said, never "907 -- about the
        # same for every city (913 to 934)" (persona test 2026-10-12).
        # Equal at the shown precision: "1 for every state", never "1 to 1".
        self.level[_key(number)] = (
            _t(self.lang, "sameExact", x=fmt(min(values)), dim=dim) if fmt(min(values)) == fmt(max(values))
            else _t(self.lang, "same", x=fmt(overall), dim=dim, lo=fmt(min(values)), hi=fmt(max(values)))
            if min(values) <= overall <= max(values)
            else _t(self.lang, "sameRange", dim=dim, lo=fmt(min(values)), hi=fmt(max(values))))
        return number, drawn

    async def one(self, widget: dict) -> tuple[dict | None, str]:
        """(the widget ready to offer, '') or (None, why not)."""
        if not isinstance(widget, dict) or not isinstance(widget.get("config"), dict):
            return None, "not a widget"
        title = widget.get("title") or widget.get("widget_type")
        # A title naming a value only ANOTHER dataset of the analysis is kept to
        # ("COMI total gain" drawn on the index's rows read the index's +62.8%).
        foreign_title = names_foreign(str(widget.get("title") or ""), getattr(self, "foreign", set()))
        if foreign_title:
            return None, (f"'{title}': the title names “{foreign_title}”, which another dataset of this analysis "
                          "is kept to, not this one")
        named = names_foreign(self.asked_text.get(str(widget.get("question") or ""), ""), self.foreign) \
            or not answers_kind(widget.get("shows"), self.wants.get(str(widget.get("question") or ""))) \
            or not self._about_question(widget)
        if not named:
            widget = self._count_whom(widget)
        if named:
            # Not this dataset's question ("How much did COMI go up?" on the
            # index's rows): the chart may stay, but never as its answer.
            widget = {**widget, "question": "", "_unlinked": True}
        try:
            checked, why = self._check(widget)
            if checked is None:
                return None, why if why.startswith("'") else f"'{title}': {why}"
            promise = title_promises(checked, self._data_only(), self.flag_of,
                                     self.elsewhere, self.percent, self.context)
            if promise:
                return None, f"'{title}': {promise} -- filter or split by it, or retitle the chart"
            declared = shows_mismatch({**checked, "shows": widget.get("shows")}, getattr(self.inputs, "df", None),
                                      self.percent, getattr(self.inputs, "column_meta", None))
            if declared:
                return None, f"'{title}': {declared} -- build the query that gives that number"
            checked = self._known_outcomes(checked)
            if self.group_size and (checked.get("config") or {}).get("min_group_rows"):
                checked = {**checked, "config": {**checked["config"], "size_column": self.group_size}}
            result, why = await self._draw(checked)
            if result is None:
                return None, f"'{title}': {why}"
            checked, result = await self._ladder(checked, result)
            bad = worth(checked, result, self.dates)
            if bad == "flat":
                level = await self._same_everywhere(checked, result)
                if level is not None:
                    checked, result = level
                    bad = None
            if bad:
                return None, f"'{title}': {_t(self.lang, bad)} -- answer the question another way or leave it out"
        except Exception as exc:                                    # noqa: BLE001
            logger.info("guided setup: a proposed widget was refused: %s", exc)
            return None, f"'{title}': could not be drawn"
        size = len(result["rows"]) if isinstance(result.get("rows"), list) else 1
        if checked.get("widget_type") == "kpi" and str(widget.get("why") or "").strip():
            # Under the number, a line for the reader instead of "avg(is_late_pct)".
            # (Not part of what the chart measures: added after it was drawn.)
            self.captions[_key(checked)] = str(widget["why"]).strip()[:90]
        said = self.level.get(_key(checked)) or finding(checked, result, self.dates, self.lang, self.percent)
        one = one_row_leader(checked, result, getattr(self.inputs, "df", None), self.dates)
        if one is not None and said:
            said = f"{said} {_t(self.lang, 'onerow', pct=f'{one:.0f}%')}"
        checked = {k: v for k, v in checked.items() if k != "_unlinked"}
        out = {**checked, "row_count": size or 1, "finding": said,
               "preview": preview_of(checked, result, self.dates, self.lang,
                                     (checked.get("config") or {}).get("measure") in self.percent)}
        self.results[_key(out)] = result
        return out, ""

    async def pages(self, pages: list) -> tuple[list[dict], list[list[str]]]:
        """Each page with its kept widgets, and each page's refusals. A chart
        already kept on an earlier page is not repeated; at most one advanced
        chart stays on a page."""
        kept_pages, whys_all, seen = [], [], self.seen
        for page in pages:
            widgets = [w for w in (page or {}).get("widgets") or [] if isinstance(w, dict)]
            got = await asyncio.gather(*(self.one(w) for w in widgets)) if widgets else []
            kept, whys, advanced = [], [], 0
            for asked_w, (w, why) in zip(widgets, got):
                if w is None:
                    whys.append(why)
                    if asked_w.get("question"):
                        self.refusals.setdefault(str(asked_w["question"]), why)
                    continue
                if _key(w) in seen or _reading(w) in seen:
                    continue
                if w["widget_type"] in self.advanced:
                    advanced += 1
                    if advanced > self.max_advanced:
                        whys.append(f"'{w.get('title')}': {_t(self.lang, 'advanced')}")
                        continue
                seen.update((_key(w), _reading(w)))
                kept.append(w)
            kept_pages.append({"title": str((page or {}).get("title") or "").strip(),
                               "rationale": str((page or {}).get("rationale") or "").strip(),
                               "widgets": kept})
            whys_all.append(whys)
        return kept_pages, whys_all


# ── the answer, in words ────────────────────────────────────────────────────

def _digest(page: dict, gate: Gate) -> tuple[str, list[float]]:
    lines, allowed = [], []
    for w in page["widgets"]:
        result = gate.results.get(_key(w)) or {}
        allowed += numbers_of(w, result, gate.dates, (w.get("config") or {}).get("measure") in gate.percent)
        line = f"- {w.get('title')}: {w.get('finding') or ''}"
        series = _series(result)
        if series and w["widget_type"] not in ("kpi", "gauge"):
            # As the chart shows them: a share carries its % sign, or 0.5%
            # is copied into the sentence as "0.511" (retry-2, 2026-10-11).
            share = (w.get("config") or {}).get("measure") in gate.percent
            line += " | " + ", ".join(f"{n}={_fmt(v)}{'%' if share else ''}" for n, v in series[:8])
        lines.append(line)
    return "\n".join(lines), allowed


async def write_answers(pages: list[dict], gate: Gate, dem: dict, lang: str, client) -> None:
    """Sets `answer` on each page: two or three sentences from its charts'
    results, every number checked against them; the charts' own findings when
    the model is away or says nothing that survives the check."""
    digests = [_digest(p, gate) for p in pages]
    got = None
    if client is not None and getattr(client, "enabled", True) and pages:
        msgs = [{"role": "system", "content":
                 "For each dashboard page below, answer the person's request in two or three short "
                 f"sentences, in {_LANGUAGE.get(lang, 'English')}, using ONLY the results listed for that "
                 "page. Lead with the answer to their first question; when a count and its share are both "
                 "listed, give both. When groups are compared both by a count and by a share, say who "
                 "leads by the SHARE, and that the count follows each group's size -- never call the group "
                 "with the biggest count the worst or the best for that alone. Say only what the results show: "
                 "never mention what is missing from a page or what it does not answer. Copy numbers exactly as given "
                 "(you may round them); never calculate a new number, never give a cause, advice or a "
                 "guess. Name things as the results name them. Describe the data as what it is, never as "
                 "the person's own unless they said so."},
                {"role": "user", "content":
                 f"The person wants: {dem.get('sentence') or '(not said)'}\n"
                 + ("The data has NOTHING called: " + "; ".join(demand_service.missing_words(dem))
                    + " -- never use those words; describe the rows as what they are.\n"
                    if demand_service.missing_words(dem) else "")
                 + "".join(f"\nPAGE {i + 1} -- {p['title']}\n{digests[i][0]}\n" for i, p in enumerate(pages))
                 + "\nGive one answer per page; `page` is the page's number as written above."}]
        try:
            got = await client.complete_json(msgs, ANSWER_SCHEMA, max_tokens=1200, temperature=0.1, enforce=True)
        except Exception:                                           # noqa: BLE001
            logger.exception("guided setup: writing the answer failed")
    answers = [a for a in (got or {}).get("answers") or [] if isinstance(a, dict)]
    said = {a.get("page"): str(a.get("text") or "") for a in answers}
    if len(answers) == len(pages) and set(said) != set(range(1, len(pages) + 1)):
        said = {i + 1: str(a.get("text") or "") for i, a in enumerate(answers)}     # numbered some other way
    for i, p in enumerate(pages):
        text = honest_text(said.get(i + 1, ""), digests[i][1])
        if not text:
            if said.get(i + 1):
                logger.info("guided setup: answer dropped by the number check: %s", said[i + 1][:300])
            charts = [w for w in p["widgets"] if w.get("finding") and w["widget_type"] not in ("table", "list")]
            text = " ".join(f"{w.get('title')}: {w['finding']}." for w in charts[:3])
        p["answer"] = "\n".join(x for x in [text, *answer_lines(p, dem, text)] if x)


#: At most this many per-question lines under a page's summary.
ANSWER_LINES_MAX = 4
_FIGURE_IN_TEXT = re.compile(r"\d[\d,.]*")


def answer_lines(page: dict, dem: dict, said: str) -> list[str]:
    """One line per question the person ASKED that this page answers, made from
    its chart's own measured finding (plan 2.1): the summary is written by the
    model and may leave a question out ("weakest criterion: s3_7 4.15" was on
    the chart and missing from the page). A finding whose numbers the summary
    already gives adds nothing."""
    asked = {q["id"]: q.get("text") or "" for q in (dem or {}).get("questions") or []
             if isinstance(q, dict) and q.get("asked") and q.get("id")}
    out, seen = [], set()
    for w in page.get("widgets") or []:
        qid, found = w.get("question"), str(w.get("finding") or "")
        if qid not in asked or qid in seen or not found or w.get("widget_type") in ("table", "list"):
            continue
        figures = _FIGURE_IN_TEXT.findall(found)
        if figures and all(f.rstrip(".,") in said for f in figures):
            seen.add(qid)
            continue
        seen.add(qid)
        out.append(f"• {asked[qid].rstrip('?؟ ')}: {found}")
        if len(out) >= ANSWER_LINES_MAX:
            break
    return out


def answer_widget(page: dict, note: str | None) -> dict | None:
    """The page's opening text block: the answer, then what the page is limited to."""
    content = "\n".join(x for x in (page.get("answer"), note) if x)
    if not content:
        return None
    return {"widget_type": "text", "title": page.get("title") or "", "config": {"content": content},
            "why": "", "row_count": 1}


# ── the whole design ────────────────────────────────────────────────────────

SHARE_SUFFIX = "_pct"
NOT_SUFFIX = "_not_pct"
LABEL_SUFFIX = "_label"
#: Words in a title that promise a share rather than a count.
_SHARE_WORD = re.compile(r"(share|percent|percentage|proportion|\brate\b|ratio|%|نسبة|نسب|معدل|٪)", re.I)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


#: The longest display name kept from the model for one column.
NAME_MAX = 40


#: A column names the things counted when at least this share of its values
#: are different (an employee number over assignment rows), not a category.
IDENTIFIES_SHARE = 0.2

#: A leader whose total rests this much on ONE row is said to: one record is
#: not a pattern (persona test: a single order of 80,995 units made a product
#: "the best seller").
ONE_ROW_SHARE = 0.5


def one_row_leader(widget: dict, result: dict, df, dates: set[str]) -> float | None:
    """The percent of the leading group's total that one row gives, when it is
    at least ONE_ROW_SHARE -- for a ranking that adds a measure up; else None."""
    import pandas as pd
    cfg = widget.get("config") or {}
    dim, measure = cfg.get("dimension"), cfg.get("measure")
    series = _series(result) or []
    if (widget.get("widget_type") not in ("bar", "donut", "treemap") or df is None or not series
            or str(cfg.get("aggregation") or "sum").lower() != "sum" or dim in (dates or set())
            or dim not in df.columns or measure not in df.columns or cfg.get("dimension2")):
        return None
    top, total = max(series, key=lambda t: t[1])
    try:
        rows = pd.to_numeric(df.loc[df[dim].astype(str) == str(top), measure], errors="coerce").dropna()
    except Exception:                                               # noqa: BLE001
        return None
    if len(rows) < 2 or not total or float(total) <= 0:
        return None
    share = float(rows.max()) / float(total)
    return share * 100 if share >= ONE_ROW_SHARE else None


def display_name(col, names: dict | None = None) -> str:
    """A column as a reader sees it: the display name the design gave it in
    the person's language, else its own name with spaces."""
    return str((names or {}).get(col) or str(col).replace("_", " "))


def clean_names(got: dict | None, columns) -> dict[str, str]:
    """The model's display names, kept only for real columns and short text."""
    cols = {str(c) for c in columns}
    raw = (got or {}).get("names") if isinstance(got, dict) else None
    return {str(k): str(v).strip() for k, v in (raw or {}).items()
            if str(k) in cols and isinstance(v, str) and 0 < len(v.strip()) <= NAME_MAX} if isinstance(raw, dict) else {}


def _slug(value) -> str:
    """A column-name piece from a value, in any script ("مرتجع", "In transit" -> "in_transit")."""
    return re.sub(r"\W+", "_", str(value)).strip("_").lower() or "value"


def share_columns(df) -> list[dict]:
    """A percent twin for each yes/no column: 100 where yes, else 0 -- so its
    average over the rows where the answer is known is the share of yes, in
    percent (the gate adds that "known" filter). A column of exactly two text
    values, in any language ("مرتجع" / "تم التسليم"), gets one twin per value
    (held-out benchmark 2026-10-13: Arabic statuses had no share at all)."""
    import pandas as pd
    out = []
    for col in df.columns:
        s = df[col]
        name = f"{col}{SHARE_SUFFIX}"
        if ("`" in str(col) or name in df.columns or f"{col}{NOT_SUFFIX}" in df.columns
                or pd.api.types.is_datetime64_any_dtype(s)):
            continue
        values = set(s.dropna().unique().tolist()[:5])
        if (len(values) == 2 and all(isinstance(v, str) for v in values)
                and not any('"' in v for v in values)):
            for v in sorted(values):
                twin = f"{col}_{_slug(v)}{SHARE_SUFFIX}"
                if twin not in df.columns:
                    out.append({"name": twin, "expression": f'IF(`{col}` == "{v}", 100, 0)', "dtype": "numeric",
                                "format": {"type": "percent", "decimals": 1}, "of": str(col), "is": "value",
                                "value": v})
            continue
        if (len(values) == 2 and pd.api.types.is_numeric_dtype(s) and s.dtype != bool
                and {float(v) for v in values} == {0.0, 1.0} and f"{col}{SHARE_SUFFIX}" not in df.columns):
            # A 0/1 number ("is_late" stored as 1/0): its share, in percent --
            # "0.0811" read as a rate was 8.1% (persona benchmark, Olist).
            out.append({"name": f"{col}{SHARE_SUFFIX}", "expression": f"IF(`{col}` == 1, 100, 0)", "dtype": "numeric",
                        "format": {"type": "percent", "decimals": 1}, "of": str(col), "is": "value", "value": 1})
            continue
        if len(values) == 2 and values <= {True, False} and all(isinstance(v, (bool,)) or type(v).__name__ == "bool_"
                                                                for v in values):
            out.append({"name": name, "expression": f"IF(`{col}` == True, 100, 0)", "dtype": "numeric",
                        "format": {"type": "percent", "decimals": 1}, "of": str(col), "is": "yes"})
            out.append({"name": f"{col}{NOT_SUFFIX}", "expression": f"IF(`{col}` == False, 100, 0)",
                        "dtype": "numeric", "format": {"type": "percent", "decimals": 1},
                        "of": str(col), "is": "no"})
            # Its two groups in words: a chart split by "True / False" makes the
            # reader -- and the model writing the answer -- guess which is which
            # ("on time: 2.83" was the LATE parcels, Nile Express 2026-10-10).
            word = re.sub(r"^(is|has|was|are)_", "", str(col)).replace("_", " ").strip() or str(col)
            if f"{col}{LABEL_SUFFIX}" not in df.columns and '"' not in word:
                out.append({"name": f"{col}{LABEL_SUFFIX}", "of": str(col), "is": "label",
                            "expression": f'IF(`{col}` == True, "{word.capitalize()}", '
                                          f'IF(`{col}` == False, "Not {word}", "Unknown"))'})
    return out


async def prepare(db, user, ds, dem: dict | None):
    """(inputs narrowed to the person's scope, facts, the scope's filters and words)."""
    from ..fact_sheet import build_facts
    from ..insights import effective_roles
    from ..dataset_profile import build_profile
    from ..suggest_inputs import prepare as load
    from ..widget_data import _apply_filters
    from .access import release

    inputs = await load(db, user, ds)
    await release(db)
    shares = share_columns(inputs.df) if not inputs.live else []
    if shares:
        # A yes/no column's share, as a percentage a person reads ("17.4%",
        # not 0.174): drawn on a copy here, created on the dataset only when
        # a page that uses it is made (the builder's own derived-field path).
        from ..analytics import detect_types
        from ..widget_data import apply_calculated_columns
        numbers = [c for c in shares if c.get("is") != "label"]
        inputs.df = await asyncio.to_thread(apply_calculated_columns, inputs.df, numbers)
        inputs.type_map = await asyncio.to_thread(detect_types, inputs.df)
        inputs.profile = await asyncio.to_thread(build_profile, inputs.df, inputs.type_map, inputs.column_meta)
        # The word columns ("Late" / "Not late") join the rows only AFTER the
        # profile is taken: they are for drawing a split by the yes/no column,
        # not for the model to choose -- and a profile that lists "Late" as a
        # value made the title check refuse every chart with "late" in its
        # title that was not filtered to it (the share charts themselves).
        inputs.df = await asyncio.to_thread(apply_calculated_columns, inputs.df,
                                            [c for c in shares if c.get("is") == "label"])
    inputs.shares = shares
    # Columns that hold one kind of score, one per item: their row average
    # is made like a share (groups.py), so "the average score" is one number.
    from .groups import score_groups
    groups = score_groups(inputs.df) if not inputs.live else []
    if groups:
        from ..analytics import detect_types
        from ..widget_data import apply_calculated_columns
        inputs.df = await asyncio.to_thread(apply_calculated_columns, inputs.df,
                                            [{k: v for k, v in g.items() if k not in ("columns", "low", "high")}
                                             for g in groups])
        groups = [g for g in groups if g["name"] in inputs.df.columns]
        inputs.type_map = await asyncio.to_thread(detect_types, inputs.df)
        inputs.profile = await asyncio.to_thread(build_profile, inputs.df, inputs.type_map, inputs.column_meta)
    inputs.groups = groups
    filters = demand_service.filters_for(dem, ds.id)
    words = demand_service.scope_words(dem, ds.id)
    total = len(inputs.df)
    scoped = inputs.df
    if filters:
        scoped = await asyncio.to_thread(_apply_filters, inputs.df, filters)
        # The model is shown the part they asked for: its values, ranges and
        # facts -- not those of everything else.
        inputs.profile = await asyncio.to_thread(build_profile, scoped, inputs.type_map, inputs.column_meta)
    roles = effective_roles(inputs.type_map, inputs.column_meta)
    facts = await asyncio.to_thread(build_facts, scoped, roles, inputs.column_meta, inputs.ineligible())
    inputs.scoped = scoped          # the rows the person asked about, for the platform's own charts
    return inputs, facts, filters, words, len(scoped), total


def scope_note(words: list[str], filters: list[dict], scoped_rows: int, total: int, lang: str,
               dem: dict | None = None, dataset_id: int | None = None,
               apart: list[dict] | None = None, names: dict | None = None) -> str | None:
    """What the page is limited to. What was asked for that the data does
    not hold is said once, in the check step -- never on every page (persona
    test 2026-10-12: "This data has nothing called '2015 to 2018'" on pages
    of a 2015-2018 dataset)."""
    parts: list[str] = []
    if words:
        what = "; ".join(words)
        parts.append(_t(lang, "scope", what=what, n=f"{scoped_rows:,}", total=f"{total:,}") if filters
                     else _t(lang, "scoped", what=what))
    for b in (dem or {}).get("base_missing") or []:
        if dataset_id is None or b.get("dataset_id") == dataset_id:
            parts.append(_t(lang, "nobase", events=str(b["events"]).replace("_", " "),
                            base=str(b["base"]).replace("_", " ")))
            break
    for a in apart or []:
        parts.append(_t(lang, "apart", what=", ".join(f"“{v}”" for v in a["values"]), col=display_name(a["column"], names)))
    return " ".join(parts) or None


#: At most this many values are set apart by the check's finding (one "is not"
#: filter each, every one shown on the dashboard and removable).
SET_APART_MAX = 8


def _not_held(values: set[str] | None, df) -> set[str]:
    """Of `values`, those this dataset's rows do not hold in any text column."""
    if not values or df is None:
        return set(values or set())
    import pandas as pd
    held: set[str] = set()
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        try:
            held |= {str(v).strip().casefold() for v in s.dropna().unique()[:5000]}
        except TypeError:
            continue
    return {v for v in values if v not in held}


#: Kinds that stand for each other when a chart answers a question.
_SAME_KIND = {"total": {"total", "count"}, "count": {"count", "total"}}


def answers_kind(shows: str | None, wants: str | None) -> bool:
    """Whether a chart declared as `shows` can answer a question that `wants`
    that kind of number. Unknown on either side, or 'other'/'list', is not
    judged. Held-out benchmark 2026-10-13: a chart of average days answered
    "which branch has the highest return SHARE" under its question."""
    shows, wants = str(shows or "").lower(), str(wants or "").lower()
    if not shows or not wants or "other" in (shows, wants) or "list" in (shows, wants):
        return True
    return shows in _SAME_KIND.get(wants, {wants})


def names_foreign(question: str, foreign: set[str]) -> str | None:
    """The first value of `foreign` the question names as a whole word."""
    text = " " + re.sub(r"[^\w]+", " ", (question or "").casefold()) + " "
    for v in sorted(foreign or set(), key=len, reverse=True):
        key = re.sub(r"[^\w]+", " ", v).strip()
        if len(key) >= 2 and f" {key} " in text:
            return v
    return None


def set_apart(entry: dict | None, df, filters: list[dict]) -> list[dict]:
    """[{"column", "values", "filters"}]: members the check MEASURED as unlike
    the rest of their column (written another way, or on another scale -- an
    index's traded value among companies'), left out of every chart of the
    design by one visible, removable "is not" filter each. Never removes a
    row from the data; never when the person's own scope names the column."""
    import ast
    out = []
    scoped = {f.get("column") for f in filters or [] if isinstance(f, dict)}
    for item in (entry or {}).get("health") or []:
        col = item.get("column")
        if item.get("kind") != "odd" or not col or col in scoped or df is None or col not in df.columns:
            continue
        values = item.get("values")
        if not values:                        # checked before `values` was kept: read the rule
            rule = str((item.get("action") or {}).get("rule") or "")
            try:
                values = ast.literal_eval(rule[rule.index("["):]) if "[" in rule else []
            except (ValueError, SyntaxError):
                values = []
        held = set(df[col].dropna().astype(str))
        values = [str(v) for v in values if str(v) in held]
        if not values or len(values) > SET_APART_MAX:
            continue
        out.append({"column": col, "values": values,
                    "filters": [{"column": col, "op": "neq", "value": v} for v in values]})
    return out


def _notes(entry: dict | None) -> list[str]:
    """What the check found that a chart must respect (extreme values, gaps)."""
    return [i["what"] for i in (entry or {}).get("health") or []
            if i.get("tone") in ("problem", "warning", "info") and i.get("what")]


def shares_lacking(pages: list[dict], gate: "Gate") -> list[tuple[int, str, str, str]]:
    """(page, chart title, percent column, group) for each chart that counts
    a yes/no outcome per group with no chart of that outcome's SHARE per the
    same group anywhere in the design."""
    have = {(w["config"].get("measure"), w["config"].get("dimension"))
            for p in pages for w in p["widgets"] if isinstance(w.get("config"), dict)}
    out = []
    for i, p in enumerate(pages):
        for w in p["widgets"]:
            c = w.get("config") or {}
            dim = c.get("dimension")
            if not dim or dim in gate.dates or not str(c.get("aggregation") or "").startswith("count"):
                continue
            for f in c.get("filters") or []:
                twin = gate.twins.get(f.get("column")) if isinstance(f, dict) else None
                if twin and f.get("op") in ("eq", "in") and (twin, dim) not in have:
                    have.add((twin, dim))
                    out.append((i, str(w.get("title")), twin, dim))
    return out


def _outcome_notes(dem: dict | None, dataset_id: int) -> list[str]:
    """What the person asks about, when it is an outcome of the rows rather
    than a part of them: said first among the notes."""
    out = []
    for o in (dem or {}).get("outcomes") or []:
        if o.get("dataset_id") != dataset_id or not o.get("column"):
            continue
        values = ", ".join(repr(v) for v in o.get("values") or [])
        out.append(f"THEY ASK ABOUT the rows where `{o['column']}` is {values} ({o.get('matched_rows'):,} of "
                   f"{o.get('of_rows'):,} rows). That is an OUTCOME, measured over ALL the rows: give its count "
                   f"(a filter on `{o['column']}`), its share of all rows, and compare groups by the SHARE with "
                   f"that outcome. Charts about the outcome itself (its reasons, its list) filter on it; never "
                   f"drop the other rows from the whole page.")
    return out


def _given(dem: dict | None, dataset_id: int) -> set[str]:
    return {demand_service._norm(v) for s in (dem or {}).get("scope") or []
            if s.get("dataset_id") == dataset_id and s.get("status") == "in_data" and not s.get("column")
            for v in s.get("values") or []}


def _reading_for(meaning_map, tables: list[str] | None, columns: set[str] | None = None) -> str:
    if not meaning_map:
        return ""
    from . import meaning
    return meaning.prompt_text(meaning_map, tables or None, columns)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for r, i in enumerate(order):
        ranks[i] = float(r)
    return ranks


def follows(counts: dict[str, float], sizes: dict[str, float]) -> bool:
    """True when the ranking of groups by `counts` is essentially their
    ranking by size, and the sizes really differ: the chart then says who is
    big, not who stands out."""
    names = [n for n in counts if n in sizes]
    if len(names) < 3:
        return False
    big, small = max(sizes[n] for n in names), min(sizes[n] for n in names)
    if small <= 0 or big / small < 2:
        return False
    a, b = _ranks([counts[n] for n in names]), _ranks([sizes[n] for n in names])
    n = len(names)
    d2 = sum((x - y) ** 2 for x, y in zip(a, b))
    return 1 - 6 * d2 / (n * (n * n - 1)) >= 0.7


async def add_rates(pages: list[dict], gate: "Gate", lang: str) -> None:
    """The size check (docs/meaning-map/PLAN.md, step 4), without a model.

    A chart that COUNTS an outcome per group -- late parcels by region,
    parcels with a complaint by branch -- gets the SHARE per group beside
    it, drawn from the same rows. Groups too small to rank by a rate are left
    out of it. When the count merely follows each group's size the share
    comes first and the count says so."""
    from . import meaning
    from ..suggest_dataset_dashboard import _probe
    from ..suggest_inputs import drawn_key
    have = {((w.get("config") or {}).get("measure"), (w.get("config") or {}).get("dimension"))
            for p in pages for w in p["widgets"]}
    for page in pages:
        out = []
        for w in page["widgets"]:
            c = w.get("config") or {}
            dim = c.get("dimension")
            outcome = [f for f in c.get("filters") or [] if isinstance(f, dict) and f.get("op") in ("eq", "in")
                       and f.get("column") not in (dim, None) and f.get("column") not in gate.scoped
                       and not (isinstance(f.get("value"), list) and len(f["value"]) != 1)]
            if (w.get("widget_type") != "bar" or not dim or dim in gate.dates or c.get("dimension2")
                    or not str(c.get("aggregation") or "").startswith("count") or not outcome
                    or len(page["widgets"]) >= PAGE_WIDGETS[1] + 2):
                out.append(w)
                continue
            rate, _why = await gate.one({**w, "title": _t(lang, "rate", title=w.get("title") or ""),
                                         "why": _t(lang, "ratewhy"), "widget_type": "bar",
                                         "config": {k: v for k, v in c.items() if k not in ("limit",)}})
            rc = (rate or {}).get("config") or {}
            shares = [v for _n, v in (_series(gate.results.get(_key(rate)) or {}) or [])] if rate else []
            # Split by a column that only describes the outcome itself (the
            # reason of a return): every group is 100% or 0%, which says nothing.
            if (rate is None or rc.get("measure") not in gate.percent
                    or all(v >= 99.5 or v <= 0.5 for v in shares)):
                out.append(w)
                continue
            # The rate may already be on the page (the designer drew it): the
            # count beside it is still told apart from it, the same way.
            already = (rc.get("measure"), dim) in have
            # Sizes: the rows of each group, whatever became of them.
            base = {**c, "aggregation": "count", "filters": [f for f in rc.get("filters") or []
                                                             if f.get("column") not in gate.flag_of.values()]}
            base.pop("limit", None)
            sizes: dict[str, float] = {}
            drew, _n, _w = await _probe({"widget_type": "bar", "config": base}, gate.inputs.probe)
            if drew:
                sizes = dict(_series(gate.inputs.drawn.get(drawn_key("bar", base)) or {}, lang) or [])
            if already:
                counts = dict(_series(gate.results.get(_key(w)) or {}, lang) or [])
                marked = _t(lang, "bysize")
                out.append({**w, "finding": (w.get("finding") or "") + marked}
                           if follows(counts, sizes) and marked not in (w.get("finding") or "") else w)
                continue
            small = [n for n, v in sizes.items() if v < meaning.MIN_BASE]
            if small and len(sizes) - len(small) >= 2:
                raw = dict(_series(gate.inputs.drawn.get(drawn_key("bar", base)) or {}) or [])
                keep = [n for n, v in raw.items() if v >= meaning.MIN_BASE]
                again, _why = await gate.one({**rate, "config": {
                    **rc, "filters": list(rc.get("filters") or []) + [{"column": dim, "op": "in", "value": keep}]}})
                if again is not None:
                    rate = {**again, "why": _t(lang, "ratewhy") + _t(lang, "small", n=meaning.MIN_BASE)}
            have.add(((rate.get("config") or {}).get("measure"), dim))
            counts = dict(_series(gate.results.get(_key(w)) or {}, lang) or [])
            if follows(counts, sizes):
                out += [rate, {**w, "finding": (w.get("finding") or "") + _t(lang, "bysize")}]
            else:
                out += [w, rate]
        page["widgets"] = out


def derived_for(pages: list[dict], inputs, made: list[dict] | None = None) -> dict:
    """The percent twins the kept charts use: what the builder must create on
    the dataset before it draws them."""
    used = json.dumps([w.get("config") for p in pages for w in p.get("widgets") or []], default=str, ensure_ascii=False)
    cols = [{k: v for k, v in c.items() if k not in ("of", "is", "value", "columns", "low", "high")}
            for c in list(getattr(inputs, "shares", None) or []) + list(getattr(inputs, "groups", None) or [])
            + list(made or [])
            if f'"{c["name"]}"' in used]
    return {"measures": [], "calculated_columns": cols}


def with_captions(pages: list[dict], gate: "Gate") -> None:
    for p in pages:
        p["widgets"] = [{**w, "config": {**w["config"], "caption": gate.captions[_key(w)]}}
                        if _key(w) in gate.captions else w for w in p["widgets"]]


def without_scope(widget: dict, scope_filters: list[dict]) -> dict:
    """The widget without the person's scope in its own filters: the scope is
    set ONCE on the dashboard (a common filter), where it can be seen and
    taken off in one place -- not buried in every chart."""
    if not scope_filters or not isinstance(widget.get("config"), dict):
        return widget
    marks = {json.dumps(f, sort_keys=True, default=str) for f in scope_filters}
    own = [f for f in widget["config"].get("filters") or []
           if json.dumps(f, sort_keys=True, default=str) not in marks]
    config = {k: v for k, v in widget["config"].items() if k != "filters"}
    return {**widget, "config": {**config, **({"filters": own} if own else {})}}


def _finish(pages: list[dict], dem: dict, note: str | None, lang: str,
            scope_filters: list[dict] | None = None, refusals: dict | None = None) -> list[dict]:
    asked = {q["id"]: q["text"] for q in dem.get("questions") or []}
    out = []
    for p in pages:
        if not p["widgets"]:
            continue
        p = {**p, "widgets": [without_scope(w, scope_filters or []) for w in p["widgets"]]}
        head = answer_widget(p, note)
        out.append({"title": p["title"], "rationale": p["rationale"], "answer": p.get("answer") or "",
                    "note": note, "scope_filters": list(scope_filters or []),
                    "answers": [q for q in asked if any(w.get("question") == q for w in p["widgets"])],
                    "widgets": ([head] if head else []) + p["widgets"]})
    # Said once, on the first page, and only for what the person asked
    # themselves: a question the setup added and could not chart is not theirs.
    answered = {q for p in out for q in p["answers"]}
    own = {q["id"] for q in dem.get("questions") or [] if q.get("asked", True)}
    # "Could not answer" always says why (persona test 2026-10-12: the gender
    # pay gap, the share of late orders and the price drop per year were all
    # "could not answer" on data that held the columns).
    missing = [_t(lang, "unansweredWhy", q=text, why=_reason(refusals.get(q))) if (refusals or {}).get(q)
               else _t(lang, "unansweredNone", q=text)
               for q, text in asked.items() if q in own and q not in answered]
    for i, p in enumerate(out):
        p["unanswered"] = missing if i == 0 else []
    return out


def _reason(why: str | None) -> str:
    """A refusal without the chart title it was written against ("'X': ...")."""
    text = str(why or "").strip()
    return re.sub(r"^'[^']*':\s*", "", text)


PICKS_SCHEMA = {
    "type": "object",
    "properties": {"pages": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "rationale": {"type": "string"},
            "picks": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "question": {"type": "string"},
                               "title": {"type": "string"}, "why": {"type": "string"},
                               # One listed value of a column the chart is narrowed to (`parts_of`).
                               "part": {"type": "integer"}},
                "required": ["id", "question", "why"]}},
        },
        "required": ["title", "rationale", "picks"]}}},
    "required": ["pages"],
}
#: Charts shown to the model to choose from (the list is its whole menu):
#: what the platform FOUND (statistics, discovery) and the plain charts of
#: every column an ordinary question is answered with.
MAX_FOUND = 40
MAX_STANDARD = 90
MAX_CARDS = MAX_FOUND + MAX_STANDARD
#: Columns the plain charts are made for, richest first.
STANDARD_GROUPS = 8
STANDARD_NUMBERS = 4
STANDARD_SHARES = 3


#: The first word of a column's name that already says how it is rolled up.
_SAID_ALREADY = {"sum": ("total", "sum"), "avg": ("average", "avg", "mean"), "median": ("median", "typical"),
                 "max": ("max", "maximum", "highest"), "min": ("min", "minimum", "lowest")}


def standard_cards(profile: dict, shares: list[dict] | None, column_meta: dict | None,
                   ineligible: set[str] | frozenset = frozenset()) -> list[dict]:
    """The plain charts of this data, made from its shape alone: how many, per
    group, over time -- and for each yes/no column its share, for each number
    its total or its typical value. Nothing here is a finding; it is the menu
    an ordinary question ("which group has most?", "what share is X?") is
    answered from when the model may only choose (live 2026-10-11: with the
    found charts alone, three of five questions had nothing to choose)."""
    from ..analyst_panel import _not_additive
    from ..semantic_guard import default_summary
    cols = [c for c in profile.get("columns", []) if c["name"] not in ineligible and not c.get("is_personal")]
    made = {c["name"] for c in shares or []}
    label = lambda m: str(m).replace("_", " ")                                  # noqa: E731
    groups = [c["name"] for c in sorted(
        (c for c in cols if c.get("role") == "categorical" and not c.get("is_identifier")
         and c["name"] not in made and 2 <= (c.get("distinct") or 0) <= 60),
        key=lambda c: (c.get("distinct") or 0))][:STANDARD_GROUPS]
    numbers = [c["name"] for c in cols if c.get("role") == "numeric" and not c.get("is_identifier")
               and c["name"] not in made][:STANDARD_NUMBERS]
    rates = [c for c in shares or [] if c.get("is") == "yes"][:STANDARD_SHARES]
    dates = [c["name"] for c in cols if c.get("role") == "datetime"][:1]
    counted = next((c["name"] for c in cols if c.get("is_identifier")), cols[0]["name"] if cols else None)
    if counted is None:
        return []

    words = {"sum": "Total", "avg": "Average", "median": "Typical", "max": "Highest", "min": "Lowest"}

    def how(m: str) -> tuple[str, str] | None:
        # As the platform rolls the column up when nobody said (the author's
        # setting, the stored classification, then the name).
        agg = default_summary(m, column_meta)
        if agg == "sum" and _not_additive(m, column_meta):
            agg = "avg"
        return (agg, words[agg]) if agg in words else None

    measures: list[tuple[str, str, str, str]] = [(counted, "count", "Number of records", "how many there are")]
    for r in rates:
        what = label(r["of"])
        measures.append((r["name"], "avg", f"Share where {what} is yes (%)", f"what share of the records have {what}"))
    for m in numbers:
        got = how(m)
        if got is None:
            continue
        agg, word = got
        # A column already named for how it is rolled up ("total shipments",
        # "avg days") is not given the word twice.
        said = label(m).casefold().split()
        named = bool(said) and said[0] in _SAID_ALREADY.get(agg, ())
        title = label(m).capitalize() if named else f"{word} {label(m)}"
        measures.append((m, agg, title, f"the {word.lower()} of {label(m)}" if not named else label(m)))

    out: list[dict] = []

    def add(wt: str, title: str, why: str, config: dict) -> None:
        out.append({"widget_type": wt, "title": title, "why": why, "config": config, "source": "standard"})

    for m, agg, title, why in measures:
        add("kpi", title, f"One number: {why}.", {"measure": m, "aggregation": agg})
    for g in groups:
        for m, agg, title, why in measures:
            add("bar", f"{title} by {label(g)}", f"Compares {why} across each {label(g)}.",
                {"dimension": g, "measure": m, "aggregation": agg, "sort": "desc", **({"limit": TOP_N} if agg else {})})
    for d in dates:
        for m, agg, title, why in measures:
            add("line", f"{title} by month", f"Shows how {why} changed month by month.",
                {"dimension": d, "measure": m, "aggregation": agg, "dimension_granularity": "month"})
    for i, a in enumerate(groups[:3]):
        for b in groups[i + 1:3]:
            add("heatmap", f"Number of records by {label(a)} and {label(b)}",
                f"Shows which {label(a)} goes with which {label(b)}.",
                {"dimension": a, "dimension2": b, "measure": counted, "aggregation": "count"})
    return out[:MAX_STANDARD]


def without_impossible(dem: dict, filters: list[dict], df) -> dict:
    """The Demand without the questions the SETUP added that the page's own
    scope rules out: once the page is narrowed to one value of a column, a
    question that names that column, or another of its values, asks for a
    comparison the page can no longer make. The person's own questions are
    never touched -- those are answered or said to be unanswered."""
    narrowed: dict[str, set[str]] = {}
    for f in filters or []:
        col, val = (f.get("column"), f.get("value")) if isinstance(f, dict) else (None, None)
        if col is None or f.get("op") not in ("eq", "in"):
            continue
        kept = {str(v).casefold() for v in (val if isinstance(val, list) else [val])}
        if len(kept) == 1:
            narrowed[str(col)] = kept
    if not narrowed:
        return dem
    out = []
    for q in dem.get("questions") or []:
        text = " " + re.sub(r"[^\w]+", " ", str(q.get("text") or "").casefold()) + " "
        ruled_out = False
        if not q.get("asked", True):
            for col, kept in narrowed.items():
                words = " " + col.replace("_", " ").casefold() + " "
                others = set()
                if col in getattr(df, "columns", []):
                    others = {str(v).casefold() for v in df[col].dropna().unique().tolist()[:200]} - kept
                if words in text or words.rstrip() + "s " in text or any(
                        len(v) >= 3 and f" {re.sub(r'[^\w]+', ' ', v)} " in text for v in others):
                    ruled_out = True
                    break
        if not ruled_out:
            out.append(q)
    return {**dem, "questions": out} if len(out) != len(dem.get("questions") or []) else dem


def setup_selection_mode(selection: str | None = None) -> str:
    """cards | free | both, as set now (settings.setup_ai_selection)."""
    if selection in ("cards", "free", "both"):
        return selection
    from ...core.config import settings
    mode = str(getattr(settings, "setup_ai_selection", "free") or "free")
    return mode if mode in ("cards", "free", "both") else "free"


async def validated_cards(inputs, facts: dict, scoped) -> list[dict]:
    """The charts the PLATFORM makes for these rows, with no model: the
    statistics engine's, the standard series, and what the discovery engine
    found in a look at the rows. In "cards" mode (settings.suggest_ai_selection)
    these are the only charts a page can hold -- the model chooses among them."""
    import pandas as pd
    from ..analyst_panel import (_section_for, choose_lenses, completion_trends, money_totals, rule_candidates,
                                 series_backbone)
    from ..discovery import engine as discovery
    from ..insights import effective_roles, generate_insights, order_event_dates
    roles = effective_roles(inputs.type_map, inputs.column_meta)
    ineligible = inputs.ineligible()
    profile = inputs.profile
    dates = sorted(c["name"] for c in profile.get("columns", []) if c.get("role") == "datetime")

    def build() -> list[dict]:
        found = generate_insights(scoped, inputs.type_map, inputs.column_meta)
        cards = rule_candidates(scoped, roles, inputs.column_meta, ineligible, found.get("findings") or [])
        if "exceptions" in choose_lenses(profile, facts.get("facts") or []):
            cards += series_backbone(profile, ineligible, facts.get("identical") or {}, order_event_dates(dates))
        cards += completion_trends(profile, ineligible)
        cards += money_totals(profile, ineligible, facts.get("mixed_units") or {}, facts.get("identical") or {})
        try:
            own = scoped[[c for c in scoped.columns if c in inputs.type_map]] if isinstance(scoped, pd.DataFrame) else scoped
            cards += discovery.candidates(own, inputs.type_map, inputs.column_meta,
                                          lambda wt, cfg: _section_for(wt, cfg, set(dates)))
        except Exception:                                           # noqa: BLE001 -- extra ideas, never a gate
            logger.warning("guided setup: discovery candidates failed", exc_info=True)
        return cards

    out, seen = [], set()
    found = (await asyncio.to_thread(build))[:MAX_FOUND]
    plain = standard_cards(profile, getattr(inputs, "shares", None), inputs.column_meta, ineligible)
    for w in found + plain:
        if not isinstance(w, dict) or not isinstance(w.get("config"), dict) or not w.get("widget_type"):
            continue
        key = json.dumps([w["widget_type"], w["config"]], sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
    return out[:MAX_CARDS]


#: A ready chart may be narrowed to ONE value of a category: the values offered.
PART_MAX_DISTINCT = 12
PART_VALUES = 8
PART_MIN_ROWS = 20
MAX_PARTS = 40


def parts_of(profile: dict, df, ineligible: set[str] | frozenset = frozenset(),
             skip: set[str] | frozenset = frozenset()) -> list[dict]:
    """The parts of the rows a ready chart may be drawn on: one value of a
    category with few values -- [{"column", "value", "rows"}]. From the rows
    themselves, so every part exists and is large enough to say something
    about. Columns the page is already narrowed by (`skip`) offer none."""
    out = []
    for c in profile.get("columns", []):
        name = c.get("name")
        if (c.get("role") not in ("categorical", "boolean") or c.get("is_identifier") or c.get("is_personal")
                or name in ineligible or name in skip or name not in getattr(df, "columns", [])):
            continue
        counts = df[name].dropna().value_counts()
        if not (2 <= len(counts) <= PART_MAX_DISTINCT):
            continue
        for value, n in counts.head(PART_VALUES).items():
            if int(n) >= PART_MIN_ROWS:
                out.append({"column": name, "value": value.item() if hasattr(value, "item") else value, "rows": int(n)})
    return out[:MAX_PARTS]


def _splits_by(config: dict, column: str) -> bool:
    return (column in (config.get("dimension"), config.get("dimension2"), config.get("measure"))
            or any(isinstance(f, dict) and f.get("column") == column for f in config.get("filters") or []))


def pick_messages(cards: list[dict], dem: dict, scope: list[str], scoped_rows: int, count: int, lang: str,
                  parts: list[dict] | None = None) -> list[dict]:
    listing = "\n".join(
        f"{i} | {w.get('widget_type')} | {str(w.get('title') or '')[:90]} | "
        f"{str(w.get('takeaway') or w.get('why') or '')[:140]}" for i, w in enumerate(cards))
    system = (
        "You lay out the pages of ONE dashboard for one person who said what they want. Every chart in the list "
        "has already been built on their data by the platform; the last column says what it shows.\n"
        "- For each of their questions choose the charts that answer it, by id; `question` is that question's "
        "id (q1, q2...). Choose ONLY from the list. You cannot change a chart or add one.\n"
        "- A question that no chart in the list answers gets none: do not stretch a chart to fit.\n"
        f"- Group what you chose into up to {count} pages, each a different angle on what they asked. Give each "
        "a short title and one sentence on what it tells them.\n"
        "- `title` says what the chart shows in the person's own vocabulary; `why` is one short sentence on what "
        f"they learn from it. Write titles, sentences and whys in {_LANGUAGE.get(lang, 'English')}.")
    user = (f"{_demand_text(dem, scope, scoped_rows, lang)}\n\n"
            f"THE CHARTS (id | kind | title | what it shows)\n{_data_block(listing)}")
    if parts:
        system += (
            "\n- A question about ONE part of the rows (one value of a column) is answered by a chart from the "
            "list drawn on that part alone: add `part`, the part's id from THE PARTS. Its title must then say "
            "which part it is. Never give a part to a chart that already splits by that part's column, and "
            "leave `part` out when the question is about all the rows. Use a part only when the question names "
            "that very value; a value that merely resembles what was asked is NOT it -- when the part asked for "
            "is not in THE PARTS, the question has no chart.")
        user += ("\n\nTHE PARTS (id | column = value | rows)\n" + _data_block("\n".join(
            f"{i} | {p['column']} = {p['value']} | {p['rows']:,}" for i, p in enumerate(parts))))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def pick_pages(client, cards: list[dict], dem: dict, scope: list[str], scoped_rows: int, count: int,
                     lang: str, parts: list[dict] | None = None) -> list[dict]:
    """Pages in the designer's own shape, every widget one of `cards` -- as it
    is, or narrowed to one of `parts`. An id outside either list is dropped
    (the part alone, when the chart is real: the chart then stands on all the
    rows); a failure is no pages, never an error."""
    if client is None or not cards:
        return []
    try:
        got = await client.complete_json(pick_messages(cards, dem, scope, scoped_rows, count, lang, parts), PICKS_SCHEMA,
                                         max_tokens=3000, temperature=0.0, enforce=True)
    except Exception as exc:                                        # noqa: BLE001
        logger.warning("guided setup: choosing among the validated charts failed: %s", exc)
        return []
    pages, used = [], set()
    for page in [p for p in (got or {}).get("pages") or [] if isinstance(p, dict)][:count]:
        widgets = []
        for pick in page.get("picks") or []:
            i = pick.get("id") if isinstance(pick, dict) else None
            if isinstance(i, bool) or not isinstance(i, int) or not (0 <= i < len(cards)):
                continue
            card = cards[i]
            config = dict(card["config"])
            k = pick.get("part")
            part = (parts[k] if parts and isinstance(k, int) and not isinstance(k, bool) and 0 <= k < len(parts)
                    and not _splits_by(config, parts[k]["column"]) else None)
            if (i, k if part else None) in used:
                continue
            used.add((i, k if part else None))
            title = str(pick.get("title") or card.get("title") or card["widget_type"])
            if part:
                config["filters"] = list(config.get("filters") or []) + [
                    {"column": part["column"], "op": "eq", "value": part["value"]}]
                # The part is named even when the model forgot to: a chart of
                # some rows must not read as a chart of all of them.
                said = (f"{str(part['column']).replace('_', ' ')}: {part['value']}"
                        if isinstance(part["value"], bool) else str(part["value"]))
                if str(part["value"]).casefold() not in title.casefold() or isinstance(part["value"], bool):
                    title = f"{title} ({said})"
            widgets.append({"question": str(pick.get("question") or ""), "widget_type": card["widget_type"],
                            "title": title[:120],
                            "why": str(pick.get("why") or card.get("why") or "")[:200],
                            "config": config})
        if widgets:
            pages.append({"title": str(page.get("title") or ""), "rationale": str(page.get("rationale") or ""),
                          "widgets": widgets})
    return pages


async def design(db, user, ds, dem: dict | None, entry: dict | None, lang: str, count: int, client,
                 meaning_map=None, tables: list[str] | None = None, selection: str | None = None,
                 richness: str | None = None, elsewhere: set[str] | None = None,
                 foreign: set[str] | None = None, group_size: str | None = None) -> dict:
    """{"proposals": pages to choose from, "reason": why some ideas were dropped}.

    One generation and one repair round, like the app's designer: the refused
    charts go back with their reasons and are replaced, then questions still
    without a chart are asked for once more."""
    dem = dem or {}
    inputs, facts, filters, words, scoped_rows, total = await prepare(db, user, ds, dem)
    if client is None or not getattr(client, "enabled", True):
        return {"proposals": [], "reason": "off"}
    apart = set_apart(entry, inputs.df, filters)
    filters = filters + [f for v in apart for f in v["filters"]]
    dem = without_impossible(dem, filters, inputs.df)
    richness = richness_now(richness)
    know = inputs.knowledge
    reading = _reading_for(meaning_map, tables, {str(c) for c in inputs.df.columns})
    messages, allowed = build_messages(inputs.profile, dem, words, scoped_rows,
                                       _outcome_notes(dem, ds.id) + _notes(entry)
                                       + [f"Rows where `{a['column']}` is " + ", ".join(f"“{v}”" for v in a["values"])
                                          + " are left out of every chart by filters the person can see and remove: "
                                          "they are not the same kind of thing as the rest." for a in apart],
                                       count, lang,
                                       know, facts.get("text"), inputs.shares, reading, richness,
                                       getattr(inputs, "groups", None))
    ids = {q["id"] for q in dem.get("questions") or []}
    gate = Gate(inputs, facts, allowed, ids, filters, lang, _given(dem, ds.id), richness)
    gate.elsewhere, gate.context = set(elsewhere or set()), str(getattr(ds, "name", "") or "")
    gate.foreign = _not_held(foreign, inputs.df)
    gate.group_size = group_size if group_size and group_size in inputs.df.columns else None
    gate.asked_text = {q["id"]: str(q.get("text") or "") for q in dem.get("questions") or [] if q.get("id")}
    gate.wants = {q["id"]: q["wants"] for q in dem.get("questions") or [] if q.get("id") and q.get("wants")}
    gate.about = {q["id"]: list(q["about"]) for q in dem.get("questions") or [] if q.get("id") and q.get("about")}

    # Where the charts come from (settings.setup_ai_selection, the guided
    # setup's own switch beside the one for "Suggest dashboards"): cards --
    # the model only CHOOSES among charts the platform built for these rows;
    # free -- it designs its own, each then checked; both -- it chooses
    # first, and designs only for the questions no ready chart answered.
    mode = setup_selection_mode(selection)
    got, proposed = None, []
    if mode in ("cards", "both"):
        rows = getattr(inputs, "scoped", inputs.df)
        proposed = await pick_pages(client, await validated_cards(inputs, facts, rows), dem, words, scoped_rows,
                                    count, lang,
                                    parts_of(inputs.profile, rows, inputs.ineligible(), {f["column"] for f in filters}))
        got = {"pages": proposed}
    if not proposed and mode != "cards":
        got = await client.complete_json(messages, PAGES_SCHEMA, max_tokens=9000, temperature=0.2, enforce=True)
        proposed = [p for p in (got or {}).get("pages") or [] if isinstance(p, dict)][:count]
        gate.names = clean_names(got, inputs.df.columns)
    if not proposed:
        # In cards mode the caller falls back to the platform's own selection.
        return {"proposals": [], "reason": "failed"}
    pages, whys = await gate.pages(proposed)
    refused = [w for ws in whys for w in ws]
    answered = {w.get("question") for p in pages for w in p["widgets"]}
    missing = [q for q in dem.get("questions") or [] if q["id"] not in answered]
    if (refused or missing) and mode != "cards":
        ask = "Some of that needs completing.\n"
        if refused:
            ask += ("For EACH page, in the same order, give replacement widgets only -- one per refused chart "
                    "-- that answer the same question without the problem:\n" + "\n".join(
                        f"{i + 1}. {p.get('title')}: " + ("; ".join(whys[i]) if whys[i] else "nothing refused")
                        for i, p in enumerate(proposed)) + "\n")
        if missing:
            ask += ("These questions have no chart yet; add one for each to the page it fits best, if these "
                    "columns can answer it:\n" + "\n".join(f"- {q['id']}. {q['text']}" for q in missing) + "\n")
        ask += "Return the same pages, same titles, with ONLY the new widgets in each."
        try:
            more = await client.complete_json(
                messages + [{"role": "assistant", "content": json.dumps(got)[:12000]},
                            {"role": "user", "content": ask}],
                PAGES_SCHEMA, max_tokens=6000, temperature=0.2, enforce=True)
        except Exception:                                           # noqa: BLE001
            more = None
        extra = [p for p in (more or {}).get("pages") or [] if isinstance(p, dict)][:len(pages)]
        if extra:
            # Earlier pages' charts are already in `seen`: build on the same gate.
            have = gate.seen
            for i, page in enumerate(extra):
                widgets = [w for w in page.get("widgets") or [] if isinstance(w, dict)]
                for w, _why in await asyncio.gather(*(gate.one(w) for w in widgets)) if widgets else []:
                    if (w is None or _key(w) in have or _reading(w) in have
                            or len(pages[i]["widgets"]) >= PAGE_WIDGETS[1] + 1):
                        continue
                    if w["widget_type"] in gate.advanced and sum(
                            x["widget_type"] in gate.advanced for x in pages[i]["widgets"]) >= gate.max_advanced:
                        continue
                    have.update((_key(w), _reading(w)))
                    pages[i]["widgets"].append(w)
    if refused:
        logger.info("guided setup: charts refused for dataset %s: %s", ds.id, " || ".join(refused)[:3000])
    pages = [p for p in pages if p["widgets"]]
    await add_rates(pages, gate, lang)
    for p in pages:
        # The headline numbers lead, as a person reads a page.
        p["widgets"].sort(key=lambda w: 0 if w["widget_type"] in ("kpi", "card", "gauge") else 1)
    await write_answers(pages, gate, dem, lang, client)
    made = derived_for(pages, inputs, gate.made)
    with_captions(pages, gate)
    note = scope_note(words, filters, scoped_rows, total, lang, dem, ds.id, apart, gate.names)
    for column, still in gate.open_notes.items():
        said = _t(lang, "open", col=column.replace("_", " "), values=", ".join(f"“{v}”" for v in still))
        note = f"{note} {said}" if note else said
    proposals = _finish(pages, dem, note, lang, filters, gate.refusals)
    # Options, click-to-filter and navigation: plain code, after the charts are chosen (dress.py).
    from . import dress
    try:
        await dress.apply(proposals, gate, inputs, lang)
    except Exception:                                               # noqa: BLE001 -- the pages stand without it
        logger.warning("guided setup: dressing the pages failed", exc_info=True)
    return {"proposals": proposals, "reason": "; ".join(refused[:6]),
            "derived": made}


async def change(db, user, ds, dem: dict | None, entry: dict | None, page: dict, message: str,
                 lang: str, client, meaning_map=None, tables: list[str] | None = None) -> dict | None:
    """One page changed as the person asks: charts they did not mention stay
    exactly as they are. None when nothing usable came back."""
    dem = dem or {}
    if client is None or not getattr(client, "enabled", True):
        return None
    inputs, facts, filters, words, scoped_rows, total = await prepare(db, user, ds, dem)
    apart = set_apart(entry, inputs.df, filters)
    filters = filters + [f for v in apart for f in v["filters"]]
    messages, allowed = build_messages(inputs.profile, dem, words, scoped_rows,
                                       _outcome_notes(dem, ds.id) + _notes(entry), 1, lang,
                                       inputs.knowledge, facts.get("text"), inputs.shares,
                                       _reading_for(meaning_map, tables, {str(c) for c in inputs.df.columns}),
                                       groups=getattr(inputs, "groups", None))
    scoped = {f["column"] for f in filters}
    current = [{"question": w.get("question") or "", "widget_type": w["widget_type"], "title": w.get("title"),
                "why": w.get("why") or "",
                "config": {**w["config"], "filters": [f for f in w["config"].get("filters") or []
                                                      if f.get("column") not in scoped]}}
               # Words, buttons and filter controls are not charts: they are put back afterwards.
               for w in page.get("widgets") or [] if w.get("widget_type") not in ("text", "slicer", "button")]
    ask = ("This page was proposed:\n" + json.dumps({"pages": [{"title": page.get("title"),
                                                               "rationale": page.get("rationale"),
                                                               "widgets": current}]}, default=str)[:9000]
           + f"\n\nThe person now asks: {message}\n\nReturn the ONE page, changed as they ask. Keep every widget "
             "they did not mention exactly as it is (same config). A chart they ask for may answer a new "
             "question of theirs: give it the id of the closest listed question.")
    got = await client.complete_json(messages + [{"role": "user", "content": ask}], PAGES_SCHEMA,
                                     max_tokens=6000, temperature=0.2, enforce=True)
    proposed = [p for p in (got or {}).get("pages") or [] if isinstance(p, dict)][:1]
    if not proposed:
        return None
    # A chart asked for by name may be advanced: the person's word is the condition.
    gate = Gate(inputs, facts, allowed, {q["id"] for q in dem.get("questions") or []}, filters, lang,
                _given(dem, ds.id))
    gate.names = clean_names(got, inputs.df.columns)
    pages, _whys = await gate.pages(proposed)
    if not pages or not pages[0]["widgets"]:
        return None
    await add_rates(pages, gate, lang)
    await write_answers(pages, gate, dem, lang, client)
    made = derived_for(pages, inputs, gate.made)
    with_captions(pages, gate)
    done = _finish(pages, dem, scope_note(words, filters, scoped_rows, total, lang, dem, ds.id, apart, gate.names), lang, filters)
    if not done:
        return None
    # The page keeps its buttons, filters and click-to-filter; a new chart gets its options (dress.redress).
    from . import dress
    try:
        await dress.redress(done[0], page, gate, inputs, lang, richness_now())
    except Exception:                                               # noqa: BLE001 -- the page stands without it
        logger.warning("guided setup: dressing the changed page failed", exc_info=True)
    return {**done[0], "_derived": made}
