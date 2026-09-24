"""The page copilot's brain: one chat message about an OPEN dashboard page.

Born from a screenshot: the user typed "change Auto-reload (seconds) to 1
minute" into the DATA chat and was told the request "is not answerable by
SQL". On the dashboard page, nothing the GUI can do should be refused — so
this node splits every message into exactly one of:

- PAGE ACTIONS: create / update / delete widgets on the page, expressed as
  validated, GUI-equivalent edits the router applies.
- A DATA QUESTION: rewritten to stand alone and handed to the existing
  agent pipeline (`run_agent`) by the router — the same brain Ask AI uses,
  so a data question in this chat is never second-class.

The model sees what the user sees: the page's widgets with their real ids,
configs and layout, and the dataset's columns. Same JSON-contract
discipline as every other node; the LLM endpoint is whatever
`llm_service.get_client()` is configured with, shared by the whole app.
"""
from __future__ import annotations

COPILOT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        # Set when the message asks about the DATA (totals, trends, samples):
        # a standalone rewrite for the agent. Exclusive with actions.
        "data_question": {"type": ["string", "null"]},
        "actions": {
            "type": "array", "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string",
                           "enum": ["create", "update", "delete",
                                    "add_calculated_column"]},
                    "widget_type": {"type": ["string", "null"]},
                    "widget_id": {"type": ["integer", "null"]},
                    "title": {"type": ["string", "null"]},
                    # Scalar values only: labels, columns, flags, numbers.
                    # Structured settings (filters, display rules) stay in
                    # the GUI -- see the design doc.
                    #
                    # KEY/VALUE PAIRS, not an open object: strict provider-
                    # side json_schema modes reject open `additionalProperties`
                    # shapes, and a rejected schema makes complete_json return
                    # None on every call -- the whole feature would 502
                    # (followup.py learned the same lesson with null-in-enum).
                    # `resolve_copilot` folds the pairs back into a dict.
                    "config": {
                        "type": ["array", "null"], "maxItems": 16,
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                                "value": {"type": ["string", "number",
                                                   "boolean", "null"]},
                            },
                            "required": ["key", "value"],
                            "additionalProperties": False,
                        },
                    },
                    # Fully closed for the same reason: every property named
                    # and required, null meaning "leave as is".
                    "layout": {
                        "type": ["object", "null"],
                        "properties": {"x": {"type": ["integer", "null"]},
                                       "y": {"type": ["integer", "null"]},
                                       "w": {"type": ["integer", "null"]},
                                       "h": {"type": ["integer", "null"]}},
                        "required": ["x", "y", "w", "h"],
                        "additionalProperties": False,
                    },
                },
                "required": ["op", "widget_type", "widget_id", "title",
                             "config", "layout"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reply", "data_question", "actions"],
    "additionalProperties": False,
}

#: Widget types the copilot may create or convert to, with the same default
#: sizes the GUI's insert catalog uses (frontend WIDGET_CATALOG -- keep in
#: step when adding a type there; see the adding-a-widget-type checklist).
CREATABLE_TYPES: dict[str, tuple[int, int]] = {
    "bar": (6, 5), "line": (6, 5), "pie": (4, 5), "donut": (4, 5),
    "area": (6, 5), "scatter": (6, 5), "step": (6, 5), "dot_plot": (6, 5),
    "histogram": (6, 5), "treemap": (6, 5), "waterfall": (6, 5),
    "funnel": (5, 6), "heatmap": (6, 6), "box_plot": (6, 5),
    "gauge": (4, 4), "word_cloud": (6, 5), "butterfly": (6, 5),
    "bubble": (6, 5), "forecast": (6, 5),
    "kpi": (3, 3), "table": (6, 6), "crosstab": (7, 6), "matrix": (7, 6),
    "list": (3, 6), "text": (4, 3),
}

#: Config keys whose values must name a dataset column.
COLUMN_KEYS = ("dimension", "dimension2", "measure", "measure2")

_TURN_CHARS = 300
_HISTORY_CHARS = 1200

_EXAMPLES = """Examples (a page with [id 41] bar "Revenue by region" (config: {"dimension": "region", "measure": "revenue", "agg": "sum"}) over columns region (text), revenue (numeric), units (numeric), date (date)):
Message: change Auto-reload (seconds) to 1 minute on the revenue chart -> {"reply": "Set the Revenue by region chart to auto-reload every 60 seconds.", "data_question": null, "actions": [{"op": "update", "widget_type": null, "widget_id": 41, "title": null, "config": [{"key": "auto_reload_seconds", "value": 60}], "layout": null}]}
Message: add a line chart of units over date -> {"reply": "Added a line chart of units over date.", "data_question": null, "actions": [{"op": "create", "widget_type": "line", "widget_id": null, "title": "Units over date", "config": [{"key": "dimension", "value": "date"}, {"key": "measure", "value": "units"}, {"key": "agg", "value": "sum"}], "layout": null}]}
Message: rename the revenue chart to Sales share and make it full width -> {"reply": "Renamed it to Sales share and stretched it to the full width.", "data_question": null, "actions": [{"op": "update", "widget_type": null, "widget_id": 41, "title": "Sales share", "config": null, "layout": {"x": null, "y": null, "w": 12, "h": null}}]}
Message: turn the revenue chart into a pie -> {"reply": "Turned Revenue by region into a pie chart.", "data_question": null, "actions": [{"op": "update", "widget_type": "pie", "widget_id": 41, "title": null, "config": null, "layout": null}]}
Message: remove the revenue chart -> {"reply": "Removed Revenue by region.", "data_question": null, "actions": [{"op": "delete", "widget_type": null, "widget_id": 41, "title": null, "config": null, "layout": null}]}
Message: what is the total revenue by region -> {"reply": "Let me look that up.", "data_question": "What is the total revenue by region?", "actions": []}
Message: what does this page show -> {"reply": "This page has one bar chart, Revenue by region, showing summed revenue per region.", "data_question": null, "actions": []}
Message (with widget [id 41] SELECTED): set auto-reload on this chart to 5 seconds -> {"reply": "Set the selected chart, Revenue by region, to auto-reload every 5 seconds.", "data_question": null, "actions": [{"op": "update", "widget_type": null, "widget_id": 41, "title": null, "config": [{"key": "auto_reload_seconds", "value": 5}], "layout": null}]}
Message: turn auto-reload off on the revenue chart -> {"reply": "Turned auto-reload off on Revenue by region.", "data_question": null, "actions": [{"op": "update", "widget_type": null, "widget_id": 41, "title": null, "config": [{"key": "auto_reload_seconds", "value": null}], "layout": null}]}
-- in an update, value null REMOVES that setting from the widget.
Message (page also has [id 52] line "Trend" at x=0,y=0,w=6,h=5, while id 41 is at x=0,y=5): move the revenue chart to the top -> {"reply": "Moved Revenue by region to the top and shifted Trend below it.", "data_question": null, "actions": [{"op": "update", "widget_type": null, "widget_id": 41, "title": null, "config": null, "layout": {"x": 0, "y": 0, "w": null, "h": null}}, {"op": "update", "widget_type": null, "widget_id": 52, "title": null, "config": null, "layout": {"x": 0, "y": 5, "w": null, "h": null}}]}
Message: make this chart 3D -> {"reply": "The builder has no 3D setting, so I left the chart unchanged.", "data_question": null, "actions": []}
Message: create a new fx expression useful -> {"reply": "Added the calculated column all_employee_count as the total of employee_count.", "data_question": null, "actions": [{"op": "add_calculated_column", "widget_type": null, "widget_id": null, "title": null, "config": [{"key": "name", "value": "all_employee_count"}, {"key": "expression", "value": "SUM(employee_count)"}], "layout": null}]}
Message: add a KPI of all_employee_count -> {"reply": "Added a KPI of all_employee_count.", "data_question": null, "actions": [{"op": "create", "widget_type": "kpi", "widget_id": null, "title": "All employee count", "config": [{"key": "measure", "value": "all_employee_count"}, {"key": "aggregation", "value": "sum"}], "layout": null}]}
Message: ƒx Calculated columns can i add one for new chart -> {"reply": "Added doubled_count and a KPI that uses it.", "data_question": null, "actions": [{"op": "add_calculated_column", "widget_type": null, "widget_id": null, "title": null, "config": [{"key": "name", "value": "doubled_count"}, {"key": "expression", "value": "employee_count * 2"}], "layout": null}, {"op": "create", "widget_type": "kpi", "widget_id": null, "title": "Doubled count", "config": [{"key": "measure", "value": "doubled_count"}, {"key": "aggregation", "value": "sum"}], "layout": null}]}
Message: dont sum please i need to see data individual -> {"reply": "Showing every all_employee_count row in a table, with no summing.", "data_question": null, "actions": [{"op": "update", "widget_type": "table", "widget_id": 41, "title": null, "config": [{"key": "aggregation", "value": "none"}, {"key": "measure", "value": "all_employee_count"}], "layout": null}]}
Message: sum all_employee_count on this chart -> {"reply": "Set the selected chart to sum all_employee_count.", "data_question": null, "actions": [{"op": "update", "widget_type": null, "widget_id": 41, "title": null, "config": [{"key": "aggregation", "value": "sum"}, {"key": "measure", "value": "all_employee_count"}], "layout": null}]}"""


def render_page_context(page_ctx: dict) -> str:
    """What the user sees, as text: the page's widgets (real ids, configs,
    layout) and the dataset's columns. Built by the router from the
    database -- authoritative, never trusted from the client."""
    lines = [f"Dashboard \"{page_ctx.get('report_name', '')}\", "
             f"page \"{page_ctx.get('page_name', '')}\".",
             "Widgets on this page:"]
    widgets = page_ctx.get("widgets") or []
    selected = page_ctx.get("selected_widget_id")
    if not widgets:
        lines.append("- (none yet)")
    for w in widgets:
        cfg = {k: v for k, v in (w.get("config") or {}).items()
               if not isinstance(v, (dict, list))}
        lay = w.get("layout") or {}
        marker = " (SELECTED)" if w["id"] == selected else ""
        lines.append(
            f"- [id {w['id']}] {w['widget_type']} \"{w.get('title') or ''}\"{marker} "
            f"config: {cfg!r} layout: x={lay.get('x')},y={lay.get('y')},"
            f"w={lay.get('w')},h={lay.get('h')}")
    if selected is not None and any(w["id"] == selected for w in widgets):
        lines.append(
            f"The user currently has widget [id {selected}] selected in the "
            "builder: \"the selected chart\", \"this chart\" and \"it\" refer "
            "to that widget unless the message names another.")
    lines.append("Dataset columns:")
    columns = page_ctx.get("columns") or {}
    if not columns:
        lines.append("- (no dataset attached)")
    for table, cols in columns.items():
        col_txt = ", ".join(f"{c} ({t})" for c, t in cols.items())
        lines.append(f"- {table}: {col_txt}")
    calc_cols = page_ctx.get("calculated_columns") or []
    lines.append("Calculated columns (fx) already on this dataset:")
    if not calc_cols:
        lines.append("- (none yet)")
    for c in calc_cols:
        name = (c.get("name") or "").strip()
        expr = (c.get("expression") or "").strip()
        if name:
            line = f"- {name} = {expr}" if expr else f"- {name}"
            compacted = (expr or "").upper().replace(" ", "")
            if any(fn in compacted for fn in
                   ("SUM(", "AVG(", "COUNT(", "COUNTD(", "MEDIAN(")):
                line += ("  [whole-dataset result copied onto every row — "
                         "Sum adds the copies, max is the value once, "
                         "none lists each row]")
            lines.append(line)
    if page_ctx.get("dataset_mode") == "directquery":
        lines.append("This dataset is DirectQuery (live): calculated "
                     "columns cannot be stored.")
    lines.append("Widget types you may create or convert to: "
                 + ", ".join(sorted(CREATABLE_TYPES)))
    return "\n".join(lines)


def render_history(history: list[dict] | None) -> str:
    """The panel's own recent turns, newest kept when the budget binds --
    enough for "make it blue" to lean on what was just said."""
    lines: list[str] = []
    used = 0
    for turn in reversed(history or []):
        who = "User" if turn.get("role") == "user" else "Copilot"
        text = str(turn.get("content") or "").strip().replace("\n", " ")
        if len(text) > _TURN_CHARS:
            text = text[:_TURN_CHARS] + "…"
        entry = f"{who}: {text}"
        if used + len(entry) > _HISTORY_CHARS:
            break
        used += len(entry) + 1
        lines.append(entry)
    return "\n".join(reversed(lines))


def _normalize_action(action: dict) -> dict:
    """The wire format back into what the router applies: config pairs fold
    into a dict (a dict from a tolerant provider passes through unchanged;
    a null VALUE survives -- in updates it means "remove that setting"),
    and a layout of all-null means "no layout change"."""
    out = dict(action)
    cfg = out.get("config")
    if isinstance(cfg, list):
        out["config"] = {str(p.get("key")): p.get("value")
                         for p in cfg if isinstance(p, dict) and p.get("key")}
    lay = out.get("layout")
    if isinstance(lay, dict):
        lay = {k: v for k, v in lay.items() if isinstance(v, int)
               and not isinstance(v, bool)}
        out["layout"] = lay or None
    return out


async def resolve_copilot(message: str, history: list[dict],
                          page_ctx: dict, client) -> dict | None:
    """`{reply, data_question, actions}`, or None when the model could not
    be reached or never satisfied the contract (the router answers 502 --
    an honest error, never a silent no-op)."""
    conversation = render_history(history)
    convo_block = f"Conversation so far:\n{conversation}\n\n" if conversation else ""
    got = await client.complete_json(
        [{"role": "system", "content": (
            "You are the page copilot of a dashboard builder. You receive "
            "ONE message about the page below and you never refuse it.\n"
            "Decide what the message is:\n"
            "1. A PAGE COMMAND (add, change, rename, resize, restyle, "
            "configure or remove a widget, OR add a calculated column / fx "
            "expression): return `actions`. Identify "
            "existing widgets by their [id] from the page listing, matching "
            "on title or type. `config` values are scalars; when creating a "
            "chart choose `dimension`, `measure` and `aggregation` (sum, avg, "
            "count, min, max, none) from the dataset's real columns or "
            "calculated columns. "
            "Time-like settings "
            "are in the unit the key names (auto_reload_seconds is seconds). "
            "For `update`, send ONLY the keys being changed; a non-null "
            "`widget_type` converts the chart.\n"
            "You CAN create calculated columns (fx expressions) with op "
            "`add_calculated_column`. Put the new column's `name` and "
            "`expression` in config. Never say the builder cannot add "
            "formulas — that is what this op is for. You may then create a "
            "widget that uses that column in the SAME reply. DirectQuery "
            "datasets cannot store calculated columns; if the listing has "
            "none and the data is live, say so instead of inventing one.\n"
            "Do exactly what the user asked. Aggregation (sum, avg, min, "
            "max, count, none) is always allowed — if they ask to Sum, "
            "Sum; if they ask for no sum / individual / raw rows, set "
            "`aggregation` to none (usually on a table). Clearing "
            "aggregation still defaults to Sum, so that is not how you "
            "stop summing. The widget config key is `aggregation` (the "
            "schema key `agg` is the same setting). A calculated column "
            "whose expression uses SUM/AVG/COUNT copies that result onto "
            "every row: Sum adds the copies, max/min is the value once, "
            "none lists each row. Pick the one that matches the request; "
            "never refuse an aggregation they asked for.\n"
            "LAYOUT: widgets sit on a 12-column grid. `x` (0-11) and `w` "
            "(1-12, 12 = full width) set horizontal position and width; `y` "
            "is the row (smaller y is HIGHER on the page) and `h` the "
            "height. You CAN move, reorder, swap and resize widgets by "
            "updating their layout -- to put a chart at the top, give it "
            "y 0 and move the widgets that occupied that space further down "
            "(several update actions in one reply are fine). Widgets can "
            "NEVER overlap or sit behind one another; asked for that, say "
            "so and offer side-by-side placement instead.\n"
            "SETTINGS HONESTY: set only config keys that exist -- keys "
            "already present in this page's widget configs, or these common "
            "ones: dimension, dimension2, measure, measure2, aggregation, agg, "
            "x_axis_label, y_axis_label, y_min, y_max, legend, "
            "legend_position, data_labels, grid, bar_mode, bins, limit, "
            "auto_reload_seconds, rtl, series_patterns, overview_axis. If "
            "NO setting can satisfy the request (e.g. an effect the builder "
            "does not have), say that plainly and return no actions -- "
            "never invent a key and claim success.\n"
            "2. A DATA QUESTION (a total, trend, lookup, sample): set "
            "`data_question` to ONE standalone question in the dataset's "
            "own column terms, and leave `actions` empty. It will be "
            "answered by the SQL agent.\n"
            "3. A question about the page itself: answer it in `reply` with "
            "no actions.\n"
            "`reply` is 1-2 sentences, past tense for edits (they are "
            "applied the moment you answer), written in the language the "
            "user wrote in. Never invent widget ids or types. Use columns "
            "listed below, or a calculated column you add in this same "
            "reply.\n" + _EXAMPLES)},
         {"role": "user", "content": (
             f"{render_page_context(page_ctx)}\n\n"
             f"{convo_block}Message: {message}")}],
        COPILOT_SCHEMA, enforce=True, max_tokens=700, temperature=0.1)
    if not got:
        return None
    actions = [_normalize_action(a) for a in (got.get("actions") or [])]
    data_q = (got.get("data_question") or "").strip() or None
    if data_q and actions:
        # Exclusive by contract; a confused reply keeps the edits and drops
        # the question rather than doing both half-way.
        data_q = None
    return {"reply": str(got.get("reply") or "").strip() or "Done.",
            "data_question": data_q, "actions": actions}
