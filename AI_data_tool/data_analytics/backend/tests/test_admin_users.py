from sqlalchemy import select
from app.models.models import User


async def test_list_users_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    resp = await client.get("/api/v1/admin/users", headers=auth_headers["a"])

    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert emails == ["admin-a@example.com"]


async def test_create_user_sets_org_id_and_hashes_password(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "new@example.com", "password": "s3cret-pass", "role_id": two_orgs["a"]["role"].id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(User).where(User.email == "new@example.com"))
    user = result.scalar_one()
    assert user.org_id == two_orgs["a"]["org"].id
    assert user.password_hash != "s3cret-pass"


async def test_create_user_with_role_from_another_org_returns_404(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "new2@example.com", "password": "s3cret-pass", "role_id": two_orgs["b"]["role"].id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_create_user_with_duplicate_email_returns_400(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "admin-a@example.com", "password": "s3cret-pass", "role_id": two_orgs["a"]["role"].id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_update_user_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    resp = await client.patch(
        f"/api/v1/admin/users/{two_orgs['b']['user'].id}", json={"is_active": False}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_delete_user_cannot_delete_self(client, db_session, two_orgs, auth_headers):
    resp = await client.delete(f"/api/v1/admin/users/{two_orgs['a']['user'].id}", headers=auth_headers["a"])

    assert resp.status_code == 400


async def test_update_user_with_duplicate_email_returns_400(client, db_session, two_orgs, auth_headers):
    # Create a second user in org A
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "second@example.com", "password": "s3cret-pass", "role_id": two_orgs["a"]["role"].id},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200
    second_user_id = resp.json()["id"]

    # Attempt to update second user's email to admin-a's email
    resp = await client.patch(
        f"/api/v1/admin/users/{second_user_id}",
        json={"email": "admin-a@example.com"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400
    # Verify the email was NOT changed in the DB
    result = await db_session.execute(select(User).where(User.id == second_user_id))
    user = result.scalar_one()
    assert user.email == "second@example.com"


# ── E-04: email format and password strength are checked server-side ────────

import pytest  # noqa: E402


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "two@@example.com", "sp ace@example.com", "@example.com"])
async def test_create_user_invalid_email_is_422(client, db_session, two_orgs, auth_headers, email):
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": email, "password": "long-enough-1", "role_id": two_orgs["a"]["role"].id})
    assert resp.status_code == 422, resp.text
    assert "email" in resp.json()["detail"].lower()
    assert (await db_session.execute(select(User).where(User.email == email.lower()))).first() is None


@pytest.mark.parametrize("password", ["x", "1234567", ""])
async def test_create_user_short_password_is_422(client, db_session, two_orgs, auth_headers, password):
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": "weak@example.com", "password": password, "role_id": two_orgs["a"]["role"].id})
    assert resp.status_code == 422, resp.text
    assert "8 characters" in resp.json()["detail"]
    assert (await db_session.execute(select(User).where(User.email == "weak@example.com"))).first() is None


async def test_create_user_password_equal_to_email_is_422(client, two_orgs, auth_headers):
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": "same@example.com", "password": "Same@Example.com", "role_id": two_orgs["a"]["role"].id})
    assert resp.status_code == 422


@pytest.mark.parametrize("email", ["qa.user@corp.local", "demo@example.invalid", "first.last+tag@sub.example.co"])
async def test_create_user_accepts_internal_and_test_domains(client, two_orgs, auth_headers, email):
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": email, "password": "long-enough-1", "role_id": two_orgs["a"]["role"].id})
    assert resp.status_code == 200, resp.text


async def test_update_user_checks_email_and_password_only_when_sent(client, db_session, two_orgs, auth_headers):
    created = (await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": "edit.me@example.com", "password": "long-enough-1",
        "role_id": two_orgs["a"]["role"].id})).json()
    url = f"/api/v1/admin/users/{created['id']}"
    assert (await client.patch(url, json={"email": "nope"}, headers=auth_headers["a"])).status_code == 422
    assert (await client.patch(url, json={"password": "short"}, headers=auth_headers["a"])).status_code == 422
    ok = await client.patch(url, json={"is_active": False}, headers=auth_headers["a"])
    assert ok.status_code == 200
    user = (await db_session.execute(select(User).where(User.id == created["id"]))).scalar_one()
    assert user.email == "edit.me@example.com"
