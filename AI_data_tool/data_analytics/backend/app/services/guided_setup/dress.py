"""What a designed page gains AFTER its charts are chosen: options,
interactivity and navigation (docs/guided-setup/RETRY_2_COMPARISON.md, "richer
dashboards"; settings.setup_dashboard_richness).

The designer decides WHICH charts answer the person's questions. This step is
plain code -- no model -- and adds only what follows from the charts
themselves and from what is stored about the columns:

* a **display rule** on a comparison of groups: the groups above the average
  are marked -- as good or as bad only when the column's stored direction says
  which; otherwise in a neutral colour;
* a headline number gains its **history**: a sparkline and the change against
  the previous period, when the data has a date and enough periods;
* a ranking of counts or totals where a few groups carry most of the whole is
  drawn as a **Pareto** (bars with the running share);
* a page that would be bar after bar keeps its first comparisons as bars and
  draws the later ones as what their own **shape** calls for: parts of a whole
  as a ring (a few parts) or a treemap (many); averages and rates of a handful
  of groups as a dot plot; one total over time per dashboard as an area;
* **filter controls** for the categories the page's charts split by;
* **click to filter**: choosing a group in one chart narrows the others on
  the page;
* **navigation**: a button to each other page, carrying the reader's
  selections with it;
* **drill-through**: one more page for a single value of the category the
  dashboard splits by most -- its headline numbers, its trend and its records
  -- opened from any chart split by that category.

Every changed chart is drawn again before it is kept; one that no longer
draws, or whose rule the engine refuses, keeps its plain form. Nothing here
reads a column's or a value's name to decide anything.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Marks above the average, by what the stored direction of the number says.
COLOUR_GOOD, COLOUR_BAD, COLOUR_NEUTRAL = "#4ade80", "#f87171", "#6c8fff"
#: A comparison needs this many groups before "above the average" says anything.
RULE_MIN_GROUPS = 3
#: Pareto: at least this many groups, and this share of them (or fewer)
#: carrying this share of the whole.
PARETO_MIN_GROUPS = 6
PARETO_FEW = 0.3
PARETO_SHARE = 0.6
#: A page of bars reads as one chart repeated: past this many, the later ones
#: are drawn as the kind their own shape calls for.
BARS_KEPT = 2
PARTS_FEW = 5          # parts of a whole a ring can carry
PRECISE_MAX = 12       # groups a dot plot compares precisely
#: Periods a number needs behind it before its history is worth a sparkline.
SPARK_MIN_PERIODS = 6
#: Filter controls and click-to-filter sources per page; buttons to other pages.
MAX_SLICERS = 2
MAX_SOURCES = 3
MAX_NAV = 5
#: What the drill-through page repeats for the one value picked.
DRILL_NUMBERS = 4
DRILL_MIN_VALUES = 3
_PLAIN = ("text", "slicer", "button")

T = {
    "en": {"above": "Above the average", "filter": "Filter by {c}", "go": "Go to: {title}",
           "pareto": "{title} — the few that carry most",
           "one": "One {c}", "onewhy": "Opened from any chart split by {c}: the headline numbers, the trend and "
                                       "the records for the {c} you picked."},
    "ar": {"above": "أعلى من المتوسط", "filter": "تصفية حسب {c}", "go": "انتقل إلى: {title}",
           "pareto": "{title} — القلّة التي تحمل الأكثر",
           "one": "تفاصيل {c} واحد", "onewhy": "تُفتح من أي مخطط مقسَّم حسب {c}: الأرقام الرئيسية والاتجاه "
                                               "والسجلات لقيمة {c} التي اخترتها."},
}


def _t(lang: str, key: str, **kw) -> str:
    return (T.get(lang) or T["en"])[key].format(**kw)


def _series(result: dict) -> list[tuple[str, float]]:
    out = []
    for r in (result or {}).get("rows") or []:
        if isinstance(r, dict) and r.get("value") is not None:
            try:
                out.append((str(r.get("name")), float(r["value"])))
            except (TypeError, ValueError):
                continue
    return out


def _direction(measure, column_meta: dict | None, flag_of: dict | None = None) -> str | None:
    """higher_better | higher_worse, when someone (or the one-time
    classification) stored it for this number -- or for the yes/no column a
    share was made from. None otherwise: no colour then carries a judgement."""
    meta = column_meta or {}
    for name in (measure, (flag_of or {}).get(measure)):
        entry = meta.get(name) if isinstance(meta.get(name), dict) else {}
        if entry.get("direction") in ("higher_better", "higher_worse"):
            return entry["direction"]
    return None


def above_average_rule(widget: dict, result: dict, lang: str, column_meta: dict | None,
                       flag_of: dict | None = None) -> dict | None:
    """The rule for a comparison of groups, or None when it would say nothing."""
    cfg = widget.get("config") or {}
    values = [v for _n, v in _series(result)]
    if (widget.get("widget_type") != "bar" or not cfg.get("dimension") or cfg.get("display_rules")
            or len(values) < RULE_MIN_GROUPS or max(values) == min(values)):
        return None
    way = _direction(cfg.get("measure"), column_meta, flag_of)
    fill = COLOUR_GOOD if way == "higher_better" else COLOUR_BAD if way == "higher_worse" else COLOUR_NEUTRAL
    return {"id": "setup-above-average", "kind": "expression", "target": "mark", "label": _t(lang, "above"),
            "expression": "value > AVG(value)", "style": {"fill": fill}}


def is_pareto(values: list[float]) -> bool:
    """True when a few of the groups carry most of the whole."""
    ranked = sorted((v for v in values if v > 0), reverse=True)
    total = sum(ranked)
    if len(ranked) < PARETO_MIN_GROUPS or not total:
        return False
    few = max(1, int(len(ranked) * PARETO_FEW))
    return sum(ranked[:few]) / total >= PARETO_SHARE


def another_kind(widget: dict, groups: int, percent: set[str], dates: set[str]) -> str | None:
    """The chart a bar could be instead, by its own shape -- or None when a bar
    is what it should stay."""
    cfg = widget.get("config") or {}
    if (widget.get("widget_type") != "bar" or cfg.get("dimension") in dates or cfg.get("dimension2")
            or cfg.get("dimension_granularity") or groups < 2):
        return None
    additive = str(cfg.get("aggregation") or "") in ("count", "sum", "countd") and cfg.get("measure") not in percent
    if additive:                       # parts of a whole
        return "donut" if groups <= PARTS_FEW else "treemap"
    return "dot_plot" if 3 <= groups <= PRECISE_MAX else None


def relations(widgets: list[dict], dates: set[str]) -> list[dict]:
    """Click to filter: each chart that splits by a category narrows the other
    charts of its page. Indices are positions in `widgets`."""
    def source(w):
        cfg = w.get("config") or {}
        dim = cfg.get("dimension")
        return (w.get("widget_type") in ("bar", "donut", "treemap", "dual_axis_bar_line", "dot_plot", "funnel")
                and isinstance(dim, str) and dim not in dates and not cfg.get("dimension_granularity"))
    data = [i for i, w in enumerate(widgets) if w.get("widget_type") not in _PLAIN]
    out = []
    for i in [i for i in data if source(widgets[i])][:MAX_SOURCES]:
        out += [{"from": i, "to": j, "mode": "filter"} for j in data if j != i]
    return out


def slicers(widgets: list[dict], profile: dict, ineligible: set[str], skip: set[str], lang: str) -> list[dict]:
    """Filter controls for the categories this page's charts split by."""
    from ..analyst_panel import slicers_for
    known = {c["name"] for c in profile.get("columns", [])}
    found = [s for s in slicers_for(widgets, profile, ineligible, limit=MAX_SLICERS + len(skip))
             if s["config"].get("dimension") in known and s["config"]["dimension"] not in skip][:MAX_SLICERS]
    return [{"widget_type": "slicer", "title": _t(lang, "filter", c=str(s["config"]["dimension"]).replace("_", " ")),
             # The control the panel chose for how many values there are (analyst_panel.control_for).
             "config": {k: v for k, v in s["config"].items() if k in ("dimension", "slicer_mode")}} for s in found]


def navigation(titles: list[str], here: int, lang: str) -> list[dict]:
    """A button to each other page. The target is named by its TITLE: the page's
    id exists only once the dashboard is built, and a person may leave pages
    out -- the builder wires each button to the page of that title, or drops it."""
    out = []
    for j, title in enumerate(titles):
        if j == here or not title:
            continue
        out.append({"widget_type": "button", "title": _t(lang, "go", title=title),
                    "config": {"label": title, "action": "navigate", "actionPageTitle": title, "carry_filters": True}})
    return out[:MAX_NAV]


def drill_page(proposals: list[dict], profile: dict, dates: set[str], skip: set[str], lang: str) -> dict | None:
    """A drill-through page for one value of the category these pages split by
    most, and the charts that open it marked (`drill_to`). The platform's own
    mechanism (analyst_panel.drill_page): a page of type `drillthrough` with a
    `prompt_column`; the builder gives each marked chart the page's id once
    the page exists. None when no category is split by, or nothing is left to
    show for one value."""
    from collections import Counter
    usable = {c["name"]: c for c in profile.get("columns", [])
              if c.get("role") == "categorical" and not c.get("is_identifier") and not c.get("is_personal")
              and (c.get("distinct") or 0) >= DRILL_MIN_VALUES}
    uses: Counter = Counter()
    for p in proposals:
        for w in p.get("widgets") or []:
            dim = (w.get("config") or {}).get("dimension")
            if w.get("widget_type") not in _PLAIN and dim in usable and dim not in skip and dim not in dates:
                uses[dim] += 1
    if not uses:
        return None
    col = sorted(uses, key=lambda c: (-uses[c], c))[0]
    charts = [w for p in proposals for w in p.get("widgets") or [] if w.get("widget_type") not in _PLAIN]
    # For one value: the numbers, one line over time, the records -- nothing split by the value itself.
    numbers = [w for w in charts if w.get("widget_type") in ("kpi", "gauge", "card")][:DRILL_NUMBERS]
    trend = [w for w in charts if w.get("widget_type") in ("line", "area")
             and (w.get("config") or {}).get("dimension") in dates][:1]
    records = [w for w in charts if w.get("widget_type") in ("table", "list")][:1]
    picked = [w for w in numbers + trend + records if (w.get("config") or {}).get("dimension") != col]
    if not numbers and not records:
        return None
    for w in charts:
        if (w.get("config") or {}).get("dimension") == col:
            w["drill_to"] = "drill"
    label = str(col).replace("_", " ")
    return {"title": _t(lang, "one", c=label), "rationale": _t(lang, "onewhy", c=label),
            "page_type": "drillthrough", "prompt_column": col, "prompt_label": label[:1].upper() + label[1:],
            "answer": "", "note": None, "answers": [], "unanswered": [],
            "scope_filters": list((proposals[0] or {}).get("scope_filters") or []),
            "widgets": [{k: v for k, v in w.items() if k not in ("layout", "drill_to")} for w in picked],
            "relations": []}


async def apply(proposals: list[dict], gate, inputs, lang: str) -> None:
    """Dress the finished pages in place. Does nothing in the `basic` setting."""
    if getattr(gate, "richness", "basic") == "basic" or not proposals:
        return
    from ..insights import order_event_dates
    meta = inputs.column_meta
    dates = [d for d in order_event_dates(sorted(gate.dates)) if d in inputs.df.columns]
    ineligible = inputs.ineligible()
    titles = [str(p.get("title") or "") for p in proposals]

    scope: list[dict] = []

    async def draws(widget: dict) -> dict | None:
        # Drawn on the part of the data the page is about: the scope lives on
        # the dashboard, not in each chart, so it is put back for the drawing.
        from .answer import with_scope
        try:
            result, _why = await gate._draw({**widget, "config": with_scope(widget.get("config") or {}, scope)})
        except Exception as exc:                                    # noqa: BLE001 -- an option, never a gate
            logger.info("guided setup: an option was not kept: %s", exc)
            return None
        return result

    area_used = False
    for at, p in enumerate(proposals):
        scope[:] = [f for f in p.get("scope_filters") or [] if isinstance(f, dict)]
        dressed = []
        bars_seen = 0
        kinds_here = {w.get("widget_type") for w in p.get("widgets") or []}
        for w in p.get("widgets") or []:
            wt, cfg = w.get("widget_type"), dict(w.get("config") or {})
            if wt in _PLAIN:
                dressed.append(w)
                continue
            result = await draws(w) or {}
            values = [v for _n, v in _series(result)]
            additive = str(cfg.get("aggregation") or "") in ("count", "sum", "countd")
            # A few groups carrying most of a total: bars with the running share.
            if (wt == "bar" and additive and cfg.get("dimension") not in gate.dates and not cfg.get("dimension2")
                    and cfg.get("measure") not in gate.percent and is_pareto(values)):
                wide = {**w, "widget_type": "dual_axis_bar_line",
                        "config": {**{k: v for k, v in cfg.items() if k != "limit"}, "pareto": True, "sort": "desc"}}
                if (await draws(wide) or {}).get("rows"):
                    dressed.append(wide)
                    continue
            # Bar after bar: the later ones as the kind their shape calls for.
            if wt == "bar":
                bars_seen += 1
                kind = another_kind(w, len(values), gate.percent, set(gate.dates)) if bars_seen > BARS_KEPT else None
                if kind and kind not in kinds_here:
                    other = {**w, "widget_type": kind, "config": {k: v for k, v in cfg.items() if k != "limit" or kind != "treemap"}}
                    if (await draws(other) or {}).get("rows"):
                        kinds_here.add(kind)
                        dressed.append(other)
                        continue
            # One total over time, per dashboard, as the volume it is.
            if (wt == "line" and additive and not area_used and cfg.get("dimension") in gate.dates
                    and cfg.get("measure") not in gate.percent and "area" not in kinds_here):
                filled = {**w, "widget_type": "area"}
                if (await draws(filled) or {}).get("rows"):
                    area_used = True
                    kinds_here.add("area")
                    dressed.append(filled)
                    continue
            # A headline number with its history beside it.
            if (wt == "kpi" and dates and cfg.get("measure") and not cfg.get("sparkline_date")
                    and not any(isinstance(f, dict) and f.get("column") == dates[0] for f in cfg.get("filters") or [])):
                trended = {**w, "config": {**cfg, "sparkline_date": dates[0]}}
                trend = (await draws(trended) or {}).get("trend") or {}
                if len(trend.get("series") or []) >= SPARK_MIN_PERIODS:
                    dressed.append(trended)
                    continue
            # A comparison of groups: the ones above the average are marked.
            rule = above_average_rule(w, result, lang, meta, getattr(gate, "flag_of", None))
            if rule is not None:
                ruled = {**w, "config": {**cfg, "display_rules": [rule]}}
                drawn = await draws(ruled) or {}
                if drawn.get("rows") and not drawn.get("rule_errors"):
                    dressed.append(ruled)
                    continue
            dressed.append(w)
        head = [w for w in dressed if w.get("widget_type") == "text"]
        body = [w for w in dressed if w.get("widget_type") != "text"]
        nav = navigation(titles, at, lang) if len(proposals) > 1 else []
        scoped = {f.get("column") for f in p.get("scope_filters") or [] if isinstance(f, dict)}
        controls = slicers(body, inputs.profile, ineligible, scoped, lang)
        p["widgets"] = head + nav + controls + body
        p["relations"] = relations(p["widgets"], gate.dates)
    # One more page, reached by clicking a group: never listed among the buttons above.
    scoped_all = {f.get("column") for p in proposals for f in p.get("scope_filters") or [] if isinstance(f, dict)}
    drill = drill_page(proposals, inputs.profile, set(gate.dates), scoped_all, lang)
    if drill is not None:
        # A way back: the drill-through page has no tab of its own.
        back = navigation(titles[:1] + [drill["title"]], 1, lang) if titles and titles[0] else []
        drill["widgets"] = back + drill["widgets"]
        proposals.append(drill)


async def redress(page: dict, previous: dict, gate, inputs, lang: str, richness: str) -> None:
    """One page after the person changed it ("Change this page"), dressed again.

    Narrower than `apply`, because here a person has spoken: a chart is never
    turned into another kind, and a chart carried over from the page as it was
    keeps exactly the options it had. Only a chart that is NEW gets a headline's
    history or the marking of groups above the average. The page keeps the
    buttons it had (they name the other pages, which did not change); its
    filter controls and click-to-filter links are worked out again, since the
    charts they belong to may have changed."""
    if richness == "basic" or not page:
        return
    from ..insights import order_event_dates
    from .answer import with_scope
    dates = [d for d in order_event_dates(sorted(gate.dates)) if d in inputs.df.columns]
    scope = [f for f in page.get("scope_filters") or [] if isinstance(f, dict)]
    was = previous.get("widgets") or []
    before = {(w.get("widget_type"), str(w.get("title") or "")) for w in was if w.get("widget_type") not in _PLAIN}

    async def draws(widget: dict) -> dict:
        try:
            result, _why = await gate._draw({**widget, "config": with_scope(widget.get("config") or {}, scope)})
        except Exception as exc:                                    # noqa: BLE001 -- an option, never a gate
            logger.info("guided setup: an option was not kept: %s", exc)
            return {}
        return result or {}

    dressed = []
    for w in page.get("widgets") or []:
        wt, cfg = w.get("widget_type"), dict(w.get("config") or {})
        if wt in _PLAIN or (wt, str(w.get("title") or "")) in before:
            dressed.append(w)
            continue
        if (wt == "kpi" and dates and cfg.get("measure") and not cfg.get("sparkline_date")
                and not any(isinstance(f, dict) and f.get("column") == dates[0] for f in cfg.get("filters") or [])):
            trended = {**w, "config": {**cfg, "sparkline_date": dates[0]}}
            if len((((await draws(trended)).get("trend") or {}).get("series")) or []) >= SPARK_MIN_PERIODS:
                dressed.append(trended)
                continue
        rule = above_average_rule(w, await draws(w), lang, inputs.column_meta, getattr(gate, "flag_of", None))
        if rule is not None and not cfg.get("display_rules"):
            ruled = {**w, "config": {**cfg, "display_rules": [rule]}}
            drawn = await draws(ruled)
            if drawn.get("rows") and not drawn.get("rule_errors"):
                dressed.append(ruled)
                continue
        dressed.append(w)
    head = [w for w in dressed if w.get("widget_type") == "text"]
    body = [w for w in dressed if w.get("widget_type") not in _PLAIN]
    nav = [w for w in was if w.get("widget_type") == "button"]
    scoped = {f.get("column") for f in scope}
    page["widgets"] = head + nav + slicers(body, inputs.profile, inputs.ineligible(), scoped, lang) + body
    page["relations"] = relations(page["widgets"], gate.dates)
