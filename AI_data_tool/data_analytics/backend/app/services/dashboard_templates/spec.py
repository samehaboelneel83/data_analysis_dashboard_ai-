"""The template specification (`datalytics.dashboard-template/1`).

    {"schema": SCHEMA, "name", "description", "category", "tags": [...],
     "slots":   [{"id", "label", "kind", "required", "many"?, "number"?, "max_distinct"?, "ordered"?}],
     "metrics": [{"id", "label", "expression", "default_aggregation"?, "format"?}],
     "style":   {...}                                   # see STYLE_KEYS
     "filters": [{"slot", "mode"}]                      # controls every page gets
     "pages":   [{"name", "title"?, "page_type"?, "page_size"?,
                  "widgets": [{"widget_type", "title", "config", "layout"}],
                  "relations": [{"from", "to", "mode"}]}]}

References, the only thing that makes this a template rather than a copy:
* a config value `"$<slot id>"` is the column mapped to that slot (a list may
  hold several; a slot declared `many` expands to all its columns);
* a config value `"$?<slot id>"` is the same, but OPTIONAL: when nothing is
  mapped to that slot the setting is simply left off and the chart stays (a
  headline number keeps its figure and loses only its history);
* a config value `"$m:<metric id>"` is that metric, created on the dataset as
  a defined measure;
* `{<slot id>}` inside a title or a metric's label or expression is the mapped
  column's name.
A widget that refers to a slot nobody mapped is left out; nothing is guessed.
"""
from __future__ import annotations

import re

SCHEMA = "datalytics.dashboard-template/1"

#: What a slot may ask for. `stage` is a category whose values have an order
#: (or are few); `detail` is any column, for a table of rows.
SLOT_KINDS = ("measure", "category", "date", "stage", "geography", "flag", "detail")
CATEGORIES = ("overview", "trend", "comparison", "stages", "target", "monitoring", "geography",
              "distribution", "detail", "analysis")
FILTER_MODES = ("auto", "dropdown", "buttons", "list", "search", "range")

#: A dashboard's look. Every key is optional; a missing one is the app's own.
STYLE_FONTS = ("system", "sans", "serif", "mono", "rounded", "condensed", "arabic")
STYLE_BORDERS = ("none", "solid", "dashed", "dotted", "double")
STYLE_SHADOWS = ("none", "soft", "raised", "strong")
STYLE_DENSITY = ("compact", "comfortable", "spacious")
STYLE_ALIGN = ("start", "center", "end")
STYLE_KEYS: dict[str, object] = {
    "mode": ("auto", "light", "dark"),
    "palette": str,
    "font_family": STYLE_FONTS, "font_size": (10, 24), "title_size": (10, 32), "title_weight": (300, 800),
    "title_align": STYLE_ALIGN, "title_color": "color", "text_color": "color", "number_size": (16, 72),
    "page_background": "color", "card_background": "color",
    "border_style": STYLE_BORDERS, "border_width": (0, 8), "border_color": "color",
    "radius": (0, 32), "shadow": STYLE_SHADOWS, "padding": (0, 32), "gap": (0, 32),
    "density": STYLE_DENSITY, "accent": "color",
}
_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_ID = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
_BRACES = re.compile(r"\{([a-z][a-z0-9_]{0,30})\}")

MAX_PAGES, MAX_WIDGETS, MAX_SLOTS, MAX_METRICS = 12, 60, 24, 24


class TemplateError(ValueError):
    """The specification, or a mapping for it, cannot be used as given."""


def clean_style(style: dict | None) -> dict:
    """`style` with only the keys and values a dashboard's look may hold."""
    out: dict = {}
    for key, rule in STYLE_KEYS.items():
        v = (style or {}).get(key)
        if v is None or v == "":
            continue
        if rule is str:
            if isinstance(v, str) and len(v) <= 40:
                out[key] = v
        elif rule == "color":
            if isinstance(v, str) and _COLOR.match(v):
                out[key] = v
        elif isinstance(rule, tuple) and rule and isinstance(rule[0], str):
            if v in rule:
                out[key] = v
        elif isinstance(rule, tuple):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and rule[0] <= v <= rule[1]:
                out[key] = v
    return out


def refs_in(value, optional: bool = False) -> tuple[set[str], set[str]]:
    """(slot ids, metric ids) a config value refers to, however deep. The
    slots are the ones the widget cannot be drawn without; with `optional`,
    the `$?` ones are included too (for checking that they are declared)."""
    slots: set[str] = set()
    metrics: set[str] = set()
    if isinstance(value, str):
        if value.startswith("$m:"):
            metrics.add(value[3:])
        elif value.startswith("$?"):
            if optional:
                slots.add(value[2:])
        elif value.startswith("$"):
            slots.add(value[1:])
    elif isinstance(value, dict):
        for v in value.values():
            s, m = refs_in(v, optional)
            slots |= s
            metrics |= m
    elif isinstance(value, (list, tuple)):
        for v in value:
            s, m = refs_in(v, optional)
            slots |= s
            metrics |= m
    return slots, metrics


def named_in(text: str | None) -> set[str]:
    """Slot ids written as {id} in a title or an expression."""
    return set(_BRACES.findall(text or ""))


def widget_needs(widget: dict, metrics: dict[str, dict]) -> set[str]:
    """Every slot a widget cannot be drawn without: its own references, and
    those of the metrics it shows."""
    slots, used = refs_in(widget.get("config") or {})
    for m in used:
        slots |= named_in((metrics.get(m) or {}).get("expression"))
    return slots


def problems(spec: dict) -> list[str]:
    """What is wrong with a specification; empty when it can be stored."""
    out: list[str] = []
    if not isinstance(spec, dict):
        return ["a template is an object"]
    if spec.get("schema") != SCHEMA:
        out.append(f"schema must be {SCHEMA}")
    if not str(spec.get("name") or "").strip():
        out.append("a template needs a name")
    if spec.get("category") not in CATEGORIES:
        out.append(f"category must be one of {', '.join(CATEGORIES)}")
    slots = spec.get("slots") or []
    ids: set[str] = set()
    if not isinstance(slots, list) or len(slots) > MAX_SLOTS:
        return out + [f"slots is a list of at most {MAX_SLOTS}"]
    for s in slots:
        sid = s.get("id") if isinstance(s, dict) else None
        if not isinstance(sid, str) or not _ID.match(sid) or sid == "m":
            out.append(f"slot id {sid!r} is not a short lowercase name")
            continue
        if sid in ids:
            out.append(f"slot '{sid}' is declared twice")
        ids.add(sid)
        if s.get("kind") not in SLOT_KINDS:
            out.append(f"slot '{sid}': kind must be one of {', '.join(SLOT_KINDS)}")
    extra = {d.get("key") for d in spec.get("datasets") or [] if isinstance(d, dict)}
    for s in slots:
        if isinstance(s, dict) and s.get("dataset") and s["dataset"] not in extra:
            out.append(f"slot '{s.get('id')}' belongs to a dataset that is not declared")
    metrics = spec.get("metrics") or []
    mids: set[str] = set()
    if not isinstance(metrics, list) or len(metrics) > MAX_METRICS:
        return out + [f"metrics is a list of at most {MAX_METRICS}"]
    for m in metrics:
        mid = m.get("id") if isinstance(m, dict) else None
        if not isinstance(mid, str) or not _ID.match(mid):
            out.append(f"metric id {mid!r} is not a short lowercase name")
            continue
        mids.add(mid)
        if not str(m.get("expression") or "").strip():
            out.append(f"metric '{mid}' has no expression")
        if m.get("format") is not None and not isinstance(m["format"], dict):
            out.append(f"metric '{mid}': format is an object (type, decimals, prefix, suffix)")
        for ref in named_in(m.get("expression")) - ids:
            out.append(f"metric '{mid}' names slot '{ref}', which is not declared")
    for f in spec.get("filters") or []:
        if not isinstance(f, dict) or f.get("slot") not in ids:
            out.append("a filter names a slot that is not declared")
        elif f.get("mode", "auto") not in FILTER_MODES:
            out.append(f"filter on '{f.get('slot')}': unknown mode")
    pages = spec.get("pages")
    if not isinstance(pages, list) or not pages or len(pages) > MAX_PAGES:
        return out + [f"a template has 1 to {MAX_PAGES} pages"]
    total = 0
    for p in pages:
        widgets = p.get("widgets") if isinstance(p, dict) else None
        if not isinstance(widgets, list):
            out.append("each page has a list of widgets")
            continue
        total += len(widgets)
        for w in widgets:
            if not isinstance(w, dict) or not w.get("widget_type"):
                out.append("each widget names its widget_type")
                continue
            used_slots, used_metrics = refs_in(w.get("config") or {}, optional=True)
            for ref in used_slots - ids:
                out.append(f"'{w.get('title') or w['widget_type']}' uses slot '{ref}', which is not declared")
            for ref in used_metrics - mids:
                out.append(f"'{w.get('title') or w['widget_type']}' uses metric '{ref}', which is not declared")
            lay = w.get("layout")
            if lay is not None and not (isinstance(lay, dict) and all(
                    isinstance(lay.get(k), (int, float)) for k in ("x", "y", "w", "h"))):
                out.append(f"'{w.get('title') or w['widget_type']}': layout needs x, y, w and h")
        for r in p.get("relations") or []:
            if not (isinstance(r, dict) and isinstance(r.get("from"), int) and isinstance(r.get("to"), int)
                    and 0 <= r["from"] < len(widgets) and 0 <= r["to"] < len(widgets)):
                out.append("a click-to-filter link points outside its page")
    if total > MAX_WIDGETS:
        out.append(f"a template holds at most {MAX_WIDGETS} widgets")
    return out


def check(spec: dict) -> dict:
    """The specification, or TemplateError naming everything wrong with it."""
    found = problems(spec)
    if found:
        raise TemplateError("; ".join(found[:8]))
    return spec


def schematic(spec: dict) -> list[dict]:
    """The first page as boxes -- [{x, y, w, h, kind}] -- for a preview drawn
    without any data."""
    page = (spec.get("pages") or [{}])[0]
    return [{**{k: (w.get("layout") or {}).get(k, 0) for k in ("x", "y", "w", "h")}, "kind": w.get("widget_type")}
            for w in page.get("widgets") or [] if isinstance(w.get("layout"), dict)]
