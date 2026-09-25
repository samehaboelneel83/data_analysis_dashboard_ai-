from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password
from ..models.models import Organization, Role, User


async def create_organization_with_admin(
    db: AsyncSession, org_name: str, admin_email: str, admin_password: str,
) -> tuple[Organization, Role, User]:
    """Create a new Organization, its implicit Admin role (is_org_admin=True), and the
    first User in that org/role. Does not commit — caller controls the transaction."""
    org = Organization(name=org_name)
    db.add(org)
    await db.flush()

    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db.add(role)
    await db.flush()

    user = User(
        org_id=org.id,
        role_id=role.id,
        email=admin_email,
        password_hash=hash_password(admin_password),
    )
    db.add(user)
    await db.flush()

    return org, role, user
