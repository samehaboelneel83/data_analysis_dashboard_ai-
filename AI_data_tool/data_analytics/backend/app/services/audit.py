"""Writing audit entries.

One helper, called from the mutation paths. Deliberately fire-and-forget in spirit but
synchronous in the transaction: the entry commits with the action it records, so the
log can never claim something happened that rolled back, and never miss something that
committed.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import AuditLogEntry, User


async def record(
    db: AsyncSession, user: User, action: str,
    entity: str | None = None, entity_id: int | None = None, detail: str | None = None,
) -> None:
    db.add(AuditLogEntry(
        org_id=user.org_id,
        user_id=user.id,
        user_email=user.email,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=(detail or "")[:500] or None,
    ))
    # Flush, not commit: the caller owns the transaction, so the entry lands if and
    # only if the action it records lands.
    await db.flush()
