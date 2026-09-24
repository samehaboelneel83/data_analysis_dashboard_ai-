"""Bootstrap script: create the first Organization and its admin User.

There is no self-service signup in this app (by design — see
docs/superpowers/specs/2026-08-13-row-level-security-design.md) — this script
is the only way to create an organization's first user.

Usage:
    python scripts/create_org_admin.py "Acme Corp" admin@acme.com supersecret
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.auth_provisioning import create_organization_with_admin  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python scripts/create_org_admin.py <org_name> <admin_email> <admin_password>")
        sys.exit(1)
    org_name, email, password = sys.argv[1], sys.argv[2], sys.argv[3]

    async with AsyncSessionLocal() as db:
        org, role, user = await create_organization_with_admin(db, org_name, email, password)
        await db.commit()

    print(f"Created organization '{org.name}' (id={org.id}) with admin user '{user.email}' (id={user.id}, role='{role.name}')")


if __name__ == "__main__":
    asyncio.run(main())
