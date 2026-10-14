"""Charts that list single records -- one bar or row per person, account or
item -- found before a dashboard is shared (persona test 3.7).

A chart grouped by a personal column (a name, an email, a national number) or
by an identifier (a column naming one record each) shows individual records,
not groups. Nothing here knows what the records are: an identifier may name a
person or an order. The share screen says which charts do this and asks the
person to check that sharing them is allowed; it never blocks.
"""
from __future__ import annotations

from .pii import personal_type
from .widget_data import _is_id_like_column

#: Config keys whose column becomes one mark (bar, slice, row) per value.
GROUP_KEYS = ("dimension", "dimension2", "legend", "row_dimension", "column_dimension")
#: Widgets that show rows as they are: every listed column is shown value by value.
ROW_WIDGETS = ("table", "list", "matrix", "pivot")


def kind_of(column: str, semantic: dict[str, str | None], column_meta: dict | None) -> str | None:
    """'personal' (with its type) or 'identifier' for a column, else None."""
    kind = personal_type(column, semantic.get(column))
    if kind:
        return kind
    return "identifier" if _is_id_like_column(column, column_meta) else None


def listed(widgets: list[dict], semantic_by_dataset: dict[int, dict[str, str | None]],
           meta_by_dataset: dict[int, dict], default_dataset: int | None) -> list[dict]:
    """[{widget_id, title, page, column, kind}] for each chart that lists single
    records. `widgets` items: {id, title, page, widget_type, config}."""
    out = []
    for w in widgets:
        cfg = w.get("config") or {}
        ds = cfg.get("dataset_id") or default_dataset
        semantic = semantic_by_dataset.get(ds) or {}
        meta = meta_by_dataset.get(ds) or {}
        cols = [cfg.get(k) for k in GROUP_KEYS]
        if w.get("widget_type") in ROW_WIDGETS:
            cols += list(cfg.get("columns") or [])
        seen = set()
        for col in cols:
            if not isinstance(col, str) or col in seen or (semantic and col not in semantic):
                continue
            seen.add(col)
            kind = kind_of(col, semantic, meta)
            if kind:
                out.append({"widget_id": w.get("id"), "title": w.get("title") or "", "page": w.get("page"),
                            "column": col, "kind": kind})
                break
    return out
