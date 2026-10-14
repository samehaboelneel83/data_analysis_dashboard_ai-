"""A template drawn on its own sample data, so it can be looked at in the
gallery before any dataset is chosen.

The rows are made here from the template's SLOTS -- a date slot gets dates, a
number slot gets numbers with a trend and a season, a stage slot gets ordered
stages that thin out -- so every template, the platform's and a person's own,
has a preview with no data of anyone's in it. The values are placeholders
("Group A", "Stage 2"): they say what goes where, nothing about any business.
The same engine that draws a real dashboard draws these.
"""
from __future__ import annotations

import functools
import json

import numpy as np
import pandas as pd

from .resolve import resolve

ROWS = 1500
_PLACES = ["France", "Brazil", "India", "Japan", "Canada", "Kenya", "Spain", "Mexico"]


def _column(slot: dict, n: int, rng, when: pd.Series) -> dict[str, pd.Series]:
    """{column name: values} for one slot (several columns for a `many` slot)."""
    sid, kind = slot["id"], slot.get("kind")
    months = (when.dt.year - when.dt.year.min()) * 12 + when.dt.month
    if kind == "date":
        return {sid: when}
    if kind == "measure":
        scale = float(rng.choice([40, 120, 600, 2500]))
        season = 1 + 0.25 * np.sin(2 * np.pi * when.dt.month / 12)
        trend = 1 + 0.02 * (months - months.min())
        return {sid: pd.Series(np.round(rng.gamma(4.0, scale / 4.0, n) * season * trend, 2))}
    if kind == "stage":
        steps = [f"Stage {i}" for i in range(1, 6)]
        return {sid: pd.Series(rng.choice(steps, n, p=[0.40, 0.25, 0.17, 0.11, 0.07]))}
    if kind == "geography":
        weights = np.array([8, 6, 5, 4, 3, 2, 2, 1], dtype=float)
        return {sid: pd.Series(rng.choice(_PLACES, n, p=weights / weights.sum()))}
    if kind == "flag":
        return {sid: pd.Series(rng.random(n) < 0.3)}
    if kind == "detail":
        return {f"{sid}_code": pd.Series([f"R-{1000 + i}" for i in range(n)]),
                f"{sid}_group": pd.Series(rng.choice([f"Group {c}" for c in "ABCD"], n)),
                f"{sid}_amount": pd.Series(np.round(rng.gamma(3.0, 80.0, n), 2))}
    count = int(min(max(int(slot.get("max_distinct") or 6), 2), 6))
    names = [f"Group {c}" for c in "ABCDEF"[:count]]
    weights = np.array([count - i for i in range(count)], dtype=float)
    return {sid: pd.Series(rng.choice(names, n, p=weights / weights.sum()))}


def frame(spec: dict, rows: int = ROWS) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """(sample rows, the mapping of every slot to its sample column)."""
    rng = np.random.default_rng(20261011)
    start = pd.Timestamp("2024-01-01")
    when = pd.Series(start + pd.to_timedelta(np.sort(rng.integers(0, 730 * 24, rows)), unit="h"))
    data: dict[str, pd.Series] = {}
    mapping: dict[str, list[str]] = {}
    by_id = {s["id"]: s for s in spec.get("slots") or []}
    for slot in spec.get("slots") or []:
        made = _column(slot, rows, rng, when)
        # What is measured against another number sits near it, as a target sits near what was reached.
        partner = by_id.get(slot.get("same_unit") or "")
        if partner is not None and partner["id"] in data and slot.get("kind") == "measure":
            made = {slot["id"]: np.round(data[partner["id"]] * rng.normal(1.08, 0.12, rows), 2)}
        data.update(made)
        mapping[slot["id"]] = list(made)
    return pd.DataFrame(data), mapping


@functools.lru_cache(maxsize=64)
def _drawn(spec_json: str) -> dict:
    from ..widget_data import get_widget_data_from_df
    spec = json.loads(spec_json)
    df, mapping = frame(spec)
    # Each sample column is said as its slot's own label: the preview reads
    # "What was reached by The groups to compare", which is what goes where.
    # ...inside a title it starts small ("Total the number to follow"), and the title starts big.
    labels = {mapping[sl["id"]][0]: _small(str(sl.get("label") or sl["id"])) for sl in spec.get("slots") or []
              if len(mapping.get(sl["id"]) or []) == 1}
    got = resolve(spec, mapping, labels)
    for p in got["pages"]:
        for w in p["widgets"]:
            w["title"] = w["title"][:1].upper() + w["title"][1:]
    pages, n = [], 0
    for p in got["pages"]:
        widgets = []
        for w in p["widgets"]:
            n += 1
            try:
                data = get_widget_data_from_df(df, w["config"], w["widget_type"], measures=got["measures"])
            except Exception as exc:                        # noqa: BLE001 -- a preview never fails as a whole
                data = {"type": "error", "message": str(exc)[:200], "rows": [], "total": 0}
            widgets.append({"id": n, "widget_type": w["widget_type"], "title": w["title"],
                            "config": w["config"], "layout": w.get("layout") or {"x": 0, "y": 0, "w": 6, "h": 5},
                            "data": data})
        pages.append({"name": p["name"], "widgets": widgets})
    return {"pages": pages, "rows": int(len(df)), "style": got["style"]}


def _small(label: str) -> str:
    """A slot's label as it reads in the middle of a title: no capital on an
    ordinary first word (an acronym keeps its own)."""
    first = label.split(" ", 1)[0]
    return label if first.isupper() and len(first) > 1 else label[:1].lower() + label[1:]


def preview(spec: dict) -> dict:
    """{"pages": [{"name", "widgets": [{id, widget_type, title, config, layout, data}]}], "rows", "style"}
    -- the template drawn on sample rows made for its slots. Kept in memory per
    specification: the rows are the same every time."""
    from ..readback import Said
    def plain(v):
        return str(v) if isinstance(v, Said) else v
    return json.loads(json.dumps(_drawn(json.dumps(spec, sort_keys=True, default=str)), default=plain))
