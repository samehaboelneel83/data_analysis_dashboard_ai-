from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.models import Organization, Role, User


async def test_creates_organization_role_and_user_with_relationships(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()

    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()

    user = User(org_id=org.id, role_id=role.id, email="admin@acme.com", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(
        select(User).options(selectinload(User.role), selectinload(User.organization)).where(User.id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.email == "admin@acme.com"
    assert fetched.is_active is True
    assert fetched.role.is_org_admin is True
    assert fetched.organization.name == "Acme Corp"


async def test_user_email_is_unique(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()

    db_session.add(User(org_id=org.id, role_id=role.id, email="dup@acme.com", password_hash="x"))
    await db_session.commit()

    db_session.add(User(org_id=org.id, role_id=role.id, email="dup@acme.com", password_hash="y"))
    with __import__("pytest").raises(Exception):
        await db_session.commit()


async def test_organization_roles_and_users_relationships(db_session):
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    db_session.add(User(org_id=org.id, role_id=role.id, email="a@acme.com", password_hash="x"))
    await db_session.commit()

    result = await db_session.execute(
        select(Organization).options(selectinload(Organization.roles), selectinload(Organization.users)).where(Organization.id == org.id)
    )
    fetched = result.scalar_one()
    assert len(fetched.roles) == 1
    assert len(fetched.users) == 1
