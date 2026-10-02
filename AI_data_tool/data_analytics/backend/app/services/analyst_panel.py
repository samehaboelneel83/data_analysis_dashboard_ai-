"""An analyst panel inside Datalytics: several lenses propose, the data decides.

The HR exercise of 2026-10-02 picked 50 useful visuals out of ~308 million
possible ones by working the way an analytics team would:

  1. a fact sheet of exact measurements (services/fact_sheet.py);
  2. several analysts, each with a lens, proposing visuals for real questions;
  3. every proposal drawn on the live rows -- broken ones dropped;
  4. each result read back into one true sentence (services/readback.py);
  5. selection by question value, by the strength of what the chart actually
     shows, and by novelty, under quotas so no kind or section crowds out
     the rest.

`run_panel` is that process. The lenses are chosen by the SHAPE of the data
(no time lens without a date column), each is one model call, and the
statistics engine's own ideas (findings, basics, shape-driven variety) join
as candidates too, so the panel still produces a selection when no model is
configured. The model only ever PROPOSES: what is kept is decided by what the
data returned.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import json
import math
import re
import logging
from typing import Any, Awaitable, Callable

#: The lenses, by the shape of data each needs.
log = logging.getLogger(__name__)

LENSES: dict[str, dict] = {
    "composition": {
        "title": "Composition",
        "brief": "who or what makes up the data: counts, shares, mix of one category within "
                 "another, structure and concentration",
        "needs": "categories",
    },
    "measures": {
        "title": "Levels & drivers",
        "brief": "the main measures: their levels and spread, how they differ between groups, "
                 "fair like-for-like comparisons, and what drives them",
        "needs": "numbers",
    },
    "time": {
        "title": "Over time",
        "brief": "change over time: volumes per period, how measures and the mix of categories "
                 "moved, cohorts, seasonality, and what the time data cannot show",
        "needs": "dates",
    },
    "relationships": {
        "title": "Patterns & models",
        "brief": "how things relate: categories that travel together, two or three measures "
                 "at once per group (a bubble of pay, tenure and size per department), models "
                 "that explain a number (regression) or predict a category (logistic for a "
                 "yes/no such as 'is senior', a tree for several values), segments",
        "needs": "relations",
    },
    # Added after the HR benchmark (2026-10-02): the hand-picked set gave pay
    # equity a whole section -- salary by gender WITHIN each department and
    # title -- and the four lenses, told to avoid flat comparisons, proposed
    # none of it. For a group people ask about, a flat result IS the finding.
    "equity": {
        "title": "Fairness & like-for-like",
        "brief": "whether a group people ask about (a two-to-four value category such as "
                 "gender) is treated alike: the main measure compared between its values "
                 "WITHIN like-for-like groups (the same department, the same title, the same "
                 "hiring year), its share in each group, and its spread. Here a result that "
                 "shows no difference is the finding -- say so in `why`. Prefer ONE chart that "
                 "compares the group inside every like-for-like group at once (that group as "
                 "`dimension`, the compared group as `dimension2`) over one filtered chart each",
        "needs": "groups",
    },
}
SUMMARY = {"key": "summary", "title": "Headline numbers"}
DETAIL = {"key": "detail", "title": "Detail",
          "brief": "The rows behind the charts, to look up one record."}
#: Ideas each lens is asked for.
PER_LENS = 12
SIZES = (12, 24, 50)

LENS_SCHEMA = {
    "type": "object",
    "properties": {
        "widgets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "widget_type": {"type": "string"},
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                    "config": {"type": "object"},
                    "value": {"type": "integer"},
                    "audience": {"type": "string"},
                },
                "required": ["question", "widget_type", "title", "config", "value"],
            },
        },
    },
    "required": ["widgets"],
}

LENS_SYSTEM = """You are one analyst on a panel designing visuals for a real \
dataset. Your lens is {lens}: {brief}. Other analysts cover the other lenses, so \
stay on yours.

Propose the {n} most useful visuals through your lens. For each: the business \
QUESTION it answers (one a manager would really ask), the widget that answers it \
best, a short title, a one-line `why`, an app config, `value` 1-5 (5 = must-have) \
and the `audience` (executive, manager or analyst).

Use the measured facts: propose for differences that exist. A comparison the \
facts call the same everywhere, or independent, is worth at most ONE visual, and \
only if showing the absence of a difference answers a real question (fairness, \
balance) -- then its `why` says it is flat. Vary the widget types when a different \
type answers better, never for decoration.

A widget splits by at most the fields its line in the menu lists (a box plot \
has one category; a bar or a line has two). For a three-way comparison -- pay by \
title, by gender -- use a heatmap or crosstab, or a filter to one group, never an \
extra field the widget does not take.

Say only what the columns hold. A value is its CURRENT value unless a column \
says otherwise: grouped by the year a record started (a hire or sign-up date), \
a measure is today's value for the records that started that year -- not its \
value at the start ("starting pay"); nothing is a history unless a date column \
dates the value itself.

When the facts say a measure is on different scales by some column, show it \
for one value of that column at a time, with a filter -- never totalled, \
averaged or side by side across it (small multiples share one scale too).

An identifier (a seller, product or customer code) may be a bar or table \
dimension only as a ranked top list with `limit` 10-25.

A date is a point in time, never a quantity: count rows by it, or put it on \
the time axis; never sum or average it as a measure (an average delivery DATE \
is not a delivery time). A year column is a date too. Two columns the facts \
say always go together are one breakdown: use one of them. A column that is \
already an average, a rate or a per-row distinct count (unique_*, active_*) \
is averaged, never totalled. Share-of-a-whole charts (pie, donut, treemap) \
show totals or counts, never averages.

Hard rules: use ONLY the column names given and ONLY the widget types offered, \
with every field each requires. Never sum or average a column marked [identifier]; \
count it with countd. For time, use the date column itself with \
`dimension_granularity` (year, quarter, month) -- there is no column called year. \
Filters are {{"column", "op", "value"}} with op in eq, neq, gt, lt, gte, lte, in."""


#: Why an idea was left out, in words a reader can be shown (`code`), matched
#: on the reason the gate gave. Order matters: the first match wins.
_REFUSAL_CODES = (
    ("units", ("different units",)),
    ("meaning", ("adds up years", "adds up map coordinates", "is not a duration",
                 "does arithmetic on identifiers")),
    ("repeat", ("always go together",)),
    ("promise", ("the title names", "percentiles need", "is not a filter the engine applies",
                 "both axes draw the same", "a card takes one aggregation")),
    ("identifier", ("is an identifier", "identifier is counted")),
    ("axis", ("continuous number",)),
    ("empty", ("returned nothing", "no rows", "nothing to draw")),
    ("error", ("could not be drawn", "could not be read", "could not be judged")),
)


def repair_and_check(w: dict, profile: dict, column_meta: dict | None = None,
                     mixed: dict | None = None, dependents: dict | None = None,
                     identical: dict | None = None, edges: dict | None = None) -> tuple[dict, bool, str]:
    """`(widget, ok, why)`: one proposed widget repaired where its meaning is
    clear, then checked. Shared by the analyst panel and the quick designer,
    so both offer only what they can draw honestly.

    One idea that trips a repair or a check is refused on its own; it must not
    take the run down with it (an Olist run failed with an unexpected error,
    2026-10-02)."""
    from .suggest_dataset_dashboard import normalise_aggregations, resolve_time_words, validate_widget
    dates = {c["name"] for c in profile.get("columns", []) if c.get("role") == "datetime"}
    mixed = mixed or {}
    try:
        # "average" and "mean" are avg before any rule reads them: "Average
        # Lead Time by Year" averaged a delivery DATE under aggregation
        # "average" and slipped past the rule that knows "avg" (Olist, 2026-10-02).
        if isinstance(w.get("config"), dict):
            w = {**w, "config": normalise_aggregations(w["config"])}
        w = _honest_title(_mix_from_filter(_aggregation_from_title(
            resolve_time_words(w, profile), column_meta, dates)), profile)
        w = _grain_from_title(_measure_from_title(_count_word_measure(w, profile), profile, column_meta), dates)
        w = one_unit(_whole_needs_a_total(_no_sum_of_rates(_rows_not_groups(w, profile))), mixed)
        w = _drop_twins(_drop_dependent_predictors(w, dependents or {}), identical or {})
        w = trim_edges(w, edges or {})
        ok, why = validate_widget(w, profile, column_meta)
        if ok:
            why = (broken_promise(w, profile) or mixes_units(w, mixed)
                   or date_as_number(w, dates) or dependent_split(w, dependents or {})
                   or same_number_twice(w, identical or {}))
            ok = why is None
        return w, ok, why or ""
    except Exception as exc:                                 # noqa: BLE001
        log.warning("could not read proposed widget %r: %s", w.get("title"), exc, exc_info=True)
        return w, False, f"{w.get('title')}: could not be read ({type(exc).__name__}: {exc})"[:300]


def refusal_code(why: str | None) -> str:
    text = str(why or "").lower()
    return next((code for code, needles in _REFUSAL_CODES if any(n in text for n in needles)), "invalid")


def _value(v) -> int:
    """The proposer's 1-5 value, whatever it wrote ("5", 4.5, "high")."""
    try:
        return max(1, min(5, int(round(float(v)))))
    except (TypeError, ValueError):
        return {"high": 5, "medium": 3, "low": 2}.get(str(v).strip().lower(), 3)


def choose_lenses(profile: dict, facts: list[dict]) -> list[str]:
    roles = [c.get("role") for c in profile.get("columns", [])]
    has = {
        "categories": "categorical" in roles,
        "numbers": "numeric" in roles,
        "dates": "datetime" in roles,
        "relations": roles.count("categorical") >= 2 or roles.count("numeric") >= 2
        or any(f["kind"] == "link" for f in facts),
        # a small category to compare fairly, a measure, and something to hold equal
        "groups": "numeric" in roles and roles.count("categorical") >= 2 and any(
            c.get("role") == "categorical" and 2 <= (c.get("distinct") or 0) <= 4
            and not c.get("is_identifier") and not c.get("is_personal")
            for c in profile.get("columns", [])),
    }
    order = ("composition", "measures", "equity", "time", "relationships")
    return [k for k in order if has[LENSES[k]["needs"]]]


def lens_messages(lens: str, profile: dict, facts_text: str, goal: str | None,
                  knowledge=None, n: int = PER_LENS) -> list[dict]:
    from .dataset_profile import describe_for_prompt
    from .suggest_dataset_dashboard import _menu_text
    spec = LENSES[lens]
    who = (f'The person this is for describes themselves: "{goal.strip()}".\n'
           if goal and goal.strip() else "")
    user = (f"{who}THE DATA\n{describe_for_prompt(profile, knowledge)}\n\n"
            f"MEASURED FACTS (exact)\n{facts_text}\n\n"
            f"WIDGETS YOU MAY USE\n{_menu_text(profile)}\n\n"
            f"Return {n} widgets for the {spec['title']} lens.")
    return [{"role": "system", "content": LENS_SYSTEM.format(lens=spec["title"], brief=spec["brief"], n=n)},
            {"role": "user", "content": user}]


# ── candidates ───────────────────────────────────────────────────────────────

def _section_for(widget_type: str, config: dict, dates: set[str] = frozenset()) -> str:
    """Which page an idea belongs on, by what it draws.

    By content, not by which lens proposed it: on the live HR run lenses
    strayed (a regression under Composition, a salary box plot under Over
    time), and a page is only readable when its charts share a subject."""
    if widget_type in ("kpi", "card", "gauge"):
        return "summary"
    if widget_type.startswith("model_") or widget_type in ("bubble", "scatter", "network",
                                                            "correlation_matrix", "parallel_coordinates"):
        return "relationships"
    axis = config.get("dimension") or config.get("category") or config.get("start")
    if config.get("dimension_granularity") or widget_type in ("line", "area", "step", "ribbon",
                                                              "dual_axis_time_series",
                                                              "comparative_time_series") \
            or (isinstance(axis, str) and axis in dates):
        return "time"
    measure = str(config.get("measure") or "")
    agg = str(config.get("aggregation") or "")
    if widget_type in ("box_plot", "histogram") or (measure and agg in ("avg", "median")):
        return "measures"
    return "composition"


_VALUE = {"kpi": 5, "baseline": 4, "mix": 4, "spread": 4, "bubble": 4, "share": 3,
          "trend_split": 4, "rules": 3}


def rule_candidates(df, roles: dict, column_meta: dict | None, ineligible: set[str],
                    findings: list[dict]) -> list[dict]:
    """The statistics engine's ideas, as panel candidates."""
    from .insights import suggest_widgets_from_findings
    import pandas as pd
    dates = {c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])}
    out = []
    for s in suggest_widgets_from_findings(findings, roles, None, limit=40, ineligible=ineligible,
                                           column_meta=column_meta, frame=df, per_type=6):
        value = _VALUE.get(s.get("kind"), 3 + (1 if float(s.get("score") or 0) > 0.6 else 0))
        out.append({"question": s["title"], "widget_type": s["widget_type"], "title": s["title"],
                    "why": s.get("reason", ""), "config": s["config"], "value": value,
                    "audience": "executive" if s["widget_type"] == "kpi" else "manager",
                    "section": _section_for(s["widget_type"], s["config"], dates), "source": "statistics"})
    return out


# ── evidence: how much the drawn result actually shows ───────────────────────

def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def evidence(widget_type: str, config: dict, result: dict | None) -> float:
    """0..1: how strong a pattern the drawn result shows. Flat results score
    near 0 -- they may still be selected as evidence of balance, but never
    ahead of a chart that shows something."""
    from .readback import _cramers_v
    if not isinstance(result, dict):
        return 0.0
    t = result.get("type")
    try:
        if t == "model":
            if result.get("status") != "ok":
                return 0.0
            kind, fit = result.get("model"), result.get("fit") or {}
            if kind == "rules":
                rules = result.get("rules") or []
                return min(1.0, (rules[0]["lift"] - 1) / 3) if rules else 0.0
            if kind == "compare":
                best = max((_f(m.get("score")) or 0 for m in result.get("models") or []), default=0)
                return min(1.0, max(0.0, best) * 1.5)
            v = _f(fit.get("value")) or 0
            base = _f((fit.get("secondary") or {}).get("accuracy of always guessing the commoner outcome"))
            if kind == "tree" and base is not None and base < 1:
                # How much of what guessing gets wrong the tree gets right.
                return max(0.0, min(1.0, (v - base) / (1 - base)))
            if kind == "logistic":
                return max(0.0, min(1.0, (v - 0.5) * 2))
            return max(0.0, min(1.0, v * 1.5))
        if t == "scalar":
            return 0.6
        if t == "crosstab":
            rows, cols = result.get("rows") or [], result.get("columns") or []
            series = [c for c in cols[1:] if str(c) not in ("__total__", "Total")]
            table = [[_f(v) or 0.0 for v in r[1:1 + len(series)]] for r in rows]
            if str(config.get("aggregation") or "").lower() in ("count", "countd", "frequency"):
                return min(1.0, _cramers_v(table) * 2)
            gaps = [abs(r[1] - r[0]) / abs(r[0]) for r in table if len(r) >= 2 and r[0]]
            return min(1.0, (sorted(gaps)[len(gaps) // 2] if gaps else 0) * 10)
        if t in ("heatmap", "ribbon"):
            if str(config.get("aggregation") or "").lower() in ("count", "countd", "frequency"):
                # The link between the two, not the size of the biggest cell.
                table = [[_f(v) or 0.0 for v in (line or [])] for line in result.get("cells") or []]
                if len(table) >= 2 and all(len(r) >= 2 for r in table):
                    return min(1.0, _cramers_v(table) * 2)
            vals = [_f(v) for line in result.get("cells") or [] for v in (line or [])]
            vals = [v for v in vals if v]
            mean = sum(vals) / len(vals) if vals else 0
            return min(1.0, (max(vals) - min(vals)) / abs(mean) / 2) if mean else 0.0
        if t == "box_plot":
            meds = [_f(r.get("median")) for r in result.get("rows") or []]
            meds = [m for m in meds if m is not None]
            mean = sum(meds) / len(meds) if meds else 0
            return min(1.0, (max(meds) - min(meds)) / abs(mean) * 2) if mean and len(meds) > 1 else 0.0
        if t == "bubble_series":
            rows = result.get("rows") or []
            spreads = []
            for k in ("x", "y"):
                vals = [_f(r.get(k)) for r in rows]
                vals = [v for v in vals if v is not None]
                mean = sum(vals) / len(vals) if vals else 0
                if mean and len(vals) > 1:
                    spreads.append((max(vals) - min(vals)) / abs(mean))
            return min(1.0, sum(spreads) / len(spreads) * 2) if spreads else 0.0
        rows = result.get("rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "value" in rows[0]:
            vals = [_f(r.get("value")) for r in rows]
            vals = [v for v in vals if v is not None]
            if len(vals) < 2:
                return 0.3
            if widget_type == "histogram":
                return 0.45
            mean = sum(vals) / len(vals)
            if not mean:
                return 0.0
            if config.get("dimension_granularity") or "bin_start" in rows[0]:
                return min(1.0, abs(vals[-1] - vals[0]) / max(abs(v) for v in vals) * 1.2)
            return min(1.0, (max(vals) - min(vals)) / abs(mean))
        return 0.5                                          # structure views: a fair default
    except Exception:                                       # noqa: BLE001
        return 0.0


# ── selection ────────────────────────────────────────────────────────────────

#: Config keys the shapers read as columns. A column under any other key is
#: not drawn, so it neither makes two ideas different nor keeps a title's promise.
ENGINE_FIELDS = frozenset({
    "dimension", "dimension2", "category", "category2", "measure", "measure2", "measures",
    "levels", "predictors", "response", "start", "end", "size", "facet_by", "id_col",
    "parent_col", "label_col", "lat", "lon", "lat2", "lon2", "split_by", "columns", "group",
    "color", "path", "target", "partition", "dimension_levels", "x", "y"})


def _columns(config: dict) -> frozenset:
    cols = set()
    for k, v in config.items():
        if k not in ENGINE_FIELDS:
            continue
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str):
                cols.add(x)
    return frozenset(cols)


_FILTERISH = re.compile(r"filter|only|subset|where", re.I)
#: Types that draw a measure's values themselves rather than a roll-up.
_DRAWS_VALUES = ("histogram", "box_plot", "numeric_series", "scatter", "violin", "parallel_coordinates",
                 "correlation_matrix")


def mixes_units(w: dict, mixed: dict) -> str | None:
    """Why a widget adds up a measure across groups that record it in
    different units (fact_sheet.mixed_units), or None.

    Filtering the unit-defining column to one value keeps each number in one
    unit; anything on a shared scale sets bytes beside seconds. Counting rows
    is unit-free and always allowed."""
    if not mixed:
        return None
    cfg = w.get("config") or {}
    wt = str(w.get("widget_type"))
    if wt.startswith("model_"):
        # A model fits the numbers it is given: clusters of call records drawn
        # from bytes and seconds on one axis are clusters of units (call
        # records panel, 2026-10-02). The outcome or the clustered measures
        # must be in one unit; a mixed PREDICTOR is fine when the column that
        # sets its unit is a predictor too (the model then separates them).
        preds = [p for p in cfg.get("predictors") or [] if isinstance(p, str)]
        fitted = [cfg.get("measure"), cfg.get("response")] + list(cfg.get("measures") or [])
        fitted += [p for p in preds if p in mixed and mixed[p]["by"] not in preds]
        cfg = {"measures": [m for m in fitted if isinstance(m, str)], "filters": cfg.get("filters")}
    # Counting rows is unit-free -- but a histogram or a box plot draws the
    # VALUES whatever its aggregation says ("Call Duration Distribution" binned
    # bytes beside seconds under aggregation: count).
    if str(cfg.get("aggregation") or "").lower() in ("count", "countd", "frequency") \
            and wt not in _DRAWS_VALUES:
        return None
    # Any field that carries the measure's values (a map's weight, a card's
    # list), not only `measure` -- a density map summed bytes and seconds.
    axes = ("dimension", "dimension2", "category", "category2", "levels", "x")
    used = [v for k, v in cfg.items() if k not in axes and k != "filters"
            for v in (v if isinstance(v, list) else [v])]
    for m in [u for u in used if isinstance(u, str) and u in mixed]:
        by = mixed[m]["by"]
        # Any shared scale sets bytes beside seconds ("GPRS carries 100% of
        # the volume") -- small multiples included: their panels share one
        # scale by design (widget_data.shape_small_multiples).
        one = any(isinstance(f, dict) and f.get("column") == by and (
            f.get("op") in ("eq", None) or (f.get("op") == "in" and len(f.get("value") or []) == 1))
            for f in cfg.get("filters") or [])
        if one:
            continue
        u = mixed[m]
        return (f"{w.get('title')}: {m} is recorded in different units by {by} ({u['high']} vs "
                f"{u['low']}); split or filter by {by} instead of adding it up across them")
    return None


def one_unit(w: dict, mixed: dict) -> dict:
    """A chart that adds up a mixed-unit measure, narrowed to the commonest
    value of the unit column -- with that value in its title.

    The call-records panel refused 45 of 71 ideas for totalling volume across
    services; "Monthly volume" is still the right chart for Mobile Telephony
    alone, so it is offered as "Monthly volume (Mobile Telephony)" instead.
    A small-multiples chart or a model is left to the refusal."""
    why = mixes_units(w, mixed)
    wt = str(w.get("widget_type"))
    if not why or wt.startswith("map_") or wt in ("model_tree", "model_logistic", "model_rules"):
        return w
    cfg = w.get("config") or {}
    hits = {mixed[v]["by"]: mixed[v].get("common") for k, v in cfg.items()
            if k not in ("filters", "predictors")
            for v in (v if isinstance(v, list) else [v]) if isinstance(v, str) and v in mixed}
    if len(hits) != 1:
        return w
    (by, value), = hits.items()
    if not value or by in (cfg.get("dimension"), cfg.get("dimension2"), cfg.get("category"),
                           cfg.get("facet_by")) or by in (cfg.get("predictors") or []):
        return w
    filters = [f for f in cfg.get("filters") or [] if not (isinstance(f, dict) and f.get("column") == by)]
    new = {**cfg, "filters": filters + [{"column": by, "op": "eq", "value": value}]}
    return {**w, "config": new, "title": f"{w.get('title')} ({value})"}


_MIX_WORDS = re.compile(r"\b(mix|split|share|shares|balance|ratio|composition|breakdown)\b", re.I)


_TIME_CLAIMS = re.compile(r"\b(starting|initial|entry|original|historical|past)\s+", re.I)


def _honest_title(w: dict, profile: dict) -> dict:
    """Drop a claim about WHEN a value was measured that no column supports.

    "Average Starting Salary Trend" was salary -- today's pay -- by hiring
    year; its own `why` even said "current pay levels" (live HR panel,
    2026-10-02). The chart is a good one, so the word goes, not the chart."""
    title = str(w.get("title") or "")
    names = " ".join(c["name"].lower() for c in profile.get("columns", []))
    def keep(m):
        return m.group(0) if m.group(1).lower() in names else ""
    fixed = _TIME_CLAIMS.sub(keep, title)
    # "Total total orders": a title that names the roll-up and then the
    # column named for it says the word once.
    fixed = re.sub(r"\b(\w+)\s+\1\b", r"\1", fixed, flags=re.I)
    return {**w, "title": fixed} if fixed != title else w


def _mix_from_filter(w: dict) -> dict:
    """A "mix" drawn as one slice becomes the mix.

    "Gender Mix by Department" arrived as a bar of the women per department --
    a filter on gender=F -- under a title that promises the split (live HR
    panel, 2026-10-02). When the title asks for a mix and the column it names
    is only a one-value filter on a bar, the filter becomes the bar's split,
    shown as shares of 100%."""
    cfg = w.get("config")
    if w.get("widget_type") not in ("bar", "column") or not isinstance(cfg, dict) or cfg.get("dimension2") \
            or not _MIX_WORDS.search(str(w.get("title") or "")):
        return w
    filters = [f for f in cfg.get("filters") or [] if isinstance(f, dict)]
    title = " " + re.sub(r"[^\w]+", " ", str(w.get("title") or "").lower()) + " "
    hit = next((f for f in filters if f.get("op") in ("eq", None)
                and isinstance(f.get("column"), str)
                and f" {f['column'].lower().replace('_', ' ')} " in title), None)
    if not hit or hit["column"] == cfg.get("dimension"):
        return w
    rest = [f for f in filters if f is not hit]
    new = {**cfg, "dimension2": hit["column"], "bar_mode": "stacked100"}
    if rest:
        new["filters"] = rest
    else:
        new.pop("filters", None)
    return {**w, "config": new}


_TITLE_AGG = (("median", "median"), ("average", "avg"), ("avg", "avg"), ("mean", "avg"),
              ("total", "sum"), ("sum", "sum"), ("headcount", "countd"), ("count", "count"))
_NO_AGG = ("box_plot", "histogram", "scatter", "numeric_series", "table", "correlation_matrix",
           "parallel_coordinates")


#: Columns that hold an average or a rate already: summing them is meaningless.
_ALREADY_A_RATE = re.compile(r"^(avg|mean|average|median)_|_(avg|mean|rate|ratio|pct|percent|share)(_|$)|"
                             r"(rate|ratio|pct|percent)$", re.I)


def _not_additive(m) -> bool:
    from .semantic_guard import _DISTINCT_SNAPSHOT
    return isinstance(m, str) and bool(_ALREADY_A_RATE.search(m) or _DISTINCT_SNAPSHOT.search(m))


def _no_sum_of_rates(w: dict) -> dict:
    """A total of a column that is already an average, a rate or a per-row
    distinct count becomes its average: "Total avg freight cost" summed daily
    averages, and "Active sellers" summed daily seller counts (daily-ops).

    A card shares one aggregation, so the columns that cannot be totalled
    leave a summed card rather than turning its totals into averages: the
    daily-ops "summary" card put active sellers beside total revenue."""
    cfg = w.get("config")
    if not isinstance(cfg, dict) or str(cfg.get("aggregation") or "").lower() not in ("sum", ""):
        return w
    wt = str(w.get("widget_type"))
    if wt == "card" and isinstance(cfg.get("measures"), list):
        keep = [m for m in cfg["measures"] if not _not_additive(m)]
        if keep and len(keep) < len(cfg["measures"]):
            return {**w, "config": {**cfg, "measures": keep}}
    m2 = cfg.get("measure2")
    if _not_additive(m2) and str(cfg.get("aggregation2") or cfg.get("aggregation") or "").lower() in ("sum", "") \
            and wt not in _NO_AGG:
        cfg = {**cfg, "aggregation2": "avg"}
        w = {**w, "config": cfg}
    ms = [cfg.get("measure")] + list(cfg.get("measures") or [])
    if not any(_not_additive(m) for m in ms):
        return w
    if not cfg.get("aggregation") and wt in _NO_AGG:
        return w
    return {**w, "config": {**cfg, "aggregation": "avg"}}


#: Charts whose area or length IS a share of a whole: only an additive
#: roll-up has a whole to share.
_PART_OF_WHOLE = ("pie", "donut", "treemap", "sunburst", "circle_pack", "icicle", "waterfall", "funnel")


def _whole_needs_a_total(w: dict) -> dict:
    """A share-of-a-whole chart of an average becomes a bar.

    "Top 20 Products Price Share" was a pie of AVERAGE prices (Olist panel,
    2026-10-02): the slices add up to nothing. The comparison is still worth
    drawing, as bars."""
    cfg = w.get("config")
    wt = str(w.get("widget_type"))
    if wt not in _PART_OF_WHOLE or not isinstance(cfg, dict):
        return w
    if str(cfg.get("aggregation") or "").lower() not in ("avg", "mean", "median", "min", "max"):
        return w
    if wt in ("sunburst", "circle_pack", "icicle") or not cfg.get("dimension"):
        return w   # left to validation: there is no bar to make of a nesting
    new = {k: v for k, v in cfg.items() if k not in ("dimension2",)}
    title = re.sub(r"\s*\b(share|mix|split|composition)\b", "", str(w.get("title") or ""), flags=re.I).strip()
    return {**w, "widget_type": "bar", "config": new, "title": title or w.get("title")}


def _rows_not_groups(w: dict, profile: dict) -> dict:
    """A table "by" an identifier is a list of records: it becomes one.

    Every designer asked for one -- "Student Detail View", "Students
    Requiring Follow-up" (notes filtered), "Top 10 Earners" -- and each was
    refused as an identifier with hundreds of values (five-dataset review,
    2026-10-02), while the analysts' reference dashboards all had such a
    list. Grouped by the identifier it is one row per record anyway; listed,
    it keeps its filter and its columns and sorts by its number."""
    from .dataset_profile import HIGH_CARDINALITY
    cfg = w.get("config")
    if str(w.get("widget_type")) not in ("table", "list") or not isinstance(cfg, dict):
        return w
    dim = cfg.get("dimension")
    known = {c["name"]: c for c in profile.get("columns", [])}
    info = known.get(dim) or {}
    if not (info.get("is_identifier") and (info.get("distinct") or 0) > HIGH_CARDINALITY):
        return w
    try:
        if 0 < int(cfg.get("limit") or 0) <= 25:
            return w          # a ranked top list stays a ranked top list
    except (TypeError, ValueError):
        pass
    cols: list = [dim]
    for k in ("dimension2", "measure", "measure2", "size"):
        if isinstance(cfg.get(k), str):
            cols.append(cfg[k])
    cols += [m for m in cfg.get("measures") or [] if isinstance(m, str)]
    cols += [f.get("column") for f in cfg.get("filters") or [] if isinstance(f, dict)]
    cols = [c for i, c in enumerate(cols) if c in known and c not in cols[:i]
            and not known[c].get("is_personal")]
    new: dict = {"columns": cols, "limit": 200}
    if cfg.get("filters"):
        new["filters"] = cfg["filters"]
    sort_by = next((c for c in (cfg.get("measure"), cfg.get("measure2")) if isinstance(c, str) and c in known
                    and known[c].get("role") == "numeric"), None)
    if sort_by:
        new.update({"sort_col": sort_by, "sort": str(cfg.get("sort") or "desc")})
    return {**w, "widget_type": "table", "config": new}


_GENERIC_WORDS = {"total", "sum", "avg", "average", "mean", "median", "count", "num", "number", "n",
                  "unique", "distinct", "daily", "value", "amount", "pct", "percent", "rate"}
_MEASURED_TYPES = ("line", "area", "step", "bar", "column", "table", "list", "dot_plot", "needle",
                   "treemap", "pie", "donut", "kpi")


def _stem(word: str) -> str:
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def _measure_from_title(w: dict, profile: dict, column_meta: dict | None = None) -> dict:
    """A chart with no measure counts rows; when its title names one number,
    it meant that number.

    Daily ops (2026-10-02): "Daily Order Volume Trend" arrived with no
    measure and drew the number of DAYS per month; "Top 20 High-Volume Days"
    named its number only as `sort: total_orders`. On pre-aggregated data a
    row count is almost never the question."""
    cfg = w.get("config")
    wt = str(w.get("widget_type"))
    if not isinstance(cfg, dict) or wt not in _MEASURED_TYPES or cfg.get("measure") or cfg.get("measures") \
            or cfg.get("columns"):
        return w
    nums = {c["name"]: c for c in profile.get("columns", [])
            if c.get("role") == "numeric" and not c.get("is_identifier")}
    pick = cfg.get("sort") if cfg.get("sort") in nums else None
    if pick is None:
        title = {_stem(t) for t in re.findall(r"[a-z]+", str(w.get("title") or "").lower())}
        hits = {}
        for name in nums:
            own = {_stem(t) for t in re.findall(r"[a-z]+", name.lower())} - _GENERIC_WORDS
            if own and own <= title:
                hits[name] = len(own)
        # The most specific match: "Canceled Orders" is canceled_orders, not
        # total_orders, though both are "orders".
        best = [n for n, k in hits.items() if k == max(hits.values(), default=0)]
        if len(best) != 1:
            return w
        pick = best[0]
    from .semantic_guard import default_summary
    new = {**cfg, "measure": pick, "aggregation": cfg.get("aggregation") or default_summary(pick, column_meta)}
    if new.get("sort") == pick:
        new["sort"] = "desc"
    return {**w, "config": new}


_GRAIN_WORDS = (("day", r"\b(day|days|daily)\b"), ("week", r"\b(week|weeks|weekly)\b"),
                ("month", r"\b(month|months|monthly)\b"), ("quarter", r"\b(quarter|quarters|quarterly)\b"),
                ("year", r"\b(year|years|yearly|annual|annually)\b"))


def _grain_from_title(w: dict, dates: set[str]) -> dict:
    """"Top 10 Days by Cancellation Rate" grouped by MONTH (daily ops,
    2026-10-02): the title's grain wins when it names exactly one."""
    cfg = w.get("config")
    if not isinstance(cfg, dict):
        return w
    axis = cfg.get("dimension") if cfg.get("dimension") in dates else \
        cfg.get("start") if cfg.get("start") in dates else None
    if not axis:
        return w
    title = str(w.get("title") or "").lower()
    said = [g for g, rx in _GRAIN_WORDS if re.search(rx, title)]
    if len(said) != 1 or cfg.get("dimension_granularity") == said[0]:
        return w
    # "Daily Order Volume Trend" by month: "daily" describes the measure
    # (orders a day), and a chosen grain stands. "Days" asks for days.
    if said[0] == "day" and cfg.get("dimension_granularity") and not re.search(r"\bdays?\b", title):
        return w
    return {**w, "config": {**cfg, "dimension_granularity": said[0]}}


_ROW_WORDS = ("count", "countd", "rows", "records", "row_count", "records_count", "n", "frequency")


def _count_word_measure(w: dict, profile: dict) -> dict:
    """`measure: "count"` names no column: it means "count the rows".

    Four Olist ideas arrived as {"measure": "count"} -- status mix over time,
    status by top seller -- and were refused as "no column called count"
    (2026-10-02). Counting the rows of the chart's own category draws exactly
    what the title asks."""
    cfg = w.get("config")
    if not isinstance(cfg, dict):
        return w
    m = cfg.get("measure")
    known = {c["name"] for c in profile.get("columns", [])}
    if not isinstance(m, str) or m in known or m.lower() not in _ROW_WORDS:
        return w
    target = cfg.get("dimension") or cfg.get("dimension2") or next(iter(known), None)
    if not target:
        return w
    return {**w, "config": {**cfg, "measure": target, "aggregation": "count"}}


def _drop_twins(w: dict, identical: dict) -> dict:
    """A list of measures that holds one number twice keeps it once."""
    cfg = w.get("config")
    if not identical or not isinstance(cfg, dict):
        return w
    for key in ("measures", "predictors"):
        vals = cfg.get(key)
        if not isinstance(vals, list):
            continue
        keep: list = []
        for v in vals:
            if not any(v in (identical.get(k) or ()) for k in keep):
                keep.append(v)
        if len(keep) < len(vals):
            cfg = {**cfg, key: keep}
            w = {**w, "config": cfg}
    return w


def same_number_twice(w: dict, identical: dict) -> str | None:
    """Why a widget draws two columns that hold the same values, or None."""
    cfg = w.get("config") or {}
    a, b = cfg.get("measure"), cfg.get("measure2")
    if isinstance(a, str) and b in (identical.get(a) or ()):
        return (f"{w.get('title')}: {a} and {b} always go together -- they hold the same value on "
                f"every row, so the chart draws one number twice")
    return None


def trim_edges(w: dict, edges: dict) -> dict:
    """A trend over whole periods only: stub and partial periods at either end
    are filtered out (fact_sheet.edge_periods), and the `why` says so.

    "Late deliveries fall from 100% (2016-09)" opened Olist's monthly trend on
    a test month with 6 orders; the HR hires line ended on a year 2000 with 9
    (five-dataset review, 2026-10-02)."""
    cfg = w.get("config")
    if not edges or not isinstance(cfg, dict):
        return w
    axis = next((cfg.get(k) for k in ("dimension", "start") if cfg.get(k) in edges), None)
    grain = cfg.get("dimension_granularity")
    span = (edges.get(axis) or {}).get(grain) if axis else None
    if not span or any(isinstance(f, dict) and f.get("column") == axis for f in cfg.get("filters") or []):
        return w
    filters = list(cfg.get("filters") or []) + [
        {"column": axis, "op": "gte", "value": span["from"]},
        {"column": axis, "op": "lt", "value": span["before"]}]
    why = str(w.get("why") or "").rstrip()
    note = f"Whole {grain}s only, {span['from']} to before {span['before']}: the partial or thin ones at the edges are left out."
    return {**w, "config": {**cfg, "filters": filters}, "why": (why + " " + note).strip()}


def date_as_number(w: dict, dates: set[str]) -> str | None:
    """Why a widget does arithmetic on a date it then draws as a number, or None.

    "Time to Carrier Trend" was the AVERAGE carrier date per month (Olist
    panel, 2026-10-02) -- a date, plotted as if it were a duration. A bubble
    or a model reads a date as years since it, and min/max of a date ("latest
    hire") is a date; everything else needs a duration column."""
    cfg = w.get("config") or {}
    wt = str(w.get("widget_type"))
    if wt.startswith("model_") or wt in ("bubble", "bubble_change", "schedule", "table", "list"):
        return None
    # A histogram or box plot does arithmetic on the values themselves; on a
    # date they raised in the shaper ("Delivery Duration Distribution by
    # Month", Olist panel 2026-10-02).
    if wt in ("histogram", "box_plot") and cfg.get("measure") in dates:
        return (f"{w.get('title')}: {cfg['measure']} is a date -- its spread is not a duration; "
                f"a duration needs its own column (one date minus another)")
    for key, agg_key in (("measure", "aggregation"), ("measure2", "aggregation2")):
        m = cfg.get(key)
        agg = str(cfg.get(agg_key) or cfg.get("aggregation") or "").lower()
        if m in dates and agg in ("sum", "avg", "mean", "median", ""):
            if m == cfg.get("dimension") or m == cfg.get("start"):
                continue
            return (f"{w.get('title')}: {m} is a date -- its {agg or 'total'} is not a duration; "
                    f"a duration needs its own column (one date minus another)")
    return None


def dependent_split(w: dict, dependents: dict) -> str | None:
    """Why a widget splits by two columns that are one fact twice, or None.

    Enrolments: every faculty has one tuition fee, so "Faculty > Fee" rings,
    a faculty-by-fee treemap and a fee pie (alongside faculty) repeat one
    breakdown under two names (2026-10-02 review). `dependents` maps a column
    to the columns it fixes one-to-one (fact_sheet.one_to_one)."""
    if not dependents:
        return None
    cfg = w.get("config") or {}
    splits = [cfg.get(k) for k in ("dimension", "dimension2", "facet_by", "category", "category2")]
    splits += list(cfg.get("levels") or [])
    splits = [s for s in splits if isinstance(s, str)]
    for i, a in enumerate(splits):
        for b in splits[i + 1:]:
            if b in (dependents.get(a) or ()) or a in (dependents.get(b) or ()):
                return (f"{w.get('title')}: {a} and {b} always go together (each {a} has one {b}), "
                        f"so splitting by both shows one breakdown twice")
    return None


def _drop_dependent_predictors(w: dict, dependents: dict) -> dict:
    """A model given two columns that are one fact keeps the first of them:
    the second only splits the same effect in two (tuition fee beside faculty)."""
    cfg = w.get("config")
    if not dependents or not isinstance(cfg, dict) or not isinstance(cfg.get("predictors"), list):
        return w
    keep: list = []
    for p in cfg["predictors"]:
        if any(p in (dependents.get(k) or ()) or k in (dependents.get(p) or ()) for k in keep):
            continue
        keep.append(p)
    return w if len(keep) == len(cfg["predictors"]) else {**w, "config": {**cfg, "predictors": keep}}


def _aggregation_from_title(w: dict, column_meta: dict | None = None,
                            dates: set[str] = frozenset()) -> dict:
    """A model that writes "Average salary by gender" and no aggregation gets
    the engine's default, a SUM -- total pay per gender under a title that
    says average (live HR panel, 2026-10-02). The title says which it meant."""
    cfg = w.get("config")
    wt = str(w.get("widget_type"))
    if not isinstance(cfg, dict) or cfg.get("aggregation") or not cfg.get("measure") \
            or wt in _NO_AGG or wt.startswith("model_"):
        return w
    title = " " + re.sub(r"[^\w]+", " ", str(w.get("title") or "").lower()) + " "
    words = _TITLE_AGG if wt not in ("bubble", "bubble_change") else \
        [(k, a) for k, a in _TITLE_AGG if a in ("avg", "median")]   # its count is the size
    agg = next((a for word, a in words if f" {word} " in title), None)
    # A bubble places each group by two of its numbers; summed, they mostly
    # measure the group's size, which the bubble's size already shows ("pay vs
    # tenure per department" drew at 4.2 billion by 750,000 years).
    if agg is None and wt in ("bubble", "bubble_change"):
        agg = "avg"
    if agg is None:
        # Otherwise how the column itself is rolled up (the author's setting,
        # then its name: salary averages, revenue sums), never a blind SUM --
        # "Salary percentiles by department" drew 4.15 billion per department.
        from .semantic_guard import default_summary
        m = cfg.get("measure")
        agg = "avg" if m in dates else default_summary(m, column_meta)
        agg = agg if agg in ("avg", "median", "sum", "countd", "count") else None
    return {**w, "config": {**cfg, "aggregation": agg}} if agg else w


def broken_promise(w: dict, profile: dict) -> str | None:
    """Why a proposed widget's title promises something its config does not
    draw, or None.

    The HR panel (2026-10-02) offered "Salary Distribution in Sales" -- a
    histogram of everyone's salary, the filter written under an invented key
    the engine ignores -- and "Salary by Title vs Gender" with no gender in it.
    A chart under a title it does not keep is worse than no chart. Judged on
    the model's titles only; the statistics engine writes its titles from its
    own config.
    """
    cfg = w.get("config") or {}
    known = {c["name"] for c in profile.get("columns", [])}
    for k in cfg:
        if k != "filters" and _FILTERISH.search(k):
            return f"{w.get('title')}: `{k}` is not a filter the engine applies"
    wt = str(w.get("widget_type"))
    ids = {c["name"] for c in profile.get("columns", []) if c.get("is_identifier")}
    agg = str(cfg.get("aggregation") or "sum").lower()
    if wt in ("kpi", "card", "gauge") and agg not in ("count", "countd", "frequency", "distinct"):
        measures = [cfg.get("measure")] + list(cfg.get("measures") or [])
        if ids & {m for m in measures if isinstance(m, str)}:
            # 60,770,729,684 -- a SUM of employee numbers -- headlined the
            # live HR panel's first page (2026-10-02).
            return f"{w.get('title')}: an identifier is counted, never summed or averaged"
    if wt == "card":
        ms = [m for m in cfg.get("measures") or [] if isinstance(m, str)]
        if ids & set(ms) and set(ms) - ids:
            return (f"{w.get('title')}: a card takes one aggregation, and a count of "
                    f"{', '.join(sorted(ids & set(ms)))} and a figure of the rest need two")
    if wt.startswith("dual_axis") or wt == "comparative_time_series":
        if cfg.get("measure") and cfg.get("measure") == cfg.get("measure2") and \
                str(cfg.get("aggregation") or "") == str(cfg.get("aggregation2") or ""):
            return f"{w.get('title')}: both axes draw the same measure"
    if w.get("source") != "model":
        return None
    title = " " + re.sub(r"[^\w]+", " ", str(w.get("title") or "").lower()) + " "
    # "Salary percentiles by department" as a dot plot of one value per
    # department: percentiles are a box plot's or a percentile aggregation's.
    if re.search(r" (percentiles?|quartiles?|p10|p25|p75|p90|p95|deciles?) ", title) \
            and wt not in ("box_plot", "histogram") and not str(cfg.get("aggregation") or "").startswith("p"):
        return f"{w.get('title')}: percentiles need a box plot or a percentile aggregation"
    # A headline number draws ONE value: a dimension on it is dropped before
    # drawing, so it cannot keep "Headcount by gender" (live HR panel).
    drawn_cfg = {k: v for k, v in cfg.items()
                 if not (wt in ("kpi", "card", "gauge") and k in ("dimension", "dimension2", "category"))}
    used = {c for c in _columns(drawn_cfg) if c in known}
    filtered = {f.get("column") for f in cfg.get("filters") or [] if isinstance(f, dict)}
    dates = {c["name"] for c in profile.get("columns", []) if c.get("role") == "datetime"}
    grain = str(cfg.get("dimension_granularity") or "")

    def same_period(name: str) -> bool:
        # "Hires by hire year" drawn on hire_date at the year grain keeps
        # its title: hire_year is that date's year (workforce, 2026-10-02).
        m = re.match(r"(.+)_(year|quarter|month|week|day)$", name)
        return bool(m and m.group(2) == grain and any(
            u in dates and u.startswith(m.group(1) + "_") for u in used))
    for c in profile.get("columns", []):
        name = c["name"]
        if name in used or name in filtered or c.get("is_identifier") or same_period(name):
            continue
        if f" {name.lower().replace('_', ' ')} " in title:
            return f"{w.get('title')}: the title names {name}, which the chart does not use"
        if c.get("role") == "categorical" and (c.get("distinct") or 0) <= 30:
            for tv in c.get("top_values") or []:
                v = str(tv.get("value") if isinstance(tv, dict) else tv)
                if len(v) >= 4 and f" {v.lower()} " in title:
                    return (f"{w.get('title')}: the title names {v}, but the chart shows every "
                            f"{name.replace('_', ' ')} (no filter on it)")
    return None


def _family(widget_type: str, config: dict) -> str:
    if widget_type == "bar" and config.get("dimension2"):
        return "bar_mix"
    return {"pie": "donut", "column": "bar"}.get(widget_type, widget_type)


_BREAKDOWN = ("bar", "column", "pie", "donut", "treemap", "dot_plot", "needle", "list",
              "funnel", "word_cloud")
_OVER_TIME = ("line", "area", "step")
_GRIDS = ("crosstab", "matrix", "heatmap", "table")


def _identity(w: dict) -> tuple:
    """Two candidates with this identity answer the same question."""
    c = w["config"]
    # A model of the same outcome is the same question however its predictors
    # were picked: the live HR panel kept "Salary drivers" and "Gender pay gap"
    # as two regressions of salary that both said Sales +22K (2026-10-02).
    wt = str(w["widget_type"])
    if wt in ("model_linear", "model_logistic", "model_tree", "model_rules"):
        return (wt, str(c.get("measure") or c.get("response") or ""))
    # One overview of how all the measures move together is enough.
    if wt in ("correlation_matrix", "parallel_coordinates"):
        return (wt,)
    # One multi-figure card per roll-up: two "snapshot" cards of nearly the
    # same figures opened the daily-ops page.
    if wt == "card":
        return (wt, str(c.get("aggregation") or ""))
    # One measure split by one category is one question whatever the mark: the
    # live HR panel kept "Headcount by Department" as a treemap AND as a bar.
    # Likewise one measure over time as a line, an area or a step.
    q = _family(wt, c)
    if not c.get("dimension2") and wt in _BREAKDOWN:
        q = "breakdown"
    elif wt in _OVER_TIME:
        q = "over_time"                    # with or without a split; the columns tell them apart
    elif wt in _GRIDS and c.get("dimension2"):
        q = "grid"                         # a crosstab and a matrix of the same two categories
    # The same series by year or by quarter is one question at two zooms.
    grain = "" if q == "over_time" else str(c.get("dimension_granularity") or "")
    # A distribution draws every value: an aggregation on it changes nothing.
    agg = "" if wt in ("box_plot", "histogram") else str(c.get("aggregation") or "")
    return (q, _columns(c), agg,
            grain, json.dumps(c.get("filters") or [], sort_keys=True))


def select(candidates: list[dict], size: int, sections: list[str]) -> tuple[list[dict], dict]:
    """Greedy pick by value x evidence x novelty, under per-type, per-section
    and flat-result quotas. Returns (chosen, stats)."""
    merged: dict[tuple, dict] = {}
    dupes = 0
    for w in candidates:
        key = _identity(w)
        if key in merged:
            dupes += 1
            # Keep the higher-valued copy; a model's question wording wins ties.
            if (w["value"], w.get("source") == "model") > (merged[key]["value"], merged[key].get("source") == "model"):
                merged[key] = w
        else:
            merged[key] = w
    pool = list(merged.values())
    per_type = max(2, size // 8)
    per_section = {s: max(2, math.ceil(size / max(1, len(sections))) + 1) for s in sections}
    per_section["summary"] = min(4, max(2, size // 8))
    max_flat = max(1, size // 12)
    # Headline numbers: one per measure and aggregation. Three "headcount"
    # tiles (all staff, then two filtered) opened the live HR page.
    headlines: set[tuple] = set()
    chosen: list[dict] = []
    type_n: dict[str, int] = {}
    sec_n: dict[str, int] = {}
    flat_n = 0
    used_cols: list[frozenset] = []

    def score(w: dict) -> float:
        cols = _columns(w["config"])
        overlap = max((len(cols & u) / max(1, len(cols | u)) for u in used_cols), default=0.0)
        # A column no chosen chart has shown yet is worth a little on its
        # own: on daily ops every lens drew orders and revenue, and canceled
        # orders -- a third of the analysts' reference -- never appeared.
        seen = frozenset().union(*used_cols) if used_cols else frozenset()
        fresh = 0.08 if cols - seen else 0.0
        return 0.45 * (w["value"] / 5) + 0.40 * w["evidence"] + 0.15 * (1 - overlap) + fresh

    # Two passes: the first keeps the page varied (per type, per section);
    # the second fills what the person asked for from what is left, when the
    # variety quotas -- not a lack of good ideas -- stopped it short (39 of 50
    # on the live HR panel). The flat-result rule holds in both.
    strict = True
    while pool and len(chosen) < size:
        pool.sort(key=score, reverse=True)
        pick = None
        for w in pool:
            fam = _family(w["widget_type"], w["config"])
            sec = w.get("section") or "composition"
            flat = w["evidence"] < 0.1
            if sec == "summary" and (_columns(w["config"]), str(w["config"].get("aggregation") or "")) in headlines:
                continue
            if strict and (type_n.get(fam, 0) >= per_type
                           or sec_n.get(sec, 0) >= per_section.get(sec, size)):
                continue
            if not strict and (w["value"] < 3 or type_n.get(fam, 0) >= 2 * per_type
                               or sec == "summary" and sec_n.get(sec, 0) >= per_section["summary"]):
                continue
            if flat and sec != "equity" and (flat_n >= max_flat or w["value"] < 4):
                continue
            pick = w
            break
        if pick is None:
            if strict:
                strict = False
                continue
            break
        pool.remove(pick)
        chosen.append(pick)
        fam = _family(pick["widget_type"], pick["config"])
        type_n[fam] = type_n.get(fam, 0) + 1
        sec = pick.get("section") or "composition"
        sec_n[sec] = sec_n.get(sec, 0) + 1
        flat_n += pick["evidence"] < 0.1 and sec != "equity"
        used_cols.append(_columns(pick["config"]))
        if sec == "summary":
            headlines.add((_columns(pick["config"]), str(pick["config"].get("aggregation") or "")))
    # Room left once the quotas stopped both passes: one chart for each
    # column nothing shows yet, the best that draws it.
    seen = frozenset().union(*used_cols) if used_cols else frozenset()
    for w in sorted(pool, key=score, reverse=True):
        if len(chosen) >= size:
            break
        new_cols = _columns(w["config"]) - seen
        if not new_cols or w["value"] < 3 or (w["evidence"] < 0.1 and w.get("section") != "equity"):
            continue
        chosen.append(w)
        seen = seen | _columns(w["config"])
    return chosen, {"duplicates_merged": dupes, "unique": len(merged)}


# ── the run ──────────────────────────────────────────────────────────────────

Probe = Callable[[str, dict], Awaitable[dict]]


#: Tiles that need the whole width: grids of rules, flows, two-scale time lines.
_FULL = ("table", "crosstab", "matrix", "model_rules", "ribbon", "sankey", "small_multiples",
         "dual_axis_time_series", "comparative_time_series", "parallel_coordinates",
         "decomposition", "network")
_TALL = {"model_linear": 6, "model_logistic": 6, "model_tree": 6, "model_cluster": 6,
         "model_rules": 6, "heatmap": 5, "correlation_matrix": 6, "sunburst": 5, "treemap": 5,
         "circle_pack": 5}
_HEADLINE = ("kpi", "gauge", "card")


def _size(w: dict, section: str, first_in_section: bool) -> tuple[int, int]:
    wt = str(w.get("widget_type"))
    if wt in ("kpi", "gauge"):
        return 3, 2
    if wt == "card":
        return 3, max(3, 1 + len((w.get("config") or {}).get("measures") or []))
    if wt in _FULL or wt.startswith("map_"):
        return 12, _TALL.get(wt, 5)
    # The page's lead trend gets the width: a time line squeezed into half a
    # page loses the years it is about.
    if section == "time" and first_in_section and wt in ("line", "area", "step", "bar"):
        return 12, 4
    return 6, _TALL.get(wt, 4)


def layout_section(widgets: list[dict], section: str) -> list[tuple[dict, dict]]:
    """Each widget with its place on a 12-column page, in reading order.

    Headline numbers first, then the rest in the order they were selected (the
    strongest first). Rows are filled greedily, looking ahead for a tile that
    fits the gap, so a half-width chart is not left alone beside a hole
    because a full-width one came next; tiles sharing a row share its height.
    The page is saved as `packed` by the dialog, so the builder keeps this
    arrangement instead of re-flowing it with its default recipe.
    """
    ordered = ([w for w in widgets if w.get("widget_type") in _HEADLINE]
               + [w for w in widgets if w.get("widget_type") not in _HEADLINE])
    lead = next((x for x in ordered if x.get("widget_type") not in _HEADLINE), None)
    sized = [(w, *_size(w, section, w is lead)) for w in ordered]
    out: list[tuple[dict, dict]] = []
    y = 0
    pending = list(sized)
    while pending:
        row = [pending.pop(0)]
        used = row[0][1]
        k = 0
        band = row[0][0].get("widget_type") in _HEADLINE
        while used < 12 and k < len(pending):
            # Headline numbers share a row only with each other.
            if (pending[k][0].get("widget_type") in _HEADLINE) == band and pending[k][1] <= 12 - used:
                used += pending[k][1]
                row.append(pending.pop(k))
            else:
                k += 1
        h = max(r[2] for r in row)
        # A row that does not reach the edge is stretched to it: a lone half-
        # width chart takes the row, two headline numbers take half each.
        if used < 12:
            n = len(row)
            row = [(w, 12 // n + (1 if i < 12 % n else 0), hh) for i, (w, _w, hh) in enumerate(row)]
        x = 0
        for w, width, _h in row:
            out.append((w, {"x": x, "y": y, "w": width, "h": h}))
            x += width
        y += h
    return out


#: Slicers per page, and the most values a slicer is offered for (beyond it a
#: reader is hunting, not choosing).
MAX_SLICERS = 2
SLICER_MAX_VALUES = 50
_SPLIT_KEYS = ("dimension", "dimension2", "facet_by", "category", "category2", "group")


def _filterable(profile: dict, ineligible: set[str] | frozenset = frozenset()) -> dict:
    return {c["name"]: c for c in profile.get("columns", [])
            if c.get("role") == "categorical" and not c.get("is_identifier")
            and not c.get("is_personal") and c["name"] not in ineligible
            and 2 <= (c.get("distinct") or 0) <= SLICER_MAX_VALUES}


def slicers_for(widgets: list[dict], profile: dict, ineligible: set[str] | frozenset = frozenset(),
                fallback: list[str] | None = None, limit: int = MAX_SLICERS) -> list[dict]:
    """Filter controls for one page: the categories its charts split by most.

    Every reference dashboard the five-dataset review drew (2026-10-02) put
    two or three slicers on each page -- faculty, department, service -- and
    the engines proposed none, so a page could be read but not questioned.
    A slicer narrows every chart on its page (the page's cross-filtering);
    a page whose charts split by nothing filterable takes the dataset's most
    used ones (`fallback`), so the headline page is filterable too."""
    ok = _filterable(profile, ineligible)
    uses: Counter = Counter()
    for w in widgets:
        cfg = w.get("config") or {}
        cols = [cfg.get(k) for k in _SPLIT_KEYS] + list(cfg.get("levels") or [])
        for c in cols:
            if isinstance(c, str) and c in ok:
                uses[c] += 1
    ranked = sorted(uses, key=lambda c: (-uses[c], ok[c].get("distinct") or 0, c))
    for c in fallback or []:
        if c in ok and c not in ranked:
            ranked.append(c)
    return [{"widget_type": "slicer", "title": f"Filter by {str(c).replace('_', ' ')}",
             "config": {"dimension": c}, "source": "panel",
             "why": f"Narrows every chart on this page to the {str(c).replace('_', ' ')} values you pick."}
            for c in ranked[:limit]]


def detail_table(profile: dict, ineligible: set[str] | frozenset = frozenset(),
                 dates: list[str] | None = None, mixed: dict | None = None) -> dict | None:
    """The rows themselves, for looking one up: the record's identifier, its
    categories, its date and its numbers -- never personal or hidden columns.

    Each of the five reference dashboards ended on a detail page (an employee
    lookup, the call records, the late-order list); the panel refused every
    such table as "an identifier with N values". A list of rows is not a chart
    of identifiers: the slicers above narrow it."""
    cols = [c for c in profile.get("columns", [])
            if c["name"] not in ineligible and not c.get("is_personal")]
    ids = sorted([c for c in cols if c.get("is_identifier")], key=lambda c: -(c.get("distinct") or 0))
    cats = [c["name"] for c in cols if c.get("role") == "categorical" and not c.get("is_identifier")
            and (c.get("distinct") or 0) <= SLICER_MAX_VALUES][:4]
    date_cols = [d for d in (dates or []) if d in {c["name"] for c in cols}][:1]
    from .semantic_guard import non_additive_kind
    nums = [c["name"] for c in cols if c.get("role") == "numeric" and not c.get("is_identifier")
            and non_additive_kind(c["name"]) != "coordinate"][:3]
    columns = ([ids[0]["name"]] if ids else []) + cats + date_cols + nums
    if len(columns) < 2:
        return None
    cfg: dict = {"columns": columns[:9], "limit": 200}
    # Largest first by a number that is one unit throughout: sorted by a
    # mixed-unit volume, the call records put bytes above every call.
    key = next((m for m in nums if m not in (mixed or {})), None)
    if key:
        cfg.update({"sort_col": key, "sort": "desc"})
    return {"widget_type": "table", "title": "Detail rows", "config": cfg, "source": "panel",
            "section": "detail",
            "why": "The records behind the charts, largest first; the filters above narrow them."}


def with_slicers(placed: list[tuple[dict, dict]], slicers: list[dict]) -> list[tuple[dict, dict]]:
    """A band of slicers across the top of a laid-out page; the page moves down."""
    if not slicers:
        return placed
    n = len(slicers)
    h = 3
    band = [(s, {"x": (12 // n) * i, "y": 0, "w": 12 // n if i < n - 1 else 12 - (12 // n) * (n - 1),
                 "h": h}) for i, s in enumerate(slicers)]
    return band + [(w, {**slot, "y": slot["y"] + h}) for w, slot in placed]


async def run_panel(*, df, profile: dict, roles: dict, column_meta: dict | None,
                    ineligible: set[str], findings: list[dict], facts: dict,
                    goal: str | None, size: int, probe: Probe, client=None,
                    knowledge=None, progress=None, extra: list[dict] | None = None) -> dict:
    from .readback import as_i18n, takeaway
    from .suggest_dataset_dashboard import (PROBE_CONCURRENCY, _probe, polish_widget,
                                            resolve_time_words, validate_widget)
    size = min(max(int(size or 24), 6), 60)
    lenses = choose_lenses(profile, facts.get("facts") or [])

    # 1. proposals: one call per lens, concurrently; plus the engine's own ideas
    proposed: list[dict] = []
    lens_notes: dict[str, str] = {}
    async def tell(stage: str, **detail) -> None:
        if progress is not None:
            await progress(stage, detail)

    # Enough ideas to choose from: about 1.6 per place, after duplicates and
    # refusals. At 50 visuals the fixed 12 per lens left the HR panel with 36
    # distinct ideas for 50 places (2026-10-02).
    per_lens = min(25, max(PER_LENS, math.ceil(size * 1.6 / max(1, len(lenses)))))
    dates = {c["name"] for c in profile.get("columns", []) if c.get("role") == "datetime"}
    groups = {c["name"] for c in profile.get("columns", []) if c.get("role") == "categorical"
              and 2 <= (c.get("distinct") or 0) <= 4 and not c.get("is_identifier")}
    if client is not None and lenses:
        await tell("proposing", lenses=len(lenses))

        async def ask(lens: str):
            got = await client.complete_json(
                lens_messages(lens, profile, facts.get("text") or "", goal, knowledge, n=per_lens),
                LENS_SCHEMA, max_tokens=8000, enforce=True)
            return lens, got
        answers = await asyncio.gather(*(ask(l) for l in lenses), return_exceptions=True)
        for lens, got in zip(lenses, answers):
            # One lens failing (a timeout, a malformed answer) costs that lens,
            # not the panel: the others and the statistics engine still stand.
            if isinstance(got, BaseException):
                lens_notes[lens] = f"failed: {type(got).__name__}"
                continue
            got = got[1]
            items = (got or {}).get("widgets") or []
            lens_notes[lens] = f"{len(items)} proposed"
            for w in items:
                # A model's answer is data: anything not shaped like a widget
                # is skipped, not trusted to have the fields it should.
                if not isinstance(w, dict) or not isinstance(w.get("widget_type"), str):
                    continue
                cfg = w.get("config") if isinstance(w.get("config"), dict) else {}
                w = {**w, "config": cfg, "title": str(w.get("title") or w.get("widget_type"))}
                section = _section_for(str(w.get("widget_type")), cfg, dates)
                # The fairness lens keeps its own page for what compares a
                # small group (gender) like for like; anything else it
                # proposed goes where its subject is.
                if lens == "equity" and section not in ("summary", "time") and groups & _columns(cfg):
                    section = "equity"
                proposed.append({**w, "section": section,
                                 "source": "model", "lens": lens,
                                 "value": _value(w.get("value"))})
    rules = await asyncio.to_thread(rule_candidates, df, roles, column_meta, ineligible, findings)
    # The derived fields' own charts (services/derived_fields): a rate of
    # totals, a duration -- through the same gate and selection as the rest.
    extra = [{**w, "value": _value(w.get("value"))} for w in extra or []]
    candidates = proposed + rules + extra

    # 2. gate: fix vocabulary, validate, draw
    rejected: list[str] = []
    refused: list[dict] = []
    ready = []
    for w in candidates:
        w, ok, why = repair_and_check(w, profile, column_meta, facts.get("mixed_units") or {},
                                      facts.get("one_to_one") or {}, facts.get("identical") or {},
                                      facts.get("edges") or {})
        if not ok:
            rejected.append(why)
            refused.append({"title": w.get("title"), "widget_type": w.get("widget_type"),
                            "config": w.get("config"), "why": why, "source": w.get("source")})
            continue
        ready.append({**w, **polish_widget(w, profile)})
    await tell("drawing", ideas=len(ready))
    gate = asyncio.Semaphore(PROBE_CONCURRENCY)
    drawn: dict[int, dict] = {}

    async def draw(i: int, w: dict):
        async with gate:
            try:
                result = await probe(w["widget_type"], w["config"])
            except Exception as exc:                         # noqa: BLE001
                # A shaper that raises on one config costs that widget only.
                log.warning("panel probe failed for %r: %s", w.get("title"), exc, exc_info=True)
                return False, 0, f"could not be drawn ({type(exc).__name__}: {exc})"[:300]
            drawn[i] = result

            async def cached(_wt, _cfg):
                return result
            try:
                return await _probe(w, cached)
            except Exception as exc:                         # noqa: BLE001
                return False, 0, f"could not be judged ({type(exc).__name__})"

    judged = await asyncio.gather(*(draw(i, w) for i, w in enumerate(ready)))
    alive = []
    for i, (w, (ok, rows, why)) in enumerate(zip(ready, judged)):
        if not ok:
            rejected.append(f"{w.get('title')}: {why or 'returned nothing to draw'}")
            refused.append({"title": w.get("title"), "widget_type": w.get("widget_type"),
                            "config": w.get("config"), "why": why or "returned nothing to draw",
                            "source": w.get("source")})
            continue
        result = drawn.get(i)
        said = takeaway(w["widget_type"], w["config"], result)
        alive.append({**w, "row_count": rows,
                      "takeaway": str(said) if said else None, "takeaway_i18n": as_i18n(said),
                      "evidence": round(evidence(w["widget_type"], w["config"], result), 3)})

    # 3. select
    await tell("selecting", drawn=len(alive))
    sections = ["summary"] + lenses
    chosen, stats = select(alive, size, sections)

    # 4. the detail page: the rows themselves, drawn like everything else
    from .insights import order_event_dates
    detail = detail_table(profile, ineligible, order_event_dates(sorted(dates)),
                          facts.get("mixed_units") or {})
    if detail is not None:
        try:
            got = await probe("table", detail["config"])
            if (got or {}).get("rows"):
                chosen.append({**detail, "row_count": len(got["rows"])})
                sections.append("detail")
        except Exception as exc:                             # noqa: BLE001
            log.warning("detail table could not be drawn: %s", exc)

    # 5. shape as one proposal per section, in section order, each laid out
    #    as the page it will become, with its filters across the top
    by_section = {sec: [w for w in chosen if (w.get("section") or "composition") == sec]
                  for sec in sections}
    overall = [s["config"]["dimension"] for s in slicers_for(chosen, profile, ineligible)]
    proposals = []
    for sec in sections:
        widgets = by_section[sec]
        if not widgets:
            continue
        spec = SUMMARY if sec == "summary" else DETAIL if sec == "detail" else LENSES[sec]
        # A page that splits by nothing filterable (a trend, a model) still
        # takes the dataset's own: "pay over time, for Sales" is a question.
        controls = slicers_for(widgets, profile, ineligible, fallback=overall)
        keys = ("widget_type", "title", "why", "config", "row_count", "takeaway", "takeaway_i18n",
                "question", "value", "audience", "evidence", "source")
        proposals.append({
            "title": spec["title"], "section": sec,
            "rationale": "The numbers to open the page with." if sec == "summary"
            else spec["brief"] if sec == "detail"
            else f"Through the {spec['title'].lower()} lens: {spec['brief']}.",
            "widgets": [{**{k: w.get(k) for k in keys}, "layout": slot}
                        for w, slot in with_slicers(layout_section(widgets, sec), controls)],
        })
    return {
        "proposals": proposals,
        "panel": {"lenses": lenses, "lens_notes": lens_notes,
                  "candidates": len(candidates), "from_model": len(proposed),
                  "from_statistics": len(rules), "from_derived": len(extra), "drawn": len(alive),
                  "rejected": len(rejected), "duplicates_merged": stats["duplicates_merged"],
                  "selected": len(chosen), "size": size,
                  # What a reader is told was left out, by kind; "not_picked"
                  # drew fine but lost to stronger ideas for the space.
                  "left_out": dict(Counter(refusal_code(r.get("why")) for r in refused)),
                  "not_picked": max(0, stats.get("unique", len(alive)) - len(chosen))},
        "reason": "; ".join(rejected[:6]),
        # Every refused idea with the config it arrived in: what the next
        # normaliser or prompt rule should be built from.
        "refused": [{**r, "code": refusal_code(r.get("why"))} for r in refused[:60]],
    }
