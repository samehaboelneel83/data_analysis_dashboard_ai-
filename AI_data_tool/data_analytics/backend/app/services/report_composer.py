"""Compose a whole report page from the insights engine's ranked findings.

The engine already finds what matters and already knows which chart shows it
(`insights.suggest_widgets_from_findings`). What was missing is PLACEMENT: a
ranked list is not a report, and turning one into a page by hand -- widget by
widget, sizing and positioning each -- is the work this removes.

**Narrative order, not density.** The page reads the way an analyst writes one:

    summary   KPI cards for the headline measures -- what the numbers ARE
    drivers   the highest-scoring findings, largest first -- what MOVED and why
    detail    the remaining findings, plus the narrative paragraph in prose

A dense grid would fit more on screen and answer less. The bands exist so the
reader meets the conclusion before the evidence, which is the order a report is
read in and the opposite of the order the detectors produce.

**Width encodes rank.** A finding scoring near 1.0 gets a full-width chart, a
mid-scoring one gets half. The strongest signal is therefore also the largest
mark on the page, so scanning the layout and reading the ranking give the same
answer. Widths are quantized to the 12-column grid the builder already uses
(`ReportBuilder.tsx`'s `COLS = 12`), never to arbitrary pixels.

**Nothing here computes statistics.** Every number reaching the page came from
`generate_insights`, over a frame the caller is already permitted to see. This
module only decides what goes where, which is why it needs no security logic of
its own -- and must never grow any, because that would be a second place for
row/column rules to be got wrong.
"""
from __future__ import annotations

from typing import Any

#: The builder canvas is 12 columns wide (ReportBuilder.tsx `COLS = 12`).
#: Mirrored, so a change there must change this -- pinned by a test.
GRID_COLS = 12

#: Row units, matching the model default's `h` of 4 for an ordinary chart.
KPI_H = 3
CHART_H = 5
TEXT_H = 3

#: A KPI row of four cards reads as a summary; more becomes a wall of numbers.
MAX_KPIS = 4
#: Past roughly a dozen widgets a page stops being read and starts being
#: scrolled. The findings are ranked, so the cut takes the weakest.
MAX_CHARTS = 8

#: A finding at or above this score earns the full width of the page.
FULL_WIDTH_SCORE = 0.75
#: Below this, a finding is supporting detail rather than a headline.
DETAIL_SCORE = 0.35


def _width_for(score: float) -> int:
    """Grid columns for a finding of this score.

    Three sizes, not a continuum: a 7-column widget beside a 5-column one looks
    like a mistake rather than a ranking. Full / half / third are the widths the
    grid divides into evenly.
    """
    if score >= FULL_WIDTH_SCORE:
        return GRID_COLS
    if score >= DETAIL_SCORE:
        return GRID_COLS // 2
    return GRID_COLS // 3


def _pack(widgets: list[dict], start_y: int) -> int:
    """Lay widgets left-to-right, wrapping when the row is full.

    Mutates each widget's `layout` in place and returns the next free row. The
    packing is deliberately simple -- no bin-packing, no gap-filling -- because
    a reader follows reading order, and a cleverly packed page reorders the
    argument to save space.
    """
    x = 0
    y = start_y
    row_h = 0
    for w in widgets:
        need = w["layout"]["w"]
        if x + need > GRID_COLS:          # wrap
            y += row_h
            x = 0
            row_h = 0
        w["layout"]["x"] = x
        w["layout"]["y"] = y
        x += need
        row_h = max(row_h, w["layout"]["h"])
    return y + row_h if widgets else start_y


def _kpi_widgets(findings: list[dict], roles: dict[str, str]) -> list[dict]:
    """One card per headline measure, taken from the findings themselves.

    Measures are drawn from the findings rather than from every numeric column,
    so the summary row is about what the engine found interesting -- not the
    first four numeric columns in file order.
    """
    seen: list[str] = []
    for f in findings:
        for col in f.get("columns") or []:
            if roles.get(col) == "numeric" and col not in seen:
                seen.append(col)
        if len(seen) >= MAX_KPIS:
            break

    out: list[dict] = []
    width = GRID_COLS // max(len(seen), 1) if seen else GRID_COLS
    for col in seen[:MAX_KPIS]:
        out.append({
            "widget_type": "kpi",
            "title": col,
            "config": {"measure": col, "aggregation": "sum"},
            "layout": {"x": 0, "y": 0, "w": width, "h": KPI_H},
        })
    return out


def compose_page(findings: list[dict], suggestions: list[dict],
                 narrative: str | None = None,
                 roles: dict[str, str] | None = None) -> dict[str, Any]:
    """Turn ranked findings and their widget suggestions into one page.

    `findings` and `suggestions` come from `insights.generate_insights` and
    `insights.suggest_widgets_from_findings` respectively -- both already
    computed over a secured frame by the caller. This never loads data.

    Returns `{"name", "widgets": [...]}` where each widget is
    `{widget_type, title, config, layout}` -- the exact shape `ReportWidget`
    stores, so the router can persist them without translation.
    """
    by_score = sorted(suggestions, key=lambda s: float(s.get("score") or 0),
                      reverse=True)[:MAX_CHARTS]

    charts: list[dict] = []
    for s in by_score:
        score = float(s.get("score") or 0)
        charts.append({
            "widget_type": s["widget_type"],
            # The finding's own sentence is the honest title: it states exactly
            # what the chart below it shows, with the figures already in it.
            "title": (s.get("title") or "")[:120],
            "config": s.get("config") or {},
            "layout": {"x": 0, "y": 0, "w": _width_for(score), "h": CHART_H},
        })

    drivers = [c for c in charts if c["layout"]["w"] >= GRID_COLS // 2]
    detail = [c for c in charts if c["layout"]["w"] < GRID_COLS // 2]

    widgets: list[dict] = []
    y = 0

    # The caller's real role map when it has one. `effective_roles` applies the
    # author's overrides -- a numeric `year` marked as a category stops being a
    # measure -- and reconstructing roles from configs cannot see that.
    summary = _kpi_widgets(findings, roles if roles is not None
                           else _roles_from(suggestions))
    if summary:
        y = _pack(summary, y)
        widgets += summary

    if drivers:
        y = _pack(drivers, y)
        widgets += drivers

    if detail:
        y = _pack(detail, y)
        widgets += detail

    # The narrative last, as the closing paragraph. It repeats the top findings
    # in prose, which is a summary AFTER the evidence rather than before it.
    if narrative:
        text = {
            "widget_type": "text",
            "title": "Summary",
            "config": {"content": narrative},
            "layout": {"x": 0, "y": y, "w": GRID_COLS, "h": TEXT_H},
        }
        widgets.append(text)

    return {"name": "Auto-generated insights", "widgets": widgets}


def _roles_from(suggestions: list[dict]) -> dict[str, str]:
    """Recover column roles from the suggestion configs.

    Fallback only, for a caller that has suggestions but no role map. It is
    strictly weaker than `insights.effective_roles`, which applies the author's
    Fields-pane overrides -- pass `roles` instead wherever they are available.
    """
    roles: dict[str, str] = {}
    for s in suggestions:
        cfg = s.get("config") or {}
        measure = cfg.get("measure")
        if isinstance(measure, str):
            roles[measure] = "numeric"
    return roles
