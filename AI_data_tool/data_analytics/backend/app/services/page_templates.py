"""Serialising pages to templates and rehydrating them.

One serialise/rehydrate pair serves three gap rows: custom page templates, built-in
page templates, and importing a page from another report -- the import IS
serialise-then-rehydrate with no stored template in between.
"""
from __future__ import annotations

from ..models.models import ReportPage, ReportWidget

# Widget config keys that reference OTHER widgets by id. Serialised as indices and
# remapped on rehydrate; an id copied verbatim would point into the source page.
_ID_REFS = ("container_id",)


def serialize_page(page: ReportPage) -> dict:
    """Page -> portable payload. Widget order is the id order, and id references are
    rewritten to indices within that order."""
    widgets = sorted(page.widgets, key=lambda w: w.id)
    index_of = {w.id: i for i, w in enumerate(widgets)}
    out = []
    for w in widgets:
        cfg = dict(w.config or {})
        for key in _ID_REFS:
            if key in cfg:
                ref = cfg[key]
                # A reference leaving the page (or dangling) is dropped rather than
                # carried: a templated child pointing at a container that is not in
                # the template would render nowhere.
                if ref in index_of:
                    cfg[key] = {"__widget_index__": index_of[ref]}
                else:
                    cfg.pop(key)
        out.append({"widget_type": w.widget_type, "title": w.title,
                    "config": cfg, "layout": dict(w.layout or {})})
    return {
        "name": page.name, "title": page.title, "page_type": page.page_type,
        "page_size": page.page_size, "widgets": out,
        "layout_mode": page.layout_mode, "layout_template": page.layout_template,
    }


def rehydrate_page(payload: dict, report_id: int, position: int, db) -> ReportPage:
    """Payload -> new page + widgets on `report_id`. Flushes to obtain ids, then
    resolves index references into the new ids. Does not commit."""
    page = ReportPage(
        report_id=report_id,
        name=str(payload.get("name") or "Page"),
        title=payload.get("title"),
        page_type=str(payload.get("page_type") or "normal"),
        page_size=str(payload.get("page_size") or "16:9"),
        position=position,
        layout_mode=payload.get("layout_mode") or "packed",
        layout_template=payload.get("layout_template") or "executive",
    )
    db.add(page)

    created: list[ReportWidget] = []
    for spec in payload.get("widgets") or []:
        w = ReportWidget(
            page=page,
            widget_type=str(spec.get("widget_type") or "text"),
            title=spec.get("title"),
            config=dict(spec.get("config") or {}),
            layout=dict(spec.get("layout") or {"x": 0, "y": 0, "w": 6, "h": 4}),
        )
        db.add(w)
        created.append(w)
    return page, created


def resolve_index_refs(created: list[ReportWidget]) -> None:
    """After flush (ids exist), rewrite {__widget_index__: i} references to real ids."""
    for w in created:
        cfg = dict(w.config or {})
        changed = False
        for key in _ID_REFS:
            ref = cfg.get(key)
            if isinstance(ref, dict) and "__widget_index__" in ref:
                idx = ref["__widget_index__"]
                if isinstance(idx, int) and 0 <= idx < len(created):
                    cfg[key] = created[idx].id
                else:
                    cfg.pop(key)
                changed = True
        if changed:
            w.config = cfg


# ── Built-in templates ────────────────────────────────────────────────────────
# Deliberately few and deliberately structural: a template's value is the layout and
# the wiring, not guessed column names. Widgets that need data roles are left for the
# author to bind, which the config panel prompts for anyway.
BUILTIN_TEMPLATES: dict[str, dict] = {
    "kpi-strip": {
        "name": "KPI overview",
        "title": "Overview",
        "page_type": "normal", "page_size": "16:9",
        "widgets": [
            {"widget_type": "kpi", "title": "KPI 1", "config": {}, "layout": {"x": 0, "y": 0, "w": 3, "h": 3}},
            {"widget_type": "kpi", "title": "KPI 2", "config": {}, "layout": {"x": 3, "y": 0, "w": 3, "h": 3}},
            {"widget_type": "kpi", "title": "KPI 3", "config": {}, "layout": {"x": 6, "y": 0, "w": 3, "h": 3}},
            {"widget_type": "kpi", "title": "KPI 4", "config": {}, "layout": {"x": 9, "y": 0, "w": 3, "h": 3}},
            {"widget_type": "bar", "title": "Breakdown", "config": {}, "layout": {"x": 0, "y": 3, "w": 6, "h": 6}},
            {"widget_type": "line", "title": "Trend", "config": {}, "layout": {"x": 6, "y": 3, "w": 6, "h": 6}},
        ],
    },
    # Four panels reading one dataset four ways. The layout most reports start
    # from, and the one an author otherwise builds by dragging four tiles into
    # a grid by hand.
    "quad": {
        "name": "Four-panel comparison",
        "title": "Comparison",
        "page_type": "normal", "page_size": "16:9",
        "widgets": [
            {"widget_type": "bar", "title": "By category", "config": {}, "layout": {"x": 0, "y": 0, "w": 6, "h": 5}},
            {"widget_type": "line", "title": "Over time", "config": {}, "layout": {"x": 6, "y": 0, "w": 6, "h": 5}},
            {"widget_type": "donut", "title": "Share", "config": {}, "layout": {"x": 0, "y": 5, "w": 6, "h": 5}},
            {"widget_type": "table", "title": "Detail", "config": {}, "layout": {"x": 6, "y": 5, "w": 6, "h": 5}},
        ],
    },
    # A map beside the numbers, which is the shape every "where" question ends
    # up in and the one that needs a geography column bound to work at all.
    "geo-overview": {
        "name": "Map and detail",
        "title": "Geography",
        "page_type": "normal", "page_size": "16:9",
        "widgets": [
            {"widget_type": "map_choropleth", "title": "By region", "config": {}, "layout": {"x": 0, "y": 0, "w": 8, "h": 8}},
            {"widget_type": "kpi", "title": "Total", "config": {}, "layout": {"x": 8, "y": 0, "w": 4, "h": 3}},
            {"widget_type": "bar", "title": "Top regions", "config": {}, "layout": {"x": 8, "y": 3, "w": 4, "h": 5}},
        ],
    },
    "detail-page": {
        "name": "Chart + detail",
        "title": "Detail",
        "page_type": "normal", "page_size": "16:9",
        "widgets": [
            {"widget_type": "slicer", "title": "Filter", "config": {}, "layout": {"x": 0, "y": 0, "w": 3, "h": 6}},
            {"widget_type": "bar", "title": "By category", "config": {}, "layout": {"x": 3, "y": 0, "w": 9, "h": 6}},
            {"widget_type": "table", "title": "Detail rows", "config": {}, "layout": {"x": 0, "y": 6, "w": 12, "h": 6}},
        ],
    },
}
