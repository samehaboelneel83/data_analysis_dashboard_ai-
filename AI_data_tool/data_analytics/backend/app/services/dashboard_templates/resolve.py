"""Specification + mapping -> the pages, widgets and measures to create.

Pure: no database, no data. The result is exactly what would be written, so
it can be shown ("12 of 14 charts; 2 left out because nothing was mapped to
…") before a single row exists.
"""
from __future__ import annotations

import copy
import re

from .mapping import normalise
from .spec import TemplateError, clean_style, named_in, refs_in, widget_needs

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BRACES = re.compile(r"\{([a-z][a-z0-9_]{0,30})\}")
#: Config keys that hold a LIST of columns: a `many` slot expands in place.
_LIST_KEYS = ("columns", "measures", "factors", "predictors")


def _label(name: str, labels: dict[str, str] | None) -> str:
    said = (labels or {}).get(name)
    return said or " ".join(str(name).replace("_", " ").split())


def _say(text: str | None, chosen: dict[str, list[str]], labels: dict[str, str] | None) -> str:
    """A title with each {slot} said as its column's label."""
    return _BRACES.sub(lambda m: _label(chosen[m.group(1)][0], labels) if chosen.get(m.group(1)) else "",
                       str(text or "")).strip(" -–—:·")


def _value(v, chosen: dict[str, list[str]], measure_names: dict[str, str], key: str | None = None):
    if isinstance(v, str):
        if v.startswith("$m:"):
            return measure_names[v[3:]]
        if v.startswith("$?"):
            return chosen[v[2:]][0] if chosen.get(v[2:]) else _ABSENT
        if v.startswith("$"):
            names = chosen[v[1:]]
            return list(names) if key in _LIST_KEYS else names[0]
        return v
    if isinstance(v, list):
        out: list = []
        for item in v:
            got = _value(item, chosen, measure_names, key)
            # A `many` slot inside a list takes its place with all its columns.
            if isinstance(item, str) and item.startswith("$") and not item.startswith("$m:") and isinstance(got, list):
                out.extend(got)
            elif isinstance(item, str) and item.startswith("$") and not item.startswith("$m:") and key in _LIST_KEYS:
                out.extend(chosen[item[1:]])
            else:
                out.append(got)
        return out
    if isinstance(v, dict):
        made = {k: _value(x, chosen, measure_names, k) for k, x in v.items()}
        # An optional setting whose slot is empty is left off.
        return {k: x for k, x in made.items() if x is not _ABSENT}
    return v


GRID = 12
_ABSENT = object()


def reflow(layouts: list[dict | None], kept: list[int]) -> dict[int, dict]:
    """The layouts of the charts that stayed, with the room of those left out
    given back: {original position: layout}.

    * In a row that lost a chart, the ones that stayed share the row's width
      in the proportions they had, in the order they had.
    * A row that lost every chart closes: what was under it moves up.
    Nothing moves on a page that kept everything."""
    have = {i: dict(layouts[i]) for i in kept if isinstance(layouts[i], dict)}
    if len(have) == len([l for l in layouts if isinstance(l, dict)]):
        return have
    rows: dict[float, list[int]] = {}
    for i, lay in enumerate(layouts):
        if isinstance(lay, dict):
            rows.setdefault(lay.get("y", 0), []).append(i)
    for members in rows.values():
        stay = sorted((i for i in members if i in have), key=lambda i: layouts[i].get("x", 0))
        if not stay or len(stay) == len(members):
            continue
        start = min(layouts[i].get("x", 0) for i in members)
        width = min(sum(layouts[i].get("w", 0) for i in members), GRID - start)
        had = sum(layouts[i].get("w", 0) for i in stay) or 1
        x = start
        for n, i in enumerate(stay):
            w = (start + width - x) if n == len(stay) - 1 else max(1, round(layouts[i].get("w", 0) * width / had))
            have[i].update(x=x, w=w)
            x += w
    # Gravity: each chart as high as the ones above it allow.
    placed: list[dict] = []
    for i in sorted(have, key=lambda i: (layouts[i].get("y", 0), layouts[i].get("x", 0))):
        lay = have[i]
        top = max((p["y"] + p["h"] for p in placed
                   if p["x"] < lay["x"] + lay["w"] and lay["x"] < p["x"] + p["w"]), default=0)
        lay["y"] = top
        placed.append(lay)

    def free(x0: int, y0: float, x1: int, y1: float, but: dict) -> bool:
        return not any(p is not but and p["x"] < x1 and x0 < p["x"] + p["w"] and p["y"] < y1 and y0 < p["y"] + p["h"]
                       for p in placed)

    # What is still empty beside a chart, or under it with another chart
    # below, is taken up by that chart: wider first, then taller.
    for lay in sorted(placed, key=lambda p: (p["y"], -p["x"])):
        while lay["x"] + lay["w"] < GRID and free(lay["x"] + lay["w"], lay["y"], lay["x"] + lay["w"] + 1,
                                                  lay["y"] + lay["h"], lay):
            lay["w"] += 1
    bottom = max((p["y"] + p["h"] for p in placed), default=0)
    for lay in sorted(placed, key=lambda p: -p["y"]):
        under = [p["y"] for p in placed if p is not lay and p["x"] < lay["x"] + lay["w"] and lay["x"] < p["x"] + p["w"]
                 and p["y"] >= lay["y"] + lay["h"]]
        limit = min(under) if under else bottom
        if limit > lay["y"] + lay["h"] and limit - lay["y"] <= lay["h"] * 2:
            lay["h"] = limit - lay["y"]
    return have


def resolve(spec: dict, mapping: dict | None, labels: dict[str, str] | None = None,
            existing_measures: set[str] | dict[str, str] | None = None, allow_metrics: bool = True,
            datasets: set[str] | None = None) -> dict:
    """{"pages": [...], "measures": [{name, expression, ...}], "style", "filters",
        "dropped": [{"title", "needs": [slot ids]}], "skipped_metrics": [{"id", "why"}]}

    Each page: {name, title, page_type, page_size, widgets: [{widget_type,
    title, config, layout}], relations}. Relations are re-pointed past the
    widgets that were left out; one that lost an end is dropped."""
    chosen = normalise(mapping)
    slots = {s["id"]: s for s in spec.get("slots") or []}
    given = set(datasets or ())
    # A slot of an additional dataset that was not given is as if it were not mapped.
    chosen = {sid: names for sid, names in chosen.items()
              if sid in slots and (not slots[sid].get("dataset") or slots[sid]["dataset"] in given)}
    for sid, s in slots.items():
        if s.get("required") and sid not in chosen and (not s.get("dataset") or s["dataset"] in given):
            raise TemplateError(f"nothing is mapped to '{s.get('label') or sid}', which this template needs")
    metrics = {m["id"]: m for m in spec.get("metrics") or []}

    # Metrics first: a chart that shows one needs to know its name.
    measure_names: dict[str, str] = {}
    measures: list[dict] = []
    skipped: list[dict] = []
    taken = set(existing_measures or set())
    have = existing_measures if isinstance(existing_measures, dict) else {}
    # Only a metric some chart shows is defined: a template never leaves an
    # unused measure behind on the dataset.
    shown = {mid for p in spec.get("pages") or [] for w in p.get("widgets") or []
             for mid in refs_in(w.get("config") or {})[1] if widget_needs(w, metrics) <= set(chosen)}
    for mid, m in metrics.items():
        if mid not in shown:
            continue
        need = named_in(m.get("expression"))
        if not allow_metrics:
            # Defining a measure changes the dataset: only for someone who may.
            skipped.append({"id": mid, "why": "no_permission"})
            continue
        if not need <= set(chosen):
            skipped.append({"id": mid, "why": "unmapped"})
            continue
        columns = {sid: chosen[sid][0] for sid in need}
        # A measure belongs to one dataset: its columns must all be that dataset's.
        owners = {slots[sid].get("dataset") for sid in need}
        if len(owners) > 1:
            skipped.append({"id": mid, "why": "two_datasets"})
            continue
        owner = next(iter(owners), None)
        # A defined measure names its columns as written: one that is not a
        # plain name cannot be written into a formula.
        if not all(_IDENT.match(c) for c in columns.values()):
            skipped.append({"id": mid, "why": "column_name"})
            continue
        name = _say(m.get("label") or mid, chosen, labels)[:80] or mid
        expression = _BRACES.sub(lambda mm: columns[mm.group(1)], m["expression"])
        # The dataset already defines this very measure (the template was used
        # on it before): it is used, not defined a second time.
        if have.get(name) == expression and owner is None:
            measure_names[mid] = name
            continue
        base, n = name, 2
        while name in taken:
            name, n = f"{base} ({n})", n + 1
        taken.add(name)
        measure_names[mid] = name
        measures.append({**({"dataset": owner} if owner else {}), "name": name,
                         "expression": expression,
                         **{k: m[k] for k in ("default_aggregation", "format") if m.get(k)}})

    usable = set(chosen)
    pages, dropped = [], []
    for p in spec.get("pages") or []:
        widgets, index_of = [], {}
        for i, w in enumerate(p.get("widgets") or []):
            need = widget_needs(w, metrics)
            _s, used_metrics = refs_in(w.get("config") or {})
            if not need <= usable or not used_metrics <= set(measure_names):
                dropped.append({"title": _say(w.get("title"), chosen, labels) or str(w.get("widget_type")),
                                "needs": sorted(need - usable)})
                continue
            index_of[i] = len(widgets)
            widgets.append({"widget_type": w["widget_type"],
                            "title": _say(w.get("title"), chosen, labels),
                            "config": _value(copy.deepcopy(w.get("config") or {}), chosen, measure_names),
                            **({"dataset": w["dataset"]} if w.get("dataset") else {}),
                            **({"layout": dict(w["layout"])} if isinstance(w.get("layout"), dict) else {})})
        if not widgets:
            continue
        # The room of the charts left out goes to the ones that stayed.
        moved = reflow([w.get("layout") if isinstance(w.get("layout"), dict) else None for w in p.get("widgets") or []],
                       list(index_of))
        for original, at in index_of.items():
            if original in moved:
                widgets[at]["layout"] = moved[original]
        relations = [{"from": index_of[r["from"]], "to": index_of[r["to"]], "mode": r.get("mode") or "filter"}
                     for r in p.get("relations") or [] if r.get("from") in index_of and r.get("to") in index_of]
        page = {"name": _say(p.get("name"), chosen, labels) or "Page",
                "title": _say(p.get("title"), chosen, labels) or None,
                "page_type": p.get("page_type") or "normal", "page_size": p.get("page_size") or "16:9",
                "widgets": widgets, "relations": relations}
        # A drill-through page needs the column it is opened for; without it the page is an ordinary one.
        prompt = p.get("prompt_column")
        if isinstance(prompt, str) and prompt.startswith("$"):
            if prompt[1:] in chosen:
                page.update(prompt_column=chosen[prompt[1:]][0], prompt_label=p.get("prompt_label"))
            else:
                page["page_type"] = "normal"
        pages.append(page)
    if not pages:
        raise TemplateError("with this mapping no chart of the template can be drawn")
    # A link to a page that was left out (every chart of it needed an empty slot) goes too.
    names = {p["name"] for p in pages}
    for p in pages:
        for w in p["widgets"]:
            for key in ("actionPageTitle", "drill_page"):
                if key in w["config"] and w["config"][key] not in names:
                    w["config"].pop(key)
    filters = [{"column": chosen[f["slot"]][0], "mode": f.get("mode") or "auto"}
               for f in spec.get("filters") or [] if f.get("slot") in chosen]
    return {"pages": pages, "measures": measures, "style": clean_style(spec.get("style")),
            "filters": filters, "dropped": dropped, "skipped_metrics": skipped}
