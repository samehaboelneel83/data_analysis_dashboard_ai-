"""Platform super-admins cannot be taken over by an org admin (TODO_PLAN E-01, E-02).

Who is a platform super-admin is decided by an email allowlist
(`settings.super_admin_emails`, compared case-insensitively by
`dependencies.is_super_admin`). Found in the QA of 2026-10-14 and reproduced
against the live API before this fix:

* E-01 -- an org admin of the org the super-admin lives in could PATCH or
  DELETE that account (change its role, email or password): a takeover of the
  whole platform. The user routes only checked "same org".
* E-02 -- user creation checked for duplicate emails CASE-SENSITIVELY, but the
  allowlist is matched case-insensitively. An org admin of ANY org could create
  `ADMIN@datalytics.local` in their own org, sign in with it and hold every
  /platform route. The same held for an allowlisted address no account had
  claimed yet (e.g. the compose default `admin@admin.com`).
* Same class -- an org admin configures their org's SSO provider, and the SSO
  callback signed in any active user of that org the provider named,
  including a platform admin.
"""
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.models import Role, User

PLATFORM = "platform@example.com"
UNCLAIMED = "unclaimed-platform@example.com"


@pytest.fixture(autouse=True)
def _allowlist(monkeypatch):
    monkeypatch.setattr(settings, "super_admin_emails", f"{PLATFORM},{UNCLAIMED}")


def _bearer(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _platform_admin(db, two_orgs):
    """A platform admin living in org A, whose own org admin (admin-a) is NOT one."""
    a = two_orgs["a"]
    user = User(org_id=a["org"].id, role_id=a["role"].id, email=PLATFORM,
                password_hash=hash_password("platform-pw"))
    db.add(user)
    await db.commit()
    return user


async def _analyst_role(db, org):
    role = Role(org_id=org.id, name="Analyst", is_org_admin=False)
    db.add(role)
    await db.commit()
    return role


async def _user(db, org, role, email):
    u = User(org_id=org.id, role_id=role.id, email=email, password_hash=hash_password("pw-123456"))
    db.add(u)
    await db.commit()
    return u


async def _count(db, email: str) -> int:
    return (await db.execute(select(func.count()).select_from(User)
                             .where(func.lower(User.email) == email.lower()))).scalar_one()


# ── E-01: an org admin cannot change or delete a platform admin ──────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"role_id": "analyst"}, {"email": "taken-over@example.com"},
    {"password": "attacker-chosen-pw"}, {"is_active": False},
])
async def test_org_admin_cannot_change_a_platform_admin(client, db_session, two_orgs, auth_headers, change):
    platform = await _platform_admin(db_session, two_orgs)
    analyst = await _analyst_role(db_session, two_orgs["a"]["org"])
    body = {k: (analyst.id if v == "analyst" else v) for k, v in change.items()}

    resp = await client.patch(f"/api/v1/admin/users/{platform.id}", json=body, headers=auth_headers["a"])

    assert resp.status_code == 403, resp.text
    await db_session.refresh(platform)
    assert platform.email == PLATFORM
    assert platform.role_id == two_orgs["a"]["role"].id
    assert platform.is_active is True
    # The real password still works: nothing was reset.
    login = await client.post("/api/v1/auth/login", json={"email": PLATFORM, "password": "platform-pw"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_org_admin_cannot_delete_a_platform_admin(client, db_session, two_orgs, auth_headers):
    platform = await _platform_admin(db_session, two_orgs)
    resp = await client.delete(f"/api/v1/admin/users/{platform.id}", headers=auth_headers["a"])
    assert resp.status_code == 403, resp.text
    assert await _count(db_session, PLATFORM) == 1


@pytest.mark.asyncio
async def test_org_admin_cannot_reassign_a_platform_admins_org_units(client, db_session, two_orgs, auth_headers):
    platform = await _platform_admin(db_session, two_orgs)
    resp = await client.put(f"/api/v1/admin/users/{platform.id}/org-units",
                            json={"org_unit_ids": []}, headers=auth_headers["a"])
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_a_platform_admin_can_still_manage_platform_admins(client, db_session, two_orgs):
    platform = await _platform_admin(db_session, two_orgs)
    resp = await client.patch(f"/api/v1/admin/users/{platform.id}", json={"is_active": True},
                              headers=_bearer(platform))
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_org_admin_still_manages_ordinary_users(client, db_session, two_orgs, auth_headers):
    """The guard is narrow: everyone else in the org is unaffected."""
    org = two_orgs["a"]["org"]
    analyst = await _analyst_role(db_session, org)
    u = await _user(db_session, org, analyst, "someone@example.com")
    assert (await client.patch(f"/api/v1/admin/users/{u.id}", json={"is_active": False},
                               headers=auth_headers["a"])).status_code == 200
    assert (await client.delete(f"/api/v1/admin/users/{u.id}", headers=auth_headers["a"])).status_code == 204


@pytest.mark.asyncio
async def test_user_list_marks_platform_admins(client, db_session, two_orgs, auth_headers):
    """So the admin UI can hide Edit/Delete on that row for an org admin."""
    await _platform_admin(db_session, two_orgs)
    rows = (await client.get("/api/v1/admin/users", headers=auth_headers["a"])).json()
    flags = {r["email"]: r["is_super_admin"] for r in rows}
    assert flags[PLATFORM] is True
    assert flags["admin-a@example.com"] is False


# ── E-02: no account can be created or renamed into the allowlist ────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("email", ["PLATFORM@example.com", "Platform@Example.COM", " platform@example.com "])
async def test_case_variant_of_a_platform_admin_cannot_be_created_in_another_org(
        client, db_session, two_orgs, auth_headers, email):
    """The exact escalation reproduced live: org B's admin registers an
    upper-case copy of the platform admin's address."""
    await _platform_admin(db_session, two_orgs)
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["b"], json={
        "email": email, "password": "escalate-123", "role_id": two_orgs["b"]["role"].id})

    assert resp.status_code in (400, 403), resp.text
    assert await _count(db_session, PLATFORM) == 1
    login = await client.post("/api/v1/auth/login", json={"email": email.strip(), "password": "escalate-123"})
    assert login.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("email", [UNCLAIMED, UNCLAIMED.upper()])
async def test_org_admin_cannot_claim_an_unused_allowlisted_address(client, db_session, two_orgs, auth_headers, email):
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["b"], json={
        "email": email, "password": "escalate-123", "role_id": two_orgs["b"]["role"].id})
    assert resp.status_code == 403, resp.text
    assert await _count(db_session, UNCLAIMED) == 0


@pytest.mark.asyncio
async def test_org_admin_cannot_rename_a_user_into_the_allowlist(client, db_session, two_orgs, auth_headers):
    org = two_orgs["b"]["org"]
    analyst = await _analyst_role(db_session, org)
    u = await _user(db_session, org, analyst, "plain@example.com")
    resp = await client.patch(f"/api/v1/admin/users/{u.id}", json={"email": UNCLAIMED.upper()},
                              headers=auth_headers["b"])
    assert resp.status_code == 403, resp.text
    await db_session.refresh(u)
    assert u.email == "plain@example.com"


@pytest.mark.asyncio
async def test_bulk_import_refuses_allowlisted_and_case_duplicate_rows(client, db_session, two_orgs, auth_headers):
    await _platform_admin(db_session, two_orgs)
    resp = await client.post("/api/v1/admin/users/bulk", headers=auth_headers["b"], json={"users": [
        {"email": "PLATFORM@example.com", "password": "x-123456", "role": "Admin"},
        {"email": UNCLAIMED, "password": "x-123456", "role": "Admin"},
        {"email": "Admin-A@Example.com", "password": "x-123456", "role": "Admin"},
        {"email": "fine@example.com", "password": "x-123456", "role": "Admin"},
    ]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == ["fine@example.com"]
    assert {e["row"] for e in body["errors"]} == {1, 2, 3}
    assert await _count(db_session, PLATFORM) == 1
    assert await _count(db_session, UNCLAIMED) == 0


@pytest.mark.asyncio
async def test_a_platform_admin_may_appoint_another_platform_admin(client, db_session, two_orgs):
    platform = await _platform_admin(db_session, two_orgs)
    resp = await client.post("/api/v1/admin/users", headers=_bearer(platform), json={
        "email": UNCLAIMED, "password": "second-admin-1", "role_id": two_orgs["a"]["role"].id})
    assert resp.status_code == 200, resp.text


# ── emails are one identity, whatever the case ───────────────────────────────

@pytest.mark.asyncio
async def test_a_case_variant_of_any_existing_email_is_a_duplicate(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"]
    analyst = await _analyst_role(db_session, org)
    await _user(db_session, org, analyst, "dup@example.com")
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": "DUP@Example.com", "password": "pw-123456", "role_id": analyst.id})
    assert resp.status_code == 400, resp.text
    assert await _count(db_session, "dup@example.com") == 1


@pytest.mark.asyncio
async def test_new_emails_are_stored_lower_case_and_login_ignores_case(client, db_session, two_orgs, auth_headers):
    analyst = await _analyst_role(db_session, two_orgs["a"]["org"])
    resp = await client.post("/api/v1/admin/users", headers=auth_headers["a"], json={
        "email": " New.Person@Example.COM ", "password": "pw-123456", "role_id": analyst.id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "new.person@example.com"
    for typed in ("new.person@example.com", "NEW.PERSON@EXAMPLE.COM"):
        login = await client.post("/api/v1/auth/login", json={"email": typed, "password": "pw-123456"})
        assert login.status_code == 200, (typed, login.text)


@pytest.mark.asyncio
async def test_login_still_works_for_an_account_stored_with_capitals(client, db_session, two_orgs):
    """Accounts created before this fix may hold capitals; they keep working
    with the address as stored and in any other case."""
    org = two_orgs["a"]["org"]
    analyst = await _analyst_role(db_session, org)
    await _user(db_session, org, analyst, "Legacy.User@Example.com")
    for typed in ("Legacy.User@Example.com", "legacy.user@example.com"):
        login = await client.post("/api/v1/auth/login", json={"email": typed, "password": "pw-123456"})
        assert login.status_code == 200, (typed, login.text)


# ── same class: SSO cannot sign anyone in as a platform admin ────────────────

@pytest.mark.asyncio
async def test_sso_refuses_to_sign_in_a_platform_admin(client, db_session, two_orgs, monkeypatch):
    """The org's SSO provider is configured by its org admin, so it must not be
    able to vouch for a platform admin: they sign in with their password."""
    from tests.test_sso import _drive_login, _id_token, _make_idp, _mock_network, session_cookie

    await _platform_admin(db_session, two_orgs)
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(email=PLATFORM, nonce=nonce))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)

    assert r.status_code == 303
    assert "sso_error=" in r.headers["location"]
    assert session_cookie(r) is None
