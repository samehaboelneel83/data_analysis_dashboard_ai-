"""Pin any chart to a personal, live home dashboard.

The dashboard tile is a REFERENCE to a report widget, and everything else
follows from that one decision:

* **Live, not a snapshot.** The tile carries the widget's current config and
  the client re-queries widget-data as the VIEWER, through the same secured
  path the report itself uses -- same RLS, same column mask, same numbers.
  There is deliberately no new data endpoint here: a second render path would
  be a second place to forget a security step, which is how seven endpoints
  leaked column-secured data this same release.

* **Visibility is re-checked on every read, not once at pin time.** A page can
  be role-restricted AFTER someone pinned a chart from it, and a pin must not
  become a keyhole into a page the viewer has since lost. GET applies the
  exact rule `get_report` applies (PageRoleVisibility: no rows = everyone;
  rows = those roles plus org admins) and silently drops what fails it --
  the pin stays, dormant, and comes back if access returns.

* **Per user.** A home dashboard is the set of numbers one person checks
  daily; sharing a curated set is what reports are for.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import (Dataset, PageRoleVisibility, PinnedTile, Report,
                             ReportPage, ReportWidget, User)

router = APIRouter(prefix="/pins", tags=["pins"])


class PinCreate(BaseModel):
    """Either a widget pin ({widget_id}) or an insight pin
    ({dataset_id, finding_key}). Exactly one shape must be given."""
    widget_id: int | None = None
    dataset_id: int | None = None
    finding_key: str | None = None


class PinUpdate(BaseModel):
    position: int | None = None
    size: str | None = None


#: Discrete size tokens. No freeform sizes: the dashboard is a flow grid, and
#: three steps are what its columns divide into legibly.
SIZES = {"s", "m", "l"}


async def _next_position(db: AsyncSession, user_id: int) -> int:
    last = (await db.execute(
        select(PinnedTile.position).where(PinnedTile.user_id == user_id)
        .order_by(PinnedTile.position.desc().nulls_last()).limit(1)
    )).scalar()
    return (last or 0) + 1


async def _widget_chain(db: AsyncSession, widget_id: int):
    """widget -> page -> report, or (None, None, None)."""
    widget = await db.get(ReportWidget, widget_id)
    if widget is None:
        return None, None, None
    page = await db.get(ReportPage, widget.page_id)
    report = await db.get(Report, page.report_id) if page else None
    return widget, page, report


async def _page_visible(db: AsyncSession, user: User, page_id: int) -> bool:
    """The get_report rule, verbatim: no rows = everyone; rows = those roles,
    plus org admins (an admin locked out of a page could not administer the
    restriction that locked them out)."""
    if user.role.is_org_admin:
        return True
    rows = (await db.execute(
        select(PageRoleVisibility.role_id)
        .where(PageRoleVisibility.page_id == page_id))).scalars().all()
    return not rows or user.role_id in rows


@router.post("", status_code=201)
async def create_pin(body: PinCreate, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    # ── Insight pin: {dataset_id, finding_key} ────────────────────────────────
    if body.dataset_id is not None and body.finding_key:
        ds = await db.get(Dataset, body.dataset_id)
        check_org(ds, current_user, "Dataset not found")
        existing = (await db.execute(
            select(PinnedTile).where(PinnedTile.user_id == current_user.id,
                                     PinnedTile.dataset_id == ds.id,
                                     PinnedTile.finding_key == body.finding_key)
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "already_pinned": True}
        pin = PinnedTile(org_id=current_user.org_id, user_id=current_user.id,
                         dataset_id=ds.id, finding_key=body.finding_key,
                         position=await _next_position(db, current_user.id))
        db.add(pin)
        await db.commit()
        return {"id": pin.id, "already_pinned": False}

    # ── Widget pin: {widget_id} ───────────────────────────────────────────────
    if body.widget_id is None:
        raise HTTPException(400, "Give either widget_id or dataset_id + finding_key")
    widget, page, report = await _widget_chain(db, body.widget_id)
    # One 404 for every failure mode -- a cross-org id, a restricted page and a
    # genuinely absent widget must be indistinguishable, or the response length
    # itself confirms what exists.
    if widget is None or report is None:
        raise HTTPException(404, "Widget not found")
    check_org(report, current_user, "Widget not found")
    if not await _page_visible(db, current_user, page.id):
        raise HTTPException(404, "Widget not found")

    existing = (await db.execute(
        select(PinnedTile).where(PinnedTile.user_id == current_user.id,
                                 PinnedTile.widget_id == widget.id)
    )).scalar_one_or_none()
    if existing:
        # Pinning twice is a double-click, not an error.
        return {"id": existing.id, "widget_id": widget.id, "already_pinned": True}

    pin = PinnedTile(org_id=current_user.org_id, user_id=current_user.id,
                     widget_id=widget.id,
                     position=await _next_position(db, current_user.id))
    db.add(pin)
    await db.commit()
    return {"id": pin.id, "widget_id": widget.id, "already_pinned": False}


@router.patch("/{pin_id}")
async def update_pin(pin_id: int, body: PinUpdate,
                     db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """Layout only -- position and size. What a pin POINTS AT is immutable;
    repointing would silently swap a card's meaning under its position."""
    pin = await db.get(PinnedTile, pin_id)
    if pin is None or pin.user_id != current_user.id:
        raise HTTPException(404, "Pin not found")
    if body.size is not None:
        if body.size not in SIZES:
            raise HTTPException(400, f"size must be one of {sorted(SIZES)}")
        pin.size = body.size
    if body.position is not None:
        pin.position = body.position
    await db.commit()
    return {"id": pin.id, "position": pin.position, "size": pin.size}


@router.get("")
async def list_pins(db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    # LEFT joins, because insight pins have no widget chain -- an inner join
    # would silently drop every insight pin from the dashboard.
    rows = (await db.execute(
        select(PinnedTile, ReportWidget, ReportPage, Report)
        .join(ReportWidget, ReportWidget.id == PinnedTile.widget_id, isouter=True)
        .join(ReportPage, ReportPage.id == ReportWidget.page_id, isouter=True)
        .join(Report, Report.id == ReportPage.report_id, isouter=True)
        .where(PinnedTile.user_id == current_user.id,
               PinnedTile.org_id == current_user.org_id)
        # position first (dense, client-renumbered), id as the stable tiebreak;
        # legacy rows with NULL position sort last rather than first.
        .order_by(PinnedTile.position.asc().nulls_last(), PinnedTile.id)
    )).all()

    out = []
    for pin, widget, page, report in rows:
        base = {"id": pin.id, "position": pin.position, "size": pin.size,
                "created_at": pin.created_at}
        if pin.finding_key is not None:
            # Insight pin. check_org on every read, the same keyhole rule as
            # pages: a dataset moved out of reach must take its card with it
            # (dormant -- the pin survives for if access returns). The
            # finding's DATA is not served here at all; the card evaluates it
            # through the secured insights endpoint as the viewer.
            ds = await db.get(Dataset, pin.dataset_id)
            if ds is None or ds.org_id != current_user.org_id:
                continue
            out.append({**base, "pin_type": "insight",
                        "dataset_id": ds.id, "dataset_name": ds.name,
                        "finding_key": pin.finding_key})
            continue
        # Widget pin.
        if widget is None or page is None or report is None:
            continue
        if not await _page_visible(db, current_user, page.id):
            continue
        out.append({**base, "pin_type": "widget",
                    "widget_id": widget.id,
                    "widget_type": widget.widget_type,
                    "title": widget.title,
                    "config": widget.config or {},
                    "report_id": report.id,
                    "report_name": report.name,
                    "dataset_id": report.dataset_id,
                    "page_id": page.id})
    return {"pins": out}


@router.delete("/{pin_id}", status_code=204)
async def delete_pin(pin_id: int, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    pin = await db.get(PinnedTile, pin_id)
    # Own pins only, and the same single 404: someone else's pin id must read
    # exactly like a pin that never existed.
    if pin is None or pin.user_id != current_user.id:
        raise HTTPException(404, "Pin not found")
    await db.delete(pin)
    await db.commit()
