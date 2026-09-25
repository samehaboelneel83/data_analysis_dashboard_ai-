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
    out: list[Dependent] = []
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
        keys = config_references(cfg, name)
        if keys:
            out.append(Dependent("widget", w.id, f"{w.title or w.widget_type} on {report_name}",
                                 ", ".join(keys), report_id=report_id, page_id=page_id))

    for m in dataset.measures or []:
        if m.get("name") != name and _identifier_in(m.get("expression"), name):
            out.append(Dependent("measure", None, m["name"], m.get("expression") or ""))
    for c in dataset.calculated_columns or []:
        if c.get("name") != name and _identifier_in(c.get("expression"), name):
            out.append(Dependent("calculated_column", None, c["name"], c.get("expression") or ""))

    for a in (await db.execute(select(DataAlert).where(DataAlert.dataset_id == ds_id))).scalars():
        if _identifier_in(a.expression, name):
            out.append(Dependent("alert", a.id, a.name, a.expression))

    for h in (await db.execute(select(HierarchyNode).where(
            HierarchyNode.dataset_id == ds_id, HierarchyNode.column_name == name))).scalars():
        out.append(Dependent("hierarchy", h.id, h.name, "column_name"))

    report_ids = [r for r, extra in (await db.execute(
        select(Report.id, Report.additional_dataset_ids).where(Report.org_id == dataset.org_id))).all()
        if extra and ds_id in extra] + list((await db.execute(
        select(Report.id).where(Report.org_id == dataset.org_id, Report.dataset_id == ds_id))).scalars())
    if report_ids:
        for cf, report_name in (await db.execute(
                select(CommonFilter, Report.name).join(Report, Report.id == CommonFilter.report_id)
                .where(CommonFilter.report_id.in_(report_ids), CommonFilter.column == name))).all():
            out.append(Dependent("common_filter", cf.id, f"filter on {report_name}", "column",
                                 report_id=cf.report_id))

    if _identifier_in(dataset.default_filter_expr, name):
        out.append(Dependent("dataset_filter", ds_id, dataset.name, dataset.default_filter_expr or ""))

    for agg in (await db.execute(select(Dataset).where(
            Dataset.aggregate_of_dataset_id == ds_id))).scalars():
        spec = agg.aggregate_spec or {}
        where = []
        if name in (spec.get("grain") or []):
            where.append("grain")
        if any(isinstance(m, dict) and m.get("column") == name for m in spec.get("measures") or []):
            where.append("measures")
        if where:
            out.append(Dependent("aggregate", agg.id, agg.name, ", ".join(where)))

    return [asdict(d) for d in out]


def describe(dependents: list[dict]) -> str:
    """One sentence naming what would break, for an error message."""
    if not dependents:
        return "nothing references it"
    shown = ", ".join(f"{d['kind'].replace('_', ' ')} '{d['label']}'" for d in dependents[:5])
    more = f" and {len(dependents) - 5} more" if len(dependents) > 5 else ""
    return f"used by {shown}{more}"
