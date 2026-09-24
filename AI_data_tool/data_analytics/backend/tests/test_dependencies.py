import pytest
from fastapi import HTTPException
from app.core.security import create_access_token, hash_password
from app.dependencies import get_current_user
from app.models.models import Organization, Role, User


async def _seed_user(db_session, is_active=True) -> User:
    org = Organization(name="Acme Corp")
    db_session.add(org)
    await db_session.flush()
    role = Role(org_id=org.id, name="Admin", is_org_admin=True)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="a@acme.com",
                password_hash=hash_password("secret"), is_active=is_active)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_valid_token_resolves_to_the_user_with_role_and_org_loaded(db_session):
    user = await _seed_user(db_session)
    token = create_access_token(user.id, user.org_id)

    resolved = await get_current_user(token=token, db=db_session)

    assert resolved.id == user.id
    assert resolved.role.is_org_admin is True
    assert resolved.organization.name == "Acme Corp"


async def test_garbage_token_raises_401(db_session):
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="not-a-real-token", db=db_session)
    assert exc_info.value.status_code == 401


async def test_token_for_a_deleted_user_raises_401(db_session):
    token = create_access_token(user_id=999999, org_id=1)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == 401


async def test_token_for_an_inactive_user_raises_401(db_session):
    user = await _seed_user(db_session, is_active=False)
    token = create_access_token(user.id, user.org_id)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, db=db_session)
    assert exc_info.value.status_code == 401
