"""Dashboard templates: the gallery, mapping a template to a dataset, making a
dashboard from one, and saving a dashboard as one (services/dashboard_templates).

A template is `builtin:<key>` (the platform's own, read-only) or `t:<id>`
(saved here: personal -- its author only -- or shared with the organisation).
Nothing a template does reads a row of data: mapping works from the dataset's
columns and their stored classification, and the charts are drawn afterwards by
the same server-side aggregation every dashboard uses.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..core.capability import max_dataset_capability, rank, require_capability, require_dataset_read
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.said_errors import refused
from ..dependencies import get_current_user
from ..models.models import (DashboardTemplate, DashboardTemplateVersion, Dataset, DatasetColumn, Report,
                             ReportPage, ReportWidget, TemplateFavorite, User)
from ..services.audit import record as audit
from ..services.dashboard_templates import builtin, capture, mapping, spec as tspec, words
from ..services.dashboard_templates.resolve import resolve

router = APIRouter(prefix="/templates", tags=["templates"])

#: Versions kept per template; the oldest fall off.
VERSIONS_KEPT = 30
#: The height of the row of filter controls a template puts above a page.
FILTER_ROW_H = 2


class MatchIn(BaseModel):
    dataset_id: int
    mapping: dict | None = None
    #: A dataset for each additional dataset the template reads: {key: dataset id}.
    datasets: dict[str, int] | None = None
    #: The language the person is working in: what a built-in template WRITES
    #: (chart titles, page names, measure names) is written in it.
    lang: str | None = None


class UseIn(BaseModel):
    dataset_id: int
    mapping: dict | None = None
    datasets: dict[str, int] | None = None
    name: str | None = Field(default=None, max_length=255)
    lang: str | None = None


class SaveIn(BaseModel):
    report_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    category: str = "overview"
    tags: list[str] = []
    visibility: str = "personal"
    #: Start from another template instead of a dashboard (a personal copy to change).
    copy_of: str | None = None


class EditIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = None
    tags: list[str] | None = None
    visibility: str | None = None
    #: Take the template's content again from this dashboard.
    report_id: int | None = None
    style: dict | None = None
    note: str | None = Field(default=None, max_length=300)


class FavoriteIn(BaseModel):
    on: bool = True


def _can_see(t: DashboardTemplate, user: User) -> bool:
    return t.org_id == user.org_id and (t.visibility == "org" or t.created_by == user.id)


def _can_change(t: DashboardTemplate, user: User) -> bool:
    return t.org_id == user.org_id and (t.created_by == user.id or bool(getattr(user.role, "is_org_admin", False)))


async def _load(db: AsyncSession, ref: str, user: User) -> tuple[dict, DashboardTemplate | None]:
    """(specification, its row or None for a built-in). 404 for anything this person may not see."""
    kind, _, key = str(ref).partition(":")
    if kind == "builtin" and key in builtin.BUILTIN:
        return builtin.BUILTIN[key], None
    if kind == "t" and key.isdigit():
        row = await db.get(DashboardTemplate, int(key))
        if row is not None and _can_see(row, user):
            return row.spec or {}, row
    raise HTTPException(404, "Template not found")


def _card(ref: str, spec: dict, *, source: str, favorite: bool, row: DashboardTemplate | None = None,
          mine: bool = False, can_change: bool = False) -> dict:
    pages = spec.get("pages") or []
    return {"ref": ref, "source": source, "key": spec.get("key"),
            "name": (row.name if row else spec.get("name")), "description": (row.description if row else spec.get("description")) or "",
            "category": (row.category if row else spec.get("category")), "tags": list((row.tags if row else spec.get("tags")) or []),
            "slots": [{k: s.get(k) for k in ("id", "label", "kind", "required", "many")} for s in spec.get("slots") or []],
            "datasets": [d for d in spec.get("datasets") or [] if isinstance(d, dict)],
            "preview": tspec.schematic(spec), "style": tspec.clean_style(spec.get("style")),
            "pages": len(pages), "widgets": sum(len(p.get("widgets") or []) for p in pages),
            "metrics": len(spec.get("metrics") or []),
            "version": row.version if row else 1, "uses": row.uses if row else None,
            "updated_at": row.updated_at if row else None, "favorite": favorite, "mine": mine,
            "can_change": can_change}


async def _columns(db: AsyncSession, user: User, ds: Dataset) -> list[dict]:
    """The dataset's columns as the mapping reads them, for THIS reader: a
    column their role may not see is not there to be mapped."""
    from ..core.rls import resolve_denied_columns
    rows = (await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
                             .order_by(DatasetColumn.id))).scalars().all()
    denied = set(await resolve_denied_columns(db, user, ds.id) or [])
    distinct: dict[str, int] = {}
    flags: set[str] = set()
    try:
        # What was measured about the data, when it has been (never measured here).
        from ..services.discovery import profile as profile_store
        kept = await profile_store.stored(db, ds)
        for name, stats in ((kept or {}).get("columns") or {}).items():
            if isinstance(stats, dict):
                if isinstance(stats.get("distinct"), (int, float)):
                    distinct[name] = int(stats["distinct"])
                if stats.get("kind") == "flag":
                    flags.add(name)
    except Exception:                                       # noqa: BLE001 -- a refinement, never a gate
        pass
    return mapping.describe_columns([{"name": c.name, "dtype": c.dtype} for c in rows], ds.column_meta,
                                    distinct, flags, denied)


async def _dataset(db: AsyncSession, user: User, dataset_id: int) -> Dataset:
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    return ds


async def _others(db: AsyncSession, user: User, spec: dict, given: dict[str, int] | None,
                  primary: Dataset) -> tuple[dict[str, Dataset], dict[str, list[dict]]]:
    """The datasets given for a template's additional ones: ({key: dataset},
    {key: its columns for this reader}). Only keys the template declares; the
    same checks as the dashboard's own dataset."""
    declared = {d.get("key") for d in spec.get("datasets") or [] if isinstance(d, dict)}
    rows: dict[str, Dataset] = {}
    columns: dict[str, list[dict]] = {}
    for key, dataset_id in (given or {}).items():
        if key not in declared or dataset_id == primary.id:
            continue
        rows[key] = await _dataset(db, user, int(dataset_id))
        columns[key] = await _columns(db, user, rows[key])
    return rows, columns


async def _favorites(db: AsyncSession, user: User) -> set[str]:
    return set((await db.execute(select(TemplateFavorite.template_ref)
                                 .where(TemplateFavorite.user_id == user.id))).scalars().all())


@router.get("")
async def gallery(dataset_id: int | None = None, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Every template this person may use: the platform's, the organisation's
    and their own. With `dataset_id`, each also says how well it suits that
    dataset -- from the dataset's columns, nothing invented -- and the list
    comes best first."""
    favorites = await _favorites(db, user)
    cards = [_card(f"builtin:{key}", s, source="builtin", favorite=f"builtin:{key}" in favorites)
             for key, s in builtin.BUILTIN.items()]
    rows = (await db.execute(
        select(DashboardTemplate).where(
            DashboardTemplate.org_id == user.org_id,
            or_(DashboardTemplate.visibility == "org", DashboardTemplate.created_by == user.id))
        .order_by(DashboardTemplate.name))).scalars().all()
    specs = {f"builtin:{key}": s for key, s in builtin.BUILTIN.items()}
    for t in rows:
        ref = f"t:{t.id}"
        specs[ref] = t.spec or {}
        cards.append(_card(ref, t.spec or {}, source="org" if t.visibility == "org" else "personal",
                           favorite=ref in favorites, row=t, mine=t.created_by == user.id,
                           can_change=_can_change(t, user)))
    if dataset_id is not None:
        columns = await _columns(db, user, await _dataset(db, user, dataset_id))
        for c in cards:
            got = mapping.fit(specs[c["ref"]], columns)
            c["fit"] = {"usable": got["usable"], "score": got["score"], "widgets": got["widgets"],
                        "missing": got["missing"], "elsewhere": got["elsewhere"]}
        cards.sort(key=lambda c: (-c["fit"]["score"], c["name"]))
    return {"templates": cards, "categories": list(tspec.CATEGORIES)}


@router.get("/style-options")
async def style_options(user: User = Depends(get_current_user)):
    """What a dashboard's look may hold: each key with its choices or range."""
    return {k: ("text" if v is str else v if isinstance(v, str) else list(v)) for k, v in tspec.STYLE_KEYS.items()}


@router.get("/{ref}")
async def one(ref: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    spec, row = await _load(db, ref, user)
    favorites = await _favorites(db, user)
    card = _card(ref, spec, source="builtin" if row is None else "org" if row.visibility == "org" else "personal",
                 favorite=ref in favorites, row=row, mine=bool(row and row.created_by == user.id),
                 can_change=bool(row and _can_change(row, user)))
    return {**card, "spec": spec}


@router.get("/{ref}/preview")
async def preview(ref: str, lang: str | None = None, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """The template drawn on its own sample rows (made from its slots -- no
    dataset is read), for looking at it before choosing any data."""
    import asyncio

    from ..services.analysis_contract import safe_clean
    from ..services.dashboard_templates import sample
    spec, _row = await _load(db, ref, user)
    spec = words.localise(spec, lang)
    try:
        return safe_clean(await asyncio.to_thread(sample.preview, spec))
    except tspec.TemplateError as e:
        raise refused(400, e)


@router.post("/{ref}/match")
async def match(ref: str, body: MatchIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Before anything is made: the dataset's columns, which of them can fill
    each slot, a suggested mapping, and what the given (or suggested) mapping
    would produce -- how many charts, which are left out and why."""
    spec, _row = await _load(db, ref, user)
    spec = words.localise(spec, body.lang)
    ds = await _dataset(db, user, body.dataset_id)
    columns = await _columns(db, user, ds)
    other_rows, other_columns = await _others(db, user, spec, body.datasets, ds)
    suggested = mapping.suggest(spec, columns, other_columns)
    chosen = mapping.normalise(body.mapping) if body.mapping is not None else suggested
    check = mapping.validate(spec, chosen, columns, other_columns)
    may_define = rank(await max_dataset_capability(db, user, ds.id)) >= rank("data")
    preview = None
    if check["ok"]:
        got = resolve(spec, chosen, {c["name"]: c["label"] for c in columns},
                      {str(m.get("name")): str(m.get("expression") or "") for m in ds.measures or []},
                      allow_metrics=may_define, datasets=set(other_columns))
        preview = {"pages": [{"name": p["name"], "widgets": [{"widget_type": w["widget_type"], "title": w["title"]}
                                                           for w in p["widgets"]]} for p in got["pages"]],
                   "measures": got["measures"], "dropped": got["dropped"], "skipped_metrics": got["skipped_metrics"],
                   "filters": got["filters"]}
    return {"columns": columns, "slots": spec.get("slots") or [],
            # The additional datasets this template reads, and which were given.
            "datasets": [{**d, "dataset_id": other_rows[d["key"]].id if d.get("key") in other_rows else None}
                         for d in spec.get("datasets") or [] if isinstance(d, dict)],
            "candidates": {s["id"]: mapping.candidates(s, mapping.columns_for(s, columns, other_columns) or [])
                           for s in spec.get("slots") or []},
            "suggested": suggested, "mapping": chosen, "check": check, "preview": preview,
            "can_define_measures": may_define}


async def _write(db: AsyncSession, user: User, ds: Dataset, got: dict, name: str, description: str,
                 others: dict[str, int] | None = None) -> tuple[Report, list[str]]:
    """The resolved template as a dashboard, in one transaction. A chart the
    engine refuses is left out and named, never stored broken."""
    from ..services.widget_roles import InvalidWidget, migrate_widget_config, validate_widget_payload
    report = Report(name=name[:255], description=description or None, dataset_id=ds.id, org_id=user.org_id,
                    created_by=user.id, origin="template", style=got["style"] or {},
                    additional_dataset_ids=sorted(set((others or {}).values())),
                    theme=str((got["style"] or {}).get("palette") or "default")[:20])
    db.add(report)
    await db.flush()
    refused_titles: list[str] = []
    page_ids: dict[str, int] = {}
    linked: list[ReportWidget] = []
    for position, p in enumerate(got["pages"]):
        page = ReportPage(report_id=report.id, name=p["name"][:255], title=p.get("title"), position=position,
                          page_type=p.get("page_type") or "normal", page_size=p.get("page_size") or "16:9",
                          prompt_column=p.get("prompt_column"), prompt_label=p.get("prompt_label"),
                          layout_mode="packed")
        db.add(page)
        await db.flush()
        page_ids.setdefault(page.name, page.id)
        # The template's filters: a row of controls above the page, the charts moved down to make room.
        controls = got["filters"] if page.page_type == "normal" else []
        width = max(2, 12 // max(len(controls), 1)) if controls else 0
        for i, f in enumerate(controls[:6]):
            db.add(ReportWidget(page_id=page.id, widget_type="slicer", title=str(f["column"]).replace("_", " "),
                                config={"dimension": f["column"], "slicer_mode": f["mode"]},
                                layout={"x": i * width, "y": 0, "w": width, "h": FILTER_ROW_H}))
        shift = FILTER_ROW_H if controls else 0
        made: dict[int, ReportWidget] = {}
        for i, w in enumerate(p["widgets"]):
            config = migrate_widget_config(w["config"])
            if w.get("dataset"):
                # A chart of an additional dataset says which one it reads.
                config["dataset_id"] = (others or {})[w["dataset"]]
            try:
                validate_widget_payload(w["widget_type"], config)
            except InvalidWidget:
                refused_titles.append(w["title"])
                continue
            lay = dict(w.get("layout") or {"x": 0, "y": 999, "w": 6, "h": 5})
            lay["y"] = lay.get("y", 0) + shift
            row = ReportWidget(page_id=page.id, widget_type=w["widget_type"], title=w["title"][:255],
                               config=config, layout=lay)
            db.add(row)
            made[i] = row
            if "actionPageTitle" in config or "drill_page" in config:
                linked.append(row)
        await db.flush()
        # Click-to-filter, now that the widgets have ids.
        by_source: dict[int, list[dict]] = {}
        for r in p.get("relations") or []:
            if r["from"] in made and r["to"] in made:
                by_source.setdefault(r["from"], []).append({"targetId": made[r["to"]].id, "mode": r["mode"]})
        for i, actions in by_source.items():
            made[i].config = {**(made[i].config or {}),
                              "interaction": {"broadcasts": True, "receives": True, "actions": actions}}
            flag_modified(made[i], "config")
    # Buttons and drill-through, now that the pages have ids: a link is stored
    # against a real page, never against a name that might change.
    for row in linked:
        config = dict(row.config or {})
        target = page_ids.get(config.pop("actionPageTitle", None))
        if target is not None:
            config["actionPageId"] = target
        drill = page_ids.get(config.pop("drill_page", None))
        if drill is not None:
            config["drillthroughPageId"] = drill
        row.config = config
        flag_modified(row, "config")
    return report, refused_titles


@router.post("/{ref}/use", status_code=201)
async def use(ref: str, body: UseIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """A new dashboard from a template, on one dataset. The template itself is
    not touched: what is made is the person's own dashboard to change."""
    spec, row = await _load(db, ref, user)
    spec = words.localise(spec, body.lang)
    ds = await _dataset(db, user, body.dataset_id)
    columns = await _columns(db, user, ds)
    other_rows, other_columns = await _others(db, user, spec, body.datasets, ds)
    chosen = (mapping.normalise(body.mapping) if body.mapping is not None
              else mapping.suggest(spec, columns, other_columns))
    check = mapping.validate(spec, chosen, columns, other_columns)
    if not check["ok"]:
        raise HTTPException(400, {"message": "This mapping cannot be used", "check": check})
    may_define = rank(await max_dataset_capability(db, user, ds.id)) >= rank("data")
    try:
        got = resolve(spec, chosen, {c["name"]: c["label"] for c in columns},
                      {str(m.get("name")): str(m.get("expression") or "") for m in ds.measures or []},
                      allow_metrics=may_define, datasets=set(other_columns))
    except tspec.TemplateError as e:
        raise refused(400, e)
    # Metric definitions: the same checks and the same history as a measure saved by hand.
    if got["measures"]:
        from ..routers.datasets import MeasureDef, _validate_measure, _versioned
        for m in got["measures"]:
            # Each measure on the dataset its columns belong to.
            target = other_rows[m["dataset"]] if m.get("dataset") else ds
            if target is not ds and rank(await max_dataset_capability(db, user, target.id)) < rank("data"):
                raise HTTPException(403, f"You may not define measures on '{target.name}', which this template needs")
            measure = MeasureDef(**{k: v for k, v in m.items() if k != "dataset"})
            have = {str(x.get("name")): x for x in target.measures or []}
            if (have.get(measure.name) or {}).get("expression") == measure.expression:
                continue
            await _validate_measure(measure, target, db)
            target.measures = [*(target.measures or []), _versioned(measure.model_dump(exclude_none=True), None, user)]
            flag_modified(target, "measures")
    name = (body.name or "").strip() or f"{row.name if row else spec.get('name')} — {ds.name}"
    report, refused_titles = await _write(db, user, ds, got, name, str(spec.get("description") or ""),
                                          {key: row.id for key, row in other_rows.items()})
    if row is not None:
        row.uses = (row.uses or 0) + 1
    await audit(db, user, "template.use", "report", report.id, f"{ref} on dataset {ds.id}")
    await db.commit()
    return {"report_id": report.id, "name": report.name, "dropped": got["dropped"],
            "skipped_metrics": got["skipped_metrics"], "refused": refused_titles,
            "measures": [m["name"] for m in got["measures"]]}


async def _capture_report(db: AsyncSession, user: User, report_id: int, *, name: str, description: str,
                          category: str, tags: list[str], style: dict | None = None) -> tuple[dict, dict]:
    report = (await db.execute(select(Report).options(selectinload(Report.pages).selectinload(ReportPage.widgets))
                               .where(Report.id == report_id))).scalar_one_or_none()
    check_org(report, user, "Report not found")
    await require_capability(db, user, report_id, "view")
    if report.dataset_id is None:
        raise HTTPException(400, "This dashboard reads no dataset, so it has no columns to turn into a template")
    ds = await _dataset(db, user, report.dataset_id)
    # The dashboard's additional datasets this person may read: their charts are carried too.
    others: dict[int, dict] = {}
    for n, other_id in enumerate([i for i in report.additional_dataset_ids or [] if i and i != ds.id], start=2):
        other = await db.get(Dataset, other_id)
        if other is None or other.org_id != user.org_id:
            continue
        try:
            await require_dataset_read(db, user, other_id)
        except HTTPException:
            continue
        others[other_id] = {"key": f"d{n}", "label": other.name, "columns": await _columns(db, user, other),
                            "measures": other.measures}
    pages = [{"id": p.id, "name": p.name, "title": p.title, "page_type": p.page_type, "page_size": p.page_size,
              "prompt_column": p.prompt_column, "prompt_label": p.prompt_label,
              "widgets": [{"id": w.id, "widget_type": w.widget_type, "title": w.title, "config": w.config or {},
                           "layout": w.layout or {}}
                          for w in sorted(p.widgets, key=lambda w: w.id)
                          if (w.config or {}).get("dataset_id") in (None, ds.id, *others)]}
             for p in sorted(report.pages, key=lambda p: (p.position, p.id))]
    made, left = capture.from_report(pages, await _columns(db, user, ds), ds.measures, name=name,
                                     description=description, category=category, tags=tags, others=others,
                                     style=style if style is not None else {**(report.style or {}),
                                                                             **({"palette": report.theme} if report.theme and report.theme != "default" else {})})
    try:
        tspec.check(made)
    except tspec.TemplateError as e:
        raise refused(400, e)
    return made, left


def _checked(category: str, visibility: str) -> None:
    if category not in tspec.CATEGORIES:
        raise HTTPException(400, f"category must be one of {', '.join(tspec.CATEGORIES)}")
    if visibility not in ("personal", "org"):
        raise HTTPException(400, "visibility is personal or org")


@router.post("", status_code=201)
async def save(body: SaveIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Save a dashboard as a template, or take a personal copy of another
    template to change. The dashboard (or the original) is left as it is."""
    _checked(body.category, body.visibility)
    left: dict = {}
    if body.copy_of:
        source, _row = await _load(db, body.copy_of, user)
        made = {**source, "name": body.name.strip(), "description": body.description or source.get("description") or "",
                "category": body.category if body.category in tspec.CATEGORIES else source.get("category"),
                "tags": body.tags or source.get("tags") or []}
        made.pop("key", None)
    elif body.report_id is not None:
        made, left = await _capture_report(db, user, body.report_id, name=body.name, description=body.description,
                                           category=body.category, tags=body.tags)
    else:
        raise HTTPException(400, "Say which dashboard (report_id) or which template (copy_of) to save from")
    row = DashboardTemplate(org_id=user.org_id, name=body.name.strip()[:120], description=made.get("description"),
                            category=made.get("category") or "overview", tags=made.get("tags") or [], spec=made,
                            visibility=body.visibility, created_by=user.id, version=1, uses=0)
    db.add(row)
    await db.flush()
    await audit(db, user, "template.create", "dashboard_template", row.id, row.name)
    await db.commit()
    return {**_card(f"t:{row.id}", made, source="org" if row.visibility == "org" else "personal", favorite=False,
                    row=row, mine=True, can_change=True), "left_out": left}


async def _owned(db: AsyncSession, template_id: int, user: User) -> DashboardTemplate:
    row = await db.get(DashboardTemplate, template_id)
    if row is None or not _can_see(row, user):
        raise HTTPException(404, "Template not found")
    if not _can_change(row, user):
        raise HTTPException(403, "Only its author or an administrator can change this template")
    return row


async def _keep_version(db: AsyncSession, row: DashboardTemplate, user: User, note: str | None) -> None:
    db.add(DashboardTemplateVersion(template_id=row.id, version=row.version, name=row.name, spec=row.spec or {},
                                    note=note, created_by=user.id))
    old = (await db.execute(select(DashboardTemplateVersion.id)
                            .where(DashboardTemplateVersion.template_id == row.id)
                            .order_by(DashboardTemplateVersion.version.desc())
                            .offset(VERSIONS_KEPT))).scalars().all()
    for vid in old:
        await db.delete(await db.get(DashboardTemplateVersion, vid))


@router.put("/{template_id}")
async def edit(template_id: int, body: EditIn, db: AsyncSession = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Change a saved template. Whatever changes its content (a dashboard
    taken again, a new style) keeps the version before it."""
    row = await _owned(db, template_id, user)
    _checked(body.category or row.category, body.visibility or row.visibility)
    left: dict = {}
    spec = dict(row.spec or {})
    content_changed = False
    if body.report_id is not None:
        spec, left = await _capture_report(db, user, body.report_id, name=body.name or row.name,
                                           description=body.description if body.description is not None else (row.description or ""),
                                           category=body.category or row.category,
                                           tags=body.tags if body.tags is not None else list(row.tags or []))
        content_changed = True
    if body.style is not None:
        spec["style"] = tspec.clean_style(body.style)
        content_changed = True
    if content_changed:
        await _keep_version(db, row, user, body.note)
        row.version = (row.version or 1) + 1
    for field in ("name", "description", "category", "visibility"):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value.strip() if isinstance(value, str) else value)
    if body.tags is not None:
        row.tags = [str(t)[:30] for t in body.tags][:8]
    spec.update(name=row.name, description=row.description or "", category=row.category, tags=list(row.tags or []))
    row.spec = spec
    flag_modified(row, "spec")
    row.updated_at = datetime.utcnow()
    await audit(db, user, "template.update", "dashboard_template", row.id, row.name)
    await db.commit()
    return {**_card(f"t:{row.id}", spec, source="org" if row.visibility == "org" else "personal",
                    favorite=f"t:{row.id}" in await _favorites(db, user), row=row,
                    mine=row.created_by == user.id, can_change=True), "left_out": left}


@router.get("/{template_id}/versions")
async def versions(template_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await db.get(DashboardTemplate, template_id)
    if row is None or not _can_see(row, user):
        raise HTTPException(404, "Template not found")
    rows = (await db.execute(select(DashboardTemplateVersion)
                             .where(DashboardTemplateVersion.template_id == template_id)
                             .order_by(DashboardTemplateVersion.version.desc()))).scalars().all()
    return {"current": row.version,
            "versions": [{"id": v.id, "version": v.version, "name": v.name, "note": v.note,
                          "created_at": v.created_at,
                          "widgets": sum(len(p.get("widgets") or []) for p in (v.spec or {}).get("pages") or [])}
                         for v in rows]}


@router.post("/{template_id}/versions/{version_id}/restore")
async def restore(template_id: int, version_id: int, db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Bring an earlier version back, as a NEW version: nothing is lost."""
    row = await _owned(db, template_id, user)
    old = await db.get(DashboardTemplateVersion, version_id)
    if old is None or old.template_id != row.id:
        raise HTTPException(404, "Version not found")
    await _keep_version(db, row, user, f"before restoring version {old.version}")
    row.spec = {**(old.spec or {}), "name": row.name}
    flag_modified(row, "spec")
    row.version = (row.version or 1) + 1
    row.updated_at = datetime.utcnow()
    await audit(db, user, "template.restore", "dashboard_template", row.id, f"version {old.version}")
    await db.commit()
    return {"version": row.version, "restored": old.version}


@router.delete("/{template_id}", status_code=204)
async def remove(template_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    row = await _owned(db, template_id, user)
    await audit(db, user, "template.delete", "dashboard_template", row.id, row.name)
    for fav in (await db.execute(select(TemplateFavorite)
                                 .where(TemplateFavorite.template_ref == f"t:{row.id}"))).scalars().all():
        await db.delete(fav)
    await db.delete(row)
    await db.commit()


@router.put("/{ref}/favorite")
async def favorite(ref: str, body: FavoriteIn, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    await _load(db, ref, user)
    have = (await db.execute(select(TemplateFavorite).where(TemplateFavorite.user_id == user.id,
                                                            TemplateFavorite.template_ref == ref))).scalar_one_or_none()
    if body.on and have is None:
        db.add(TemplateFavorite(user_id=user.id, template_ref=ref))
    elif not body.on and have is not None:
        await db.delete(have)
    await db.commit()
    return {"ref": ref, "favorite": body.on}
