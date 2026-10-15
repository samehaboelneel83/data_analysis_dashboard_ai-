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


# ── E-15: role names are unique per organization ─────────────────────────────

import pytest  # noqa: E402


@pytest.mark.parametrize("second", ["QA E Role", "qa e role", "  QA E Role  "])
async def test_duplicate_role_name_is_409(client, db_session, two_orgs, auth_headers, second):
    first = await client.post("/api/v1/admin/roles", json={"name": "QA E Role"}, headers=auth_headers["a"])
    assert first.status_code == 200
    again = await client.post("/api/v1/admin/roles", json={"name": second}, headers=auth_headers["a"])
    assert again.status_code == 409, again.text
    assert again.json()["detail"] == "A role with this name already exists"
    names = [r["name"] for r in (await client.get("/api/v1/admin/roles", headers=auth_headers["a"])).json()]
    assert sum(n.strip().lower() == "qa e role" for n in names) == 1


async def test_rename_to_existing_name_is_409(client, db_session, two_orgs, auth_headers):
    await client.post("/api/v1/admin/roles", json={"name": "Analyst"}, headers=auth_headers["a"])
    other = (await client.post("/api/v1/admin/roles", json={"name": "Viewer"}, headers=auth_headers["a"])).json()
    r = await client.patch(f"/api/v1/admin/roles/{other['id']}", json={"name": "ANALYST"}, headers=auth_headers["a"])
    assert r.status_code == 409
    # Renaming a role to its own name in another case is fine.
    ok = await client.patch(f"/api/v1/admin/roles/{other['id']}", json={"name": "viewer"}, headers=auth_headers["a"])
    assert ok.status_code == 200 and ok.json()["name"] == "viewer"


async def test_same_name_in_other_org_is_ok(client, db_session, two_orgs, auth_headers):
    a = await client.post("/api/v1/admin/roles", json={"name": "Analyst"}, headers=auth_headers["a"])
    b = await client.post("/api/v1/admin/roles", json={"name": "Analyst"}, headers=auth_headers["b"])
    assert a.status_code == 200 and b.status_code == 200


@pytest.mark.parametrize("name", ["", "   "])
async def test_empty_role_name_is_422(client, db_session, two_orgs, auth_headers, name):
    r = await client.post("/api/v1/admin/roles", json={"name": name}, headers=auth_headers["a"])
    assert r.status_code == 422
    created = (await client.post("/api/v1/admin/roles", json={"name": "Keeper"}, headers=auth_headers["a"])).json()
    p = await client.patch(f"/api/v1/admin/roles/{created['id']}", json={"name": name}, headers=auth_headers["a"])
    assert p.status_code == 422


async def test_role_names_are_stored_trimmed(client, db_session, two_orgs, auth_headers):
    r = await client.post("/api/v1/admin/roles", json={"name": "  Finance  "}, headers=auth_headers["a"])
    assert r.json()["name"] == "Finance"
