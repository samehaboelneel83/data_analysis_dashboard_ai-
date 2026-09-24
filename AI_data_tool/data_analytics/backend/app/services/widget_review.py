"""A second pass over proposed widgets: make each chart say something.

A widget that passes `suggest_dashboard.validate_suggestion` is *valid*. It is not
necessarily *useful*. The first dashboards the designer produced were bar charts
of 400 courses with no limit, tables sorted by nothing in particular, and a line
chart of raw per-second timestamps — all of which run, render, and tell the reader
nothing.

The query engine reads more than dimension/measure/aggregation. `limit`, `sort`,
`sort_by`, `dimension_granularity` and `running` each change what a chart says,
and the designer set none of them. This pass does.

WHY IT IS SEPARATE FROM THE DESIGNER
------------------------------------
The first prompt answers "which tables answer this person's question". This one
answers "how should the answer be drawn". One prompt doing both does neither
reliably, and more practically: this pass needs the query's real output columns
and a sample row, which do not exist until the first pass has run and been probed.

EVERY SUGGESTION CARRIES ITS REASON
-----------------------------------
`note` is shown under the widget in the chat. An attribute whose reason the person
cannot see is one they cannot overrule, and this is a draft they are meant to edit.
"""
from __future__ import annotations

#: Only what `services/widget_data.py` actually reads off a widget config. Colours,
#: axis labels and legends are frontend concerns the query engine ignores entirely
#: -- offering them would produce settings that look applied and change nothing.
TUNABLE = ("limit", "sort", "sort_by", "dimension_granularity", "running")

#: What `_dimension_granularity_label` understands. Anything else raises there and
#: the widget path swallows it into an empty chart.
GRANULARITIES = ("year", "quarter", "month", "week", "day")

#: Column types a granularity can be applied to. On anything else the bucketing
#: produces nothing -- silently, which is the failure this whole area keeps making.
DATE_TYPES = ("datetime", "date", "timestamp")

ATTRIBUTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["attributes"],
    "properties": {
        "attributes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "limit", "sort", "sort_by",
                             "dimension_granularity", "running", "note"],
                "properties": {
                    "index": {"type": "integer"},
                    # 0 and "" mean "leave it alone". Strict JSON mode is happier
                    # with one type per field than with nullable ones, and an
                    # explicit "no opinion" value is easier for a model to emit
                    # than omitting a required key.
                    "limit": {"type": "integer"},
                    "sort": {"type": "string", "enum": ["", "asc", "desc"]},
                    "sort_by": {"type": "string", "enum": ["", "value", "name"]},
                    "dimension_granularity": {
                        "type": "string", "enum": ["", *GRANULARITIES]},
                    "running": {
                        "type": "string", "enum": ["", "running_sum", "running_avg"]},
                    "note": {"type": "string"},
                },
            },
        },
    },
}


def build_review_prompt(widgets: list[dict], column_types: dict[str, str],
                        sample_row: dict) -> list[dict]:
    """Show the model each widget beside the data it will actually draw."""
    listed = "\n".join(
        f"{i}. [{w.get('widget_type')}] {w.get('title')} — "
        f"dimension={w.get('dimension') or '(none)'}, measure={w.get('measure')}, "
        f"aggregation={w.get('aggregation')}"
        for i, w in enumerate(widgets))
    types = ", ".join(f"{k} ({v})" for k, v in column_types.items())
    example = ", ".join(f"{k}={v!r}" for k, v in (sample_row or {}).items())

    system = (
        "You improve the settings on charts that have already been designed. You "
        "do not change what a chart measures — only how it is drawn.\n"
        "For each chart return:\n"
        "- limit: how many categories to show. 0 = leave it. A bar chart of "
        "hundreds of categories is unreadable; a chart of five needs no limit.\n"
        "- sort / sort_by: '' = leave it. 'desc' by 'value' puts the biggest "
        "first, which is what a ranking chart is for.\n"
        "- dimension_granularity: '' = leave it. ONLY for a dimension whose type "
        f"is a date. One of: {', '.join(GRANULARITIES)}. Raw timestamps make a "
        "line chart with one point per row.\n"
        "- running: '' = leave it. 'running_sum' or 'running_avg' for a "
        "cumulative view over time.\n"
        "- note: one short sentence saying why, in plain words, for the person "
        "who will read this chart."
    )
    user = (
        f"Charts:\n{listed}\n\nColumn types: {types}\n"
        + (f"A row of the data: {example}\n" if example else "")
        + "\nReturn one entry per chart you would change, under 'attributes'."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def apply_attributes(widgets: list[dict], attributes: list[dict],
                     column_types: dict[str, str] | None = None) -> list[dict]:
    """Fold the model's suggestions into the widgets, dropping what cannot work.

    Copies rather than mutating: the caller keeps the original proposal so a
    before/after is possible, and a rejected review costs nothing.
    """
    out = [dict(w) for w in widgets]
    for attr in attributes or []:
        i = attr.get("index")
        if not isinstance(i, int) or not (0 <= i < len(out)):
            continue
        widget = out[i]

        applied = False

        limit = attr.get("limit") or 0
        if isinstance(limit, int) and limit > 0:
            widget["limit"] = limit
            applied = True

        for key in ("sort", "sort_by", "running"):
            value = (attr.get(key) or "").strip()
            if value:
                widget[key] = value
                applied = True

        grain = (attr.get("dimension_granularity") or "").strip()
        if grain in GRANULARITIES:
            # A granularity on a column that is not a date buckets nothing and
            # draws an empty chart. Checked here rather than trusted from the
            # prompt, because "only for date columns" is exactly the instruction
            # a model follows nine times in ten.
            dim = widget.get("dimension")
            dtype = (column_types or {}).get(dim)
            if column_types is None or (dtype or "").lower() in DATE_TYPES:
                widget["dimension_granularity"] = grain
                applied = True

        # A note only survives if something it could be describing survived.
        # Seen live: the model asked for a monthly bucket on a line chart, the
        # date guard dropped it, and "ensures the x-axis displays distinct
        # monthly intervals" was still printed under an unchanged chart. A
        # sentence that describes a change nobody made is worse than silence.
        note = (attr.get("note") or "").strip()
        if note and applied:
            widget["note"] = note
    return out


async def review_attributes(widgets: list[dict], column_types: dict[str, str],
                            sample_row: dict | None = None) -> list[dict]:
    """The whole pass. Returns the widgets unchanged if anything goes wrong.

    An improvement, never a requirement: a dashboard with plain attributes is
    worth having, and no dashboard is not. Every failure here is silent by design.
    """
    try:
        from .llm import get_client
        client = get_client()
    except Exception:                                    # noqa: BLE001
        return widgets
    if client is None:
        return widgets

    try:
        got = await client.complete_json(
            build_review_prompt(widgets, column_types, sample_row or {}),
            ATTRIBUTE_SCHEMA, max_tokens=1200, enforce=True)
    except Exception:                                    # noqa: BLE001
        return widgets
    if not got or not got.get("attributes"):
        return widgets
    return apply_attributes(widgets, got["attributes"], column_types)
