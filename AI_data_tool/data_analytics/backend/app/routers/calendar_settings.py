"""The org's calendar: the month its fiscal year starts in (E10).

Read by anyone in the org (the widget panel shows it beside "Fiscal year"),
set by an org admin, audited. Charts grouped by fiscal year or quarter follow
the setting unless a widget names its own start month, so changing it moves
every such chart at once -- which is what an org that changes its fiscal year
wants.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..dependencies import get_current_user, require_org_admin
from ..models.models import Organization, User
from ..services.audit import record as audit

router = APIRouter(prefix="/calendar-settings", tags=["calendar-settings"])


def _out(org: Organization | None) -> dict:
    return {"fiscal_year_start_month": (org.fiscal_year_start_month if org else None) or 1}


@router.get("")
async def get_calendar_settings(db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    return _out(await db.get(Organization, current_user.org_id))


@router.put("")
async def set_calendar_settings(body: dict, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_org_admin)):
    month = body.get("fiscal_year_start_month")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise HTTPException(400, "The fiscal year's first month is a number from 1 (January) to 12 (December)")
    org = await db.get(Organization, current_user.org_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    before = org.fiscal_year_start_month or 1
    org.fiscal_year_start_month = month
    await audit(db, current_user, "calendar.fiscal_year", "organization", org.id,
                f"fiscal year starts in month {month} (was {before})")
    await db.commit()
    return _out(org)
