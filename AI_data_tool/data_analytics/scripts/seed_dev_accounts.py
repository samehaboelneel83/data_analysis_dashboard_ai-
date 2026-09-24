# -*- coding: utf-8 -*-
"""Seed the dev accounts the local stack was missing: a super admin, and two
extra orgs each with their own admin plus an ordinary user.

Idempotent by email: re-running updates nothing and creates nothing that already
exists, so it is safe to run twice.

The super-admin address is not arbitrary -- `is_super_admin` resolves purely from
the SUPER_ADMIN_EMAILS allowlist, which already contains admin@datalytics.local.
Creating any other address would produce an account that looks like a super admin
and is not one.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.models import Organization, Role, User  # noqa: E402

PASSWORD = "demo-password"

# (org name, [(email, role name, is_org_admin)])
PLAN = [
    # Super admin lands in the existing org: platform routes are gated on the
    # email allowlist, not on org membership, so a separate org would add
    # nothing and just make the account harder to find.
    (None, [("admin@datalytics.local", "Platform Admin", True)]),
    ("Contoso Ltd", [
        ("admin@contoso.invalid", "Admin", True),
        ("analyst@contoso.invalid", "Analyst", False),
    ]),
    ("Northwind Trading", [
        ("admin@northwind.invalid", "Admin", True),
        ("analyst@northwind.invalid", "Analyst", False),
    ]),
]


async def main() -> None:
    created, skipped = [], []
    async with AsyncSessionLocal() as s:
        default_org = (await s.execute(
            select(Organization).order_by(Organization.id))).scalars().first()

        for org_name, members in PLAN:
            if org_name is None:
                org = default_org
            else:
                org = (await s.execute(select(Organization).where(
                    Organization.name == org_name))).scalar_one_or_none()
                if org is None:
                    org = Organization(name=org_name)
                    s.add(org)
                    await s.flush()
                    created.append("org  %s" % org_name)
                else:
                    skipped.append("org  %s" % org_name)

            for email, role_name, is_admin in members:
                existing = (await s.execute(select(User).where(
                    User.email == email))).scalar_one_or_none()
                if existing is not None:
                    skipped.append("user %s" % email)
                    continue

                role = (await s.execute(select(Role).where(
                    Role.org_id == org.id, Role.name == role_name))).scalar_one_or_none()
                if role is None:
                    role = Role(org_id=org.id, name=role_name, is_org_admin=is_admin)
                    s.add(role)
                    await s.flush()

                s.add(User(org_id=org.id, role_id=role.id, email=email,
                           password_hash=hash_password(PASSWORD), is_active=True))
                created.append("user %s  (%s / %s)" % (email, org.name, role_name))
        await s.commit()

    for line in created:
        print("created  " + line)
    for line in skipped:
        print("exists   " + line)


asyncio.run(main())
