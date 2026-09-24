"""A dashboard proposed from the statistics alone, with no model involved.

`suggest_dataset_dashboard.py` exists to tailor a page to a person: it takes
their description of their own job and asks a model which of 64 chart types
serves it. When there is no description, there is nothing to tailor to — and
asking a model anyway spends half a minute and a network round trip to produce
something generic, non-reproducible, and no better than what the statistics
engine already knows.

So an empty goal takes this path instead. `insights.generate_insights` finds
what actually stands out — trends, standouts, laggards, correlations —
`suggest_widgets_from_findings` turns each finding into the chart that shows it,
and this assembles them. Instant, deterministic, and every chart's caption is
the finding's own sentence, with the figures already in it.

WHAT IT DOES NOT SKIP
---------------------
The gates. `suggest_widgets_from_findings` was written to feed a one-click
"add this chart" button, and its configs have never been checked against the
widget contract: it hard-codes a monthly granularity whatever the data's span,
puts a bar chart over whatever categorical column a finding names however many
values it has, and knows nothing about identifier columns. Every widget here
goes through the same `validate_widget`, `polish_widget` and probe as anything a
model proposes. A blank tile is no better for having been chosen by statistics.

RELATIONS
---------
Two charts cut by the same column are not merely both on the page: clicking a
department in one is a question the other can answer. `build_relations` finds
those pairs and the proposal carries them, so accepting a dashboard wires the
cross-filters up as well as placing the tiles.
"""
from __future__ import annotations

import asyncio

from .suggest_dataset_dashboard import (
    PROBE_CONCURRENCY, _probe, polish_widget, validate_widget,
)

#: How many charts a proposal from findings may carry. The findings are ranked
#: by interest, so this is a floor on quality rather than a budget: past the
#: first handful the engine is reporting things nobody asked about.
MAX_WIDGETS = 8

#: Widget types with a dimension worth clicking. A KPI has none — making it a
#: filter source would be an edge that can never fire.
_CLICKABLE = ("bar", "line", "pie", "donut", "treemap", "scatter", "step",
              "dot_plot", "needle", "box_plot", "area", "histogram", "funnel",
              "waterfall", "heatmap", "table", "crosstab")


def build_relations(widgets: list[dict]) -> list[dict]:
    """Which of these widgets can filter which others, and on what.

    Only a shared dimension counts. Two charts over `department` are two views
    of the same breakdown, and a selection in one is meaningful in the other; two
    charts that merely share a MEASURE are not — clicking a bar in "cost by
    department" tells "cost over time" nothing it can apply.

    Symmetric: the pair is reported both ways, because either chart is a
    reasonable place for a reader to start.
    """
    out: list[dict] = []
    for i, a in enumerate(widgets):
        dim_a = (a.get("config") or {}).get("dimension")
        if not dim_a or a.get("widget_type") not in _CLICKABLE:
            continue
        for j, b in enumerate(widgets):
            if i == j:
                continue
            dim_b = (b.get("config") or {}).get("dimension")
            if dim_b != dim_a or b.get("widget_type") not in _CLICKABLE:
                continue
            out.append({
                "from": i, "to": j, "via": dim_a, "mode": "filter",
                "note": "{} filters {} — both are cut by {}.".format(
                    a.get("title") or "this chart",
                    b.get("title") or "that chart", dim_a),
            })
    return out


def _title_for(profile: dict) -> str:
    span = (profile.get("structure") or {}).get("date_range") or {}
    if span.get("column"):
        return "What stands out"
    return "What stands out in this data"


async def suggest_from_insights(df, profile: dict, probe=None,
                                description: str | None = None) -> tuple[list[dict], str]:
    """`(proposals, reason)` — one dashboard, chosen by statistics.

    `df` is the SECURED frame the caller already loaded for the profile, so this
    reads nothing itself and cannot see past the caller's row and column rules.
    """
    from .analytics import detect_types
    from .insights import (
        effective_roles, generate_insights, suggest_widgets_from_findings,
    )

    try:
        insights = generate_insights(df, detect_types(df), None)
    except Exception as exc:                                 # noqa: BLE001
        return [], "the data could not be analysed: {}".format(exc)

    findings = insights.get("findings") or []
    if not findings:
        return [], (insights.get("narrative")
                    or "there is not enough data here to say anything with confidence")

    roles = effective_roles(detect_types(df), None)
    suggestions = suggest_widgets_from_findings(findings, roles, description,
                                                limit=MAX_WIDGETS)
    if not suggestions:
        return [], "nothing in this data suggested a chart"

    # Same three gates as the model path. These configs come from a helper that
    # predates the widget contract, so they are no more trusted than a model's.
    candidates: list[dict] = []
    rejected: list[str] = []
    for s in suggestions:
        config = dict(s.get("config") or {})
        # `suggest_widgets_from_findings` hard-codes a MONTHLY bucket: it is
        # handed findings and column roles, never the frame, so it cannot know
        # whether the data spans six weeks or six years. Dropping it lets
        # `polish_widget` choose from the profile's actual span -- otherwise 120
        # days of daily data draws four points and calls itself a trend.
        # `polish_widget` deliberately keeps a granularity it is given, because
        # from a model that IS a choice; from here it is a placeholder.
        config.pop("dimension_granularity", None)
        widget = {
            "widget_type": s["widget_type"],
            "title": (s.get("title") or "")[:120],
            # The finding's own sentence: what this chart shows, with numbers.
            "why": s.get("reason") or s.get("title") or "",
            "config": config,
        }
        ok, why = validate_widget(widget, profile)
        if not ok:
            rejected.append(why)
            continue
        candidates.append(polish_widget(widget, profile))

    if not candidates:
        return [], ("nothing the analysis suggested could be drawn: "
                    + "; ".join(rejected[:4]))

    gate = asyncio.Semaphore(PROBE_CONCURRENCY)

    async def _guarded(w):
        async with gate:
            return await _probe(w, probe)

    results = await asyncio.gather(*(_guarded(w) for w in candidates))

    widgets: list[dict] = []
    # `_probe` reports a REASON now: an engine refusal is a different fact
    # from an empty result, and this path drops widgets on both.
    for widget, (drew, rows, _why) in zip(candidates, results):
        if not drew:
            rejected.append("{}: returned nothing to draw".format(widget.get("title")))
            continue
        widgets.append({**widget, "row_count": rows})

    if not widgets:
        return [], ("nothing the analysis suggested could be drawn: "
                    + "; ".join(rejected[:4]))

    # Relations LAST, over the survivors, so every index points at a widget the
    # person will actually receive.
    return [{
        "title": _title_for(profile),
        "rationale": (insights.get("narrative")
                      or "The strongest patterns this data contains, ranked."),
        "source": "insights",
        "widgets": widgets,
        "relations": build_relations(widgets),
    }], ("; ".join(rejected[:6]) if rejected else "")
