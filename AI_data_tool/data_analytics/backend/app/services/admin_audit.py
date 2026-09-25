"""Writing admin-plane security audit entries (S5).

One helper, called from the security-relevant mutation paths: row/column security
rules, share-link create/revoke, export policy, API keys. Same shape as
`services/audit.py` and deliberately separate from it -- this is the trail an
org's admins read on its own page to answer "what changed in the security
surface", not the general activity log.

Flush, not commit: the caller owns the transaction, so the entry lands if and
only if the action it records lands.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import AdminAudit, User


async def record(
    db: AsyncSession, actor: User, action: str,
    target: str | None = None, detail: str | None = None,
) -> None:
    db.add(AdminAudit(
        org_id=actor.org_id,
        actor_id=actor.id,
        actor_email=actor.email,
        action=action,
        target=target,
        # Hash-safe by construction -- callers pass a short summary, never a raw
        # secret. Truncated defensively so one runaway caller can't blow past the
        # column width or silently smuggle something large into the trail.
        detail=(detail or "")[:500] or None,
    ))
    await db.flush()
