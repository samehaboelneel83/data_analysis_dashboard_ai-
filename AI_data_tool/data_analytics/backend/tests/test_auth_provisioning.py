from sqlalchemy import select
from app.core.security import verify_password
from app.models.models import Organization, Role, User
from app.services.auth_provisioning import create_organization_with_admin


async def test_creates_org_admin_role_and_user(db_session):
    org, role, user = await create_organization_with_admin(
        db_session, "Acme Corp", "admin@acme.com", "supersecret"
    )
    await db_session.commit()

    assert org.name == "Acme Corp"
    assert role.name == "Admin"
    assert role.is_org_admin is True
    assert role.org_id == org.id
    assert user.email == "admin@acme.com"
    assert user.org_id == org.id
    assert user.role_id == role.id


async def test_password_is_hashed_not_stored_in_plaintext(db_session):
    _, _, user = await create_organization_with_admin(
        db_session, "Acme Corp", "admin@acme.com", "supersecret"
    )
    await db_session.commit()

    assert user.password_hash != "supersecret"
    assert verify_password("supersecret", user.password_hash) is True


async def test_created_rows_are_queryable_after_commit(db_session):
    await create_organization_with_admin(db_session, "Acme Corp", "admin@acme.com", "supersecret")
    await db_session.commit()

    org_result = await db_session.execute(select(Organization).where(Organization.name == "Acme Corp"))
    assert org_result.scalar_one() is not None
    role_result = await db_session.execute(select(Role).where(Role.name == "Admin"))
    assert role_result.scalar_one().is_org_admin is True
    user_result = await db_session.execute(select(User).where(User.email == "admin@acme.com"))
    assert user_result.scalar_one() is not None
