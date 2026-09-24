"""Reusable data views: snapshot a dataset's semantic layer, apply it elsewhere.

What travels: per-column meta (role, aggregation, hidden, label), display
formats, calculated columns, measures, the dataset-level filter expression,
prep steps, and the hierarchy tree. What deliberately does not: reserved
__keys (export policy is governance, not semantics) and anything tied to the
physical source (filename, mode, connection).

Apply is match-by-name and skip-with-report: each piece lands only where the
target has the columns it references, and the response says exactly what was
applied and what was skipped -- a silent partial apply would leave the author
believing formats exist that don't.
"""
from __future__ import annotations

import re

from sqlalchemy import select

from ..models.models import Dataset, DatasetColumn, HierarchyNode
from .prep import PREP_STEPS_KEY, prep_steps_of, validate_prep_steps

_COLUMN_META_KEYS = {"role", "aggregation", "hidden", "label"}


def _missing_refs(expression: str, known: set[str]) -> set[str]:
    """Backtick-referenced columns the target does NOT have -- good enough to
    decide applicability without evaluating anything."""
    return {m.group(1) for m in re.finditer(r"`([^`]+)`", expression or "")} - known


async def snapshot_dataset(db, ds: Dataset) -> dict:
    """The bundle. Pure data, no ids from the source dataset."""
    nodes = (await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == ds.id)
        .order_by(HierarchyNode.position, HierarchyNode.id)
    )).scalars().all()
    by_parent: dict[int | None, list[HierarchyNode]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)

    def serialize(parent_id):
        return [{
            "name": n.name, "node_type": n.node_type, "column_name": n.column_name,
            "aggregation": n.aggregation, "format": n.format,
            "children": serialize(n.id),
        } for n in by_parent.get(parent_id, [])]

    return {
        "column_meta": {c: {k: v for k, v in (m or {}).items() if k in _COLUMN_META_KEYS}
                        for c, m in (ds.column_meta or {}).items()
                        if not c.startswith("__")},
        "column_formats": dict(ds.column_formats or {}),
        "calculated_columns": list(ds.calculated_columns or []),
        "measures": list(ds.measures or []),
        "default_filter_expr": ds.default_filter_expr,
        "prep_steps": prep_steps_of(ds),
        "hierarchy": serialize(None),
    }


async def apply_view(db, ds: Dataset, payload: dict) -> dict:
    """Apply a bundle to `ds`, matching by column name. Returns an applied/skipped
    report. Commits nothing -- the caller owns the transaction."""
    from sqlalchemy.orm.attributes import flag_modified

    result = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == ds.id))
    target_cols = {r[0] for r in result.all()}
    applied: dict[str, int] = {}
    skipped: list[str] = []

    # Calculated columns first: they extend the name set everything else may use.
    calc_names: set[str] = set()
    kept_calcs = []
    for c in payload.get("calculated_columns") or []:
        name, expr = c.get("name"), c.get("expression") or ""
        if not name:
            continue
        missing = _missing_refs(expr, target_cols | calc_names)
        if missing:
            skipped.append(f"calculated column '{name}' (needs {', '.join(sorted(missing))})")
            continue
        kept_calcs.append(c)
        calc_names.add(name)
    if kept_calcs:
        ds.calculated_columns = kept_calcs
        flag_modified(ds, "calculated_columns")
        applied["calculated_columns"] = len(kept_calcs)
    known = target_cols | calc_names

    kept_measures = []
    for m in payload.get("measures") or []:
        expr = m.get("expression") or ""
        missing = _missing_refs(expr, known)
        if missing:
            skipped.append(f"measure '{m.get('name')}' (needs {', '.join(sorted(missing))})")
            continue
        kept_measures.append(m)
    if kept_measures:
        ds.measures = kept_measures
        flag_modified(ds, "measures")
        applied["measures"] = len(kept_measures)

    # Column meta and formats: only entries whose column exists here. Reserved
    # __keys on the TARGET survive untouched, same contract as PUT /column-meta.
    meta_in = payload.get("column_meta") or {}
    kept_meta = {c: m for c, m in meta_in.items() if c in known and not c.startswith("__")}
    for c in meta_in:
        if c not in known:
            skipped.append(f"column settings for '{c}'")
    preserved = {k: v for k, v in (ds.column_meta or {}).items() if k.startswith("__")}
    ds.column_meta = {**preserved, **kept_meta}
    flag_modified(ds, "column_meta")
    applied["column_meta"] = len(kept_meta)

    fmts_in = payload.get("column_formats") or {}
    kept_fmts = {c: f for c, f in fmts_in.items() if c in known}
    for c in fmts_in:
        if c not in known:
            skipped.append(f"format for '{c}'")
    ds.column_formats = kept_fmts
    flag_modified(ds, "column_formats")
    applied["column_formats"] = len(kept_fmts)

    expr = payload.get("default_filter_expr")
    if expr:
        missing = _missing_refs(expr, known)
        if missing:
            skipped.append(f"dataset filter (needs {', '.join(sorted(missing))})")
        else:
            ds.default_filter_expr = expr
            applied["default_filter_expr"] = 1

    steps = payload.get("prep_steps") or []
    if steps:
        try:
            validate_prep_steps(steps, target_cols)
            meta = dict(ds.column_meta or {})
            meta[PREP_STEPS_KEY] = steps
            ds.column_meta = meta
            flag_modified(ds, "column_meta")
            applied["prep_steps"] = len(steps)
        except ValueError as e:
            skipped.append(f"prep steps ({e})")

    # Hierarchy: replace wholesale, keeping only nodes whose column exists (or
    # folders, which reference nothing). A half-transplanted tree is still a tree.
    tree = payload.get("hierarchy") or []
    if tree:
        old = (await db.execute(
            select(HierarchyNode).where(HierarchyNode.dataset_id == ds.id))).scalars().all()
        for n in old:
            await db.delete(n)
        await db.flush()
        count = 0

        async def plant(children, parent_id):
            nonlocal count
            for i, node in enumerate(children):
                col = node.get("column_name")
                if col and col not in known:
                    skipped.append(f"hierarchy node '{node.get('name')}'")
                    continue
                row = HierarchyNode(
                    dataset_id=ds.id, parent_id=parent_id, name=node.get("name") or "node",
                    node_type=node.get("node_type") or "folder", column_name=col,
                    aggregation=node.get("aggregation"), format=node.get("format"), position=i)
                db.add(row)
                await db.flush()
                count += 1
                await plant(node.get("children") or [], row.id)

        await plant(tree, None)
        applied["hierarchy_nodes"] = count

    return {"applied": applied, "skipped": skipped}
