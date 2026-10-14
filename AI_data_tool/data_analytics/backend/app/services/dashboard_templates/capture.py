"""An existing dashboard -> a template specification ("Save as template").

The columns a dashboard uses become slots, the defined measures it shows become
metrics, and what belongs to this one dashboard's data is taken out:

* a filter on a VALUE ("status is Late") cannot mean anything on other data,
  so it is removed and counted -- a filter relative to today stays;
* a rule that names values (a colour per value) is removed the same way;
* ids -- of widgets, pages, datasets -- become positions or titles.

What was removed is returned beside the specification, so the person saving
knows what the template does not carry.
"""
from __future__ import annotations

import copy
import re

from .spec import SCHEMA, clean_style

_SINGLE = ("dimension", "dimension2", "measure", "measure2", "sparkline_date", "date_column", "target",
           "size", "start", "end", "animation", "response", "x", "y", "latitude", "longitude", "tooltip")
_LISTS = ("columns", "measures", "factors", "predictors")
#: Never part of a reusable specification.
_DROPPED = ("dataset_id", "container_id", "interaction", "actionPageId", "drillthroughPageId", "measure_defs")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NOT_ID = re.compile(r"[^a-z0-9]+")


def _slot_kind(col: dict | None, key: str) -> str:
    if col is None:
        return "measure" if key.startswith("measure") else "category"
    if col["kind"] == "date":
        return "date"
    if col["kind"] == "number" and not col.get("identifier"):
        # A number used to split a chart is a category there (a year, a grade).
        return "category" if key.startswith("dimension") and (col.get("distinct") or 99) <= 60 else "measure"
    if col["kind"] == "flag":
        return "flag"
    if col["kind"] == "text" or col.get("identifier"):
        return "detail"
    if col.get("geo") and col["geo"] not in ("latitude", "longitude"):
        return "geography"
    return "stage" if col.get("ordered") else "category"


def from_report(pages: list[dict], columns: list[dict], measures: list[dict] | None, *, name: str,
                description: str = "", category: str = "overview", style: dict | None = None,
                tags: list[str] | None = None, others: dict[int, dict] | None = None) -> tuple[dict, dict]:
    """(specification, what was left out: {"filters": n, "rules": n, "unknown": [names]}).

    `others` are the dashboard's additional datasets, by id: {"key", "label",
    "columns", "measures"}. A chart that reads one of them keeps doing so in
    the template: its columns become slots OF THAT DATASET, filled from
    whichever dataset is given for it when the template is used."""
    sets = {None: ({c["name"]: c for c in columns},
                   {str(m.get("name")): m for m in measures or [] if m.get("name")})}
    key_of: dict[int, str] = {}
    for ds_id, other in (others or {}).items():
        key_of[ds_id] = other["key"]
        sets[other["key"]] = ({c["name"]: c for c in other.get("columns") or []},
                              {str(m.get("name")): m for m in other.get("measures") or [] if m.get("name")})
    by_name, defined = sets[None]
    slots: dict[tuple, dict] = {}        # (dataset key, column) -> slot
    metrics: dict[tuple, dict] = {}      # (dataset key, measure name) -> metric
    uses: dict[str, int] = {}
    left = {"filters": 0, "rules": 0, "unknown": []}

    def slot_for(column: str, key: str, owner: str | None = None) -> str:
        by_name = sets[owner][0]
        if (owner, column) not in slots:
            base = _NOT_ID.sub("_", column.lower()).strip("_")[:24] or "col"
            if not base[0].isalpha():
                base = "c_" + base
            sid, n = base, 2
            while sid == "m" or any(s["id"] == sid for s in slots.values()):
                sid, n = f"{base[:22]}_{n}", n + 1
            col = by_name.get(column)
            slots[(owner, column)] = {"id": sid, "label": (col or {}).get("label") or column,
                                      "kind": _slot_kind(col, key), "required": False,
                                      **({"dataset": owner} if owner else {})}
        return slots[(owner, column)]["id"]

    def metric_for(measure: str, owner: str | None = None) -> str | None:
        by_name, defined = sets[owner]
        if (owner, measure) in metrics:
            return metrics[(owner, measure)]["id"]
        expr = str(defined[measure].get("expression") or "")
        named = [w for w in set(_WORD.findall(expr)) if w in by_name]
        mid = f"m{len(metrics) + 1}"
        for col in sorted(named, key=len, reverse=True):
            expr = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(col)}(?![A-Za-z0-9_])", "{" + slot_for(col, "measure", owner) + "}", expr)
        metrics[(owner, measure)] = {"id": mid, "label": measure, "expression": expr,
                            **{k: defined[measure][k] for k in ("default_aggregation", "format")
                               if defined[measure].get(k)}}
        return mid

    def ref(value, key: str, counted: set[str], owner: str | None = None):
        by_name, defined = sets[owner]
        if not isinstance(value, str) or not value:
            return value
        if value in by_name:
            counted.add(value)
            return "$" + slot_for(value, key, owner)
        if value in defined:
            return "$m:" + metric_for(value, owner)
        if value not in left["unknown"]:
            left["unknown"].append(value)
        return None

    out_pages = []
    # Links between pages are kept by the page's NAME: ids mean nothing elsewhere.
    page_name = {p.get("id"): str(p.get("name") or "Page") for p in pages if p.get("id") is not None}
    for p in pages:
        widgets, index_of, ids = [], {}, {}
        for i, w in enumerate(p.get("widgets") or []):
            cfg = copy.deepcopy(w.get("config") or {})
            counted: set[str] = set()
            ok = True
            # The dataset this chart reads: the dashboard's own, or one of its additional ones.
            owner = key_of.get(cfg.get("dataset_id"))
            by_name = sets[owner][0]
            for key in _SINGLE:
                if cfg.get(key):
                    cfg[key] = ref(cfg[key], key, counted, owner)
                    if cfg[key] is None:
                        ok = False
            for key in _LISTS:
                if isinstance(cfg.get(key), list):
                    cfg[key] = [r for r in (ref(v, key, counted, owner) for v in cfg[key] if isinstance(v, str)) if r]
            kept_filters = []
            for f in cfg.get("filters") or []:
                if isinstance(f, dict) and f.get("op") == "relative" and f.get("column") in by_name:
                    kept_filters.append({**f, "column": "$" + slot_for(f["column"], "dimension", owner)})
                else:
                    left["filters"] += 1
            if "filters" in cfg:
                cfg["filters"] = kept_filters
            rules = cfg.get("display_rules")
            if isinstance(rules, list):
                keep = [r for r in rules if isinstance(r, dict) and r.get("kind") in ("expression", "data_bar")]
                left["rules"] += len(rules) - len(keep)
                cfg["display_rules"] = keep
            # Click-to-filter is kept as positions on the page.
            actions = ((cfg.get("interaction") or {}).get("actions") or []) if isinstance(cfg.get("interaction"), dict) else []
            ids[i] = [(a.get("targetId"), a.get("mode") or "filter") for a in actions if isinstance(a, dict)]
            # A button that opens a page, and a chart that drills through to one.
            if cfg.get("actionPageId") in page_name:
                cfg["actionPageTitle"] = page_name[cfg["actionPageId"]]
            if cfg.get("drillthroughPageId") in page_name:
                cfg["drill_page"] = page_name[cfg["drillthroughPageId"]]
            for key in list(cfg):
                if key in _DROPPED or key.startswith("__"):
                    cfg.pop(key)
            if not ok:
                continue
            for c in counted:
                uses[(owner, c)] = uses.get((owner, c), 0) + 1
            title = str(w.get("title") or "")
            for c in sorted(counted, key=len, reverse=True):
                for said in {c, c.replace("_", " "), str((by_name.get(c) or {}).get("label") or c)}:
                    title = re.sub(rf"(?i)(?<![A-Za-z0-9_{{]){re.escape(said)}(?![A-Za-z0-9_}}])",
                                   "{" + slots[(owner, c)]["id"] + "}", title)
            index_of[w.get("id", i)] = len(widgets)
            widgets.append({"widget_type": w.get("widget_type"), "title": title, "config": cfg,
                            **({"dataset": owner} if owner else {}),
                            **({"layout": {k: w["layout"][k] for k in ("x", "y", "w", "h") if k in w["layout"]}}
                               if isinstance(w.get("layout"), dict) else {}), "_at": i})
        relations = []
        for w in widgets:
            for target, mode in ids.get(w["_at"], []):
                if target in index_of:
                    relations.append({"from": widgets.index(w), "to": index_of[target], "mode": mode})
        for w in widgets:
            w.pop("_at")
        if widgets:
            page = {"name": p.get("name") or "Page", "title": p.get("title"),
                    "page_type": p.get("page_type") or "normal", "page_size": p.get("page_size") or "16:9",
                    "widgets": widgets, "relations": relations}
            # A drill-through page is opened for one value of a column: that column is a slot too.
            if p.get("prompt_column") in sets[None][0]:
                page["prompt_column"] = "$" + slot_for(p["prompt_column"], "dimension")
                if p.get("prompt_label"):
                    page["prompt_label"] = str(p["prompt_label"])
            out_pages.append(page)
    # What most of the dashboard stands on is what a new dataset must have.
    if uses:
        for column, n in uses.items():
            # What a dataset's own charts mostly stand on is what a dataset given for it must have.
            mine = [m for (o, _c), m in uses.items() if o == column[0]]
            if n == max(mine) or n * 2 >= sum(mine):
                slots[column]["required"] = True
    spec = {"schema": SCHEMA, "name": name.strip()[:120], "description": description.strip()[:500],
            "category": category, "tags": [str(t)[:30] for t in (tags or [])][:8],
            "slots": list(slots.values()), "metrics": list(metrics.values()), "style": clean_style(style),
            "datasets": [{"key": o["key"], "label": str(o.get("label") or o["key"])} for o in (others or {}).values()
                         if any(k[0] == o["key"] for k in slots)],
            "filters": [], "pages": out_pages}
    return spec, left
