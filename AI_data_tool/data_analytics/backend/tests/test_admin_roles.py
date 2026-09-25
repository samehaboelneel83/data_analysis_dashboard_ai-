from sqlalchemy import select
from app.core.security import create_access_token, hash_password
from app.models.models import Role, User


async def test_list_roles_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    resp = await client.get("/api/v1/admin/roles", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert names == ["Admin"]  # only org A's auto-created Admin role, not org B's


async def test_create_role_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/roles", json={"name": "Regional Manager", "is_org_admin": False}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(Role).where(Role.id == resp.json()["id"]))
    role = result.scalar_one()
    assert role.org_id == two_orgs["a"]["org"].id
    assert role.is_org_admin is False


async def test_update_role_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    resp = await client.patch(
        f"/api/v1/admin/roles/{two_orgs['b']['role'].id}", json={"name": "Hacked"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_delete_role_with_assigned_users_is_rejected(client, db_session, two_orgs, auth_headers):
    # two_orgs["a"]["role"] already has two_orgs["a"]["user"] assigned to it.
    resp = await client.delete(f"/api/v1/admin/roles/{two_orgs['a']['role'].id}", headers=auth_headers["a"])

    assert resp.status_code == 400


async def test_delete_role_with_two_assigned_users_returns_400_not_500(client, db_session, two_orgs, auth_headers):
    # Regression test: scalar_one_or_none() raises MultipleResultsFound when 2+ rows
    # match, which previously crashed this endpoint with a 500 instead of a clean 400.
    role = Role(org_id=two_orgs["a"]["org"].id, name="Shared Role", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user1 = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="shared1@example.com", password_hash=hash_password("pw"))
    user2 = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="shared2@example.com", password_hash=hash_password("pw"))
    db_session.add(user1)
    db_session.add(user2)
    await db_session.commit()
    await db_session.refresh(role)

    resp = await client.delete(f"/api/v1/admin/roles/{role.id}", headers=auth_headers["a"])

    assert resp.status_code == 400
    result = await db_session.execute(select(Role).where(Role.id == role.id))
    assert result.scalar_one_or_none() is not None


async def test_non_admin_cannot_list_roles(client, db_session, two_orgs):
    non_admin_role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
    db_session.add(non_admin_role)
    await db_session.flush()
    non_admin_user = User(
        org_id=two_orgs["a"]["org"].id, role_id=non_admin_role.id,
        email="viewer@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(non_admin_user)
    await db_session.commit()
    await db_session.refresh(non_admin_user)
    headers = {"Authorization": f"Bearer {create_access_token(non_admin_user.id, non_admin_user.org_id)}"}

    resp = await client.get("/api/v1/admin/roles", headers=headers)

    assert resp.status_code == 403
