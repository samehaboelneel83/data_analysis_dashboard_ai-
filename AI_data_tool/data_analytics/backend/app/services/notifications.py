"""In-app notifications: one row per event per user, capped per user.

`notify` is deliberately fire-and-forget-shaped but synchronous on the caller's
session: producers (the scheduler loop, alert evaluation, comments) already hold
a session and commit as part of their own unit of work, so notification writes
ride along instead of opening sessions of their own.
"""
from __future__ import annotations

from sqlalchemy import select

from ..models.models import Notification

# Oldest-read rows are trimmed past this so the table cannot grow unboundedly for
# a user who never opens the bell.
MAX_PER_USER = 200


async def notify(db, org_id: int, user_id: int, kind: str, text: str, link: str | None = None) -> None:
    db.add(Notification(org_id=org_id, user_id=user_id, kind=kind,
                        text=(text or "")[:500], link=(link or None)))
    rows = (await db.execute(
        select(Notification).where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(MAX_PER_USER)
    )).scalars().all()
    for r in rows:
        await db.delete(r)
