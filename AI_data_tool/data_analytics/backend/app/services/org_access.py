"""Per-organization MCP / machine-access switch (see models.OrgMcpAccess).

A platform super-admin can disable MCP for an org; when disabled, that org's API keys
stop authenticating — which is exactly the credential the MCP server uses, so the whole
machine-access surface goes dark for that org in one switch. Absence of a row means
enabled (the default), so nothing has to be provisioned for MCP to keep working.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import OrgMcpAccess


async def mcp_enabled(db: AsyncSession, org_id: int) -> bool:
    row = (await db.execute(
        select(OrgMcpAccess).where(OrgMcpAccess.org_id == org_id))).scalar_one_or_none()
    return True if row is None else bool(row.enabled)


async def enabled_map(db: AsyncSession) -> dict[int, bool]:
    """org_id -> enabled for every org that has an explicit row (others default True)."""
    rows = (await db.execute(select(OrgMcpAccess))).scalars().all()
    return {r.org_id: bool(r.enabled) for r in rows}


async def set_mcp_enabled(db: AsyncSession, org_id: int, enabled: bool) -> None:
    row = (await db.execute(
        select(OrgMcpAccess).where(OrgMcpAccess.org_id == org_id))).scalar_one_or_none()
    if row is None:
        db.add(OrgMcpAccess(org_id=org_id, enabled=enabled))
    else:
        row.enabled = enabled
