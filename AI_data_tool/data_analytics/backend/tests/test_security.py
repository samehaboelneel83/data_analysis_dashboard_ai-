from datetime import timedelta
from freezegun import freeze_time
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_hash_password_does_not_return_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert len(hashed) > 20


def test_verify_password_accepts_the_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_the_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hashing_the_same_password_twice_produces_different_hashes():
    """bcrypt salts each hash — this guards against someone 'optimizing' by
    caching or reusing a hash, which would defeat the salt's purpose."""
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a) is True
    assert verify_password("same password", b) is True


def test_create_and_decode_access_token_round_trips():
    token = create_access_token(user_id=42, org_id=7)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["org_id"] == 7


def test_decode_access_token_rejects_garbage():
    assert decode_access_token("not.a.valid.jwt") is None


def test_decode_access_token_rejects_a_token_signed_with_a_different_key():
    from jose import jwt as _jwt
    bad_token = _jwt.encode({"sub": "1", "org_id": 1}, "wrong-secret-key", algorithm="HS256")
    assert decode_access_token(bad_token) is None


def test_decode_access_token_rejects_an_expired_token():
    with freeze_time("2026-01-01"):
        token = create_access_token(user_id=1, org_id=1)
    with freeze_time("2026-01-01") as frozen:
        frozen.move_to("2026-01-09")   # the default lifetime is 168h (7 days)
        assert decode_access_token(token) is None


# ── Gap 8: secrets, session lifetime, revocation ──────────────────────────────

import pytest  # noqa: E402


class TestProductionRefusesAPublicSigningKey:
    """The JWT signing key's default is printed in config.py and compose, so a
    production install left on it lets anyone mint an admin token."""

    @pytest.mark.parametrize("key", ["change_me_in_production", "short-but-custom"])
    def test_production_will_not_start_on_a_known_or_short_key(self, key):
        from pydantic import ValidationError
        from app.core.config import Settings
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings(env="production", secret_key=key)

    def test_a_long_random_key_starts(self):
        from app.core.config import Settings
        assert Settings(env="production", secret_key="x" * 48).is_production()

    @pytest.mark.parametrize("env", ["development", "dev", "test"])
    def test_development_keeps_working_on_the_default(self, env):
        from app.core.config import Settings
        assert not Settings(env=env, secret_key="change_me_in_production").is_production()


def test_the_token_lifetime_is_a_setting(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "access_token_expire_hours", 2)
    payload = decode_access_token(create_access_token(user_id=1, org_id=1))
    assert payload["exp"] - payload["iat"] == 2 * 3600


class TestAPasswordResetEndsExistingSessions:
    """A login token lived its full 7 days whatever happened to the password;
    a reset -- the moment revocation is certainly wanted -- changed nothing."""

    async def _member(self, db_session, two_orgs):
        from app.models.models import User
        u = User(org_id=two_orgs["a"]["org"].id, role_id=two_orgs["a"]["role"].id,
                 email="sess@example.com", password_hash=hash_password("old-pw"))
        db_session.add(u)
        await db_session.commit()
        await db_session.refresh(u)
        return u

    @staticmethod
    def _token_issued_ago(user, seconds):
        from datetime import datetime, timezone
        from jose import jwt as _jwt
        from app.core.config import settings
        now = datetime.now(timezone.utc)
        return _jwt.encode({"sub": str(user.id), "org_id": user.org_id,
                            "iat": int(now.timestamp()) - seconds,
                            "exp": now + timedelta(days=7)},
                           settings.secret_key, algorithm="HS256")

    async def test_an_old_token_stops_working_after_a_reset(
            self, client, db_session, two_orgs, auth_headers):
        user = await self._member(db_session, two_orgs)
        old = {"Authorization": f"Bearer {self._token_issued_ago(user, 60)}"}
        assert (await client.get("/api/v1/auth/me", headers=old)).status_code == 200

        r = await client.patch(f"/api/v1/admin/users/{user.id}",
                               json={"password": "new-pw"}, headers=auth_headers["a"])
        assert r.status_code == 200, r.text

        assert (await client.get("/api/v1/auth/me", headers=old)).status_code == 401
        fresh = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
        assert (await client.get("/api/v1/auth/me", headers=fresh)).status_code == 200

    async def test_editing_anything_else_leaves_sessions_alone(
            self, client, db_session, two_orgs, auth_headers):
        user = await self._member(db_session, two_orgs)
        old = {"Authorization": f"Bearer {self._token_issued_ago(user, 60)}"}
        r = await client.patch(f"/api/v1/admin/users/{user.id}",
                               json={"email": "renamed@example.com"}, headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        assert (await client.get("/api/v1/auth/me", headers=old)).status_code == 200


class TestErrorsKeepCorsHeaders:
    """An escaped exception used to reach the browser as a CORS violation: the
    safeguard that turns it into a JSON 500 sat OUTSIDE CORSMiddleware, so the
    500 carried no Access-Control-Allow-Origin and the real error was invisible
    (a one-line TypeError once became a CORS hunt). CORS is now registered
    last, which makes it the outermost layer."""

    ORIGIN = "http://localhost:3001"

    async def test_an_unhandled_error_is_a_readable_500_with_cors_headers(self, client):
        from app.main import app

        async def _boom():
            raise TypeError("escaped on purpose")

        app.add_api_route("/api/v1/__cors_boom", _boom, methods=["GET"])
        try:
            r = await client.get("/api/v1/__cors_boom", headers={"Origin": self.ORIGIN})
        finally:
            app.router.routes[:] = [rt for rt in app.router.routes
                                    if getattr(rt, "path", "") != "/api/v1/__cors_boom"]
        assert r.status_code == 500
        assert r.json()["code"] == "internal"
        assert r.headers.get("access-control-allow-origin") == self.ORIGIN

    def test_cors_is_the_outermost_middleware(self):
        from starlette.middleware.cors import CORSMiddleware as _Cors
        from app.main import app
        assert app.user_middleware[0].cls is _Cors
