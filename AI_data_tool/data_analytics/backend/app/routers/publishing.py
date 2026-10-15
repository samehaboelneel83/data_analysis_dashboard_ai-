"""Publishing and sharing a dashboard, and the reader's portal
(docs/publishing/PLAN.md).

Nothing here is a second way to decide access: every route asks
`core.capability`, the one resolver the rest of the product uses. What this
module adds is what was missing AROUND that resolver --

  * sharing with a person, a role or a team, with an expiry and the two
    rights a level cannot express (download, share on);
  * a dashboard's publication details, archive and restore, going back to an
    earlier release, handing it to another owner, and approval where the
    organisation asks for one;
  * the portal: one light catalogue of what a person may open, their
    favourites, and what was delivered to them.

Access is refused as the rest of the product refuses it: 404 for what a
person may not know exists, 403 with the reason for what they may see but not
do. Every change of access or state is written to the audit log.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import (LEVELS, effective_capabilities, effective_capability, export_refusal,
                               grant_expired, rank, report_grants, require_capability)
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user, require_org_admin
from ..models.models import (Dataset, Delivery, OrgReviewSettings, OrgUnit, RecentView, Report, ReportFavorite,
                             ReportRelease, ReportSchedule, ReportUserGrant, Role, ShareLink, User)
from ..services.audit import record as audit

router = APIRouter(prefix="/reports", tags=["publishing"])
portal = APIRouter(prefix="/portal", tags=["portal"])

#: How many tags a dashboard carries, and how long one is.
MAX_TAGS, TAG_CHARS = 12, 30


def _is_admin(user: User) -> bool:
    return bool(user.role and user.role.is_org_admin)


def _owns(report: Report, user: User) -> bool:
    return _is_admin(user) or (report.created_by is not None and report.created_by == user.id)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


async def _report(db: AsyncSession, report_id: int, user: User) -> Report:
    """The dashboard, for someone who may at least open it. Anything else is
    404 -- never 403, which would confirm that the id exists (the discipline
    `reports.router` applies to every route under it)."""
    report = await db.get(Report, report_id)
    check_org(report, user, "Report not found")
    if await effective_capability(db, user, report_id) == "none":
        raise HTTPException(404, "Report not found")
    return report


# ── Sharing ──────────────────────────────────────────────────────────────────

class GrantIn(BaseModel):
    #: Exactly one of the three names who it is for.
    email: str | None = Field(default=None, max_length=255)
    role_id: int | None = None
    org_unit_id: int | None = None
    level: str = "view"
    expires_at: datetime | None = None
    can_export: bool = True
    can_share: bool = False
    #: Sent to the person (or the members of the role or team) with the notice.
    message: str | None = Field(default=None, max_length=300)


class GrantChange(BaseModel):
    level: str | None = None
    #: Sent as null to remove the expiry; left out to keep it.
    expires_at: datetime | None = None
    clear_expiry: bool = False
    can_export: bool | None = None
    can_share: bool | None = None


async def grant_rows(db: AsyncSession, report_id: int) -> list[dict]:
    """Every direct share of a dashboard, each with who it names."""
    rows = (await db.execute(
        select(ReportUserGrant, User.email, Role.name, OrgUnit.name)
        .outerjoin(User, User.id == ReportUserGrant.user_id)
        .outerjoin(Role, Role.id == ReportUserGrant.role_id)
        .outerjoin(OrgUnit, OrgUnit.id == ReportUserGrant.org_unit_id)
        .where(ReportUserGrant.report_id == report_id).order_by(ReportUserGrant.id))).all()
    out = []
    for g, email, role_name, unit_name in rows:
        kind = "user" if g.user_id is not None else "role" if g.role_id is not None else "team"
        out.append({"id": g.id, "kind": kind, "name": email or role_name or unit_name,
                    "user_id": g.user_id, "role_id": g.role_id, "org_unit_id": g.org_unit_id,
                    # Kept for clients written before a grant could name a role or a team.
                    "email": email, "level": g.level, "expires_at": _iso(g.expires_at),
                    "expired": grant_expired(g.expires_at), "can_export": bool(g.can_export),
                    "can_share": bool(g.can_share)})
    return out


async def _members_of(db: AsyncSession, org_id: int, grant: ReportUserGrant) -> list[int]:
    """Who a grant reaches now, for the notice (capped: a notice, not a broadcast)."""
    if grant.user_id is not None:
        return [grant.user_id]
    if grant.role_id is not None:
        q = select(User.id).where(User.org_id == org_id, User.role_id == grant.role_id, User.is_active.is_(True))
    else:
        from ..models.models import UserOrgUnit
        q = (select(User.id).join(UserOrgUnit, UserOrgUnit.user_id == User.id)
             .where(User.org_id == org_id, UserOrgUnit.org_unit_id == grant.org_unit_id, User.is_active.is_(True)))
    return list((await db.execute(q.limit(200))).scalars().all())


async def create_or_update_grant(db: AsyncSession, report: Report, actor: User, body: GrantIn) -> dict:
    """Share a dashboard. The author or an administrator may give any level
    to a person, a role or a team. Someone who holds a grant with "may share"
    may pass it on -- to people only, view only, never with more than they
    hold -- which is what stops sharing from becoming a way up."""
    owner = _owns(report, actor)
    mine = None if owner else (await report_grants(db, actor, [report.id])).get(report.id)
    if not owner and not (mine and mine.can_share):
        raise HTTPException(403, "Only the dashboard's owner, an administrator, or someone it was shared "
                                 "with the right to share it on can share it")
    if report.archived_at is not None:
        raise HTTPException(409, "This dashboard is archived. Restore it before sharing it.")
    named = [v for v in (body.email, body.role_id, body.org_unit_id) if v not in (None, "")]
    if len(named) != 1:
        raise HTTPException(400, "Name exactly one of: a person (email), a role, or a team")
    if body.level not in LEVELS:
        raise HTTPException(400, f"level must be one of {', '.join(LEVELS)}")
    if body.expires_at is not None and grant_expired(body.expires_at):
        raise HTTPException(400, "The expiry is in the past")
    if not owner:
        # Passing it on: people only, view only, and no more than is held.
        if body.email in (None, "") or body.level != "view" or body.can_share:
            raise HTTPException(403, "You can share this on with people, to view only")
        body.can_export = body.can_export and mine.can_export and (await export_refusal(db, actor, report)) is None
        if mine.expires_at is not None and (body.expires_at is None or body.expires_at > mine.expires_at):
            body.expires_at = mine.expires_at           # what was passed on ends with what was held
    where = [ReportUserGrant.report_id == report.id]
    subject = ""
    if body.email:
        email = body.email.strip().lower()
        who = (await db.execute(select(User).where(User.email == email, User.org_id == actor.org_id))).scalar_one_or_none()
        if who is None:
            raise HTTPException(404, "No user with that email in your organization")
        if report.created_by is not None and who.id == report.created_by:
            raise HTTPException(400, "That user is the dashboard's author")
        where.append(ReportUserGrant.user_id == who.id)
        keys, subject = {"user_id": who.id}, who.email
    elif body.role_id is not None:
        role = await db.get(Role, body.role_id)
        if role is None or role.org_id != actor.org_id:
            raise HTTPException(404, "No such role in your organization")
        where.append(ReportUserGrant.role_id == role.id)
        keys, subject = {"role_id": role.id}, f"role {role.name}"
    else:
        unit = await db.get(OrgUnit, body.org_unit_id)
        if unit is None or unit.org_id != actor.org_id:
            raise HTTPException(404, "No such team in your organization")
        where.append(ReportUserGrant.org_unit_id == unit.id)
        keys, subject = {"org_unit_id": unit.id}, f"team {unit.name}"
    grant = (await db.execute(select(ReportUserGrant).where(*where))).scalar_one_or_none()
    fresh = grant is None
    if fresh:
        grant = ReportUserGrant(report_id=report.id, created_by=actor.id, **keys)
        db.add(grant)
    elif not owner:
        raise HTTPException(409, "That person already has access; only the owner can change it")
    grant.level, grant.expires_at = body.level, body.expires_at
    grant.can_export, grant.can_share = bool(body.can_export), bool(body.can_share)
    await db.flush()
    rights = [body.level] + ([] if body.can_export else ["no downloads"]) + (["may share"] if body.can_share else []) \
        + ([f"until {body.expires_at.date().isoformat()}"] if body.expires_at else [])
    await audit(db, actor, "report.share", "report", report.id, f"{subject}: {', '.join(rights)}")
    if fresh:
        from ..services.notifications import notify
        note = f" — {body.message.strip()}" if body.message and body.message.strip() else ""
        for uid in await _members_of(db, actor.org_id, grant):
            if uid != actor.id:
                await notify(db, actor.org_id, uid, "share",
                             (f"{actor.email} shared the dashboard “{report.name}” with you{note}")[:500],
                             f"/reports/{report.id}")
    await db.commit()
    return next(r for r in await grant_rows(db, report.id) if r["id"] == grant.id)


@router.patch("/{report_id}/grants/{grant_id}")
async def change_grant(report_id: int, grant_id: int, body: GrantChange, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """Change what a share gives, or when it ends. Owner or administrator."""
    report = await _report(db, report_id, current_user)
    if not _owns(report, current_user):
        raise HTTPException(403, "Only the dashboard's owner or an administrator can change a share")
    grant = await db.get(ReportUserGrant, grant_id)
    if grant is None or grant.report_id != report_id:
        raise HTTPException(404, "Grant not found")
    if body.level is not None:
        if body.level not in LEVELS:
            raise HTTPException(400, f"level must be one of {', '.join(LEVELS)}")
        grant.level = body.level
    if body.clear_expiry:
        grant.expires_at = None
    elif body.expires_at is not None:
        grant.expires_at = body.expires_at
    if body.can_export is not None:
        grant.can_export = body.can_export
    if body.can_share is not None:
        grant.can_share = body.can_share
    await audit(db, current_user, "report.share_change", "report", report.id,
                f"grant:{grant_id}: {grant.level}, export {'yes' if grant.can_export else 'no'}, "
                f"share {'yes' if grant.can_share else 'no'}, until {_iso(grant.expires_at) or 'no end'}")
    await db.commit()
    return next(r for r in await grant_rows(db, report_id) if r["id"] == grant_id)


@router.get("/{report_id}/access")
async def my_access(report_id: int, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """What the person asking may do with this dashboard, action by action --
    what a screen shows or hides. The server decides each again when asked to
    do it; this is the answer in advance, not the enforcement."""
    report = await _report(db, report_id, current_user)
    level = await effective_capability(db, current_user, report_id)
    if level == "none":
        raise HTTPException(404, "Report not found")
    held = (await report_grants(db, current_user, [report_id])).get(report_id)
    owner = _owns(report, current_user)
    refusal = await export_refusal(db, current_user, report)
    return {"level": level, "view": True, "interact": True, "drill": True,
            "export": refusal is None, "export_refusal": refusal,
            "share": owner or bool(held and held.can_share), "edit": rank(level) >= rank("edit"),
            "publish": owner, "administer": owner, "is_owner": report.created_by == current_user.id,
            "via": "admin" if _is_admin(current_user) else "owner" if owner else (held.via if held else "published"),
            "expires_at": _iso(held.expires_at) if held and not owner else None}


# ── Publication ──────────────────────────────────────────────────────────────

class PublicationIn(BaseModel):
    category: str | None = Field(default=None, max_length=60)
    tags: list[str] | None = None
    viewers_may_export: bool | None = None


def _clean_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    for t in tags or []:
        t = " ".join(str(t).split())[:TAG_CHARS]
        if t and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:MAX_TAGS]


async def approval_required(db: AsyncSession, org_id: int) -> bool:
    row = (await db.execute(select(OrgReviewSettings).where(OrgReviewSettings.org_id == org_id))).scalar_one_or_none()
    return bool(row and row.require_approval)


async def approval_gate(db: AsyncSession, report: Report, user: User) -> None:
    """Where the organisation asks for approval, what goes out to readers must
    be the revision an administrator approved. An administrator publishing is
    their own approval. An edit after approval needs a new one."""
    if _is_admin(user) or not await approval_required(db, report.org_id):
        return
    if report.review_state == "approved" and report.review_revision == int(report.revision or 0):
        return
    why = ("it was changed after it was approved" if report.review_state == "approved"
           else "approval was refused" if report.review_state == "rejected"
           else "approval has been asked for and not given yet" if report.review_state == "requested"
           else "nobody has asked for approval yet")
    raise HTTPException(409, {"code": "approval_needed",
                              "message": f"Your organisation asks for an administrator's approval before a "
                                         f"dashboard goes out to its readers, and {why}. Ask for a review, "
                                         f"then publish once it is approved."})


def stamp_published(report: Report, user: User) -> None:
    report.published_at, report.published_by = datetime.now(timezone.utc), user.id


def publication_state(report: Report) -> str:
    return "archived" if report.archived_at is not None else "published" if report.published else "draft"


@router.get("/{report_id}/publication")
async def get_publication(report_id: int, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Where a dashboard stands: its state, who sent it out and when, what
    readers see against what is being edited, and what stopping it would stop."""
    report = await _report(db, report_id, current_user)
    await require_capability(db, current_user, report_id, "view")
    owner = _owns(report, current_user)
    names = dict((await db.execute(select(User.id, User.email).where(
        User.id.in_([i for i in (report.created_by, report.published_by, report.review_requested_by,
                                 report.review_decided_by) if i] or [0])))).all())
    from ..services.report_release import latest_release, summary
    release = await latest_release(db, report_id)
    out = {"state": publication_state(report), "category": report.category, "tags": report.tags or [],
           "owner": names.get(report.created_by), "published_at": _iso(report.published_at),
           "published_by": names.get(report.published_by), "updated_at": _iso(report.updated_at),
           "archived_at": _iso(report.archived_at), "viewers_may_export": bool(report.viewers_may_export),
           "release": summary(release),
           "review": {"required": await approval_required(db, report.org_id), "state": report.review_state,
                      "current": report.review_revision == int(report.revision or 0),
                      "note": report.review_note, "requested_by": names.get(report.review_requested_by),
                      "decided_by": names.get(report.review_decided_by)}}
    if rank(await effective_capability(db, current_user, report_id)) >= rank("edit"):
        out["unreleased_changes"] = release is not None and int(report.revision or 0) != int(release.revision)
    if owner:
        # What unpublishing or archiving would touch, counted so it can be said first.
        now = datetime.now(timezone.utc)
        out["depends"] = {
            "shares": int((await db.execute(select(func.count()).select_from(ReportUserGrant)
                                            .where(ReportUserGrant.report_id == report_id))).scalar() or 0),
            "links": int((await db.execute(select(func.count()).select_from(ShareLink).where(
                ShareLink.report_id == report_id, ShareLink.revoked_at.is_(None), ShareLink.expires_at > now))).scalar() or 0),
            "schedules": int((await db.execute(select(func.count()).select_from(ReportSchedule)
                                               .where(ReportSchedule.report_id == report_id))).scalar() or 0)}
    return out


@router.patch("/{report_id}/publication")
async def set_publication(report_id: int, body: PublicationIn, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    report = await _report(db, report_id, current_user)
    if not _owns(report, current_user):
        raise HTTPException(403, "Only the dashboard's owner or an administrator can change how it is published")
    said = []
    if "category" in body.model_fields_set:
        report.category = " ".join((body.category or "").split())[:60] or None
        said.append(f"category {report.category or 'none'}")
    if body.tags is not None:
        report.tags = _clean_tags(body.tags)
        said.append(f"tags {', '.join(report.tags) or 'none'}")
    if body.viewers_may_export is not None and bool(report.viewers_may_export) != body.viewers_may_export:
        report.viewers_may_export = body.viewers_may_export
        said.append(f"viewers may download: {'yes' if body.viewers_may_export else 'no'}")
    if said:
        await audit(db, current_user, "report.publication", "report", report.id, "; ".join(said))
    await db.commit()
    return {"category": report.category, "tags": report.tags or [], "viewers_may_export": bool(report.viewers_may_export)}


@router.post("/{report_id}/archive")
async def archive(report_id: int, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """Take a dashboard out of use without deleting it. Nobody but its owner
    and administrators can open it; its guest links answer "does not exist"
    and its scheduled deliveries stop with that reason. Its shares, links and
    schedules are KEPT, so restoring it brings them back as they were."""
    report = await _report(db, report_id, current_user)
    if not _owns(report, current_user):
        raise HTTPException(403, "Only the dashboard's owner or an administrator can archive it")
    if report.archived_at is None:
        report.archived_at = datetime.now(timezone.utc)
        await audit(db, current_user, "report.archive", "report", report.id, report.name)
        await db.commit()
    return {"state": publication_state(report), "archived_at": _iso(report.archived_at)}


@router.post("/{report_id}/restore")
async def restore(report_id: int, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    report = await _report(db, report_id, current_user)
    if not _owns(report, current_user):
        raise HTTPException(403, "Only the dashboard's owner or an administrator can restore it")
    if report.archived_at is not None:
        report.archived_at = None
        # F-04: back as a DRAFT. Readers who reached it only by publication do
        # not get it back until someone publishes it again (through the same
        # approval gate); named shares, links and schedules are kept as they
        # were. `published_at` stays, as history.
        was_published = bool(report.published)
        report.published = False
        await audit(db, current_user, "report.restore", "report", report.id,
                    f"{report.name} (restored as draft{'; was published' if was_published else ''})")
        await db.commit()
    return {"state": publication_state(report)}


@router.post("/{report_id}/releases/{release_id}/rollback", status_code=201)
async def rollback_release(report_id: int, release_id: int, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Put an earlier release back in front of readers. It is issued again as
    a NEW release (reason "rollback"), so the record of what was distributed
    and when stays whole. The draft being edited is not touched."""
    report = await _report(db, report_id, current_user)
    if not _owns(report, current_user):
        raise HTTPException(403, "Only the dashboard's owner or an administrator can go back to an earlier release")
    old = await db.get(ReportRelease, release_id)
    if old is None or old.report_id != report_id:
        raise HTTPException(404, "Release not found")
    row = ReportRelease(report_id=report_id, revision=old.revision, snapshot=old.snapshot, reason="rollback",
                        note=f"Back to the release of {old.released_at.date().isoformat() if old.released_at else 'earlier'}"[:500],
                        released_by=current_user.id)
    db.add(row)
    stamp_published(report, current_user)
    await audit(db, current_user, "report.rollback", "report", report.id, f"release:{release_id}")
    await db.commit()
    await db.refresh(row)
    from ..services.report_release import summary
    return {"release": summary(row), "unreleased_changes": int(report.revision or 0) != int(row.revision)}


class OwnerIn(BaseModel):
    email: str = Field(max_length=255)


@router.post("/{report_id}/owner")
async def transfer_owner(report_id: int, body: OwnerIn, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Hand a dashboard to another person in the organisation. The previous
    owner keeps an edit-level share (they are not locked out of what they
    built); a share the new owner already held is removed, being superseded."""
    report = await _report(db, report_id, current_user)
    if not _owns(report, current_user):
        raise HTTPException(403, "Only the dashboard's owner or an administrator can hand it over")
    who = (await db.execute(select(User).where(User.email == body.email.strip().lower(),
                                               User.org_id == current_user.org_id))).scalar_one_or_none()
    if who is None or not who.is_active:
        raise HTTPException(404, "No active user with that email in your organization")
    before = report.created_by
    if before == who.id:
        return {"owner": who.email}
    held = (await db.execute(select(ReportUserGrant).where(ReportUserGrant.report_id == report_id,
                                                           ReportUserGrant.user_id == who.id))).scalar_one_or_none()
    if held is not None:
        await db.delete(held)
    report.created_by = who.id
    if before is not None:
        kept = (await db.execute(select(ReportUserGrant).where(ReportUserGrant.report_id == report_id,
                                                               ReportUserGrant.user_id == before))).scalar_one_or_none()
        if kept is None:
            db.add(ReportUserGrant(report_id=report_id, user_id=before, level="edit", created_by=current_user.id))
    await audit(db, current_user, "report.owner", "report", report.id, f"to {who.email}")
    from ..services.notifications import notify
    await notify(db, current_user.org_id, who.id, "share",
                 f"{current_user.email} made you the owner of the dashboard “{report.name}”"[:500], f"/reports/{report.id}")
    await db.commit()
    return {"owner": who.email}


class ReviewIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/{report_id}/review/request")
async def request_review(report_id: int, body: ReviewIn | None = None, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Ask an administrator to approve this revision for publication."""
    report = await _report(db, report_id, current_user)
    await require_capability(db, current_user, report_id, "edit")
    report.review_state, report.review_revision = "requested", int(report.revision or 0)
    report.review_requested_by, report.review_decided_by = current_user.id, None
    report.review_note = (body.note if body else None) or None
    await audit(db, current_user, "report.review_request", "report", report.id, report.name)
    from ..services.notifications import notify
    admins = (await db.execute(select(User.id).join(Role, Role.id == User.role_id).where(
        User.org_id == current_user.org_id, Role.is_org_admin.is_(True), User.is_active.is_(True)).limit(50))).scalars().all()
    for uid in admins:
        if uid != current_user.id:
            await notify(db, current_user.org_id, uid, "review",
                         f"{current_user.email} asks for approval to publish “{report.name}”"[:500], f"/reports/{report.id}")
    await db.commit()
    return {"state": report.review_state, "revision": report.review_revision}


@router.post("/{report_id}/review/decision")
async def decide_review(report_id: int, body: DecisionIn, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_org_admin)):
    """Approve or refuse what was asked. The approval is of the revision that
    was asked about: if the dashboard has moved on since, it is refused here
    and has to be asked again."""
    report = await _report(db, report_id, current_user)
    if report.review_state != "requested":
        raise HTTPException(409, "No approval is being asked for on this dashboard")
    if body.approve and report.review_revision != int(report.revision or 0):
        raise HTTPException(409, "The dashboard was changed after approval was asked for. Ask its owner to request it again.")
    report.review_state = "approved" if body.approve else "rejected"
    report.review_decided_by, report.review_note = current_user.id, (body.note or None)
    await audit(db, current_user, "report.review_approve" if body.approve else "report.review_reject",
                "report", report.id, (body.note or report.name))
    if report.review_requested_by:
        from ..services.notifications import notify
        await notify(db, current_user.org_id, report.review_requested_by, "review",
                     (f"“{report.name}” was {'approved for publication' if body.approve else 'not approved'}"
                      + (f" — {body.note}" if body.note else ""))[:500], f"/reports/{report.id}")
    await db.commit()
    return {"state": report.review_state}


# ── The portal ───────────────────────────────────────────────────────────────

SECTIONS = ("all", "mine", "shared", "team", "favorites", "recent", "archived")


async def _catalogue(db: AsyncSession, user: User) -> list[dict]:
    """Every dashboard this person may open, as light rows -- no pages, no
    widgets. A fixed number of queries whatever the size of the catalogue."""
    rows = (await db.execute(
        select(Report.id, Report.name, Report.description, Report.category, Report.tags, Report.created_by,
               Report.published, Report.published_at, Report.updated_at, Report.archived_at, Report.origin,
               Report.viewers_may_export, User.email, Dataset.last_refreshed_at)
        .outerjoin(User, User.id == Report.created_by).outerjoin(Dataset, Dataset.id == Report.dataset_id)
        .where(Report.org_id == user.org_id))).all()
    ids = [r[0] for r in rows]
    caps = await effective_capabilities(db, user, ids)
    grants = await report_grants(db, user, ids)
    from ..core.capability import folder_granted_reports, team_shared_report_ids
    folder = {} if _is_admin(user) else await folder_granted_reports(db, user)
    team_shared = await team_shared_report_ids(db, user, ids)
    favorites = set((await db.execute(select(ReportFavorite.report_id).where(ReportFavorite.user_id == user.id))).scalars().all())
    recent = dict((await db.execute(select(RecentView.report_id, RecentView.viewed_at).where(RecentView.user_id == user.id))).all())
    out = []
    for (rid, name, desc, category, tags, created_by, published, published_at, updated_at, archived_at, origin,
         may_export, owner, refreshed) in rows:
        level = caps.get(rid, "none")
        if level == "none":
            continue
        mine = created_by is not None and created_by == user.id
        g = grants.get(rid)
        can_export = rank(level) >= rank("edit") or (bool(may_export) and (g is None or g.can_export))
        out.append({"id": rid, "name": name, "description": desc, "category": category, "tags": tags or [],
                    "owner": owner, "is_mine": mine, "level": level,
                    "state": "archived" if archived_at is not None else "published" if published else "draft",
                    "published_at": _iso(published_at), "updated_at": _iso(updated_at),
                    "data_as_of": _iso(refreshed), "favorite": rid in favorites, "last_viewed": _iso(recent.get(rid)),
                    "can_export": can_export,
                    # How it reached them: named on it, through their role or team, a shared folder, or published.
                    "via": "owner" if mine else (g.via if g else "folder" if rid in folder else "published"),
                    # Shared with one of their teams, whatever decided their rights (F-05).
                    "via_team": rid in team_shared})
    return out


def _in_section(row: dict, section: str) -> bool:
    if section == "archived":
        return row["state"] == "archived"
    if row["state"] == "archived":
        return False
    return {"all": True, "mine": row["is_mine"], "shared": row["via"] in ("user", "role", "folder"),
            "team": row["via"] == "team" or bool(row.get("via_team")), "favorites": row["favorite"],
            "recent": row["last_viewed"] is not None}.get(section, False)


@portal.get("/catalog")
async def catalog(section: str = "all", q: str | None = None, category: str | None = None, tag: str | None = None,
                  owner: str | None = None, limit: int = 24, offset: int = 0,
                  db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The reader's catalogue: only what they may open, in the section asked
    for, searched by name, description, category, tag and owner, one page at
    a time. `counts` is how many each section holds for this person."""
    if section not in SECTIONS:
        raise HTTPException(400, f"section must be one of {', '.join(SECTIONS)}")
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    rows = await _catalogue(db, current_user)
    counts = {s: sum(1 for r in rows if _in_section(r, s)) for s in SECTIONS}
    found = [r for r in rows if _in_section(r, section)]
    if q and q.strip():
        words = q.lower().split()
        def hay(r):
            return " ".join(str(v) for v in (r["name"], r["description"] or "", r["category"] or "",
                                             " ".join(r["tags"]), r["owner"] or "")).lower()
        found = [r for r in found if all(w in hay(r) for w in words)]
    if category:
        found = [r for r in found if (r["category"] or "").lower() == category.lower()]
    if tag:
        found = [r for r in found if tag.lower() in {t.lower() for t in r["tags"]}]
    if owner:
        found = [r for r in found if (r["owner"] or "").lower() == owner.lower()]
    key = (lambda r: r["last_viewed"] or "") if section == "recent" else (lambda r: r["published_at"] or r["updated_at"] or "")
    found.sort(key=key, reverse=True)
    return {"items": found[offset:offset + limit], "total": len(found), "limit": limit, "offset": offset,
            "counts": counts}


@portal.get("/facets")
async def facets(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The categories, tags and owners that exist among what this person may
    open -- so a filter never offers a value that would reveal something else."""
    rows = [r for r in await _catalogue(db, current_user) if r["state"] != "archived"]
    def top(values):
        seen: dict[str, int] = {}
        for v in values:
            if v:
                seen[v] = seen.get(v, 0) + 1
        return [{"value": k, "count": n} for k, n in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:100]]
    return {"categories": top(r["category"] for r in rows), "tags": top(t for r in rows for t in r["tags"]),
            "owners": top(r["owner"] for r in rows)}


@portal.put("/favorites/{report_id}", status_code=204)
async def add_favorite(report_id: int, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    await require_capability(db, current_user, report_id, "view")        # 404 for what they may not open
    exists = (await db.execute(select(ReportFavorite.id).where(ReportFavorite.user_id == current_user.id,
                                                               ReportFavorite.report_id == report_id))).scalar_one_or_none()
    if exists is None:
        db.add(ReportFavorite(user_id=current_user.id, report_id=report_id))
        await db.commit()


@portal.delete("/favorites/{report_id}", status_code=204)
async def remove_favorite(report_id: int, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    row = (await db.execute(select(ReportFavorite).where(ReportFavorite.user_id == current_user.id,
                                                         ReportFavorite.report_id == report_id))).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()


@portal.get("/deliveries")
async def my_deliveries(limit: int = 30, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """What was sent from the schedules this person set up, newest first:
    when, of which dashboard, whether it went, and why not when it did not.
    Only for dashboards they can still open."""
    limit = max(1, min(int(limit), 100))
    rows = (await db.execute(
        select(Delivery, ReportSchedule.report_id, Report.name)
        .join(ReportSchedule, ReportSchedule.id == Delivery.schedule_id)
        .join(Report, Report.id == ReportSchedule.report_id)
        .where(ReportSchedule.creator_user_id == current_user.id, Report.org_id == current_user.org_id)
        .order_by(Delivery.id.desc()).limit(limit))).all()
    caps = await effective_capabilities(db, current_user, list({r[1] for r in rows}))
    return [{"id": d.id, "report_id": rid, "report": name, "status": d.status, "at": _iso(d.created_at),
             "error": d.error, "format": d.artifact_kind}
            for d, rid, name in rows if caps.get(rid, "none") != "none"]
