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
#: Slices a donut can carry before a bar reads better; bars before a top list does.
DONUT_MAX = 5
BAR_MAX = 12
TOP_N = 10
#: Points a line carries before it is drawn by month instead.
TIME_POINTS_MAX = 80
#: Values closer together than this share of their size say "the same everywhere".
FLAT_SHARE = 0.03
#: A chart mostly made of "unknown" describes the gap, not the subject.
UNKNOWN_SHARE = 0.6
PROBE_CONCURRENCY = 4
PAGE_WIDGETS = (3, 6)

_UNKNOWN = {"", "unknown", "none", "nan", "null", "n/a", "na", "غير معروف", "(blank)", "other"}
_CHANGE = re.compile(r"(change|chg|growth|delta|diff|return|pct|percent)", re.I)
_LANGUAGE = {"ar": "Arabic (Modern Standard, simple words)", "en": "English"}

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
                               "config": {"type": "object"}},
                "required": ["question", "widget_type", "title", "why", "config"]}},
        },
        "required": ["title", "rationale", "widgets"]}}},
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
           "scope": "Showing only {what} — {n} of {total} rows. Remove the dashboard's filter to see everything.", "scoped": "This data holds only {what}.",
           "unanswered": "This data could not answer: {q}",
           "nomatch": "This data has nothing called “{what}”, so this page shows everything it holds.",
           "nobase": "These are counts of {events}, not rates: this data does not hold the {base} they are counted "
                     "against, and a bigger group has more of everything. Go back to Choose data and take the "
                     "suggestion that includes the {base} to compare groups fairly.",
           "rate": "{title} — share of each group (%)",
           "ratewhy": "The share within each group, so that big groups do not lead only because they are big.",
           "small": " Groups with fewer than {n} rows are left out.",
           "bysize": " (follows the size of each group)",
           "flat": "it shows the same value everywhere", "single": "it has only one group to show",
           "unknown": "most of it is “unknown”", "zero": "its number is exactly zero",
           "tied": "its top values are all the same", "empty": "it has nothing to show",
           "advanced": "a simpler chart answers this", "noq": "it does not say which question it answers"},
    "ar": {"high": "الأعلى: {a} ({x})؛ الأدنى: {b} ({y})", "one": "{a}: {x}",
           "trend": "{a}: {x} ← {b}: {y} ({pct})", "rows": "{n} سجل",
           "scope": "المعروض فقط: {what} — {n} من {total} صف. احذف فلتر اللوحة لعرض كل شيء.", "scoped": "هذه البيانات تحتوي فقط على {what}.",
           "unanswered": "تعذّر على هذه البيانات الإجابة عن: {q}",
           "nomatch": "لا يوجد في هذه البيانات ما يسمى «{what}»، لذلك تعرض هذه الصفحة كل ما فيها.",
           "nobase": "هذه أعداد {events} وليست نسبًا: هذه البيانات لا تحتوي على {base} التي تُحسب نسبةً إليها، "
                     "والمجموعة الأكبر لديها أكثر من كل شيء. ارجع إلى «اختيار البيانات» واختر الاقتراح الذي يتضمن "
                     "{base} لمقارنة عادلة.",
           "rate": "{title} — النسبة داخل كل مجموعة (٪)",
           "ratewhy": "النسبة داخل كل مجموعة، حتى لا تتصدر المجموعات الكبيرة لمجرد أنها كبيرة.",
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
    if wt in ("kpi", "gauge"):
        return fmt(series[0][1])
    if wt == "card":
        return "; ".join(_t(lang, "one", a=n.replace("_", " "), x=fmt(v)) for n, v in series[:4])
    if is_time(widget, dates):
        # A last period still filling up is not where the trend ends.
        if result.get("partial_period") and len(series) > 2:
            series = series[:-1]
        (a, x), (b, y) = series[0], series[-1]
        pct = f"{(y - x) / abs(x) * 100:+.0f}%" if x else "—"
        return _t(lang, "trend", a=a, x=fmt(x), b=b, y=fmt(y), pct=pct)
    hi, lo = max(series, key=lambda p: p[1]), min(series, key=lambda p: p[1])
    return _t(lang, "high", a=hi[0], x=fmt(hi[1]), b=lo[0], y=fmt(lo[1]))


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

def menu(profile: dict) -> tuple[list[str], str]:
    """(types that may be used, the menu text): simple first, advanced with its condition."""
    from ..suggest_dataset_dashboard import REQUIRED_ROLES, WIDGET_GUIDE, usable_widgets
    from ..widget_roles import config_key_for_role
    usable = set(usable_widgets(profile))

    def line(wt: str, note: str = "") -> str:
        keys = ", ".join(config_key_for_role(r) for r in REQUIRED_ROLES.get(wt, ())) or "no required fields"
        return f"- {wt}: {WIDGET_GUIDE[wt]}{note}\n    requires: {keys}"

    simple = [wt for wt in SIMPLE if wt in usable]
    advanced = [wt for wt in ADVANCED if wt in usable]
    text = "SIMPLE CHARTS -- use these for almost everything:\n" + "\n".join(line(wt) for wt in simple)
    if advanced:
        text += ("\n\nADVANCED CHARTS -- at most one per page, and only under its condition:\n"
                 + "\n".join(line(wt, f" {ADVANCED[wt]}.") for wt in advanced))
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


def build_messages(profile: dict, dem: dict, scope: list[str], scoped_rows: int, notes: list[str],
                   count: int, lang: str, knowledge=None, facts: str | None = None,
                   shares: list[dict] | None = None, reading: str = "") -> tuple[list[dict], list[str]]:
    from ..dataset_profile import describe_for_prompt
    allowed, menu_text = menu(profile)
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
        "  An advanced chart only under the condition written beside it; when in doubt, simple.\n"
        "- 'How many are X' (late, returned, cancelled...) is answered by the COUNT and by its "
        "SHARE of the whole, shown as a kpi beside the count. And when comparing groups on X, "
        "compare the SHARE per group: the biggest group always has the biggest count, which tells "
        "them nothing about where the problem is. A share is the `avg` of the column's percent "
        "twin when one is listed under SHARES below (never a filter on that column as well); "
        "otherwise the `avg` of the yes/no column.\n"
        "- Titles say what the chart shows in the person's own vocabulary, never column names. "
        "`why` is one short sentence: what they learn from it.\n"
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
            + ("TRUE" if c.get("is") == "yes" else "FALSE") + ", in percent."
            for c in shares if c.get("is") != "label")
           + "\nPick the column for what the TITLE says: a title about the outcome being true (late, "
             "returned, active) takes the TRUE column; a title about the opposite (on time, kept, "
             "inactive) takes the FALSE column. A title must never promise the opposite of its column.\n"
           if shares else "")
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


class Gate:
    """Checks, draws and judges proposed widgets for one dataset."""

    def __init__(self, inputs, facts: dict, allowed: list[str], question_ids: set[str],
                 scope_filters: list[dict], lang: str, given: set[str] | None = None):
        #: Values the dataset is ALREADY narrowed to by its own query.
        self.given = given or set()
        self.inputs, self.facts, self.allowed = inputs, facts, set(allowed)
        self.question_ids, self.scope_filters, self.lang = question_ids, scope_filters, lang
        self.dates = {c["name"] for c in inputs.profile.get("columns", []) if c.get("role") == "datetime"}
        shares = getattr(inputs, "shares", None) or []
        self.percent = {c["name"] for c in shares if c.get("is") != "label"}
        self.twins = {c["of"]: c["name"] for c in shares if c.get("is") == "yes"}
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
        self._sem = asyncio.Semaphore(PROBE_CONCURRENCY)

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
        if self.question_ids and widget.get("question") not in self.question_ids:
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
        elif cfg.get("measure") in self.percent and not averaged:
            cfg = {**cfg, "aggregation": "avg"}
            widget = {**widget, "config": cfg}
        flag = self.flag_of.get(cfg.get("measure"))
        if flag:
            # A share of an outcome is over ALL rows where the outcome is known:
            # a filter to "yes" (or "no") would make it 100% (or 0%). Rows where
            # it is not known yet count for neither side.
            same = {flag, self.labels.get(flag), self.twins.get(flag), f"{flag}{NOT_SUFFIX}"}
            rest = [f for f in cfg.get("filters") or [] if not (isinstance(f, dict) and f.get("column") in same)]
            widget = {**widget, "config": {**cfg, "filters": rest
                                           + [{"column": flag, "op": "in", "value": [True, False]}]}}
        keep = {k: widget.get(k) for k in ("question", "why")}
        fixed, ok, why = repair_and_check(
            {**widget, "source": "model"}, self.inputs.profile, self.inputs.column_meta,
            self.facts.get("mixed_units"), self.facts.get("one_to_one"), self.facts.get("identical"),
            self.facts.get("edges"))
        if not ok:
            return None, str(why)
        fixed = polish_widget({k: v for k, v in fixed.items() if k != "source"}, self.inputs.profile)
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
        """A title that promises a share over a COUNT of the rows where a
        column holds one value ("Share returned": count, status = Returned)
        shows a count. Drawn instead as what it says: the average of a
        percent column that is 100 on those rows -- made here, created on the
        dataset when the page is built."""
        cfg = widget.get("config") or {}
        if not _SHARE_WORD.search(str(widget.get("title") or "")) or cfg.get("measure") in self.percent \
                or not str(cfg.get("aggregation") or "").startswith("count"):
            return widget
        df = self.inputs.df
        for f in cfg.get("filters") or []:
            col, op, val = (f.get("column"), f.get("op"), f.get("value")) if isinstance(f, dict) else (None,) * 3
            val = val[0] if isinstance(val, list) and len(val) == 1 else val
            if (op not in ("eq", "in") or isinstance(val, (list, dict)) or col not in df.columns
                    or col == cfg.get("dimension") or not _IDENT.match(str(col)) or '"' in str(val)):
                continue
            if col in self.twins and str(val).casefold() in ("true", "false"):
                name = self.twins[col] if str(val).casefold() == "true" else f"{col}{NOT_SUFFIX}"
            else:
                slug = re.sub(r"[^A-Za-z0-9]+", "_", str(val)).strip("_").lower() or "value"
                name = f"{col}_{slug}{SHARE_SUFFIX}"
                if name not in df.columns:
                    from ..widget_data import apply_calculated_columns
                    literal = str(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else f'"{val}"'
                    calc = {"name": name, "expression": f"IF({col} == {literal}, 100, 0)", "dtype": "numeric",
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

    async def one(self, widget: dict) -> tuple[dict | None, str]:
        """(the widget ready to offer, '') or (None, why not)."""
        if not isinstance(widget, dict) or not isinstance(widget.get("config"), dict):
            return None, "not a widget"
        title = widget.get("title") or widget.get("widget_type")
        try:
            checked, why = self._check(widget)
            if checked is None:
                return None, why if why.startswith("'") else f"'{title}': {why}"
            result, why = await self._draw(checked)
            if result is None:
                return None, f"'{title}': {why}"
            checked, result = await self._ladder(checked, result)
            bad = worth(checked, result, self.dates)
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
        out = {**checked, "row_count": size or 1, "finding": finding(checked, result, self.dates, self.lang, self.percent),
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
            for w, why in got:
                if w is None:
                    whys.append(why)
                    continue
                if _key(w) in seen or _reading(w) in seen:
                    continue
                if w["widget_type"] in ADVANCED:
                    advanced += 1
                    if advanced > MAX_ADVANCED_PER_PAGE:
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
            line += " | " + ", ".join(f"{n}={_fmt(v)}" for n, v in series[:8])
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
        p["answer"] = text


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


def share_columns(df) -> list[dict]:
    """A percent twin for each yes/no column: 100 where yes, else 0 -- so its
    average over the rows where the answer is known is the share of yes, in
    percent (the gate adds that "known" filter)."""
    import pandas as pd
    out = []
    for col in df.columns:
        s = df[col]
        name = f"{col}{SHARE_SUFFIX}"
        if (not _IDENT.match(str(col)) or name in df.columns or f"{col}{NOT_SUFFIX}" in df.columns
                or pd.api.types.is_datetime64_any_dtype(s)):
            continue
        values = set(s.dropna().unique().tolist()[:5])
        if len(values) == 2 and values <= {True, False} and all(isinstance(v, (bool,)) or type(v).__name__ == "bool_"
                                                                for v in values):
            out.append({"name": name, "expression": f"IF({col} == True, 100, 0)", "dtype": "numeric",
                        "format": {"type": "percent", "decimals": 1}, "of": str(col), "is": "yes"})
            out.append({"name": f"{col}{NOT_SUFFIX}", "expression": f"IF({col} == False, 100, 0)",
                        "dtype": "numeric", "format": {"type": "percent", "decimals": 1},
                        "of": str(col), "is": "no"})
            # Its two groups in words: a chart split by "True / False" makes the
            # reader -- and the model writing the answer -- guess which is which
            # ("on time: 2.83" was the LATE parcels, Nile Express 2026-10-10).
            word = re.sub(r"^(is|has|was|are)_", "", str(col)).replace("_", " ").strip() or str(col)
            if f"{col}{LABEL_SUFFIX}" not in df.columns and '"' not in word:
                out.append({"name": f"{col}{LABEL_SUFFIX}", "of": str(col), "is": "label",
                            "expression": f'IF({col} == True, "{word.capitalize()}", '
                                          f'IF({col} == False, "Not {word}", "Unknown"))'})
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
    return inputs, facts, filters, words, len(scoped), total


def scope_note(words: list[str], filters: list[dict], scoped_rows: int, total: int, lang: str,
               dem: dict | None = None, dataset_id: int | None = None) -> str | None:
    """What the page is limited to -- and, said first, what was asked for
    that the data does not hold."""
    parts = [_t(lang, "nomatch", what=m) for m in demand_service.missing_words(dem)]
    if words:
        what = "; ".join(words)
        parts.append(_t(lang, "scope", what=what, n=f"{scoped_rows:,}", total=f"{total:,}") if filters
                     else _t(lang, "scoped", what=what))
    for b in (dem or {}).get("base_missing") or []:
        if dataset_id is None or b.get("dataset_id") == dataset_id:
            parts.append(_t(lang, "nobase", events=str(b["events"]).replace("_", " "),
                            base=str(b["base"]).replace("_", " ")))
            break
    return " ".join(parts) or None


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
            if (rate is None or rc.get("measure") not in gate.percent or (rc.get("measure"), dim) in have
                    or all(v >= 99.5 or v <= 0.5 for v in shares)):
                out.append(w)
                continue
            # Sizes: the rows of each group, whatever became of them.
            base = {**c, "aggregation": "count", "filters": [f for f in rc.get("filters") or []
                                                             if f.get("column") not in gate.flag_of.values()]}
            base.pop("limit", None)
            sizes: dict[str, float] = {}
            drew, _n, _w = await _probe({"widget_type": "bar", "config": base}, gate.inputs.probe)
            if drew:
                sizes = dict(_series(gate.inputs.drawn.get(drawn_key("bar", base)) or {}, lang) or [])
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
    used = json.dumps([w.get("config") for p in pages for w in p.get("widgets") or []], default=str)
    cols = [{k: v for k, v in c.items() if k not in ("of", "is")}
            for c in list(getattr(inputs, "shares", None) or []) + list(made or [])
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
            scope_filters: list[dict] | None = None) -> list[dict]:
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
    missing = [_t(lang, "unanswered", q=text) for q, text in asked.items() if q in own and q not in answered]
    for i, p in enumerate(out):
        p["unanswered"] = missing if i == 0 else []
    return out


async def design(db, user, ds, dem: dict | None, entry: dict | None, lang: str, count: int, client,
                 meaning_map=None, tables: list[str] | None = None) -> dict:
    """{"proposals": pages to choose from, "reason": why some ideas were dropped}.

    One generation and one repair round, like the app's designer: the refused
    charts go back with their reasons and are replaced, then questions still
    without a chart are asked for once more."""
    dem = dem or {}
    inputs, facts, filters, words, scoped_rows, total = await prepare(db, user, ds, dem)
    if client is None or not getattr(client, "enabled", True):
        return {"proposals": [], "reason": "off"}
    know = inputs.knowledge
    reading = _reading_for(meaning_map, tables, {str(c) for c in inputs.df.columns})
    messages, allowed = build_messages(inputs.profile, dem, words, scoped_rows,
                                       _outcome_notes(dem, ds.id) + _notes(entry), count, lang,
                                       know, facts.get("text"), inputs.shares, reading)
    ids = {q["id"] for q in dem.get("questions") or []}
    gate = Gate(inputs, facts, allowed, ids, filters, lang, _given(dem, ds.id))

    got = await client.complete_json(messages, PAGES_SCHEMA, max_tokens=9000, temperature=0.2, enforce=True)
    proposed = [p for p in (got or {}).get("pages") or [] if isinstance(p, dict)][:count]
    if not proposed:
        return {"proposals": [], "reason": "failed"}
    pages, whys = await gate.pages(proposed)
    refused = [w for ws in whys for w in ws]
    answered = {w.get("question") for p in pages for w in p["widgets"]}
    missing = [q for q in dem.get("questions") or [] if q["id"] not in answered]
    if refused or missing:
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
                    if w["widget_type"] in ADVANCED and any(
                            x["widget_type"] in ADVANCED for x in pages[i]["widgets"]):
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
    note = scope_note(words, filters, scoped_rows, total, lang, dem, ds.id)
    return {"proposals": _finish(pages, dem, note, lang, filters), "reason": "; ".join(refused[:6]),
            "derived": made}


async def change(db, user, ds, dem: dict | None, entry: dict | None, page: dict, message: str,
                 lang: str, client, meaning_map=None, tables: list[str] | None = None) -> dict | None:
    """One page changed as the person asks: charts they did not mention stay
    exactly as they are. None when nothing usable came back."""
    dem = dem or {}
    if client is None or not getattr(client, "enabled", True):
        return None
    inputs, facts, filters, words, scoped_rows, total = await prepare(db, user, ds, dem)
    messages, allowed = build_messages(inputs.profile, dem, words, scoped_rows,
                                       _outcome_notes(dem, ds.id) + _notes(entry), 1, lang,
                                       inputs.knowledge, facts.get("text"), inputs.shares,
                                       _reading_for(meaning_map, tables, {str(c) for c in inputs.df.columns}))
    scoped = {f["column"] for f in filters}
    current = [{"question": w.get("question") or "", "widget_type": w["widget_type"], "title": w.get("title"),
                "why": w.get("why") or "",
                "config": {**w["config"], "filters": [f for f in w["config"].get("filters") or []
                                                      if f.get("column") not in scoped]}}
               for w in page.get("widgets") or [] if w.get("widget_type") != "text"]
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
    pages, _whys = await gate.pages(proposed)
    if not pages or not pages[0]["widgets"]:
        return None
    await add_rates(pages, gate, lang)
    await write_answers(pages, gate, dem, lang, client)
    made = derived_for(pages, inputs, gate.made)
    with_captions(pages, gate)
    done = _finish(pages, dem, scope_note(words, filters, scoped_rows, total, lang, dem, ds.id), lang, filters)
    return {**done[0], "_derived": made} if done else None
