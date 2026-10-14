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

from ..models.models import (CommonFilter, DataAlert, Dataset, DatasetColumn, HierarchyNode, Report,
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


async def column_origin(db: AsyncSession, dataset: Dataset, name: str) -> dict:
    """Where a column comes from (2026-10-10, docs/pipeline/PLAN.md): the
    upstream half of column lineage -- `find_dependents` is the downstream.

    {"kind": "calculated" | "measure", "expression", "inputs"}: built from
    other columns of this dataset; {"kind": "source", "source", "table",
    "column", "native_type"}: read from that table of that connection;
    {"kind": "upload"}: from the uploaded file; {"kind": "query"}: produced by
    the dataset's own query (no single source column); {"kind": "unknown"}."""
    from ..models.models import DataSource, SourceColumn, SourceObject
    cols = (await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id))).scalars().all()
    calc = {c.get("name"): c for c in (dataset.calculated_columns or []) if isinstance(c, dict)}
    measures = {m.get("name"): m for m in (dataset.measures or []) if isinstance(m, dict)}
    # Columns the prep steps make (a rename, date parts...) are inputs too.
    # Collected step by step, never by validating the whole pipeline: one step
    # that no longer validates must not hide the others' columns here.
    from .prep import prep_steps_of
    made = [n for st in prep_steps_of(dataset) if isinstance(st, dict) for n in _made_names(st)]
    known = [c.name for c in cols] + made + list(calc)

    def inputs(expr: str | None) -> list[str]:
        return [n for n in known if n != name and _identifier_in(expr, n)]

    if name in calc:
        expr = calc[name].get("expression") or ""
        return {"kind": "calculated", "expression": expr, "inputs": inputs(expr)}
    if name in measures:
        expr = measures[name].get("expression") or ""
        return {"kind": "measure", "expression": expr, "inputs": inputs(expr)}
    col = next((c for c in cols if c.name == name), None)
    if col is None:
        return {"kind": "unknown"}
    if col.source_column_id:
        row = (await db.execute(
            select(SourceColumn, SourceObject, DataSource)
            .join(SourceObject, SourceObject.id == SourceColumn.source_object_id)
            .join(DataSource, DataSource.id == SourceObject.data_source_id)
            .where(SourceColumn.id == col.source_column_id))).first()
        if row is not None:
            sc, obj, src = row
            if src.org_id == dataset.org_id:
                table = f"{obj.schema_name}.{obj.name}" if obj.schema_name else obj.name
                return {"kind": "source", "source": src.name, "source_id": src.id, "table": table,
                        "column": sc.name, "native_type": sc.native_type}
    if dataset.data_source_id is None:
        return {"kind": "upload"}
    return {"kind": "query"}


def _strings(v) -> list[str]:
    """Every string inside a prep step's value (str, list, dict), for "does
    this step touch that column?" without knowing each step's field names."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [x for i in v for x in _strings(i)]
    if isinstance(v, dict):
        return [x for i in v.values() for x in _strings(i)]
    return []


#: Prep steps that MAKE new columns, and the names they make (see
#: prep.prep_added_columns): a column made by one of them comes from the step.
def _made_by(step: dict, name: str) -> str | None:
    """The input column a prep step made `name` from, or None."""
    k, col = step.get("kind"), step.get("column")
    if k == "rename" and step.get("to") == name:
        return col
    if k == "date_parts" and any(f"{col}_{p}" == name for p in step.get("parts") or []):
        return col
    if k == "encode" and isinstance(col, str) and name.startswith(f"{col}_"):
        return col
    if k == "normalize" and step.get("suffix"):
        for c in step.get("columns") or []:
            if f"{c}{step['suffix']}" == name:
                return c
    if k == "aggregate":
        for a in step.get("aggregations") or []:
            if isinstance(a, dict) and (a.get("as") or a.get("column")) == name:
                return a.get("column")
    return None


def _made_names(step: dict) -> list[str]:
    """The column names a prep step creates (mirrors _made_by)."""
    k, col = step.get("kind"), step.get("column")
    if k == "rename" and step.get("to"):
        return [step["to"]]
    if k == "date_parts" and col:
        return [f"{col}_{p}" for p in step.get("parts") or []]
    if k == "normalize" and step.get("suffix"):
        return [f"{c}{step['suffix']}" for c in step.get("columns") or []]
    if k == "aggregate":
        return [a.get("as") or a.get("column") for a in step.get("aggregations") or []
                if isinstance(a, dict) and (a.get("as") or a.get("column"))]
    return []


def _trace_back(steps: list[dict], name: str) -> str:
    """The name a column arrived with, following renames and made-by steps back."""
    for i in range(len(steps) - 1, -1, -1):
        src = _made_by(steps[i], name)
        if src:
            name = src
    return name


async def column_process(db: AsyncSession, dataset: Dataset, name: str, *, editor: bool) -> list[dict]:
    """A column's whole journey, in order (2026-10-10, docs/pipeline/PLAN.md P5):
    source -> how the dataset loads (and how the last load went) -> the
    transformation steps that touch it -> the formula that makes it -> the
    checks run on it. `find_dependents` is the rest (what uses it).
    `editor`: the dataset's SQL and the last error are shown to editors only."""
    from sqlalchemy import select as _select
    from ..models.models import DataCheck, RefreshRun, Watermark
    from .prep import derived_from_of, prep_steps_of
    stages: list[dict] = []
    steps = [s for s in prep_steps_of(dataset) if isinstance(s, dict)]

    # Follow renames / made-by steps back to the name the data arrived with.
    original, made_by_step = name, None
    for i in range(len(steps) - 1, -1, -1):
        src = _made_by(steps[i], original)
        if src:
            if made_by_step is None and steps[i].get("kind") != "rename":
                made_by_step = i
            original = src

    calc = next((c for c in dataset.calculated_columns or [] if isinstance(c, dict) and c.get("name") == name), None)
    meas = next((m for m in dataset.measures or [] if isinstance(m, dict) and m.get("name") == name), None)
    formula = await column_origin(db, dataset, name) if (calc or meas) else None

    # 1. Source -- for a formula, where each of its inputs comes from.
    origin = await column_origin(db, dataset, original)
    if formula:
        inputs = []
        for i in formula["inputs"]:
            first = _trace_back(steps, i)
            entry = {"name": i, **(await column_origin(db, dataset, first))}
            if first != i:
                entry["arrives_as"] = first
            inputs.append(entry)
        origin = {"kind": "inputs", "inputs": inputs}
    derived = derived_from_of(dataset)
    if derived and not formula:
        names = []
        from .prep import derived_source_ids
        for did in derived_source_ids(derived):
            d = await db.get(Dataset, did)
            if d is not None and d.org_id == dataset.org_id:
                names.append({"id": d.id, "name": d.name})
        origin = {"kind": "derived", "datasets": names}
    stage = {"stage": "source", **origin}
    if original != name:
        stage["arrives_as"] = original
    stages.append(stage)

    # 2. Load
    wm = (await db.execute(_select(Watermark).where(Watermark.dataset_id == dataset.id))).scalar_one_or_none()
    last = (await db.execute(_select(RefreshRun).where(
        RefreshRun.kind == "dataset", RefreshRun.item_id == dataset.id).order_by(RefreshRun.id.desc()).limit(1))
    ).scalar_one_or_none()
    load = {"stage": "load", "mode": dataset.mode or "import",
            "strategy": (wm.strategy if wm else None) or "full",
            "cursor_column": wm.cursor_column if wm else None, "key_column": wm.key_column if wm else None,
            "reconcile_deletes": bool(wm.reconcile_deletes) if wm else False,
            "has_query": bool(dataset.source_query), "last_refreshed_at": dataset.last_refreshed_at,
            "last_run": None}
    if editor and dataset.source_query:
        load["query"] = dataset.source_query[:2000]
    if last is not None:
        load["last_run"] = {"status": last.status, "started_at": last.started_at, "rows": last.rows,
                            "duration_ms": last.duration_ms,
                            "error": (last.error or "").splitlines()[0][:300] if (editor and last.error) else None}
    stages.append(load)

    # 3. Transformation steps that touch it (or the name it arrived with)
    touched = []
    names_seen = {name, original} | set((formula or {}).get("inputs") or [])
    for i, st in enumerate(steps):
        values = set(_strings({k: v for k, v in st.items() if k != "kind"}))
        made = _made_by(st, name) is not None
        if made or (values & names_seen) or st.get("kind") in ("join", "append", "filter_rows", "dedupe",
                                                              "drop_duplicates", "sort", "balance"):
            other = None
            if st.get("kind") in ("join", "append") and st.get("dataset_id"):
                d = await db.get(Dataset, st["dataset_id"])
                other = d.name if d is not None and d.org_id == dataset.org_id else None
            touched.append({"index": i + 1, "kind": st.get("kind"), "dataset": other,
                            "role": "makes" if (made_by_step == i or made) else
                                    ("rows" if not (values & names_seen) else "changes"),
                            "detail": {k: v for k, v in st.items() if k in (
                                "column", "columns", "to", "how", "dataset_id", "expression", "parts", "value")}})
    if touched:
        stages.append({"stage": "steps", "steps": touched, "total_steps": len(steps)})

    # 4. Formula (a calculated column or a measure)
    if formula:
        stages.append({"stage": "formula", **formula})

    # 5. Checks on it (and the dataset-wide ones that guard every column)
    checks = (await db.execute(_select(DataCheck).where(DataCheck.dataset_id == dataset.id))).scalars().all()
    mine = [{"kind": c.kind, "severity": c.severity, "enabled": bool(c.enabled), "column": c.column}
            for c in checks if c.column == name or c.column is None]
    if mine:
        stages.append({"stage": "checks", "checks": mine})
    return stages


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


# ── What a saved version of a report depends on (E09) ─────────────────────────
#
# Restoring a version recreates its pages and widgets exactly as they were. The
# widgets name datasets, columns, measures, calculated columns, report
# parameters and hierarchy nodes that may have been renamed or deleted since,
# and a widget whose measure is gone does not fail: it draws something else
# (see the module docstring). So before a restore -- and in its answer, and
# when a draft is released -- the version's dependencies are checked against
# what exists NOW, and whatever is missing is named.

#: Widget types that draw no data, so name nothing a dataset must hold.
_NO_DATA_TYPES = {"text", "image", "shape", "button", "web_content", "container", "script",
                  "custom_visual"}
_PARAM_REF = re.compile(r"^@([A-Za-z_][A-Za-z0-9_]*)$")
_ANY = frozenset()


def config_names(config: object) -> set[str]:
    """Every column or measure name a widget config refers to (the keys
    `config_references` searches)."""
    out: set[str] = set()
    if not isinstance(config, dict):
        return out

    def add(v):
        if isinstance(v, str) and v and not v.startswith("#"):
            out.add(v)
        elif isinstance(v, dict) and isinstance(v.get("name"), str):
            out.add(v["name"])
    for key in _NAME_KEYS:
        add(config.get(key))
    for key in _LIST_KEYS:
        v = config.get(key)
        for x in (v if isinstance(v, list) else []):
            add(x)
    roles = config.get("roles")
    if isinstance(roles, dict):
        for v in roles.values():
            for x in (v if isinstance(v, list) else [v]):
                add(x)
    for f in config.get("filters") or []:
        if isinstance(f, dict):
            add(f.get("column"))
    return out


def _param_refs(config: dict) -> set[str]:
    refs: set[str] = set()
    for f in config.get("filters") or []:
        if not isinstance(f, dict):
            continue
        values = f.get("value") if isinstance(f.get("value"), list) else [f.get("value")]
        for v in values:
            m = _PARAM_REF.match(v) if isinstance(v, str) else None
            if m:
                refs.add(m.group(1))
    return refs


async def version_dependencies(db: AsyncSession, report: Report, snapshot: dict) -> list[dict]:
    """What a version's widgets use that no longer exists, one row per gap:
    `{page, widget, kind, name}` with kind dataset | field | parameter |
    hierarchy. An empty list means the version restores with everything it
    names in place."""
    from ..models.models import DatasetColumn, ReportParameter
    from .prep import prep_steps_of
    rep = (snapshot or {}).get("report") or {}
    primary = rep.get("dataset_id") if "dataset_id" in rep else report.dataset_id
    params = set((await db.execute(select(ReportParameter.name).where(
        ReportParameter.report_id == report.id))).scalars().all())
    known: dict[int, set[str] | None] = {}

    async def fields_of(ds_id) -> set[str] | None:
        if ds_id not in known:
            ds = await db.get(Dataset, ds_id) if isinstance(ds_id, int) else None
            if ds is None or ds.org_id != report.org_id:
                known[ds_id] = None
            elif prep_steps_of(ds):
                # A prep pipeline can add columns (a join, a derived field)
                # the stored column list does not have: nothing to check
                # names against without running it.
                known[ds_id] = _ANY
            else:
                cols = set((await db.execute(select(DatasetColumn.name).where(
                    DatasetColumn.dataset_id == ds.id))).scalars().all())
                cols |= {c.get("name") for c in (ds.calculated_columns or []) if isinstance(c, dict)}
                cols |= {m.get("name") for m in (ds.measures or []) if isinstance(m, dict)}
                known[ds_id] = cols
        return known[ds_id]

    missing: list[dict] = []
    for page in (snapshot or {}).get("pages") or []:
        for w in page.get("widgets") or []:
            if w.get("widget_type") in _NO_DATA_TYPES:
                continue
            config = w.get("config") or {}
            where = {"page": page.get("name"), "widget": w.get("title") or w.get("widget_type")}
            raw = config.get("dataset_id")
            ds_id = int(raw) if isinstance(raw, str) and raw.isdigit() else (raw if isinstance(raw, int) else primary)
            if ds_id is not None:
                fields = await fields_of(ds_id)
                if fields is None:
                    missing.append({**where, "kind": "dataset", "name": str(ds_id)})
                elif fields is not _ANY:
                    for name in sorted(config_names(config) - fields):
                        missing.append({**where, "kind": "field", "name": name})
            for name in sorted(_param_refs(config) - params):
                missing.append({**where, "kind": "parameter", "name": name})
            node = config.get("hierarchyNodeId")
            if isinstance(node, int) and await db.get(HierarchyNode, node) is None:
                missing.append({**where, "kind": "hierarchy", "name": str(node)})
    return missing
