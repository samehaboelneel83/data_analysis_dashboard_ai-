"""Bulk user provisioning: CSV-style import with partial success (enterprise admin)."""
import pytest


async def _role(client, headers, name):
    r = await client.post("/api/v1/admin/roles", json={"name": name, "is_org_admin": False}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_bulk_create_reports_per_row_and_creates_the_valid_ones(client, auth_headers):
    await _role(client, auth_headers["a"], "Analyst")
    body = {"users": [
        {"email": "u1@x.com", "password": "pw1-long-1", "role": "Analyst"},
        {"email": "u2@x.com", "password": "pw2-long-2", "role": "analyst"},   # role match is case-insensitive
        {"email": "bad-email", "password": "pw-long-12", "role": "Analyst"},    # invalid email
        {"email": "u3@x.com", "password": "pw-long-12", "role": "Ghost"},       # unknown role
        {"email": "u1@x.com", "password": "pw-long-12", "role": "Analyst"},     # duplicate within the upload
        {"email": "u4@x.com", "password": "", "role": "Analyst"},       # missing password
    ]}
    r = await client.post("/api/v1/admin/users/bulk", json=body, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["created_count"] == 2
    assert set(d["created"]) == {"u1@x.com", "u2@x.com"}
    assert {e["row"] for e in d["errors"]} == {3, 4, 5, 6}          # 1-based, spreadsheet-aligned
    # and the created users are real
    users = (await client.get("/api/v1/admin/users", headers=auth_headers["a"])).json()
    assert {"u1@x.com", "u2@x.com"} <= {u["email"] for u in users}


@pytest.mark.asyncio
async def test_a_bulk_created_user_can_log_in(client, auth_headers):
    await _role(client, auth_headers["a"], "Staff")
    await client.post("/api/v1/admin/users/bulk",
                      json={"users": [{"email": "loginme@x.com", "password": "s3cret-pass", "role": "Staff"}]},
                      headers=auth_headers["a"])
    r = await client.post("/api/v1/auth/login", json={"email": "loginme@x.com", "password": "s3cret-pass"})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_email_already_in_use_is_reported_not_fatal(client, auth_headers):
    rid = await _role(client, auth_headers["a"], "Team")
    await client.post("/api/v1/admin/users", json={"email": "taken@x.com", "password": "pw-long-12", "role_id": rid},
                      headers=auth_headers["a"])
    r = await client.post("/api/v1/admin/users/bulk",
                          json={"users": [
                              {"email": "taken@x.com", "password": "pw-long-12", "role": "Team"},
                              {"email": "fresh@x.com", "password": "pw-long-12", "role": "Team"},
                          ]}, headers=auth_headers["a"])
    d = r.json()
    assert d["created"] == ["fresh@x.com"]
    assert d["errors"][0]["email"] == "taken@x.com" and "already in use" in d["errors"][0]["error"]


@pytest.mark.asyncio
async def test_roles_resolve_within_the_admins_own_org(client, auth_headers):
    # Org A defines "Analyst"; org B's admin cannot resolve that name.
    await _role(client, auth_headers["a"], "Analyst")
    r = await client.post("/api/v1/admin/users/bulk",
                          json={"users": [{"email": "b1@x.com", "password": "pw-long-12", "role": "Analyst"}]},
                          headers=auth_headers["b"])
    d = r.json()
    assert d["created_count"] == 0
    assert "unknown role" in d["errors"][0]["error"]


@pytest.mark.asyncio
async def test_non_admin_is_forbidden(client, auth_headers, db_session, two_orgs):
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User
    role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    u = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="viewer@x.com", password_hash=hash_password("pw"))
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    hdr = {"Authorization": f"Bearer {create_access_token(u.id, u.org_id)}"}
    r = await client.post("/api/v1/admin/users/bulk",
                          json={"users": [{"email": "x@x.com", "password": "pw-long-12", "role": "Viewer"}]}, headers=hdr)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bulk_import_reports_short_password_row(client, auth_headers):
    """E-04: a too-short password is a per-row error, like a bad email."""
    await _role(client, auth_headers["a"], "Analyst")
    r = await client.post("/api/v1/admin/users/bulk", json={"users": [
        {"email": "short@x.com", "password": "x", "role": "Analyst"},
        {"email": "a@b", "password": "long-enough-1", "role": "Analyst"},
        {"email": "ok@x.com", "password": "long-enough-1", "role": "Analyst"},
    ]}, headers=auth_headers["a"])
    d = r.json()
    assert d["created"] == ["ok@x.com"]
    by_row = {e["row"]: e["error"] for e in d["errors"]}
    assert "8 characters" in by_row[1]
    assert by_row[2] == "invalid email"
