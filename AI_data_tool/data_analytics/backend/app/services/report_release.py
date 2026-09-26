"""Releases: what a report's viewers see while its editors change it (E09).

A report's pages and widgets are its DRAFT: every edit persists at once, with
no save button, which is right for the person building it and wrong for the
people reading it. A release is a frozen copy of the content. Once a report
has one:

- its **viewers** (capability 'view'), and the guest links and embeds that
  distribute it, are served the latest release;
- its **editors** work on the draft, see whether it has unreleased changes,
  and release it when it is ready. They can also look at the released
  version as its viewers do.

A report gets a release when an editor releases it, when it is published,
and -- so nothing changes for anyone on the day this ships -- the first time
a published report without one is edited: what its viewers were seeing
becomes its release, and the edit goes to the draft.

Access is never frozen. A release is served under the rules of now: the
viewer must still be able to open the report, a page restricted when it was
released stays restricted even if the draft has since deleted it (and its
restriction with it), and a restriction added since applies too. The data is
live and goes through row and column security as usual. The dataset rung
("a dashboard you can open") hands a viewer the datasets the RELEASE draws
on, not ones the draft has added since.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import (CommonFilter, PageRoleVisibility, Report, ReportPage,
                             ReportParameter, ReportRelease, ReportWidget)
from ..schemas.schemas import PageOut


async def content_snapshot(db: AsyncSession, report_id: int) -> tuple[dict, int] | None:
    """`(snapshot, revision)` of the report's content as last COMMITTED.

    Core selects with autoflush suspended, like `reports._capture_version`:
    this is called from inside a mutation that has already changed ORM
    objects, and a release taken on a report's first edit must be what its
    viewers were seeing, not the edit that is about to commit."""
    rep_t, page_t, widget_t = Report.__table__, ReportPage.__table__, ReportWidget.__table__
    vis_t, cf_t, par_t = PageRoleVisibility.__table__, CommonFilter.__table__, ReportParameter.__table__
    with db.sync_session.no_autoflush:
        rep = (await db.execute(
            select(rep_t.c.revision, rep_t.c.theme, rep_t.c.display_rules, rep_t.c.dataset_id,
                   rep_t.c.additional_dataset_ids).where(rep_t.c.id == report_id))).first()
        if rep is None:
            return None
        pages = (await db.execute(
            select(page_t).where(page_t.c.report_id == report_id)
            .order_by(page_t.c.position, page_t.c.id))).mappings().all()
        page_ids = [p["id"] for p in pages] or [0]
        widgets = (await db.execute(
            select(widget_t).where(widget_t.c.page_id.in_(page_ids))
            .order_by(widget_t.c.id))).mappings().all()
        restricted = (await db.execute(
            select(vis_t.c.page_id, vis_t.c.role_id).where(vis_t.c.page_id.in_(page_ids)))).all()
        filters = (await db.execute(
            select(cf_t).where(cf_t.c.report_id == report_id)
            .order_by(cf_t.c.position, cf_t.c.id))).mappings().all()
        params = (await db.execute(
            select(par_t).where(par_t.c.report_id == report_id)
            .order_by(par_t.c.position, par_t.c.id))).mappings().all()

    by_page: dict[int, list[dict]] = {}
    for w in widgets:
        by_page.setdefault(w["page_id"], []).append(dict(w))
    roles: dict[int, list[int]] = {}
    for page_id, role_id in restricted:
        roles.setdefault(page_id, []).append(role_id)
    out_pages = []
    for p in pages:
        d = PageOut.model_validate({**dict(p), "widgets": by_page.get(p["id"], [])}).model_dump(mode="json")
        d["role_visibility"] = sorted(roles.get(p["id"], []))
        out_pages.append(d)
    snapshot = {
        "report": {"theme": rep.theme, "display_rules": rep.display_rules or [],
                   "dataset_id": rep.dataset_id,
                   "additional_dataset_ids": list(rep.additional_dataset_ids or [])},
        "pages": out_pages,
        "common_filters": [{"id": f["id"], "column": f["column"], "op": f["op"], "value": f["value"]}
                           for f in filters],
        # Report parameters are content too: a chart that filters on @region
        # must be served the definition it was released with.
        "parameters": [{"id": x["id"], "name": x["name"], "param_type": x["param_type"],
                        "label": x["label"], "default_value": x["default_value"],
                        "options": list(x["options"] or [])} for x in params],
    }
    return snapshot, int(rep.revision or 0)


async def make_release(db: AsyncSession, report_id: int, user_id: int | None, *,
                       reason: str = "release", note: str | None = None) -> ReportRelease | None:
    """Freeze the report's committed content as its new release."""
    taken = await content_snapshot(db, report_id)
    if taken is None:
        return None
    snapshot, revision = taken
    row = ReportRelease(report_id=report_id, revision=revision, snapshot=snapshot,
                        note=(note or None) and note[:500], reason=reason, released_by=user_id)
    # Not flushed here: on a first edit the caller's own change is still in
    # flight, and a flush would write it before the version snapshot that
    # follows reads the committed "before".
    db.add(row)
    return row


async def latest_release(db: AsyncSession, report_id: int) -> ReportRelease | None:
    return (await db.execute(
        select(ReportRelease).where(ReportRelease.report_id == report_id)
        .order_by(ReportRelease.id.desc()).limit(1))).scalar_one_or_none()


async def latest_releases(db: AsyncSession, report_ids) -> dict[int, ReportRelease]:
    """The newest release of each of these reports that has one."""
    ids = [i for i in report_ids if i is not None]
    if not ids:
        return {}
    newest = (select(func.max(ReportRelease.id)).where(ReportRelease.report_id.in_(ids))
              .group_by(ReportRelease.report_id))
    rows = (await db.execute(select(ReportRelease).where(ReportRelease.id.in_(newest)))).scalars().all()
    return {r.report_id: r for r in rows}


async def has_release(db: AsyncSession, report_id: int) -> bool:
    return (await db.execute(
        select(ReportRelease.id).where(ReportRelease.report_id == report_id).limit(1))).first() is not None


def summary(release: ReportRelease | None) -> dict | None:
    if release is None:
        return None
    return {"id": release.id, "revision": release.revision, "reason": release.reason,
            "note": release.note, "released_by": release.released_by,
            "released_at": release.released_at.isoformat() if release.released_at else None}


def released_dataset_ids(snapshot: dict) -> set[int]:
    """Every dataset a release draws on: its primary, additional ids and each
    widget's own `config.dataset_id` -- what `report_dataset_ids` reads from
    the live rows."""
    from ..core.capability import _config_dataset_ids
    rep = (snapshot or {}).get("report") or {}
    out: set[int] = set()
    if isinstance(rep.get("dataset_id"), int):
        out.add(rep["dataset_id"])
    out.update(x for x in (rep.get("additional_dataset_ids") or []) if isinstance(x, int))
    for page in (snapshot or {}).get("pages") or []:
        for w in page.get("widgets") or []:
            out |= _config_dataset_ids(w.get("config"))
    return out


async def allowed_roles_by_page(db: AsyncSession, snapshot: dict) -> dict[int, set[int]]:
    """Which roles may see each restricted page of a release, under today's rules.

    A page restricted when it was released stays restricted: its current
    PageRoleVisibility rows may be gone with the page. A restriction added to
    the page since applies as well. Both apply, so a role must be allowed by
    each; an empty result means no role (an org admin still sees it).
    Pages absent from the mapping are unrestricted."""
    pages = (snapshot or {}).get("pages") or []
    ids = [p["id"] for p in pages] or [0]
    current: dict[int, set[int]] = {}
    for page_id, role_id in (await db.execute(
            select(PageRoleVisibility.page_id, PageRoleVisibility.role_id)
            .where(PageRoleVisibility.page_id.in_(ids)))).all():
        current.setdefault(page_id, set()).add(role_id)
    out: dict[int, set[int]] = {}
    for p in pages:
        frozen = set(p.get("role_visibility") or [])
        now = current.get(p["id"])
        if frozen and now is not None:
            out[p["id"]] = frozen & now
        elif frozen:
            out[p["id"]] = frozen
        elif now is not None:
            out[p["id"]] = now
    return out


async def visible_release_pages(db: AsyncSession, snapshot: dict, user) -> list[dict]:
    """The release's pages this user may see, in PageOut shape."""
    pages = (snapshot or {}).get("pages") or []
    if user.role and user.role.is_org_admin:
        return [{k: v for k, v in p.items() if k != "role_visibility"} for p in pages]
    allowed = await allowed_roles_by_page(db, snapshot)
    return [{k: v for k, v in p.items() if k != "role_visibility"} for p in pages
            if p["id"] not in allowed or user.role_id in allowed[p["id"]]]


async def served_release(db: AsyncSession, report_id: int, user) -> ReportRelease | None:
    """The release `user` is served, or None when they get the draft: a
    reader who holds only 'view' on a report that has a release."""
    from ..core.capability import effective_capability
    release = await latest_release(db, report_id)
    if release is None:
        return None
    return release if await effective_capability(db, user, report_id) == "view" else None


def page_objects(snapshot: dict) -> list:
    """A release's pages as objects shaped like ReportPage/ReportWidget rows,
    for the renderers (PDF, offline package, e-mailed digest) that walk them."""
    from types import SimpleNamespace
    out = []
    for p in (snapshot or {}).get("pages") or []:
        widgets = [SimpleNamespace(id=w["id"], page_id=p["id"], widget_type=w["widget_type"],
                                   title=w.get("title"), config=w.get("config") or {},
                                   layout=w.get("layout") or {})
                   for w in p.get("widgets") or []]
        out.append(SimpleNamespace(id=p["id"], name=p["name"], title=p.get("title"),
                                   page_type=p.get("page_type") or "normal",
                                   position=p.get("position", 0), widgets=widgets))
    return out


def primary_dataset_id(snapshot: dict):
    return ((snapshot or {}).get("report") or {}).get("dataset_id")


def find_widget(snapshot: dict, widget_id: int) -> tuple[dict, dict] | None:
    """`(page, widget)` of a widget id in a release, or None."""
    for page in (snapshot or {}).get("pages") or []:
        for w in page.get("widgets") or []:
            if w.get("id") == widget_id:
                return page, w
    return None
