"""What depends on a dataset's field or measure (E05: changes show affected consumers).

A measure or calculated column is referenced BY NAME from many places, and
nothing used to resolve them: deleting "Margin" removed the definition and
every widget that named it fell through shape_series to the no-measure branch
and silently became a row count. This module answers "what uses this name?"
so a change can be shown its consequences first, and so a delete can refuse
until they are acknowledged.

Resolution is by the exact name, org-scoped, over every stored object that
can carry a column or measure name:

    report widgets      the role keys of `config` (measure, dimension, roles,
                        measures, columns, filters, sort_col, target) -- on
                        widgets whose effective dataset is this one
    measures            other measures' expressions on this dataset
    calculated columns  their expressions
    data alerts         the alert expression
    hierarchies         a level's column
    common filters      report-level filters on reports drawing on the dataset
    dataset filter      the dataset's own default filter expression
    aggregates          the grain and measures of aggregates built on it

An expression matches on an identifier boundary, so `sales` does not match
`sales_tax`; the bracket form `[sales]` matches too. Names are compared as
stored -- this is a lookup, not a parser.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import (CommonFilter, DataAlert, Dataset, HierarchyNode, Report,
                             ReportPage, ReportWidget)

#: Widget-config keys whose STRING value is a column or measure name.
_NAME_KEYS = ("measure", "measure2", "dimension", "dimension2", "sort_col", "target",
              "x_axis", "y_axis", "start", "column", "size", "color", "lat", "lon")
#: Widget-config keys whose LIST holds column or measure names.
_LIST_KEYS = ("measures", "columns", "levels", "dimension_levels")


@dataclass
class Dependent:
    kind: str            # widget | measure | calculated_column | alert | hierarchy | common_filter | dataset_filter | aggregate
    id: int | None
    label: str           # what a person would recognise it by
    where: str           # the key or expression the name was found in
    report_id: int | None = None
    page_id: int | None = None


def _identifier_in(text: str | None, name: str) -> bool:
    if not text or not name:
        return False
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text) is not None


def config_references(config: object, name: str) -> list[str]:
    """The keys in a widget config that name `name`."""
    if not isinstance(config, dict):
        return []
    hits: list[str] = []
    for key in _NAME_KEYS:
        if config.get(key) == name:
            hits.append(key)
    for key in _LIST_KEYS:
        v = config.get(key)
        if isinstance(v, list) and any(x == name or (isinstance(x, dict) and x.get("name") == name) for x in v):
            hits.append(key)
    roles = config.get("roles")
    if isinstance(roles, dict):
        hits += [f"roles.{k}" for k, v in roles.items()
                 if v == name or (isinstance(v, list) and name in v)]
    for i, f in enumerate(config.get("filters") or []):
        if isinstance(f, dict) and f.get("column") == name:
            hits.append(f"filters[{i}]")
    return hits


async def find_dependents(db: AsyncSession, dataset: Dataset, name: str) -> list[dict]:
    """Every object that references `name` on `dataset`, as plain dicts."""
    return (await find_dependents_of(db, dataset, [name]))[name]


async def find_dependents_of(db: AsyncSession, dataset: Dataset,
                             names: list[str]) -> dict[str, list[dict]]:
    """find_dependents for several names in ONE pass over the stored objects --
    a refresh asks about every column at once, and one query per column would
    re-read every widget in the org each time. Every name is a key, empty
    lists included."""
    out: dict[str, list[Dependent]] = {n: [] for n in names}
    ds_id = dataset.id

    # Widgets: every report in the org, each widget judged by its EFFECTIVE
    # dataset (its own config.dataset_id, else the report's).
    rows = (await db.execute(
        select(ReportWidget, ReportPage.id, Report.id, Report.name, Report.dataset_id)
        .join(ReportPage, ReportPage.id == ReportWidget.page_id)
        .join(Report, Report.id == ReportPage.report_id)
        .where(Report.org_id == dataset.org_id))).all()
    for w, page_id, report_id, report_name, report_ds in rows:
        cfg = w.config or {}
        effective = cfg.get("dataset_id") or report_ds
        try:
            if int(effective) != ds_id:
                continue
        except (TypeError, ValueError):
            continue
        for name in names:
            keys = config_references(cfg, name)
            if keys:
                out[name].append(Dependent("widget", w.id, f"{w.title or w.widget_type} on {report_name}",
                                           ", ".join(keys), report_id=report_id, page_id=page_id))

    for name in names:
        for m in dataset.measures or []:
            if m.get("name") != name and _identifier_in(m.get("expression"), name):
                out[name].append(Dependent("measure", None, m["name"], m.get("expression") or ""))
        for c in dataset.calculated_columns or []:
            if c.get("name") != name and _identifier_in(c.get("expression"), name):
                out[name].append(Dependent("calculated_column", None, c["name"], c.get("expression") or ""))

    alerts = (await db.execute(select(DataAlert).where(DataAlert.dataset_id == ds_id))).scalars().all()
    for name in names:
        for a in alerts:
            if _identifier_in(a.expression, name):
                out[name].append(Dependent("alert", a.id, a.name, a.expression))

    for h in (await db.execute(select(HierarchyNode).where(
            HierarchyNode.dataset_id == ds_id, HierarchyNode.column_name.in_(names)))).scalars():
        out[h.column_name].append(Dependent("hierarchy", h.id, h.name, "column_name"))

    report_ids = [r for r, extra in (await db.execute(
        select(Report.id, Report.additional_dataset_ids).where(Report.org_id == dataset.org_id))).all()
        if extra and ds_id in extra] + list((await db.execute(
        select(Report.id).where(Report.org_id == dataset.org_id, Report.dataset_id == ds_id))).scalars())
    if report_ids:
        for cf, report_name in (await db.execute(
                select(CommonFilter, Report.name).join(Report, Report.id == CommonFilter.report_id)
                .where(CommonFilter.report_id.in_(report_ids), CommonFilter.column.in_(names)))).all():
            out[cf.column].append(Dependent("common_filter", cf.id, f"filter on {report_name}", "column",
                                            report_id=cf.report_id))

    for name in names:
        if _identifier_in(dataset.default_filter_expr, name):
            out[name].append(Dependent("dataset_filter", ds_id, dataset.name, dataset.default_filter_expr or ""))

    aggregates = (await db.execute(select(Dataset).where(
        Dataset.aggregate_of_dataset_id == ds_id))).scalars().all()
    for name in names:
        for agg in aggregates:
            spec = agg.aggregate_spec or {}
            where = []
            if name in (spec.get("grain") or []):
                where.append("grain")
            if any(isinstance(m, dict) and m.get("column") == name for m in spec.get("measures") or []):
                where.append("measures")
            if where:
                out[name].append(Dependent("aggregate", agg.id, agg.name, ", ".join(where)))

    return {n: [asdict(d) for d in deps] for n, deps in out.items()}


def _rewrite_identifier(text: str | None, old: str, new: str) -> str | None:
    """Replace `old` as a whole identifier -- the same boundary rule
    `_identifier_in` matches with, so a rename rewrites exactly what "used by"
    reports and never the inside of a longer name (`sales` in `sales_tax`)."""
    if not text:
        return text
    return re.sub(r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])",
                  lambda _m: new, text)


def _rewrite_config(config: dict, old: str, new: str) -> dict:
    """A copy of a widget config with every reference to `old` renamed
    (the keys config_references reads, and nothing else)."""
    cfg = dict(config)
    for key in _NAME_KEYS:
        if cfg.get(key) == old:
            cfg[key] = new
    for key in _LIST_KEYS:
        v = cfg.get(key)
        if isinstance(v, list):
            cfg[key] = [new if x == old else ({**x, "name": new} if isinstance(x, dict) and x.get("name") == old else x)
                        for x in v]
    roles = cfg.get("roles")
    if isinstance(roles, dict):
        cfg["roles"] = {k: (new if v == old else [new if x == old else x for x in v] if isinstance(v, list) else v)
                        for k, v in roles.items()}
    if isinstance(cfg.get("filters"), list):
        cfg["filters"] = [{**f, "column": new} if isinstance(f, dict) and f.get("column") == old else f
                          for f in cfg["filters"]]
    return cfg


class RenameRefused(ValueError):
    """The rename would collide or has nothing to rename."""


async def rename_field(db: AsyncSession, dataset: Dataset, kind: str, old: str, new: str) -> list[dict]:
    """Rename a measure or calculated column AND every reference to it, in the
    caller's transaction (it does not commit), so either all of it changes or
    none does. Returns the references rewritten, shaped like find_dependents.

    Renaming used to be impossible: saving under a new name added a second
    definition and left every widget on the old one -- how the demo's
    "Margin %" came to chart row counts once its measure was renamed."""
    new = (new or "").strip()
    if kind not in ("measure", "calculated_column"):
        raise RenameRefused(f"cannot rename a {kind}")
    if not new or new == old:
        raise RenameRefused("give a new name different from the current one")
    attr = "measures" if kind == "measure" else "calculated_columns"
    items = list(getattr(dataset, attr) or [])
    if not any(i.get("name") == old for i in items):
        raise RenameRefused(f"no {kind.replace('_', ' ')} named '{old}'")
    from ..models.models import DatasetColumn
    taken = {c for c in (await db.execute(select(DatasetColumn.name).where(
        DatasetColumn.dataset_id == dataset.id))).scalars()}
    taken |= {m.get("name") for m in dataset.measures or []}
    taken |= {c.get("name") for c in dataset.calculated_columns or []}
    if new in taken:
        raise RenameRefused(f"'{new}' is already a column or measure on this dataset")

    # Everything that references it, resolved BEFORE the definition moves.
    dependents = await find_dependents(db, dataset, old)

    setattr(dataset, attr, [{**i, "name": new} if i.get("name") == old else i for i in items])
    # Other definitions' expressions (a measure built on this one, a calculated
    # column over this column), in both lists -- reassigned so the JSON
    # columns register the change.
    dataset.measures = [{**m, "expression": _rewrite_identifier(m.get("expression"), old, new)}
                        if m.get("name") != new else m for m in dataset.measures or []]
    dataset.calculated_columns = [{**c, "expression": _rewrite_identifier(c.get("expression"), old, new)}
                                  if c.get("name") != new else c for c in dataset.calculated_columns or []]
    if dataset.default_filter_expr:
        dataset.default_filter_expr = _rewrite_identifier(dataset.default_filter_expr, old, new)
    formats = dict(dataset.column_formats or {})
    if old in formats:
        formats[new] = formats.pop(old)
        dataset.column_formats = formats

    for d in dependents:
        if d["kind"] == "widget":
            w = await db.get(ReportWidget, d["id"])
            w.config = _rewrite_config(w.config or {}, old, new)
        elif d["kind"] == "alert":
            a = await db.get(DataAlert, d["id"])
            a.expression = _rewrite_identifier(a.expression, old, new)
        elif d["kind"] == "hierarchy":
            (await db.get(HierarchyNode, d["id"])).column_name = new
        elif d["kind"] == "common_filter":
            (await db.get(CommonFilter, d["id"])).column = new
        elif d["kind"] == "aggregate":
            agg = await db.get(Dataset, d["id"])
            spec = dict(agg.aggregate_spec or {})
            spec["grain"] = [new if g == old else g for g in spec.get("grain") or []]
            spec["measures"] = [{**m, "column": new} if isinstance(m, dict) and m.get("column") == old else m
                                for m in spec.get("measures") or []]
            agg.aggregate_spec = spec
    return dependents


def describe(dependents: list[dict]) -> str:
    """One sentence naming what would break, for an error message."""
    if not dependents:
        return "nothing references it"
    shown = ", ".join(f"{d['kind'].replace('_', ' ')} '{d['label']}'" for d in dependents[:5])
    more = f" and {len(dependents) - 5} more" if len(dependents) > 5 else ""
    return f"used by {shown}{more}"
