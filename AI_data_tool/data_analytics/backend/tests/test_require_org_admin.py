import pytest
from fastapi import HTTPException
from app.core.security import hash_password
from app.dependencies import require_org_admin
from app.models.models import Organization, Role, User


async def _seed_user(db_session, is_org_admin: bool) -> User:
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Some Role", is_org_admin=is_org_admin)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="u@acme.com", password_hash=hash_password("secret"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    user.role = role
    return user


async def test_require_org_admin_allows_org_admin(db_session):
    user = await _seed_user(db_session, is_org_admin=True)

    result = await require_org_admin(current_user=user)

    assert result is user


async def test_require_org_admin_rejects_non_admin(db_session):
    user = await _seed_user(db_session, is_org_admin=False)

    with pytest.raises(HTTPException) as exc_info:
        await require_org_admin(current_user=user)

    assert exc_info.value.status_code == 403
