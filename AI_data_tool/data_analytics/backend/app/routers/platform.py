"""Platform super-admin: manage organizations across the whole platform.

A tier above any single org's admin — gated by `require_super_admin` (the config email
allowlist). Creates organizations with their first admin, lists every org, and arranges
the org hierarchy. It does NOT relax per-org data isolation: setting a parent is
structural metadata, not a grant of a child's data to the parent's users.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta

from ..core.database import get_db
from ..dependencies import require_super_admin
from ..models.models import AgentRun, Dataset, Organization, OrgParent, QueryRun, Quota, User
from ..services.audit import record as audit
from ..services.auth_provisioning import create_organization_with_admin
from ..services import org_access, quotas

router = APIRouter(prefix="/platform", tags=["platform"])


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=255)
    admin_password: str = Field(min_length=1)


@router.post("/organizations", status_code=201)
async def create_org(body: OrgCreate, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(require_super_admin)):
    """Provision a whole organization plus its first admin user in one call."""
    email = body.admin_email.strip()
    if "@" not in email:
        raise HTTPException(400, "admin_email must be an email address")
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none() is not None:
        raise HTTPException(400, "That admin email is already in use")
    org, role, admin = await create_organization_with_admin(db, body.name.strip(), email, body.admin_password)
    await audit(db, current_user, "platform.create_org", "organization", None, body.name.strip())
    await db.commit()
    return {"org_id": org.id, "name": org.name, "admin_user_id": admin.id, "admin_email": admin.email}


async def _parent_map(db: AsyncSession) -> dict[int, int]:
    rows = (await db.execute(select(OrgParent))).scalars().all()
    return {r.org_id: r.parent_org_id for r in rows}


def _midnight_utc() -> datetime:
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/organizations")
async def list_orgs(db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_super_admin)):
    """Every organization on the platform, with member counts, its parent,
    and (Task E2) its quota config alongside today's usage against it --
    three grouped aggregates, not N per-org queries, so this stays one
    round trip regardless of how many orgs exist."""
    orgs = (await db.execute(select(Organization).order_by(Organization.name))).scalars().all()
    counts = dict((await db.execute(
        select(User.org_id, func.count(User.id)).group_by(User.org_id))).all())
    parents = await _parent_map(db)
    mcp = await org_access.enabled_map(db)   # explicit rows only; missing = enabled

    quota_rows = (await db.execute(select(Quota))).scalars().all()
    quota_by_org = {q.org_id: q for q in quota_rows}

    midnight = _midnight_utc()
    queries_today = dict((await db.execute(
        select(QueryRun.org_id, func.count(QueryRun.id))
        .where(QueryRun.created_at >= midnight).group_by(QueryRun.org_id))).all())
    asks_today = dict((await db.execute(
        select(AgentRun.org_id, func.count(AgentRun.id))
        .where(AgentRun.created_at >= midnight).group_by(AgentRun.org_id))).all())
    storage_bytes = dict((await db.execute(
        select(Dataset.org_id, func.coalesce(func.sum(Dataset.file_size), 0))
        .group_by(Dataset.org_id))).all())

    def _quota_out(o_id: int) -> dict:
        q = quota_by_org.get(o_id)
        return {
            "max_queries_per_day": q.max_queries_per_day if q else None,
            "max_agent_asks_per_day": q.max_agent_asks_per_day if q else None,
            "max_storage_mb": q.max_storage_mb if q else None,
            "max_concurrent_asks": q.max_concurrent_asks if q else None,
        }

    return [{"id": o.id, "name": o.name, "created_at": o.created_at,
             "user_count": counts.get(o.id, 0), "parent_org_id": parents.get(o.id),
             "mcp_enabled": mcp.get(o.id, True),
             "quota": _quota_out(o.id),
             "usage": {"queries_today": queries_today.get(o.id, 0),
                       "agent_asks_today": asks_today.get(o.id, 0),
                       "storage_bytes": int(storage_bytes.get(o.id, 0))}}
            for o in orgs]


class OrgQuotaSet(BaseModel):
    max_queries_per_day: int | None = None
    max_agent_asks_per_day: int | None = None
    max_storage_mb: int | None = None
    max_concurrent_asks: int | None = None


@router.put("/organizations/{org_id}/quota")
async def set_org_quota(org_id: int, body: OrgQuotaSet, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_super_admin)):
    """Create or update the one Quota row for an org. Every field is
    nullable and null means unlimited, so a caller wanting to CLEAR a limit
    just omits it (Pydantic default None) or sends it explicitly as null --
    both look the same on this model, which is the desired byte-preserved
    "unlimited" behavior."""
    if await db.get(Organization, org_id) is None:
        raise HTTPException(404, "Organization not found")
    row = (await db.execute(select(Quota).where(Quota.org_id == org_id))).scalar_one_or_none()
    if row is None:
        row = Quota(org_id=org_id)
        db.add(row)
    row.max_queries_per_day = body.max_queries_per_day
    row.max_agent_asks_per_day = body.max_agent_asks_per_day
    row.max_storage_mb = body.max_storage_mb
    row.max_concurrent_asks = body.max_concurrent_asks
    await audit(db, current_user, "platform.set_org_quota", "organization", org_id,
               f"queries={body.max_queries_per_day} asks={body.max_agent_asks_per_day} "
               f"storage_mb={body.max_storage_mb} concurrent={body.max_concurrent_asks}")
    await db.commit()
    quotas.invalidate_quota_cache(org_id)
    return {"org_id": org_id, "max_queries_per_day": row.max_queries_per_day,
            "max_agent_asks_per_day": row.max_agent_asks_per_day,
            "max_storage_mb": row.max_storage_mb,
            "max_concurrent_asks": row.max_concurrent_asks}


@router.get("/organizations/tree")
async def org_tree(db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(require_super_admin)):
    """The organization hierarchy as nested nodes, rooted at the top-level orgs."""
    orgs = (await db.execute(select(Organization).order_by(Organization.name))).scalars().all()
    parents = await _parent_map(db)
    children: dict[int, list[int]] = {}
    for org_id, parent_id in parents.items():
        children.setdefault(parent_id, []).append(org_id)
    by_id = {o.id: o for o in orgs}

    def node(oid: int) -> dict:
        return {"id": oid, "name": by_id[oid].name if oid in by_id else "?",
                "children": [node(c) for c in sorted(children.get(oid, []))]}
    roots = [o.id for o in orgs if o.id not in parents]
    return [node(r) for r in roots]


class OrgMcpSet(BaseModel):
    enabled: bool


@router.put("/organizations/{org_id}/mcp")
async def set_org_mcp(org_id: int, body: OrgMcpSet, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_super_admin)):
    """Activate or deactivate MCP / machine (API-key) access for one org. Deactivating
    makes every one of that org's API keys stop authenticating immediately."""
    if await db.get(Organization, org_id) is None:
        raise HTTPException(404, "Organization not found")
    await org_access.set_mcp_enabled(db, org_id, body.enabled)
    await audit(db, current_user, "platform.set_org_mcp", "organization", org_id,
                "enabled" if body.enabled else "disabled")
    await db.commit()
    return {"org_id": org_id, "mcp_enabled": body.enabled}


class OrgParentSet(BaseModel):
    parent_org_id: int | None = None   # null clears the parent (make top-level)


@router.put("/organizations/{org_id}/parent")
async def set_org_parent(org_id: int, body: OrgParentSet, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_super_admin)):
    """Set (or clear, with null) an org's parent. Guards against a self-parent and any
    cycle — a parent may not be the org itself or one of its own descendants."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    parent_id = body.parent_org_id
    existing = (await db.execute(
        select(OrgParent).where(OrgParent.org_id == org_id))).scalar_one_or_none()

    if parent_id is None:
        if existing:
            await db.delete(existing)
        await audit(db, current_user, "platform.set_org_parent", "organization", org_id, "(root)")
        await db.commit()
        return {"org_id": org_id, "parent_org_id": None}

    if parent_id == org_id:
        raise HTTPException(400, "An organization cannot be its own parent")
    if await db.get(Organization, parent_id) is None:
        raise HTTPException(404, "Parent organization not found")
    # Walk UP from the proposed parent; reaching org_id would close a cycle.
    parents = await _parent_map(db)
    cursor, seen = parent_id, set()
    while cursor is not None and cursor not in seen:
        if cursor == org_id:
            raise HTTPException(400, "That parent would create a cycle in the hierarchy")
        seen.add(cursor)
        cursor = parents.get(cursor)

    if existing:
        existing.parent_org_id = parent_id
    else:
        db.add(OrgParent(org_id=org_id, parent_org_id=parent_id))
    await audit(db, current_user, "platform.set_org_parent", "organization", org_id, f"parent={parent_id}")
    await db.commit()
    return {"org_id": org_id, "parent_org_id": parent_id}
