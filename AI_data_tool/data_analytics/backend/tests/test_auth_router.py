from app.routers import auth as auth_router
from app.services.auth_provisioning import create_organization_with_admin


async def _seed_admin(db_session, email="admin@acme.com", password="supersecret"):
    org, role, user = await create_organization_with_admin(db_session, "Acme Corp", email, password)
    await db_session.commit()
    return org, role, user


async def test_login_with_correct_credentials_returns_a_token(client, db_session):
    await _seed_admin(db_session)

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


async def test_login_with_wrong_password_returns_401(client, db_session):
    await _seed_admin(db_session)

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "wrong"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


async def test_login_with_unknown_email_returns_the_same_generic_401(client, db_session):
    resp = await client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.com", "password": "x"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


async def test_login_with_inactive_user_returns_the_same_generic_401(client, db_session):
    org, role, user = await _seed_admin(db_session)
    user.is_active = False
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


async def test_me_with_valid_token_returns_the_current_user(client, db_session):
    await _seed_admin(db_session)
    login_resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "admin@acme.com"
    assert body["organization"]["name"] == "Acme Corp"
    assert body["role"]["is_org_admin"] is True


async def test_me_without_a_token_returns_401(client, db_session):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_an_invalid_token_returns_401(client, db_session):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def _spy_on_verify_password(monkeypatch):
    """Wraps auth_router.verify_password with a call-counting spy, preserving
    its real (slow, bcrypt) behavior so the fix's timing property still holds
    during the call -- only the call count is observed."""
    calls = []
    real_verify_password = auth_router.verify_password

    def spy(password, password_hash):
        calls.append((password, password_hash))
        return real_verify_password(password, password_hash)

    monkeypatch.setattr(auth_router, "verify_password", spy)
    return calls


async def test_login_with_wrong_password_calls_verify_password_once(client, db_session, monkeypatch):
    calls = _spy_on_verify_password(monkeypatch)
    await _seed_admin(db_session)

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "wrong"})

    assert resp.status_code == 401
    assert len(calls) == 1


async def test_login_with_unknown_email_calls_verify_password_once(client, db_session, monkeypatch):
    """Proves the timing-side-channel fix structurally: an unknown email must
    still pay the bcrypt cost by calling verify_password (against the dummy
    hash), rather than short-circuiting before ever hashing anything -- which
    is exactly what let an attacker previously distinguish "unknown email"
    from "wrong password" by response time alone."""
    calls = _spy_on_verify_password(monkeypatch)

    resp = await client.post("/api/v1/auth/login", json={"email": "nobody@nowhere.com", "password": "x"})

    assert resp.status_code == 401
    assert len(calls) == 1


async def test_login_with_inactive_user_calls_verify_password_once(client, db_session, monkeypatch):
    """Same as above for the inactive-user case: a naive `not user.is_active or
    not verify_password(...)` would short-circuit past verify_password for an
    inactive user, silently reopening the same timing gap. It must be called."""
    calls = _spy_on_verify_password(monkeypatch)
    org, role, user = await _seed_admin(db_session)
    user.is_active = False
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})

    assert resp.status_code == 401
    assert len(calls) == 1
