import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.capability import (effective_capabilities, effective_capability,
                               require_capability)
from ..dependencies import get_current_user
from ..services.audit import record as audit
from ..models.models import CommonFilter, DataAlert, OrgTheme, PageRoleVisibility, PageTemplate, Report, ReportClassification, ReportParameter, ReportSchedule, ReportPage, ReportUserGrant, ReportVersion, ReportWidget, Bookmark, RecentView, Role, User
from ..schemas.schemas import (
    ReportCreate, ReportUpdate, ReportOut,
    PageCreate, PageUpdate, PageOut,
    WidgetCreate, WidgetUpdate, WidgetOut,
    BookmarkCreate, BookmarkOut,
)

async def _report_access_gate(report_id: int | None = None,
                              db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)) -> None:
    """Router-wide draft privacy: every endpoint with a {report_id} path param
    404s when the report resolves to 'none' for this viewer (an unpublished
    dashboard someone else authored, with no grant).

    A ROUTER dependency rather than per-endpoint calls, for the reason the RLS
    choke point exists: this file has dozens of report-scoped endpoints, and a
    privacy rule enforced by remembering to call it would be a privacy rule
    with holes. Endpoints without the param (the list, templates, roles/lite)
    resolve report_id to None and pass through; unowned legacy reports resolve
    to at least 'view' for every org member, so nothing pre-existing changes.
    """
    if report_id is not None:
        await require_capability(db, current_user, report_id, "view")


router = APIRouter(prefix="/reports", tags=["reports"],
                   dependencies=[Depends(_report_access_gate)])

logger = logging.getLogger(__name__)

# Sensitivity labels, ordered least → most restrictive. A fixed set rather than a
# free string so a label means the same thing on every report and can be styled and
# ranked consistently; "" clears the classification.
SENSITIVITY_LABELS = ["Public", "Internal", "Confidential", "Restricted"]


async def _classification_of(report_id: int, db: AsyncSession) -> str | None:
    row = (await db.execute(
        select(ReportClassification).where(ReportClassification.report_id == report_id)
    )).scalar_one_or_none()
    return row.label if row else None


_FILTER_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "like", "relative"}


async def _common_filters_of(report_id: int, db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(CommonFilter).where(CommonFilter.report_id == report_id)
        .order_by(CommonFilter.position, CommonFilter.id)
    )).scalars().all()
    return [{"id": f.id, "column": f.column, "op": f.op, "value": f.value} for f in rows]

_REPORT_OPTS = [selectinload(Report.pages).selectinload(ReportPage.widgets)]
_PAGE_OPTS   = [selectinload(ReportPage.widgets)]


async def _get_page(page_id: int, report_id: int, db: AsyncSession, current_user: User) -> ReportPage:
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(
        select(ReportPage).options(*_PAGE_OPTS)
        .where(ReportPage.id == page_id, ReportPage.report_id == report_id)
    )
    obj = r.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Page not found")
    return obj


async def _get_report(report_id: int, db: AsyncSession, current_user: User) -> Report:
    r = await db.execute(select(Report).options(*_REPORT_OPTS).where(Report.id == report_id))
    obj = r.scalar_one_or_none()
    check_org(obj, current_user, "Report not found")
    return obj


async def _bump_revision(report_id: int, db: AsyncSession, current_user: User,
                         *, via: str | None = None, note: str | None = None) -> "ReportVersion | None":
    """Increment the report's revision counter AND enforce edit capability.

    Called by every report mutation below, so it is also the one place that
    guarantees a 'view'-level role cannot change a report: the capability check
    happens here, before the commit, so a refusal rolls the staged mutation back.
    Ones that only touch nested pages, widgets or bookmarks route through here
    too — that is where nearly all editing happens, so a counter that only moved
    for report-level fields would miss almost every real conflict, and a gate
    that only covered report-level fields would miss almost every real edit.

    The UPDATE is issued as a single expression (`revision = revision + 1`) rather
    than a read-modify-write in Python, so two concurrent requests cannot both read
    the same value and write the same increment.
    """
    version = await _capture_version(report_id, db, current_user, via=via, note=note)
    await require_capability(db, current_user, report_id, "edit")
    await db.execute(
        sa_update(Report).where(Report.id == report_id).values(revision=Report.revision + 1)
    )
    return version


#: Restorable snapshots kept per report. Fifty covers a heavy editing day;
#: past that the oldest state is history nobody scrolls back to, and an
#: unbounded table of full-content JSON would grow with every drag.
VERSIONS_KEPT = 50


async def _capture_version(report_id: int, db: AsyncSession,
                           current_user: User, *, via: str | None = None,
                           note: str | None = None) -> "ReportVersion | None":
    """Snapshot the report's CONTENT as it stands in the database, before the
    mutation that triggered this bump commits (R2: history with restore).

    CORE selects on the tables, not ORM queries: the calling request has
    usually already modified the very ORM objects being snapshotted (an
    update sets attributes first, then bumps), and an ORM query would hand
    back those same dirty instances from the identity map — the "before"
    picture would contain the "after". Reading rows keeps the snapshot at
    the last-committed state; a pending INSERT (add_widget) is invisible for
    the same reason, which is equally correct — it is not part of "before".

    Autoflush is suspended around the reads so the session does not flush
    the in-flight mutation mid-snapshot and defeat the point.
    """
    rep_t = Report.__table__
    page_t = ReportPage.__table__
    widget_t = ReportWidget.__table__
    with db.sync_session.no_autoflush:
        rep = (await db.execute(
            select(rep_t.c.revision, rep_t.c.theme, rep_t.c.display_rules)
            .where(rep_t.c.id == report_id))).first()
        if rep is None:
            return None
        page_rows = (await db.execute(
            select(page_t).where(page_t.c.report_id == report_id)
            .order_by(page_t.c.position, page_t.c.id))).mappings().all()
        page_ids = [p["id"] for p in page_rows]
        widget_rows = (await db.execute(
            select(widget_t).where(widget_t.c.page_id.in_(page_ids))
            .order_by(widget_t.c.id))).mappings().all() if page_ids else []

    by_page: dict[int, list[dict]] = {}
    for w in widget_rows:
        by_page.setdefault(w["page_id"], []).append(
            {"widget_type": w["widget_type"], "title": w["title"],
             "config": w["config"], "layout": w["layout"]})
    snapshot = {
        "report": {"theme": rep.theme, "display_rules": rep.display_rules},
        "pages": [{
            "name": p["name"], "title": p["title"], "page_type": p["page_type"],
            "prompt_column": p["prompt_column"], "prompt_label": p["prompt_label"],
            "position": p["position"], "page_size": p["page_size"],
            "custom_width": p["custom_width"], "custom_height": p["custom_height"],
            "mobile_layout": p["mobile_layout"],
            "layout_mode": p.get("layout_mode"),
            "layout_template": p.get("layout_template"),
            "widgets": by_page.get(p["id"], []),
        } for p in page_rows],
    }
    if via or note:
        # Who made the change this snapshot precedes, when it was not the
        # person's own hand (Phase 7.1: "the AI changed X" is attributable
        # and one restore from gone). Kept in the snapshot JSON: history is
        # additive metadata, not a schema change.
        snapshot["meta"] = {"via": via, "note": (note or "")[:500]}
    version = ReportVersion(report_id=report_id, revision=rep.revision,
                            snapshot=snapshot, created_by=current_user.id)
    db.add(version)

    # Prune beyond the retention window, oldest first.
    stale = (await db.execute(
        select(ReportVersion.id).where(ReportVersion.report_id == report_id)
        .order_by(ReportVersion.id.desc()).offset(VERSIONS_KEPT))).scalars().all()
    if stale:
        from sqlalchemy import delete as sa_delete
        await db.execute(sa_delete(ReportVersion)
                         .where(ReportVersion.id.in_(stale)))
    return version


# ── Reports ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ReportOut])
async def list_reports(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(Report).options(*_REPORT_OPTS)
        .where(Report.org_id == current_user.org_id)
        .order_by(Report.created_at.desc())
    )
    reports = r.scalars().all()
    # The list used to leave my_capability at its schema default ('data'),
    # which claimed full access on every row -- the Reports page then offered
    # "Open designer" and Delete on reports the server would refuse to mutate.
    # Populated for real, plus authorship for the My-workspaces / Granted
    # grouping -- and rows resolving to 'none' (someone else's unpublished
    # draft, no grant) are not listed at all: a draft is private, not greyed.
    caps = await effective_capabilities(db, current_user, [x.id for x in reports])
    visible = [x for x in reports if caps[x.id] != "none"]
    for x in visible:
        x.my_capability = caps[x.id]
        x.is_mine = x.created_by is not None and x.created_by == current_user.id
    return visible


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(body: ReportCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = Report(**body.model_dump(), org_id=current_user.org_id,
                 created_by=current_user.id)
    db.add(obj)
    await db.flush()
    # Create default first page
    page = ReportPage(report_id=obj.id, name="Page 1", position=0)
    db.add(page)
    await audit(db, current_user, "report.create", "report", obj.id, obj.name)
    await db.commit()
    created = await _get_report(obj.id, db, current_user)
    # _get_report is the bare loader (no transient attrs); the response must
    # still say whose this is -- it is the row the client prepends to its list.
    created.is_mine = True
    return created


@router.get("/recent")
async def list_recent(limit: int = 8, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """This user's recently opened dashboards, newest first.

    Declared BEFORE `/{report_id}` would otherwise capture it -- FastAPI
    matches in declaration order, and "recent" is a valid-looking int-free path
    that a later `{report_id}` route would swallow into a 422.

    Rows the viewer may no longer open are filtered out rather than shown
    greyed: a draft that was unpublished, or a grant that was revoked, must
    disappear from a personal list the same way it disappears from every other
    surface. That is the keyhole rule -- visibility is re-checked on every
    read, never trusted from when the row was written.
    """
    limit = max(1, min(limit, 50))
    rows = (await db.execute(
        select(RecentView, Report)
        .join(Report, Report.id == RecentView.report_id)
        .where(RecentView.user_id == current_user.id,
               Report.org_id == current_user.org_id)
        .order_by(RecentView.viewed_at.desc())
        .limit(limit * 2)          # headroom for the capability filter below
    )).all()

    caps = await effective_capabilities(db, current_user, [r.id for _v, r in rows])
    out = []
    for view, report in rows:
        if caps.get(report.id) == "none":
            continue
        out.append({
            "id": report.id,
            "name": report.name,
            "viewed_at": view.viewed_at,
            "published": bool(report.published),
            "created_by": report.created_by,
            "is_mine": report.created_by is not None and report.created_by == current_user.id,
            "my_capability": caps.get(report.id, "data"),
        })
        if len(out) >= limit:
            break
    return out


async def _visible_page_ids(db: AsyncSession, report: Report, user: User) -> set[int]:
    """Ids of the report's pages this user may see (all of them for an admin).

    Computed, never applied by reassigning `report.pages`: that relationship
    cascades delete-orphan, so narrowing it in place and then committing
    anything (a recent-view row, an audit entry) DELETED the hidden pages for
    everyone. A restricted viewer opening a report used to do exactly that."""
    ids = set((await db.execute(select(ReportPage.id).where(ReportPage.report_id == report.id))).scalars().all())
    if user.role.is_org_admin or not ids:
        return ids
    rows = (await db.execute(
        select(PageRoleVisibility).where(PageRoleVisibility.page_id.in_(ids)))).scalars().all()
    restricted: dict[int, set[int]] = {}
    for row in rows:
        restricted.setdefault(row.page_id, set()).add(row.role_id)
    return {pid for pid in ids if pid not in restricted or user.role_id in restricted[pid]}


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await _get_report(report_id, db, current_user)
    # Server-side page visibility: a page restricted to roles the viewer lacks is
    # ABSENT from the response, not hidden by the client -- its widgets' configs are
    # never serialised to that viewer at all. Admins are exempt: an admin locked out
    # of a page could not administer the restriction that locked them out.
    visible = await _visible_page_ids(db, report, current_user)
    report.my_capability = await effective_capability(db, current_user, report_id)
    report.is_mine = report.created_by is not None and report.created_by == current_user.id
    report.classification = await _classification_of(report_id, db)
    report.common_filters = await _common_filters_of(report_id, db)
    # Serialised BEFORE anything commits, and narrowed on the copy.
    out = ReportOut.model_validate(report)
    out.pages = [p for p in out.pages if p.id in visible]
    await _record_view(db, current_user, report_id)
    return out


async def _record_view(db: AsyncSession, user: User, report_id: int) -> None:
    """Remember that this user opened this dashboard, for Home's Recents.

    FAIL-SOFT, and that is the whole design note: recording a view is a
    convenience, so it must never turn a successful read into an error. A
    unique violation from two tabs opening the same dashboard at once, or a
    database that has not run 0015 yet, both resolve to "no recents entry" --
    never to a 500 on the page the user actually asked for.

    Upsert by hand rather than a dialect-specific ON CONFLICT: this app runs on
    Postgres in production and SQLite in the migration tests, and one portable
    read-then-write is cheaper than maintaining two statements.
    """
    try:
        row = (await db.execute(
            select(RecentView).where(RecentView.user_id == user.id,
                                     RecentView.report_id == report_id)
        )).scalar_one_or_none()
        if row is None:
            db.add(RecentView(user_id=user.id, report_id=report_id,
                              viewed_at=datetime.utcnow()))
        else:
            row.viewed_at = datetime.utcnow()
        await db.commit()
    except Exception:
        await db.rollback()


@router.get("/{report_id}/revision")
async def get_report_revision(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Just the revision counter — deliberately cheap, with none of the page and
    widget eager-loading GET /{report_id} does, because a client polls this to
    notice concurrent edits and should not pull the whole report to do it."""
    obj = await db.get(Report, report_id)
    check_org(obj, current_user, "Report not found")
    return {"revision": obj.revision or 0}


@router.get("/{report_id}/classification")
async def get_report_classification(report_id: int, db: AsyncSession = Depends(get_db),
                                    current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    from ..services.sensitivity import report_effective, report_floor
    floor, floor_reasons = await report_floor(db, report)
    effective, reasons = await report_effective(db, report)
    return {"label": await _classification_of(report_id, db), "options": SENSITIVITY_LABELS,
            # Phase 7.3: the label cannot go below its data, and what it enforces.
            "floor": floor, "floor_reasons": floor_reasons,
            "effective": effective, "effective_reasons": reasons}


@router.put("/{report_id}/classification", response_model=ReportOut)
async def set_report_classification(report_id: int, body: dict,
                                    db: AsyncSession = Depends(get_db),
                                    current_user: User = Depends(get_current_user)):
    """Set (or clear, with an empty label) a report's sensitivity label. Editing the
    classification is a report edit, so it goes through the same capability gate and
    revision bump as any other mutation."""
    report = await _get_report(report_id, db, current_user)
    label = (body.get("label") or "").strip()
    if label and label not in SENSITIVITY_LABELS:
        raise HTTPException(400, f"label must be one of {SENSITIVITY_LABELS} or empty")
    # The badge cannot claim less than the data underneath it (Phase 7.3).
    from ..services.sensitivity import rank as s_rank, report_floor
    floor, floor_reasons = await report_floor(db, report)
    if floor and s_rank(label or None) < s_rank(floor):
        raise HTTPException(400, f"This report cannot be labelled {label or 'unclassified'}: "
                                 f"{floor_reasons[0] if floor_reasons else 'its data'} "
                                 f"-- the lowest it can carry is {floor}.")
    await _bump_revision(report_id, db, current_user)  # also enforces edit capability
    row = (await db.execute(
        select(ReportClassification).where(ReportClassification.report_id == report_id)
    )).scalar_one_or_none()
    if not label:
        if row:
            await db.delete(row)
    elif row:
        row.label = label
    else:
        db.add(ReportClassification(report_id=report_id, org_id=report.org_id, label=label))
    await audit(db, current_user, "report.classify", "report", report_id, label or "(cleared)")
    await db.commit()
    report = await _get_report(report_id, db, current_user)
    report.my_capability = await effective_capability(db, current_user, report_id)
    report.classification = label or None
    return report


@router.post("/{report_id}/common-filters", status_code=201)
async def add_common_filter(report_id: int, body: dict,
                            db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Add a report-level filter applied to every widget. Editing report filters is
    a report edit — same capability gate and revision bump as any mutation."""
    await _get_report(report_id, db, current_user)
    column = (body.get("column") or "").strip()
    op = (body.get("op") or "eq").strip()
    if not column:
        raise HTTPException(400, "A common filter needs a column")
    if op not in _FILTER_OPS:
        raise HTTPException(400, f"op must be one of {sorted(_FILTER_OPS)}")
    if op == "relative":
        from ..services.relative_dates import RelativeDateError, validate_spec
        try:
            body = {**body, "value": validate_spec(body.get("value"))}
        except RelativeDateError as e:
            raise HTTPException(400, str(e))
    await _bump_revision(report_id, db, current_user)  # also enforces edit capability
    n = len((await db.execute(
        select(CommonFilter).where(CommonFilter.report_id == report_id))).scalars().all())
    cf = CommonFilter(report_id=report_id, column=column, op=op, value=body.get("value"), position=n)
    db.add(cf)
    await audit(db, current_user, "report.add_common_filter", "report", report_id, f"{column} {op}")
    await db.commit()
    await db.refresh(cf)
    return {"id": cf.id, "column": cf.column, "op": cf.op, "value": cf.value}


@router.delete("/{report_id}/common-filters/{filter_id}", status_code=204)
async def delete_common_filter(report_id: int, filter_id: int,
                               db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    await _get_report(report_id, db, current_user)
    cf = await db.get(CommonFilter, filter_id)
    if cf is None or cf.report_id != report_id:
        raise HTTPException(404, "Common filter not found")
    await _bump_revision(report_id, db, current_user)
    await db.delete(cf)
    await audit(db, current_user, "report.delete_common_filter", "report", report_id, cf.column)
    await db.commit()


@router.patch("/{report_id}", response_model=ReportOut)
async def update_report(report_id: int, body: ReportUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy.orm.attributes import flag_modified
    obj = await _get_report(report_id, db, current_user)
    # Unset fields are left alone; an explicit null clears ONLY the primary
    # dataset (undoing "attach data" on a report created without one). Every
    # other null is ignored as before -- a report cannot lose its name.
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k != "dataset_id":
            continue
        setattr(obj, k, v)
    if body.additional_dataset_ids is not None:
        flag_modified(obj, 'additional_dataset_ids')
    if body.display_rules is not None:
        flag_modified(obj, 'display_rules')
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    return await _get_report(report_id, db, current_user)


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Report, report_id)
    check_org(obj, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    # No revision bump: the row is being deleted, so there is nothing left to
    # version and no client that could usefully compare against it.
    await audit(db, current_user, "report.delete", "report", obj.id, obj.name)
    await db.delete(obj)
    await db.commit()


# ── Publish & per-user grants ────────────────────────────────────────────────
# Two different acts on two different axes, deliberately not one dialog's
# checkboxes: PUBLISH controls audience (the whole org may open it, at view
# strength -- the layout locks, no widget moves); a GRANT controls capability
# for one named person (see a draft, or design it). Both are the author's to
# give -- capability level does not carry this right: an 'edit' grantee can
# move widgets, and still cannot publish someone else's work or re-share it.

def _may_administer_sharing(report: Report, user: User) -> bool:
    return bool(user.role and user.role.is_org_admin) or (
        report.created_by is not None and report.created_by == user.id)


@router.post("/{report_id}/publish")
async def set_published(report_id: int, body: dict,
                        db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if report.created_by is None:
        # Grandfathered rows ignore the regime entirely -- storing the flag
        # would render a "Published" badge that controls nothing.
        raise HTTPException(400, "This report predates publishing; it is already "
                                 "visible and editable org-wide")
    if not _may_administer_sharing(report, current_user):
        raise HTTPException(403, "Only the dashboard's author or an admin can publish it")
    if body.get("published") and not report.published:
        # Report quality as CI (Phase 7.4): when the org turns the gate on,
        # a report with open review errors does not go out to everyone.
        from ..services.report_review import high_findings
        from .review import gate_on, report_pages
        if await gate_on(db, report.org_id):
            open_errors = high_findings(await report_pages(db, report_id))
            if open_errors:
                raise HTTPException(409, {
                    "message": f"Publishing is blocked while {len(open_errors)} review error"
                               f"{'s are' if len(open_errors) != 1 else ' is'} open (your organisation's "
                               f"publish gate). Fix them in the Review pane, then publish.",
                    "findings": open_errors})
    report.published = bool(body.get("published"))
    await audit(db, current_user,
                "report.publish" if report.published else "report.unpublish",
                "report", report.id, report.name)
    await db.commit()
    return {"published": report.published}


@router.get("/{report_id}/grants")
async def list_grants(report_id: int, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not _may_administer_sharing(report, current_user):
        raise HTTPException(403, "Only the dashboard's author or an admin can see its grants")
    rows = (await db.execute(
        select(ReportUserGrant, User.email)
        .join(User, User.id == ReportUserGrant.user_id)
        .where(ReportUserGrant.report_id == report_id)
        .order_by(ReportUserGrant.id)
    )).all()
    return [{"id": g.id, "user_id": g.user_id, "email": email, "level": g.level}
            for g, email in rows]


@router.post("/{report_id}/grants", status_code=201)
async def create_grant(report_id: int, body: dict,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """Share to a user BY EMAIL. An email input rather than a user picker on
    purpose: members cannot list the org directory, and sharing should not be
    the endpoint that leaks it -- you share with someone you already know."""
    from ..core.capability import LEVELS
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not _may_administer_sharing(report, current_user):
        raise HTTPException(403, "Only the dashboard's author or an admin can share it")
    level = str(body.get("level") or "edit")
    if level not in LEVELS:
        raise HTTPException(400, f"level must be one of {', '.join(LEVELS)}")
    email = str(body.get("email") or "").strip().lower()
    grantee = (await db.execute(
        select(User).where(User.email == email, User.org_id == current_user.org_id)
    )).scalar_one_or_none()
    if grantee is None:
        raise HTTPException(404, "No user with that email in your organization")
    if report.created_by is not None and grantee.id == report.created_by:
        raise HTTPException(400, "That user is the dashboard's author")
    existing = (await db.execute(
        select(ReportUserGrant).where(ReportUserGrant.report_id == report_id,
                                      ReportUserGrant.user_id == grantee.id)
    )).scalar_one_or_none()
    if existing:
        existing.level = level      # re-sharing updates the level, not a 409
        grant = existing
    else:
        grant = ReportUserGrant(report_id=report_id, user_id=grantee.id, level=level)
        db.add(grant)
        await db.flush()
    await audit(db, current_user, "report.share", "report", report.id,
                f"{grantee.email}: {level}")
    await db.commit()
    return {"id": grant.id, "user_id": grantee.id, "email": grantee.email,
            "level": level}


@router.delete("/{report_id}/grants/{grant_id}", status_code=204)
async def delete_grant(report_id: int, grant_id: int,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not _may_administer_sharing(report, current_user):
        raise HTTPException(403, "Only the dashboard's author or an admin can unshare it")
    grant = await db.get(ReportUserGrant, grant_id)
    if grant is None or grant.report_id != report_id:
        raise HTTPException(404, "Grant not found")
    await audit(db, current_user, "report.unshare", "report", report.id,
                f"grant:{grant_id}")
    await db.delete(grant)
    await db.commit()


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.post("/{report_id}/pages", response_model=PageOut, status_code=201)
async def add_page(report_id: int, body: PageCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    page = ReportPage(report_id=report_id, **body.model_dump())
    db.add(page)
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    return await _get_page(page.id, report_id, db, current_user)


@router.patch("/{report_id}/pages/{page_id}", response_model=PageOut)
async def update_page(report_id: int, page_id: int, body: PageUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    page = await _get_page(page_id, report_id, db, current_user)
    changes = body.model_dump(exclude_none=True)
    if "background_url" in changes:
        # The same rule every author-typed address in this product follows
        # (image widget, web content, custom visual, precision container):
        # http(s) or a same-origin path, never javascript: or data:. Refused
        # here rather than filtered at render, so a stored value is always one
        # the page can actually fetch.
        url = (changes["background_url"] or "").strip()
        if url and not (url.startswith("/") or _HTTP_URL.match(url)):
            raise HTTPException(
                400, "A page background must be an http(s) URL or a path on this server")
        changes["background_url"] = url or None
    for k, v in changes.items():
        setattr(page, k, v)
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    return await _get_page(page_id, report_id, db, current_user)


@router.delete("/{report_id}/pages/{page_id}", status_code=204)
async def delete_page(report_id: int, page_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(select(ReportPage).where(ReportPage.id == page_id, ReportPage.report_id == report_id))
    page = r.scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Page not found")
    await db.delete(page)
    await _bump_revision(report_id, db, current_user)
    await db.commit()


_HTTP_URL = re.compile(r"^https?://", re.I)


# ── Widgets ───────────────────────────────────────────────────────────────────

SCRIPT_WIDGET = "script"


def _guard_script_authoring(widget_type: str | None, config: dict | None,
                            current_user: User) -> None:
    """A script tile runs Python on the server. Only an org admin may write one.

    The execution model (services/script_tile.py) keeps credentials out of the
    child process and stops a runaway one, but it is NOT a sandbox: the code
    runs as the server user. Offering the tile is offering a shell, so the gate
    that matters is who may author one -- everyone else runs what an admin
    already wrote, which is the trust model of a saved SQL view.

    Editing an existing tile's CODE is gated as well as creating one: gating
    creation alone would leave every admin-made tile as a writable place to put
    anything, which is the same hole with one extra step.
    """
    if widget_type != SCRIPT_WIDGET or config is None:
        return
    if current_user.role and current_user.role.is_org_admin:
        return
    raise HTTPException(
        403, "A script tile runs code on the server, so only an organisation "
             "admin can create or change one. Ask an admin to review the code.")


#: The widget types whose renderer draws totals and subtotals (WidgetBody's table
#: branch); only these are created carrying the totals defaults.
_TOTALS_TABLE_TYPES = frozenset({"table", "crosstab", "matrix"})


@router.post("/{report_id}/pages/{page_id}/widgets", response_model=WidgetOut, status_code=201)
async def add_widget(report_id: int, page_id: int, body: WidgetCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(select(ReportPage).where(ReportPage.id == page_id, ReportPage.report_id == report_id))
    page = r.scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Page not found")
    fields = body.model_dump()
    _guard_script_authoring(fields.get("widget_type"), fields.get("config"), current_user)
    if fields.get("widget_type") in _TOTALS_TABLE_TYPES:
        # New tables take the current totals defaults: subtotals off, totals drawn
        # BEFORE their data. Stamped here, on creation, rather than changed at read
        # time, so every saved table keeps the defaults it was built with (row
        # subtotals on, totals after the data). A value the caller sent wins.
        fields["config"] = {"show_subtotals": False, "totals_position": "before",
                            **(fields.get("config") or {})}
    widget = ReportWidget(page_id=page_id, **fields)
    db.add(widget)
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    await db.refresh(widget)
    return widget


@router.patch("/{report_id}/pages/{page_id}/widgets/{widget_id}", response_model=WidgetOut)
async def update_widget(report_id: int, page_id: int, widget_id: int, body: WidgetUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(
        select(ReportWidget).join(ReportPage, ReportWidget.page_id == ReportPage.id)
        .where(ReportWidget.id == widget_id, ReportPage.id == page_id, ReportPage.report_id == report_id)
    )
    widget = r.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")
    changes = body.model_dump(exclude_none=True)
    # The TYPE decides the gate, and it may be the stored one (editing an
    # existing tile) or the incoming one (turning a chart into a script tile).
    _guard_script_authoring(changes.get("widget_type") or widget.widget_type,
                            changes.get("config"), current_user)
    for k, v in changes.items():
        setattr(widget, k, v)
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    await db.refresh(widget)
    return widget


async def _prune_actions_targeting(db: AsyncSession, report_id: int, widget_id: int) -> None:
    """Drop every per-pair action aimed at a widget that is going away.

    `config.interaction.actions` holds target widget IDS, so deleting the
    target leaves the edge behind pointing at nothing. It does not error and
    it does not log: `actionReaches` walks to an id nothing matches and the
    selection is silently dropped, for ever. The author sees only that a
    widget is gone, not that their remaining wiring now routes into a hole.

    Two rules, both load-bearing:

    * Widgets with no `actions` are left completely alone. Writing an empty
      list onto them would change their meaning from "reaches everything" to
      "reaches only the listed targets, of which there are none" -- silencing
      them. An empty list is not a neutral value here.
    * The dict is REBUILT rather than mutated in place, because SQLAlchemy
      does not track mutation inside a JSON column; an in-place edit would
      look identical and never be written.

    Scoped to the whole report, not one page: the UI only offers same-page
    targets, but the API, the copilot and a restored snapshot can all carry
    an edge that crosses pages.
    """
    rows = (await db.execute(
        select(ReportWidget).join(ReportPage, ReportWidget.page_id == ReportPage.id)
        .where(ReportPage.report_id == report_id, ReportWidget.id != widget_id)
    )).scalars().all()
    for w in rows:
        cfg = w.config or {}
        interaction = cfg.get("interaction")
        if not isinstance(interaction, dict):
            continue
        actions = interaction.get("actions")
        if not isinstance(actions, list) or not actions:
            continue
        kept = [a for a in actions
                if not (isinstance(a, dict) and a.get("targetId") == widget_id)]
        if len(kept) == len(actions):
            continue
        w.config = {**cfg, "interaction": {**interaction, "actions": kept}}


@router.delete("/{report_id}/pages/{page_id}/widgets/{widget_id}", status_code=204)
async def delete_widget(report_id: int, page_id: int, widget_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    r = await db.execute(
        select(ReportWidget).join(ReportPage, ReportWidget.page_id == ReportPage.id)
        .where(ReportWidget.id == widget_id, ReportPage.id == page_id, ReportPage.report_id == report_id)
    )
    widget = r.scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")
    await db.delete(widget)
    await _prune_actions_targeting(db, report_id, widget_id)
    await _bump_revision(report_id, db, current_user)
    await db.commit()


# ── Version history (R2) ─────────────────────────────────────────────────────

@router.get("/{report_id}/versions")
async def list_versions(report_id: int, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Newest first. Every entry is a restorable content state; `revision` is
    the counter value it describes. Small on purpose — the snapshot itself
    only travels on restore, never in the list."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(ReportVersion, User.email)
        .join(User, User.id == ReportVersion.created_by, isouter=True)
        .where(ReportVersion.report_id == report_id)
        .order_by(ReportVersion.id.desc()))).all()
    return [{
        "id": v.id, "revision": v.revision,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "created_by": email,
        "via": ((v.snapshot or {}).get("meta") or {}).get("via"),
        "note": ((v.snapshot or {}).get("meta") or {}).get("note"),
        "pages": len(v.snapshot.get("pages") or []),
        "widgets": sum(len(p.get("widgets") or [])
                       for p in (v.snapshot.get("pages") or [])),
    } for v, email in rows]


@router.post("/{report_id}/versions/{version_id}/restore")
async def restore_version(report_id: int, version_id: int,
                          db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Put the report's CONTENT back as it was at that version.

    Pages and widgets are recreated from the snapshot (new ids — pins and
    per-page role visibility that pointed at the old ones cascade away, and
    the response says so). Identity is untouched: name, owner, publish
    state and classification stay as they are, because going back to
    Tuesday's charts must not also rename or re-share the dashboard.

    The bump at the top captures the CURRENT state as its own version
    first, so a restore is always itself undoable."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    version = await db.get(ReportVersion, version_id)
    if version is None or version.report_id != report_id:
        raise HTTPException(404, "Version not found")

    saved = await _bump_revision(report_id, db, current_user)
    await db.flush()

    existing = (await db.execute(select(ReportPage).where(
        ReportPage.report_id == report_id))).scalars().all()
    for page in existing:
        await db.delete(page)
    await db.flush()

    snap = version.snapshot or {}
    for pdata in snap.get("pages") or []:
        page = ReportPage(report_id=report_id,
                          name=pdata.get("name") or "Page 1",
                          title=pdata.get("title"),
                          page_type=pdata.get("page_type") or "normal",
                          prompt_column=pdata.get("prompt_column"),
                          prompt_label=pdata.get("prompt_label"),
                          position=pdata.get("position") or 0,
                          page_size=pdata.get("page_size") or "16:9",
                          custom_width=pdata.get("custom_width"),
                          custom_height=pdata.get("custom_height"),
                          mobile_layout=pdata.get("mobile_layout"),
                          layout_mode=pdata.get("layout_mode"),
                          layout_template=pdata.get("layout_template"))
        db.add(page)
        await db.flush()
        for wdata in pdata.get("widgets") or []:
            db.add(ReportWidget(page_id=page.id,
                                widget_type=wdata.get("widget_type") or "text",
                                title=wdata.get("title"),
                                config=wdata.get("config") or {},
                                layout=wdata.get("layout") or {"x": 0, "y": 0, "w": 6, "h": 4}))
    rep_content = snap.get("report") or {}
    if rep_content.get("theme") is not None:
        report.theme = rep_content["theme"]
    if rep_content.get("display_rules") is not None:
        report.display_rules = rep_content["display_rules"]
    await audit(db, current_user, "report.restore_version", "report",
                report_id, f"restored to revision {version.revision}")
    await db.commit()
    return {"restored_version_id": version_id,
            "restored_revision": version.revision,
            # The state this restore replaced, itself restorable -- what a redo
            # of an undone copilot change goes back to.
            "saved_current_as_version_id": saved.id if saved is not None else None,
            "note": "Pins and page-role visibility that pointed at the "
                    "replaced widgets were removed with them."}


# ── Bookmarks ─────────────────────────────────────────────────────────────────

@router.get("/{report_id}/bookmarks", response_model=list[BookmarkOut])
async def list_bookmarks(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    result = await db.execute(select(Bookmark).where(Bookmark.report_id == report_id).order_by(Bookmark.position))
    return result.scalars().all()


@router.post("/{report_id}/bookmarks", response_model=BookmarkOut)
async def create_bookmark(report_id: int, body: BookmarkCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    bm = Bookmark(report_id=report_id, **body.model_dump())
    db.add(bm)
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    await db.refresh(bm)
    return bm


@router.delete("/{report_id}/bookmarks/{bookmark_id}", status_code=204)
async def delete_bookmark(report_id: int, bookmark_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    result = await db.execute(select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.report_id == report_id))
    bm = result.scalar_one_or_none()
    if not bm:
        raise HTTPException(404, "Bookmark not found")
    await db.delete(bm)
    await _bump_revision(report_id, db, current_user)
    await db.commit()


# ── Org themes ────────────────────────────────────────────────────────────────
_HEX = __import__("re").compile(r"^#[0-9a-fA-F]{6}$")


@router.get("/themes/custom")
async def list_org_themes(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(OrgTheme).where(OrgTheme.org_id == current_user.org_id).order_by(OrgTheme.name)
    )).scalars().all()
    return [{"id": t.id, "name": t.name, "colors": t.colors} for t in rows]


@router.post("/themes/custom", status_code=201)
async def create_org_theme(body: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Save a custom palette for the org.

    Colours are validated as #rrggbb: they reach SVG fill attributes on every chart,
    and a palette of garbage renders everything black -- rejecting early beats
    debugging that.
    """
    name = str(body.get("name") or "").strip()[:100]
    colors = body.get("colors") or []
    if not name:
        raise HTTPException(400, "A theme needs a name")
    if not (isinstance(colors, list) and 2 <= len(colors) <= 20 and all(
            isinstance(c, str) and _HEX.match(c) for c in colors)):
        raise HTTPException(400, "colors must be 2-20 #rrggbb strings")
    theme = OrgTheme(org_id=current_user.org_id, name=name, colors=colors)
    db.add(theme)
    await db.commit()
    return {"id": theme.id, "name": theme.name, "colors": theme.colors}


@router.delete("/themes/custom/{theme_id}", status_code=204)
async def delete_org_theme(theme_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    theme = await db.get(OrgTheme, theme_id)
    check_org(theme, current_user, "Theme not found")
    await db.delete(theme)
    await db.commit()


# ── Report parameters ─────────────────────────────────────────────────────────
_PARAM_NAME = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]{0,59}$")
# "expression" parameters carry a measure expression in default_value instead of a
# literal; the widget-data path computes their value over the whole source (immune to
# filters) at query time. See widget_data._apply_report_parameters.
_PARAM_TYPES = {"number", "text", "date", "expression"}


@router.get("/{report_id}/parameters")
async def list_parameters(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(ReportParameter).where(ReportParameter.report_id == report_id)
        .order_by(ReportParameter.position, ReportParameter.id)
    )).scalars().all()
    return [{"id": p.id, "name": p.name, "param_type": p.param_type, "label": p.label,
             "default_value": p.default_value, "options": p.options or []} for p in rows]


@router.put("/{report_id}/parameters")
async def save_parameters(report_id: int, body: list[dict], db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Replace the report's parameter definitions wholesale.

    Names are identifiers because they are referenced as @name inside expressions --
    a name with spaces or punctuation could never be referenced, so it is rejected at
    definition time rather than discovered at use time. Duplicate names are rejected
    for the same reason `resolve_roles` conflicts are: two definitions one reference
    cannot distinguish.
    """
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")

    seen = set()
    for i, d in enumerate(body):
        name = str(d.get("name") or "")
        if not _PARAM_NAME.match(name):
            raise HTTPException(400, f"Parameter name {name!r} must be an identifier")
        if name in seen:
            raise HTTPException(400, f"Duplicate parameter name {name!r}")
        seen.add(name)
        if d.get("param_type") not in _PARAM_TYPES:
            raise HTTPException(400, f"param_type must be one of {sorted(_PARAM_TYPES)}")

    existing = (await db.execute(
        select(ReportParameter).where(ReportParameter.report_id == report_id)
    )).scalars().all()
    for row in existing:
        await db.delete(row)
    for i, d in enumerate(body):
        db.add(ReportParameter(
            report_id=report_id, name=d["name"], param_type=d["param_type"],
            label=(d.get("label") or "")[:120] or None,
            default_value=(str(d["default_value"])[:500] if d.get("default_value") is not None else None),
            options=[str(o)[:200] for o in (d.get("options") or [])][:50],
            position=i,
        ))
    report.revision = (report.revision or 0) + 1
    await db.commit()
    return await list_parameters(report_id, db, current_user)


# ── Schedules & alerts ────────────────────────────────────────────────────────
from ..services.delivery import valid_recipients as _valid_recipients  # noqa: E402


async def _resolve_report_sections(db, report: Report, user: User,
                                   allowed_page_ids: set[int] | None = None,
                                   context_label: str | None = None) -> list[dict]:
    """Resolve every data widget on every page to its shaped result, applying
    row-level security as `user` (the caller for a download, the creator for a
    delivery). Shared by the PDF endpoint and scheduled PDF delivery so the two
    can never drift. Widgets that fail resolve are skipped, not fatal."""
    import asyncio

    from ..core.rls import expand_author_expressions, resolve_rls_expr
    from ..models.models import Dataset
    from ..services.pdf_export import _SKIP_TYPES
    from ..services.prep import prep_steps_of, resolve_join_frames
    from ..services.widget_data import get_widget_data

    pages = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.report_id == report.id).order_by(ReportPage.position)
    )).scalars().all()

    # Only the pages the caller may see (and chose): re-reading every page
    # here used to put role-restricted pages straight back into the PDF.
    sections: list[dict] = []
    for page in pages:
        if allowed_page_ids is not None and page.id not in allowed_page_ids:
            continue
        widgets: list[dict] = []
        for w in sorted(page.widgets, key=lambda x: ((x.layout or {}).get("y", 0), (x.layout or {}).get("x", 0))):
            if w.widget_type in _SKIP_TYPES or w.widget_type == "text":
                continue
            dataset_id = (w.config or {}).get("dataset_id") or report.dataset_id
            if not dataset_id:
                continue
            ds = await db.get(Dataset, dataset_id)
            if ds is None or ds.org_id != report.org_id or not ds.filename:
                continue
            try:
                steps = prep_steps_of(ds)
                aux = await resolve_join_frames(db, user, steps) if steps else {}
                rls = await resolve_rls_expr(db, user, ds.id)
                # Column security, as every other read path applies it: the
                # PDF computed widgets over columns the reader is denied.
                from ..core.rls import resolve_denied_columns as _denied
                denied = await _denied(db, user, ds.id)
                # Sensitivity redaction (Phase 7.3): personal-data columns of
                # Confidential+ data leave in no file.
                from ..services.sensitivity import redacted_columns
                denied = sorted(set(denied or []) | set(await redacted_columns(db, ds.id, context_label)))
                author_filter_expr, calc_cols, measure_defs = await expand_author_expressions(
                    db, user, ds.default_filter_expr, ds.calculated_columns, ds.measures,
                )
                result = await asyncio.to_thread(
                    get_widget_data,
                    ds.filename, dict(w.config or {}), widget_type=w.widget_type,
                    calculated_columns=calc_cols or None,
                    filter_expr=author_filter_expr or None,
                    rls_filter_expr=rls, use_cache=False, measures=measure_defs or None,
                    prep_steps=steps or None, prep_aux_frames=aux or None,
                    custom_functions=ds.custom_functions, drop_columns=denied or None,
                )
                widgets.append({"title": w.title or w.widget_type,
                                "widget_type": w.widget_type, "result": result})
            except Exception:  # noqa: BLE001 -- one broken widget must not sink the PDF
                continue
        sections.append({"page_name": page.name, "widgets": widgets})
    return sections


@router.get("/{report_id}/pdf")
async def export_report_pdf(report_id: int, paper: str = "A4", orientation: str = "landscape",
                            contents: bool = True, pages: str | None = None,
                            db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Download the report as a server-rendered PDF -- cover, table of contents,
    and every page's visuals drawn. Any viewer may export what they can see;
    row-level security is applied as the CALLER, so the PDF never contains rows
    the downloader could not view on screen."""
    import asyncio
    import io as _io

    from fastapi.responses import StreamingResponse

    from ..services.pdf_export import build_report_pdf

    report = await _get_report(report_id, db, current_user)
    # Honour page visibility: a viewer's PDF excludes pages hidden from their role.
    visible = await _visible_page_ids(db, report, current_user)

    if paper not in ("A4", "A3", "Letter"):
        raise HTTPException(400, "paper must be A4, A3 or Letter")
    if orientation not in ("landscape", "portrait"):
        raise HTTPException(400, "orientation must be landscape or portrait")
    if pages:
        # Chosen pages only; a page the caller cannot see stays out regardless.
        wanted = {int(p) for p in pages.split(",") if p.strip().isdigit()}
        visible = visible & wanted
    from .shared import download_gate
    label = await download_gate(db, current_user, report=report)
    sections = await _resolve_report_sections(db, report, current_user, allowed_page_ids=visible,
                                              context_label=label)
    classification = await _classification_of(report_id, db)
    pdf = await asyncio.to_thread(build_report_pdf, report.name, report.description, sections, classification,
                                  paper, orientation, contents)
    # `isalnum()` is True for Arabic, Hebrew and CJK letters, so a non-Latin
    # report name survived this filter and then hit the latin-1 encoding that
    # HTTP headers require -- a 500 on export for any such report. Two params,
    # per RFC 6266: an ASCII `filename` every client understands, and a
    # UTF-8 `filename*` that carries the real name for those that do.
    from urllib.parse import quote
    raw = (report.name or "report").strip()[:60] or "report"
    ascii_name = "".join(
        c for c in raw if (c.isalnum() and c.isascii()) or c in " _-").strip() or "report"
    disposition = (f'attachment; filename="{ascii_name}.pdf"; '
                   f"filename*=UTF-8''{quote(raw + '.pdf')}")
    return StreamingResponse(
        _io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": disposition})


@router.get("/{report_id}/package")
async def export_report_package(report_id: int, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """The report as ONE offline HTML file: visible pages, every widget's
    result frozen as the caller sees it, and an inline renderer.

    Resolved through the widget endpoint's own path (`_resolve_widget_data`),
    so row security, column security and parameters are exactly what the
    screen applies. A widget on a dataset whose exports are disabled is kept
    as a titled placeholder saying so -- withheld, never silently missing."""
    from fastapi.responses import Response
    from urllib.parse import quote

    from ..models.models import Dataset
    from ..schemas.schemas import WidgetDataRequest
    from ..services.report_package import build_package_html
    from .datasets import _dataset_has_security, _exports_disabled, _policy_dataset
    from .widget_data import _resolve_widget_data

    report = await _get_report(report_id, db, current_user)
    from ..services.sensitivity import redacted_columns
    from .shared import download_gate
    label = await download_gate(db, current_user, report=report)
    visible_ids = {p.id for p in report.pages}
    if not current_user.role.is_org_admin and visible_ids:
        rows = (await db.execute(
            select(PageRoleVisibility).where(PageRoleVisibility.page_id.in_(visible_ids)))).scalars().all()
        restricted: dict[int, set[int]] = {}
        for row in rows:
            restricted.setdefault(row.page_id, set()).add(row.role_id)
        visible_ids = {pid for pid in visible_ids if pid not in restricted or current_user.role_id in restricted[pid]}
    pages = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.report_id == report.id).order_by(ReportPage.position))).scalars().all()

    policy_cache: dict[int, bool] = {}
    out_pages = []
    for page in pages:
        if page.id not in visible_ids or (page.page_type or "normal") != "normal":
            continue
        widgets = []
        for w in sorted(page.widgets, key=lambda x: ((x.layout or {}).get("y", 0), (x.layout or {}).get("x", 0))):
            cfg = dict(w.config or {})
            entry = {"title": w.title, "widget_type": w.widget_type, "layout": w.layout or {}}
            if w.widget_type == "text":
                entry["content"] = cfg.get("content") or ""
                widgets.append(entry)
                continue
            if w.widget_type in ("button", "image", "shape", "slicer", "container", "web_content", "script"):
                continue
            ds_id = cfg.get("dataset_id") or report.dataset_id
            if not ds_id:
                continue
            if ds_id not in policy_cache:
                ds = await db.get(Dataset, ds_id)
                policy_cache[ds_id] = bool(ds is not None and _exports_disabled(
                    await _policy_dataset(db, ds), None, await _dataset_has_security(db, ds_id)))
            if policy_cache[ds_id]:
                entry["withheld"] = "Not included: exports are disabled for this widget's data."
                widgets.append(entry)
                continue
            try:
                entry["result"] = await _resolve_widget_data(
                    ds_id, WidgetDataRequest(config=cfg, widget_type=w.widget_type, report_id=report.id),
                    db, current_user, via_report_id=report.id,
                    redact_columns=await redacted_columns(db, int(ds_id), label))
            except Exception as e:  # noqa: BLE001 -- one widget must not sink the package
                entry["withheld"] = f"Not included: {getattr(e, 'detail', None) or 'this widget could not be resolved'}"
            widgets.append(entry)
        out_pages.append({"name": page.name, "widgets": widgets})

    doc = build_package_html({"name": report.name, "description": report.description,
                              "classification": await _classification_of(report_id, db),
                              "pages": out_pages}, exporter=current_user.email)
    raw = (report.name or "report").strip()[:60] or "report"
    ascii_name = "".join(c for c in raw if (c.isalnum() and c.isascii()) or c in " _-").strip() or "report"
    await audit(db, current_user, "report.package", "report", report.id, f"{len(out_pages)} pages")
    await db.commit()
    return Response(doc, media_type="text/html; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{ascii_name}.html"; filename*=UTF-8\'\'{quote(raw + ".html")}'})


@router.post("/{report_id}/suggest-widgets")
async def suggest_widgets(report_id: int, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Widget suggestions for THIS report: the insights engine's ranked
    findings over the report's dataset, each mapped to a one-click widget
    config, with findings about columns the report's name/description
    mentions boosted to the top -- the description says what the report is
    FOR, so it steers what gets suggested first."""
    import asyncio

    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from ..models.models import Dataset

    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not report.dataset_id:
        raise HTTPException(400, "Attach a dataset to this report first")
    ds = await db.get(Dataset, report.dataset_id)
    if ds is None or ds.org_id != report.org_id or not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Suggestions run over import-mode datasets")

    denied = await resolve_denied_columns(db, current_user, ds.id)
    rls_expr = await resolve_rls_expr(db, current_user, ds.id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}
    description = " ".join(x for x in [report.name, report.description] if x)

    # What the author marked not-to-be-volunteered. Resolved out here because
    # it is database work and `_run` below is a worker thread; `denied` is
    # passed so a column this role may not see cannot come back as a reason for
    # anything. Never fatal -- an eligibility lookup that fails means every
    # column stays eligible, which is what the platform did before the flag
    # existed.
    from ..services import knowledge as knowledge_service
    try:
        _know = await knowledge_service.for_dataset(db, ds, denied=set(denied))
        _ineligible = {n for n, c in _know.columns.items()
                       if not c.eligible_for_suggestion}
    except Exception:                                    # noqa: BLE001
        logger.warning("could not resolve suggestion eligibility for dataset %s",
                       ds.id, exc_info=True)
        _ineligible = set()

    def _run():
        from ..services.analytics import detect_types, load_file
        from ..services.insights import (effective_roles, generate_insights,
                                         suggest_widgets_from_findings)
        from ..services.widget_data import apply_calculated_columns, apply_rls_filter
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        type_map = detect_types(df)
        result = generate_insights(df, type_map, ds.column_meta or {})
        roles = effective_roles(type_map, ds.column_meta or {})
        return {"suggestions": suggest_widgets_from_findings(
            result["findings"], roles, description, ineligible=_ineligible)}

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


@router.post("/{report_id}/auto-compose")
async def auto_compose(report_id: int, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """Build a whole page from the insights engine, in one call.

    `suggest-widgets` (above) already returns ranked, runnable widget configs;
    what it does not do is place them, so acting on it meant adding widgets one
    at a time and sizing each by hand. This composes the page instead: summary
    KPIs, then the strongest findings as charts sized by rank, then supporting
    detail and the narrative.

    It reuses `suggest-widgets`' exact secured pipeline -- same RLS expression,
    same denied-column drop, same prep steps -- rather than loading the frame a
    second way. A second load path is a second chance to forget a security step.
    """
    import asyncio

    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from ..models.models import Dataset

    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not report.dataset_id:
        raise HTTPException(400, "Attach a dataset to this report first")
    ds = await db.get(Dataset, report.dataset_id)
    if ds is None or ds.org_id != report.org_id or not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Auto-compose runs over import-mode datasets")

    denied = await resolve_denied_columns(db, current_user, ds.id)
    rls_expr = await resolve_rls_expr(db, current_user, ds.id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}
    description = " ".join(x for x in [report.name, report.description] if x)

    # What the author marked not-to-be-volunteered. Resolved out here because
    # it is database work and `_run` below is a worker thread; `denied` is
    # passed so a column this role may not see cannot come back as a reason for
    # anything. Never fatal -- an eligibility lookup that fails means every
    # column stays eligible, which is what the platform did before the flag
    # existed.
    from ..services import knowledge as knowledge_service
    try:
        _know = await knowledge_service.for_dataset(db, ds, denied=set(denied))
        _ineligible = {n for n, c in _know.columns.items()
                       if not c.eligible_for_suggestion}
    except Exception:                                    # noqa: BLE001
        logger.warning("could not resolve suggestion eligibility for dataset %s",
                       ds.id, exc_info=True)
        _ineligible = set()

    def _run():
        from ..services.analytics import detect_types, load_file
        from ..services.insights import (effective_roles, generate_insights,
                                         suggest_widgets_from_findings)
        from ..services.report_composer import compose_page
        from ..services.widget_data import apply_calculated_columns, apply_rls_filter
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        type_map = detect_types(df)
        result = generate_insights(df, type_map, ds.column_meta or {})
        roles = effective_roles(type_map, ds.column_meta or {})
        suggestions = suggest_widgets_from_findings(
            result["findings"], roles, description, ineligible=_ineligible)
        return compose_page(result["findings"], suggestions,
                            result.get("narrative"), roles)

    try:
        page_spec = await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    if not page_spec["widgets"]:
        # Nothing worth charting is a real answer, not an error: a tiny or
        # uniform dataset genuinely has no findings, and an empty page would be
        # a worse response than saying so.
        raise HTTPException(400, "No findings strong enough to build a report from")

    # Appended after the existing pages, using the same order_by idiom the rest
    # of this router uses rather than importing `func` for one call.
    existing = await db.execute(
        select(ReportPage.position).where(ReportPage.report_id == report_id)
        .order_by(ReportPage.position.desc()).limit(1))
    next_pos = (existing.scalar() or 0) + 1

    page = ReportPage(report_id=report_id, name=page_spec["name"], position=next_pos)
    db.add(page)
    await db.flush()

    for w in page_spec["widgets"]:
        db.add(ReportWidget(page_id=page.id, widget_type=w["widget_type"],
                            title=w["title"], config=w["config"], layout=w["layout"]))
    await db.commit()

    return {"page_id": page.id, "name": page.name,
            "widget_count": len(page_spec["widgets"])}


@router.get("/{report_id}/schedules")
async def list_schedules(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(ReportSchedule).where(ReportSchedule.report_id == report_id)
    )).scalars().all()
    from ..services.refresh_scheduler import calendar_spec
    return [{"id": r.id, "interval_minutes": r.interval_minutes,
             "recipients": [x for x in (r.recipients or []) if isinstance(x, str)],
             "calendar": calendar_spec(r.recipients),
             "format": next((r["__format__"] for r in (r.recipients or []) if isinstance(r, dict) and r.get("__format__")), "xlsx"),
             "subject": r.subject, "last_run_at": r.last_run_at, "last_status": r.last_status,
             "timezone": r.timezone}
            for r in rows]


@router.post("/{report_id}/schedules", status_code=201)
async def create_schedule(report_id: int, body: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a recurring delivery. Runs AS THE CREATOR: the schedule's emails carry
    the creator's row-level slice, which is why the identity is recorded here and
    never substituted later."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")

    recipients = _valid_recipients(body.get("recipients"))
    if not recipients:
        raise HTTPException(400, "At least one valid recipient email is required")

    # Calendar semantics (daily/weekly/monthly at a UTC clock time) ride as a
    # reserved dict entry in the recipients JSON -- the table gains no column,
    # and valid_recipients()/delivery ignore non-string entries by contract.
    # interval_minutes is set to the period's bound so the scheduler's SQL scan
    # filter and the interval fallback both keep working.
    calendar = body.get("calendar")
    if calendar is not None:
        from ..services.refresh_scheduler import CALENDAR_INTERVAL_BOUNDS, _last_occurrence
        if not isinstance(calendar, dict) or calendar.get("kind") not in CALENDAR_INTERVAL_BOUNDS:
            raise HTTPException(400, "calendar.kind must be daily, weekly or monthly")
        spec = {"kind": calendar["kind"],
                "hour": int(calendar.get("hour", 9)), "minute": int(calendar.get("minute", 0))}
        if spec["kind"] == "weekly":
            spec["weekday"] = int(calendar.get("weekday", 0))
            if not 0 <= spec["weekday"] <= 6:
                raise HTTPException(400, "calendar.weekday must be 0 (Monday) to 6 (Sunday)")
        if spec["kind"] == "monthly":
            spec["monthday"] = int(calendar.get("monthday", 1))
            if not 1 <= spec["monthday"] <= 28:
                raise HTTPException(400, "calendar.monthday must be 1-28 (a day every month has)")
        if not (0 <= spec["hour"] <= 23 and 0 <= spec["minute"] <= 59):
            raise HTTPException(400, "calendar time must be a valid HH:MM")
        from datetime import datetime as _dt
        if _last_occurrence(spec, _dt.utcnow()) is None and spec["kind"] not in ("daily", "weekly", "monthly"):
            raise HTTPException(400, "calendar specification is not valid")
        interval = CALENDAR_INTERVAL_BOUNDS[spec["kind"]]
        recipients = [*recipients, {"__calendar__": spec}]
    else:
        interval = int(body.get("interval_minutes") or 0)
        if interval < 15:
            raise HTTPException(400, "interval_minutes must be at least 15")

    fmt = body.get("format")
    if fmt is not None:
        if fmt not in ("xlsx", "pdf"):
            raise HTTPException(400, "format must be 'xlsx' or 'pdf'")
        if fmt == "pdf":  # xlsx is the default; store only a real override
            recipients = [*recipients, {"__format__": "pdf"}]

    # T3: an IANA zone the scheduler interprets this schedule's calendar
    # hour/minute in (zoneinfo). Validated against the system tz database at
    # write time -- 422 on anything zoneinfo doesn't recognise -- rather than
    # at run time, where a typo would just silently fall back to a due-check
    # that never fires.
    tz_name = body.get("timezone") or None
    if tz_name is not None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, f"Unknown timezone: {tz_name!r}")

    sched = ReportSchedule(
        org_id=current_user.org_id, report_id=report_id, creator_user_id=current_user.id,
        interval_minutes=interval, recipients=recipients,
        subject=(body.get("subject") or "")[:200] or None,
        timezone=tz_name,
    )
    db.add(sched)
    await db.commit()
    from ..services.refresh_scheduler import calendar_spec
    return {"id": sched.id, "interval_minutes": sched.interval_minutes,
            "recipients": [x for x in (sched.recipients or []) if isinstance(x, str)],
            "calendar": calendar_spec(sched.recipients),
            "format": next((r["__format__"] for r in (sched.recipients or []) if isinstance(r, dict) and r.get("__format__")), "xlsx"),
            "timezone": sched.timezone}


#: A schedule created by `POST /reports/{id}/subscribe`. Stored as a reserved
#: entry in the recipients JSON, the same mechanism `__calendar__` and
#: `__format__` already use, so the table gains no column and the delivery path
#: is untouched -- a subscription IS a schedule, it simply has one recipient and
#: an owner who is not an author.
SUBSCRIPTION_MARKER = "__subscription__"


def _is_subscription(sched) -> bool:
    return any(isinstance(r, dict) and r.get(SUBSCRIPTION_MARKER)
               for r in (sched.recipients or []))


@router.get("/{report_id}/subscription")
async def get_my_subscription(report_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Whether the caller is subscribed to this report, and on what cadence."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "view")

    rows = (await db.execute(select(ReportSchedule).where(
        ReportSchedule.report_id == report_id,
        ReportSchedule.creator_user_id == current_user.id,
    ))).scalars().all()
    mine = next((r for r in rows if _is_subscription(r)), None)
    if mine is None:
        return {"subscribed": False}
    from ..services.refresh_scheduler import calendar_spec
    return {"subscribed": True, "id": mine.id,
            "calendar": calendar_spec(mine.recipients),
            "interval_minutes": mine.interval_minutes,
            "format": next((r["__format__"] for r in (mine.recipients or [])
                            if isinstance(r, dict) and r.get("__format__")), "xlsx"),
            "last_run_at": mine.last_run_at, "last_status": mine.last_status}


@router.post("/{report_id}/subscribe", status_code=201)
async def subscribe_to_report(report_id: int, body: dict | None = None,
                              db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Subscribe YOURSELF to a recurring copy of this report.

    Needs only `view`, unlike creating a schedule for other people, which needs
    `edit`. Signing yourself up for data you can already read grants nobody
    anything new; adding somebody else to a distribution list does.

    **Why this creates its own schedule rather than joining an existing one.**
    A schedule resolves row-level security AS ITS CREATOR (see ReportSchedule's
    docstring). Appending a subscriber to somebody else's schedule would email
    them the CREATOR's slice of the data -- silently, and possibly rows they are
    not allowed to see. Owning the schedule is what makes the delivered numbers
    the subscriber's own. The cost is one render per subscriber, which is the
    correct trade against sending the wrong data cheaply.
    """
    body = body or {}
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "view")

    if not (current_user.email or "").strip():
        raise HTTPException(400, "Your account has no email address to deliver to")

    existing = (await db.execute(select(ReportSchedule).where(
        ReportSchedule.report_id == report_id,
        ReportSchedule.creator_user_id == current_user.id,
    ))).scalars().all()
    already = next((r for r in existing if _is_subscription(r)), None)

    from ..services.refresh_scheduler import CALENDAR_INTERVAL_BOUNDS
    kind = (body.get("cadence") or "daily").lower()
    if kind not in CALENDAR_INTERVAL_BOUNDS:
        raise HTTPException(400,
                            f"cadence must be one of {sorted(CALENDAR_INTERVAL_BOUNDS)}")
    hour = int(body.get("hour", 8))
    minute = int(body.get("minute", 0))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(400, "hour must be 0-23 and minute 0-59")

    spec = {"kind": kind, "hour": hour, "minute": minute}
    if kind == "weekly":
        spec["weekday"] = int(body.get("weekday", 0))
        if not 0 <= spec["weekday"] <= 6:
            raise HTTPException(400, "weekday must be 0 (Monday) to 6 (Sunday)")
    if kind == "monthly":
        spec["monthday"] = int(body.get("monthday", 1))
        if not 1 <= spec["monthday"] <= 28:
            raise HTTPException(400, "monthday must be 1-28 (a day every month has)")

    fmt = (body.get("format") or "xlsx").lower()
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(400, "format must be 'xlsx' or 'pdf'")

    tz_name = body.get("timezone") or None
    if tz_name is not None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, f"Unknown timezone: {tz_name!r}")

    recipients = [current_user.email, {"__calendar__": spec},
                  {SUBSCRIPTION_MARKER: True}]
    if fmt == "pdf":
        recipients.append({"__format__": "pdf"})

    # Re-subscribing edits the existing one rather than stacking duplicates --
    # otherwise a double click would deliver the report twice, forever.
    if already is not None:
        already.recipients = recipients
        already.interval_minutes = CALENDAR_INTERVAL_BOUNDS[kind]
        already.timezone = tz_name
        sched = already
    else:
        sched = ReportSchedule(
            org_id=current_user.org_id, report_id=report_id,
            creator_user_id=current_user.id,
            interval_minutes=CALENDAR_INTERVAL_BOUNDS[kind],
            recipients=recipients,
            subject=f"{report.name}"[:200], timezone=tz_name,
        )
        db.add(sched)
    await audit(db, current_user, "report.subscribe", "report", report_id, kind)
    await db.commit()
    return {"subscribed": True, "id": sched.id, "calendar": spec, "format": fmt,
            "timezone": tz_name}


@router.delete("/{report_id}/subscribe", status_code=204)
async def unsubscribe_from_report(report_id: int, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Cancel your own subscription.

    Only ever removes a schedule this user created AND that was created by
    subscribing -- an author's distribution schedule is not something a
    subscriber can delete out from under them, even on a report they can see.
    """
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "view")

    rows = (await db.execute(select(ReportSchedule).where(
        ReportSchedule.report_id == report_id,
        ReportSchedule.creator_user_id == current_user.id,
    ))).scalars().all()
    mine = next((r for r in rows if _is_subscription(r)), None)
    if mine is None:
        raise HTTPException(404, "You are not subscribed to this report")
    await db.delete(mine)
    await audit(db, current_user, "report.unsubscribe", "report", report_id, None)
    await db.commit()


@router.delete("/{report_id}/schedules/{schedule_id}", status_code=204)
async def delete_schedule(report_id: int, schedule_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    sched = await db.get(ReportSchedule, schedule_id)
    check_org(sched, current_user, "Schedule not found")
    await require_capability(db, current_user, report_id, "edit")
    await db.delete(sched)
    await db.commit()


@router.post("/{report_id}/schedules/{schedule_id}/run-now")
async def run_schedule_now(report_id: int, schedule_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Trigger one delivery immediately -- how an author verifies the pipe before
    trusting the timer with it."""
    from ..services.delivery import run_schedule
    sched = await db.get(ReportSchedule, schedule_id)
    check_org(sched, current_user, "Schedule not found")
    await run_schedule(db, sched)
    return {"last_status": sched.last_status}


@router.get("/{report_id}/deliveries")
async def list_deliveries(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """T3: recent delivery attempts for this report's schedules -- status, time,
    duration, error. 404-never-403 org scoping via check_org, same as
    list_schedules (its nearest sibling): a viewer who can see the report can
    see whether its scheduled deliveries have been landing."""
    from ..models.models import Delivery
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(Delivery).where(Delivery.report_id == report_id)
        .order_by(Delivery.created_at.desc()).limit(50)
    )).scalars().all()
    return [{"id": d.id, "schedule_id": d.schedule_id, "kind": d.kind, "status": d.status,
             "error": d.error, "artifact_kind": d.artifact_kind, "duration_ms": d.duration_ms,
             "created_at": d.created_at}
            for d in rows]


# ── Page templates & import ───────────────────────────────────────────────────
from ..services.page_templates import (  # noqa: E402
    BUILTIN_TEMPLATES, rehydrate_page, resolve_index_refs, serialize_page,
)


async def _load_page(db, report_id: int, page_id: int, current_user: User) -> ReportPage:
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    page = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.id == page_id, ReportPage.report_id == report_id)
    )).scalar_one_or_none()
    if page is None:
        raise HTTPException(404, "Page not found")
    return page


@router.get("/templates/builtin")
async def list_builtin_templates(current_user: User = Depends(get_current_user)):
    return [{"key": k, "name": v["name"], "widgets": len(v["widgets"])}
            for k, v in BUILTIN_TEMPLATES.items()]


@router.get("/templates/page")
async def list_page_templates(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(PageTemplate).where(PageTemplate.org_id == current_user.org_id,
                                   PageTemplate.kind == "page")
        .order_by(PageTemplate.name)
    )).scalars().all()
    return [{"id": t.id, "name": t.name, "widgets": len((t.payload or {}).get("widgets") or [])}
            for t in rows]


@router.delete("/templates/page/{template_id}", status_code=204)
async def delete_page_template(template_id: int, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(get_current_user)):
    """Remove a saved page template.

    A template is a STAMP, not a link: pages already built from it are ordinary
    pages and are untouched. Without this a name typed wrong was permanent, in a
    list every author in the org sees.

    Declared above the parameterised page routes for the same reason
    `/templates/page` is: a literal segment after /{report_id} would be
    swallowed by the int route and 422.
    """
    tpl = await db.get(PageTemplate, template_id)
    check_org(tpl, current_user, "Template not found")
    await db.delete(tpl)
    await db.commit()


@router.post("/{report_id}/pages/{page_id}/save-as-template", status_code=201)
async def save_page_as_template(report_id: int, page_id: int, body: dict,
                                db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    page = await _load_page(db, report_id, page_id, current_user)
    name = str(body.get("name") or "").strip()[:120]
    if not name:
        raise HTTPException(400, "A template needs a name")
    tpl = PageTemplate(org_id=current_user.org_id, name=name, kind="page",
                       payload=serialize_page(page))
    db.add(tpl)
    await db.commit()
    return {"id": tpl.id, "name": tpl.name}


@router.post("/{report_id}/pages/from-template", status_code=201)
async def add_page_from_template(report_id: int, body: dict,
                                 db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Instantiate a page from a saved template, a built-in, or another report's page.

    All three are the same serialise/rehydrate pair; the import case serialises the
    source page on the fly with no stored template in between. Both ends are
    org-checked -- the source report must be the caller's as much as the target.
    """
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")

    if body.get("template_id") is not None:
        tpl = await db.get(PageTemplate, int(body["template_id"]))
        check_org(tpl, current_user, "Template not found")
        payload = tpl.payload
    elif body.get("builtin") is not None:
        payload = BUILTIN_TEMPLATES.get(str(body["builtin"]))
        if payload is None:
            raise HTTPException(404, "No such built-in template")
    elif body.get("source_report_id") is not None and body.get("source_page_id") is not None:
        source = await _load_page(db, int(body["source_report_id"]),
                                  int(body["source_page_id"]), current_user)
        payload = serialize_page(source)
    else:
        raise HTTPException(400, "Provide template_id, builtin, or source_report_id + source_page_id")

    position = len((await db.execute(
        select(ReportPage).where(ReportPage.report_id == report_id)
    )).scalars().all())
    page, created = rehydrate_page(payload, report_id, position, db)
    await db.flush()
    resolve_index_refs(created)
    report.revision = (report.revision or 0) + 1
    await db.commit()
    return {"page_id": page.id, "widgets": len(created)}


# ── Page visibility & roles ───────────────────────────────────────────────────
# Two path segments on purpose: the single-segment "/roles-lite" is swallowed by the
# earlier-registered "/{report_id}" route, which 422s trying to parse it as an int.
@router.get("/roles/lite")
async def list_roles_lite(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Role ids and names for the caller's org. Not admin-gated: the page-visibility
    control needs the list to offer, and role NAMES within one's own org are not a
    secret -- the admin surface (membership, permissions) stays admin-only."""
    rows = (await db.execute(
        select(Role).where(Role.org_id == current_user.org_id).order_by(Role.name)
    )).scalars().all()
    return [{"id": r.id, "name": r.name} for r in rows]


@router.get("/{report_id}/capabilities")
async def get_report_capabilities(report_id: int, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """The per-role capability map for a report. Admin-only: capability is a
    governance control, and a control any user can read the shape of (then
    infer they could set) is a step toward one they can flip."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not current_user.role.is_org_admin:
        raise HTTPException(403, "Only an organization admin can view report capabilities")
    from ..models.models import ReportCapability
    rows = (await db.execute(
        select(ReportCapability).where(ReportCapability.report_id == report_id)
    )).scalars().all()
    return {"levels": {r.role_id: r.level for r in rows}}


@router.put("/{report_id}/capabilities")
async def set_report_capabilities(report_id: int, body: dict, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Replace a report's per-role capability map. Each value is 'view', 'edit'
    or 'data'; a role omitted (or set to 'data') is unrestricted. Role ids are
    validated against the caller's org so a foreign role cannot be smuggled in,
    and an org-admin role is never restrictable -- admins are always 'data'."""
    from ..core.capability import LEVELS
    from ..models.models import ReportCapability
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    if not current_user.role.is_org_admin:
        raise HTTPException(403, "Only an organization admin can change report capabilities")
    levels = body.get("levels") or {}
    org_roles = {r.id: r for r in (await db.execute(
        select(Role).where(Role.org_id == current_user.org_id)
    )).scalars().all()}
    clean: dict[int, str] = {}
    for rid, lvl in levels.items():
        rid = int(rid)
        if rid not in org_roles:
            raise HTTPException(400, f"Unknown role id: {rid}")
        if lvl not in LEVELS:
            raise HTTPException(400, f"Level must be one of {list(LEVELS)}")
        if org_roles[rid].is_org_admin:
            continue  # admins are always 'data'; a stored restriction would be a lie
        if lvl != "data":  # 'data' is the default -- store only real restrictions
            clean[rid] = lvl
    existing = (await db.execute(
        select(ReportCapability).where(ReportCapability.report_id == report_id)
    )).scalars().all()
    for row in existing:
        await db.delete(row)
    for rid, lvl in clean.items():
        db.add(ReportCapability(report_id=report_id, role_id=rid, level=lvl))
    await audit(db, current_user, "report.capabilities", "report", report_id,
                "; ".join(f"role {rid}={lvl}" for rid, lvl in clean.items()) or "cleared")
    await db.commit()
    return {"levels": clean}


@router.get("/{report_id}/pages/{page_id}/visibility")
async def get_page_visibility(report_id: int, page_id: int,
                              db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _load_page(db, report_id, page_id, current_user)
    rows = (await db.execute(
        select(PageRoleVisibility).where(PageRoleVisibility.page_id == page_id)
    )).scalars().all()
    return {"role_ids": [r.role_id for r in rows]}


@router.put("/{report_id}/pages/{page_id}/visibility")
async def set_page_visibility(report_id: int, page_id: int, body: dict,
                              db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Replace the page's role restriction. An empty list clears it (everyone sees).
    Role ids are validated against the caller's org so a foreign role id cannot be
    smuggled into the restriction table."""
    await _load_page(db, report_id, page_id, current_user)
    role_ids = body.get("role_ids") or []
    if role_ids:
        org_roles = {r.id for r in (await db.execute(
            select(Role).where(Role.org_id == current_user.org_id)
        )).scalars().all()}
        bad = [r for r in role_ids if r not in org_roles]
        if bad:
            raise HTTPException(400, f"Unknown role ids: {bad}")
    existing = (await db.execute(
        select(PageRoleVisibility).where(PageRoleVisibility.page_id == page_id)
    )).scalars().all()
    for row in existing:
        await db.delete(row)
    for rid in role_ids:
        db.add(PageRoleVisibility(page_id=page_id, role_id=int(rid)))
    await _bump_revision(report_id, db, current_user)
    await db.commit()
    return {"role_ids": role_ids}


# ── Comments ──────────────────────────────────────────────────────────────────

from ..models.models import ReportComment  # noqa: E402


@router.get("/{report_id}/comments")
async def list_comments(report_id: int, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(ReportComment, User.email).join(User, User.id == ReportComment.user_id)
        .where(ReportComment.report_id == report_id)
        .order_by(ReportComment.created_at, ReportComment.id)
    )).all()
    return [{"id": c.id, "page_id": c.page_id, "text": c.text, "created_at": c.created_at,
             "author": email, "mine": c.user_id == current_user.id}
            for c, email in rows]


@router.post("/{report_id}/comments", status_code=201)
async def add_comment(report_id: int, body: dict, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "A comment needs text")
    page_id = body.get("page_id")
    if page_id is not None:
        page = await db.get(ReportPage, page_id)
        if page is None or page.report_id != report_id:
            raise HTTPException(400, "page_id does not belong to this report")
    comment = ReportComment(org_id=current_user.org_id, report_id=report_id,
                            page_id=page_id, user_id=current_user.id, text=text[:4000])
    db.add(comment)

    # Notify every prior participant except the author: the report has no owner
    # field, so the thread's participants are the audience.
    from ..services.notifications import notify
    prior = (await db.execute(
        select(ReportComment.user_id).where(ReportComment.report_id == report_id).distinct()
    )).scalars().all()
    for uid in set(prior) - {current_user.id}:
        await notify(db, current_user.org_id, uid, "comment",
                     f'{current_user.email} commented on "{report.name}": {text[:120]}',
                     f"/reports/{report_id}")
    await db.commit()
    return {"id": comment.id}


@router.delete("/{report_id}/comments/{comment_id}", status_code=204)
async def delete_comment(report_id: int, comment_id: int, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Own comments only, unless org admin -- deleting someone's words is a
    moderation act, not an editing convenience."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    comment = await db.get(ReportComment, comment_id)
    if comment is None or comment.report_id != report_id:
        raise HTTPException(404, "Comment not found")
    if comment.user_id != current_user.id and not current_user.role.is_org_admin:
        raise HTTPException(403, "You can only delete your own comments")
    await db.delete(comment)
    await db.commit()


# ── Share links (guest access) ────────────────────────────────────────────────

from ..models.models import ShareLink  # noqa: E402


async def _report_snapshot(report_id: int, db: AsyncSession) -> list[dict]:
    """The report's render-definition (pages + widgets) as of THIS instant, in
    the exact shape PageOut/WidgetOut -- the same models GET /reports/{id}
    serializes through -- produce. Reusing them (rather than hand-rolling a
    parallel dict shape) is what keeps a pinned snapshot from drifting out of
    sync with what an unpinned link, or the builder itself, would show.

    S3 snapshot edge case: each page dict also carries its
    PageRoleVisibility role-id list AT THIS INSTANT under "role_visibility".
    A pinned link's guest render (routers/shared.py `_visible_pages`) reads
    restriction from THIS frozen copy, never a live lookup -- because
    PageRoleVisibility cascade-deletes with its page, a live query for a
    page later deleted finds nothing and would silently treat it as
    unrestricted. Freezing it here is what keeps that impossible."""
    pages = (await db.execute(
        select(ReportPage).options(selectinload(ReportPage.widgets))
        .where(ReportPage.report_id == report_id).order_by(ReportPage.position)
    )).scalars().all()
    restricted = (await db.execute(
        select(PageRoleVisibility).where(
            PageRoleVisibility.page_id.in_([p.id for p in pages] or [0]))
    )).scalars().all()
    roles_by_page: dict[int, list[int]] = {}
    for r in restricted:
        roles_by_page.setdefault(r.page_id, []).append(r.role_id)
    out = []
    for p in pages:
        d = PageOut.model_validate(p).model_dump(mode="json")
        d["role_visibility"] = roles_by_page.get(p.id, [])
        out.append(d)
    return out


@router.post("/{report_id}/share-links", status_code=201)
async def create_share_link(report_id: int, body: dict, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Mint a guest link. The plaintext token is returned exactly ONCE; only its
    sha256 is stored. Anyone holding the URL sees the report as THIS user sees
    it -- stated in the response so the sharer decides with eyes open.

    `pinned` (default False, today's behaviour) freezes the report's LAYOUT --
    its pages and widget config -- at mint time; the underlying widget DATA
    still resolves live. See ShareLink.snapshot."""
    import hashlib
    import secrets
    from datetime import timedelta

    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    from ..services.sensitivity import rank as s_rank, report_effective
    label, reasons = await report_effective(db, report)
    if s_rank(label) >= s_rank("Restricted"):
        raise HTTPException(403, "This report is Restricted"
                            + (f" ({reasons[0]})" if reasons else "")
                            + "; it cannot be shared by link. Grant access to named people instead.")
    try:
        days = int(body.get("expires_days", 7))
    except (TypeError, ValueError):
        days = 7
    days = min(max(days, 1), 90)
    pinned = bool(body.get("pinned", False))

    token = secrets.token_urlsafe(32)
    link = ShareLink(org_id=current_user.org_id, report_id=report_id,
                     creator_user_id=current_user.id,
                     token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     expires_at=datetime.utcnow() + timedelta(days=days),
                     pinned=pinned,
                     snapshot=(await _report_snapshot(report_id, db)) if pinned else None)
    db.add(link)
    await audit(db, current_user, "report.share_link_created", "report", report_id, f"{days}d{' pinned' if pinned else ''}")
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "share_link.create", f"report:{report_id}",
                              f"{days}d{' pinned' if pinned else ''}")
    await db.commit()
    return {"id": link.id, "token": token, "expires_at": link.expires_at, "pinned": link.pinned,
            "note": "Anyone with this link sees the report with your data permissions."}


@router.get("/{report_id}/share-links")
async def list_share_links(report_id: int, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(ShareLink, User.email).join(User, User.id == ShareLink.creator_user_id)
        .where(ShareLink.report_id == report_id)
        .order_by(ShareLink.created_at.desc())
    )).all()
    from ..routers.shared import _expired

    # Access counts/last-access (S4): one aggregate query for every link on
    # this report, rather than N+1 per row.
    from ..models.models import ShareLinkAccess
    from sqlalchemy import func
    link_ids = [l.id for l, _ in rows]
    access_rows = (await db.execute(
        select(ShareLinkAccess.share_link_id, func.count(), func.max(ShareLinkAccess.ts))
        .where(ShareLinkAccess.share_link_id.in_(link_ids or [0]))
        .group_by(ShareLinkAccess.share_link_id)
    )).all()
    access_by_link = {lid: (count, last) for lid, count, last in access_rows}

    return [{"id": l.id, "creator": email, "created_at": l.created_at, "expires_at": l.expires_at,
             "active": l.revoked_at is None and not _expired(l.expires_at), "pinned": l.pinned,
             "access_count": access_by_link.get(l.id, (0, None))[0],
             "last_access_at": access_by_link.get(l.id, (0, None))[1]}
            for l, email in rows]


@router.delete("/{report_id}/share-links/{link_id}", status_code=204)
async def revoke_share_link(report_id: int, link_id: int, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """Revocation, not deletion: the row stays as the audit trail of what was
    exposed and when. Own links, or org admin."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    link = await db.get(ShareLink, link_id)
    if link is None or link.report_id != report_id:
        raise HTTPException(404, "Share link not found")
    if link.creator_user_id != current_user.id and not current_user.role.is_org_admin:
        raise HTTPException(403, "Only the link's creator or an admin can revoke it")
    link.revoked_at = datetime.utcnow()
    await audit(db, current_user, "report.share_link_revoked", "report", report_id, str(link_id))
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "share_link.revoke", f"report:{report_id}", str(link_id))
    await db.commit()


# ── Translations (localisation of report text) ────────────────────────────────

from ..models.models import ReportTranslation  # noqa: E402

_LOCALE = __import__("re").compile(r"^[a-z]{2}(-[A-Za-z]{2,8})?$")


@router.get("/{report_id}/translations")
async def list_translations(report_id: int, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    rows = (await db.execute(
        select(ReportTranslation).where(ReportTranslation.report_id == report_id)
    )).scalars().all()
    return {t.locale: t.payload for t in rows}


@router.put("/{report_id}/translations/{locale}")
async def save_translation(report_id: int, locale: str, payload: dict,
                           db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Replace one locale's overrides wholesale. Keys are 'w<widgetId>' (title)
    and 'c<widgetId>' (text-widget content); values are plain strings. An empty
    payload deletes the locale -- no override rows lingering as empty husks."""
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    await require_capability(db, current_user, report_id, "edit")
    if not _LOCALE.match(locale):
        raise HTTPException(400, "locale must look like 'ar' or 'pt-BR'")
    clean = {k: str(v)[:2000] for k, v in payload.items()
             if isinstance(k, str) and k[:1] in ("w", "c") and k[1:].isdigit() and str(v).strip()}
    row = (await db.execute(
        select(ReportTranslation).where(ReportTranslation.report_id == report_id,
                                        ReportTranslation.locale == locale)
    )).scalar_one_or_none()
    if not clean:
        if row:
            await db.delete(row)
        await db.commit()
        return {}
    if row:
        row.payload = clean
    else:
        db.add(ReportTranslation(report_id=report_id, locale=locale, payload=clean))
    await db.commit()
    return clean
