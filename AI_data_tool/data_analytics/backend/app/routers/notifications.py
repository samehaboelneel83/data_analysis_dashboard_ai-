"""The bell: a user's own notifications, newest first, with mark-read."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..dependencies import get_current_user
from ..models.models import Notification, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(limit: int = 30, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Notification).where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(min(max(limit, 1), 100))
    )).scalars().all()
    unread = sum(1 for r in rows if r.read_at is None)
    return {"unread": unread,
            "notifications": [{"id": r.id, "kind": r.kind, "text": r.text, "link": r.link,
                               "created_at": r.created_at, "read": r.read_at is not None}
                              for r in rows]}


@router.post("/mark-read")
async def mark_read(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Marks ALL of the caller's notifications read. Only ever the caller's own
    rows -- there is no cross-user surface here at all."""
    rows = (await db.execute(
        select(Notification).where(Notification.user_id == current_user.id,
                                   Notification.read_at.is_(None))
    )).scalars().all()
    for r in rows:
        r.read_at = datetime.utcnow()
    await db.commit()
    return {"marked": len(rows)}
