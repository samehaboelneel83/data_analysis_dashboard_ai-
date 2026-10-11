"""Dataset columns -> template slots: describe, suggest, validate, score.

Everything here reads the dataset's own facts (type, stored classification,
how many different values) -- never a column's name against a list of words.
A slot nobody can fill is reported as missing; no column is invented.
"""
from __future__ import annotations

from .spec import widget_needs

#: Most columns a `many` slot takes when it is filled automatically.
MANY_DEFAULT = 6
DEFAULT_MAX_DISTINCT = 60
STAGE_MAX_DISTINCT = 12


def describe_columns(columns: list[dict], column_meta: dict | None, distinct: dict[str, int] | None = None,
                     flags: set[str] | None = None, denied: set[str] | None = None) -> list[dict]:
    """One plain record per usable column:
    {name, kind: number|date|category|text|flag, number, distinct, ordered, geo, identifier, label}.

    `columns` are the dataset's stored columns ({name, dtype}); `distinct` and
    `flags` come from the dataset's measured profile when there is one (how
    many different values, which columns are yes/no). A hidden column, and one
    this reader may not see (`denied`), is not listed at all."""
    meta = column_meta or {}
    hidden = {str(d).casefold() for d in denied or set()}
    out = []
    for c in columns:
        name = str(c.get("name"))
        entry = meta.get(name) if isinstance(meta.get(name), dict) else {}
        if name.startswith("__") or entry.get("hidden") or name.casefold() in hidden:
            continue
        dtype = str(c.get("dtype") or "").lower()
        author = entry.get("role")
        n = (distinct or {}).get(name)
        is_number = (any(t in dtype for t in ("int", "float", "numeric", "decimal", "double", "number"))
                     and author not in ("category", "dimension", "freetext", "geography")) or author == "measure"
        is_date = "date" in dtype or "time" in dtype or author in ("temporal", "timestamp")
        is_flag = "bool" in dtype or name in (flags or set()) or (bool(entry.get("outcome")) and n == 2)
        kind = ("date" if is_date else "number" if is_number else "flag" if is_flag
                else "text" if dtype == "text" or author == "freetext" else "category")
        identifier = author == "identifier" or entry.get("number") == "code"
        geo = entry.get("geo_level") or ("region" if author == "geography" else None)
        out.append({"name": name, "kind": kind, "number": entry.get("number") if kind == "number" else None,
                    "unit": str(entry.get("unit") or "") or None,
                    "distinct": int(n) if isinstance(n, (int, float)) else None,
                    "ordered": bool(entry.get("order")), "geo": geo, "identifier": bool(identifier),
                    "label": str(entry.get("label") or name)})
    return out


def score(slot: dict, col: dict) -> float:
    """How well a column fills a slot: 0 = it cannot, higher = better."""
    kind = slot.get("kind")
    if kind == "detail":
        return 1.0
    if kind == "date":
        return 2.0 if col["kind"] == "date" else 0.0
    if kind == "measure":
        if col["kind"] != "number" or col["identifier"]:
            return 0.0
        wanted = slot.get("number") or []
        if wanted and col.get("number"):
            return 3.0 if col["number"] in wanted else 1.0
        return 2.0
    distinct = col.get("distinct")
    if kind == "flag":
        if col["kind"] == "flag":
            return 3.0
        return 1.5 if col["kind"] == "category" and distinct == 2 else 0.0
    if col["kind"] not in ("category", "flag") or col["identifier"]:
        return 0.0
    if kind == "geography":
        return 3.0 if col.get("geo") and col["geo"] not in ("latitude", "longitude") else 0.0
    limit = slot.get("max_distinct") or (STAGE_MAX_DISTINCT if kind == "stage" else DEFAULT_MAX_DISTINCT)
    if distinct is not None and (distinct < 2 or distinct > limit):
        return 0.0
    if kind == "stage":
        return 3.0 if col["ordered"] else 1.5 if distinct is not None and distinct <= 8 else 1.0
    # A category: one a chart can show whole reads best.
    return 2.5 if distinct is not None and distinct <= 25 else 2.0 if distinct is not None else 1.5


def candidates(slot: dict, columns: list[dict], partner: dict | None = None) -> list[str]:
    """The columns that can fill a slot, best first. `partner` is the column
    already chosen for the slot this one is measured against (`same_unit`):
    a number in the same unit comes first."""
    def rank(c: dict) -> float:
        s = score(slot, c)
        if s > 0 and partner is not None and partner.get("unit") and c.get("unit") == partner["unit"]:
            s += 2.0
        return s
    scored = [(rank(c), i, c["name"]) for i, c in enumerate(columns)]
    return [name for s, _i, name in sorted(scored, key=lambda t: (-t[0], t[1])) if s > 0]


def quality(slot: dict, col: dict, partner: dict | None = None) -> float:
    """0-1: how surely this column is what the slot means, beyond merely
    being usable. A stage with no order, a target in another unit than what it
    is measured against, a number of a kind the slot did not ask for -- each
    can be drawn, and each is a weaker match."""
    s = score(slot, col)
    if s <= 0:
        return 0.0
    if slot.get("same_unit"):
        if partner is None or not partner.get("unit") or not col.get("unit"):
            return 0.4
        return 1.0 if partner["unit"] == col["unit"] else 0.2
    return {"date": 1.0, "detail": 1.0}.get(slot.get("kind"), min(s / 3.0, 1.0) if slot.get("kind") != "category"
                                            else min(s / 2.5, 1.0))


def columns_for(slot: dict, columns: list[dict], others: dict[str, list[dict]] | None) -> list[dict] | None:
    """The columns a slot is filled from: the dashboard's own dataset, or the
    additional dataset the slot belongs to (`slot["dataset"]`). None when that
    dataset was not given -- its charts are then simply left out."""
    key = slot.get("dataset")
    return columns if not key else (others or {}).get(key)


def suggest(spec: dict, columns: list[dict], others: dict[str, list[dict]] | None = None) -> dict[str, list[str]]:
    """{slot id: [columns]} -- each slot its best column not already taken by
    a slot of the same kind (in the same dataset); required slots choose first."""
    taken: dict[tuple, set[str]] = {}
    out: dict[str, list[str]] = {}
    slots = spec.get("slots") or []
    # A slot measured against another is chosen after it.
    for slot in sorted(slots, key=lambda s: (bool(s.get("same_unit")), not s.get("required"), slots.index(s))):
        own = columns_for(slot, columns, others)
        if own is None:
            continue
        by_name = {c["name"]: c for c in own}
        used = taken.setdefault((slot.get("dataset"), slot["kind"]), set())
        partner = by_name.get((out.get(slot.get("same_unit")) or [None])[0]) if slot.get("same_unit") else None
        free = [n for n in candidates(slot, own, partner) if n not in used]
        take = free[:int(slot.get("max") or MANY_DEFAULT)] if slot.get("many") else free[:1]
        if take:
            out[slot["id"]] = take
            used.update(take)
    return out


def normalise(mapping: dict | None) -> dict[str, list[str]]:
    """A mapping as {slot id: [column, ...]}, whatever shape it arrived in."""
    out: dict[str, list[str]] = {}
    for k, v in (mapping or {}).items():
        names = [v] if isinstance(v, str) else [x for x in v or [] if isinstance(x, str)] if isinstance(v, list) else []
        names = [n for n in names if n]
        if names:
            out[str(k)] = names
    return out


def validate(spec: dict, mapping: dict | None, columns: list[dict],
             others: dict[str, list[dict]] | None = None) -> dict:
    """What a mapping would give, before anything is created:

    {"ok", "problems": [{"slot", "code", "column"?}], "missing": [slot ids],
     "widgets": {"kept", "total"}, "dropped": [widget titles]}

    codes: unknown_column · wrong_kind · required_missing · too_many."""
    by_name = {c["name"]: c for c in columns}
    chosen = normalise(mapping)
    slots = {s["id"]: s for s in spec.get("slots") or []}
    found: list[dict] = []
    filled: set[str] = set()
    for sid, names in chosen.items():
        slot = slots.get(sid)
        if slot is None:
            continue
        if len(names) > 1 and not slot.get("many"):
            found.append({"slot": sid, "code": "too_many"})
            continue
        good = True
        own = columns_for(slot, columns, others)
        if own is None:
            continue                                      # its dataset was not given: nothing to check
        by_name = {c["name"]: c for c in own}
        for n in names:
            col = by_name.get(n)
            if col is None:
                found.append({"slot": sid, "code": "unknown_column", "column": n})
                good = False
            elif score(slot, col) <= 0:
                found.append({"slot": sid, "code": "wrong_kind", "column": n})
                good = False
        if good:
            filled.add(sid)
    missing = [sid for sid, s in slots.items() if sid not in filled]
    for sid in missing:
        # A slot of an additional dataset nobody gave is not required of anyone.
        if slots[sid].get("required") and columns_for(slots[sid], columns, others) is not None:
            found.append({"slot": sid, "code": "required_missing"})
    metrics = {m["id"]: m for m in spec.get("metrics") or []}
    kept, total, dropped = 0, 0, []
    for p in spec.get("pages") or []:
        for w in p.get("widgets") or []:
            total += 1
            if widget_needs(w, metrics) <= filled:
                kept += 1
            else:
                dropped.append(str(w.get("title") or w.get("widget_type")))
    return {"ok": not found and kept > 0, "problems": found, "missing": missing,
            "widgets": {"kept": kept, "total": total}, "dropped": dropped}


def fit(spec: dict, columns: list[dict]) -> dict:
    """How well a template suits a dataset, from the dataset's own columns:
    {"usable", "score" 0-1, "mapping", "widgets": {kept, total}, "missing", "match"}.
    Half the score is the share of the template's charts this data can draw,
    half is how surely the chosen columns are what the slots mean (`quality`).
    A template whose required slots cannot all be filled is not usable."""
    mapping = suggest(spec, columns)
    got = validate(spec, mapping, columns)
    # Charts of an ADDITIONAL dataset are not this dataset's to draw: they are
    # counted apart ("3 more need a second dataset"), never against the fit.
    metrics = {m["id"]: m for m in spec.get("metrics") or []}
    extra_slots = {s["id"] for s in spec.get("slots") or [] if s.get("dataset")}
    elsewhere = sum(1 for p in spec.get("pages") or [] for w in p.get("widgets") or []
                    if w.get("dataset") or widget_needs(w, metrics) & extra_slots)
    got["widgets"] = {"kept": got["widgets"]["kept"], "total": got["widgets"]["total"] - elsewhere}
    total = got["widgets"]["total"] or 1
    by_name = {c["name"]: c for c in columns}
    sure = []
    for slot in spec.get("slots") or []:
        names = mapping.get(slot["id"])
        if not names:
            continue
        partner = by_name.get((mapping.get(slot.get("same_unit")) or [None])[0]) if slot.get("same_unit") else None
        sure.append((quality(slot, by_name[names[0]], partner), 2 if slot.get("required") else 1))
    match = sum(q * w for q, w in sure) / (sum(w for _q, w in sure) or 1)
    drawn = got["widgets"]["kept"] / total
    return {"usable": got["ok"], "score": round(0.5 * drawn + 0.5 * match, 3) if got["ok"] else 0.0,
            "mapping": mapping, "widgets": got["widgets"], "match": round(match, 3),
            "missing": [sid for sid in got["missing"] if sid not in extra_slots],
            "elsewhere": {"widgets": elsewhere,
                          "datasets": [str(d.get("label") or d.get("key")) for d in spec.get("datasets") or []
                                       if isinstance(d, dict)]} if elsewhere else None}
