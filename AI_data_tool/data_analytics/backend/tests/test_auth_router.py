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


class TestTheBrowserSessionIsAnHttpOnlyCookie:
    """T6 (BUG-040): the login JWT lived in localStorage, where any injected
    script could read it. The browser now holds it as an httpOnly cookie; the
    Authorization header keeps working for API keys, embeds and scripts."""

    async def _login(self, client, db_session):
        await _seed_admin(db_session)
        r = await client.post("/api/v1/auth/login", json={"email": "admin@acme.com", "password": "supersecret"})
        assert r.status_code == 200
        return r

    async def test_login_sets_an_httponly_lax_cookie_that_alone_authenticates(self, client, db_session):
        r = await self._login(client, db_session)
        cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("datalytics_session="))
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api" in cookie
        me = await client.get("/api/v1/auth/me")                  # no Authorization header
        assert me.status_code == 200 and me.json()["email"] == "admin@acme.com"

    async def test_a_cookie_write_needs_the_csrf_header(self, client, db_session):
        await self._login(client, db_session)
        forged = await client.post("/api/v1/reports", json={"name": "From another site"})
        assert forged.status_code == 401        # a cross-site form cannot add the header
        ours = await client.post("/api/v1/reports", json={"name": "Mine"},
                                 headers={"X-Requested-With": "XMLHttpRequest"})
        assert ours.status_code in (200, 201), ours.text

    async def test_logout_clears_the_cookie(self, client, db_session):
        await self._login(client, db_session)
        out = await client.post("/api/v1/auth/logout")
        assert out.status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_an_old_stored_token_is_adopted_into_the_cookie_once(self, client, db_session):
        token = (await self._login(client, db_session)).json()["access_token"]
        client.cookies.clear()
        r = await client.post("/api/v1/auth/session", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 200

    async def test_an_api_key_never_becomes_a_browser_cookie(self, client, db_session):
        token = (await self._login(client, db_session)).json()["access_token"]
        key = (await client.post("/api/v1/auth/api-keys", json={"name": "agent"},
                                 headers={"Authorization": f"Bearer {token}"})).json()
        raw = key.get("key") or key.get("api_key") or key.get("token")
        assert raw and raw.startswith("dk_"), key
        client.cookies.clear()
        r = await client.post("/api/v1/auth/session", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 400
        assert not any(h.startswith("datalytics_session=") for h in r.headers.get_list("set-cookie"))
