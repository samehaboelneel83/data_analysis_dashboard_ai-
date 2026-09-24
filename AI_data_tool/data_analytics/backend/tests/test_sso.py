"""OIDC SSO flow, driven against a mocked identity provider.

Only the IdP *network* calls are stubbed (discovery, JWKS, code exchange). Everything
security-critical runs for real: PKCE/state sealing, the id_token signature check against
a JWKS key, and `aud`/`iss`/`exp`/`nonce` validation. The id_token is a genuine RS256 JWT
signed with a test RSA key whose public half is served as the JWKS.
"""
import time

import pytest
from jose import jwk, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings
from app.core.security import decode_access_token
from app.models.models import OrgIdp
from app.services import sso
from app.services.secrets import encrypt_value, is_encrypted, REDACTED

ISSUER = "https://idp.test"
CLIENT_ID = "client-123"
KID = "test-key-1"

# One RSA keypair for the whole module: private half signs id_tokens, public half is JWKS.
_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIV_PEM = _PRIV.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()


def _jwks() -> dict:
    pub_pem = _PRIV.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    d = jwk.construct(pub_pem, "RS256").to_dict()
    d = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in d.items()}
    d["kid"], d["alg"], d["use"] = KID, "RS256", "sig"
    return {"keys": [d]}


def _disco() -> dict:
    return {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize",
            "token_endpoint": ISSUER + "/token", "jwks_uri": ISSUER + "/jwks"}


def _id_token(*, email="admin-a@example.com", nonce="n", aud=CLIENT_ID, iss=ISSUER,
              exp_delta=300, email_verified=True) -> str:
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "idp-user-1", "email": email,
              "email_verified": email_verified, "nonce": nonce, "iat": now,
              "exp": now + exp_delta}
    return jwt.encode(claims, _PRIV_PEM, algorithm="RS256", headers={"kid": KID})


async def _make_idp(db, org_id, *, domain="example.com", enabled=True):
    idp = OrgIdp(org_id=org_id, protocol="oidc", enabled=enabled, email_domain=domain,
                 issuer=ISSUER, client_id=CLIENT_ID,
                 client_secret=encrypt_value("shh-secret"), config={})
    db.add(idp)
    await db.commit()
    return idp


def _mock_network(monkeypatch, *, id_token):
    async def fake_disco(issuer): return _disco()
    async def fake_jwks(uri): return _jwks()
    async def fake_exchange(disco, idp, code, redirect_uri, code_verifier):
        return {"id_token": id_token}
    monkeypatch.setattr(sso, "fetch_discovery", fake_disco)
    monkeypatch.setattr(sso, "fetch_jwks", fake_jwks)
    monkeypatch.setattr(sso, "exchange_code", fake_exchange)


# ── discovery for the login page ─────────────────────────────────────────────────
async def test_discover_reports_configured_domain(client, db_session, two_orgs):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    r = await client.post("/api/v1/auth/sso/discover", json={"email": "admin-a@example.com"})
    assert r.status_code == 200 and r.json()["sso"] is True
    r2 = await client.post("/api/v1/auth/sso/discover", json={"email": "who@nowhere.io"})
    assert r2.json()["sso"] is False


async def test_discover_accepts_reserved_internal_domains(client, db_session, two_orgs):
    # EmailStr rejects .local as reserved; discover must still resolve internal IdP domains.
    await _make_idp(db_session, two_orgs["a"]["org"].id, domain="corp.local")
    r = await client.post("/api/v1/auth/sso/discover", json={"email": "user@corp.local"})
    assert r.status_code == 200 and r.json()["sso"] is True


# ── login initiation ─────────────────────────────────────────────────────────────
async def test_login_redirects_to_idp_and_sets_flow_cookie(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    async def fake_disco(issuer): return _disco()
    monkeypatch.setattr(sso, "fetch_discovery", fake_disco)

    r = await client.get("/api/v1/auth/sso/oidc/login",
                         params={"email": "admin-a@example.com"}, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith(ISSUER + "/authorize")
    assert "code_challenge=" in loc and "code_challenge_method=S256" in loc and "state=" in loc
    assert "sso_flow" in r.headers.get("set-cookie", "")


async def test_login_unconfigured_domain_bounces_to_login(client, db_session, two_orgs):
    r = await client.get("/api/v1/auth/sso/oidc/login",
                         params={"email": "nobody@unknown.test"}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=not_configured" in r.headers["location"]


# ── callback: the security-critical path ─────────────────────────────────────────
async def _drive_login(client, monkeypatch):
    """Run the login leg and return (state, nonce) from the sealed flow cookie."""
    async def fake_disco(issuer): return _disco()
    monkeypatch.setattr(sso, "fetch_discovery", fake_disco)
    r = await client.get("/api/v1/auth/sso/oidc/login",
                         params={"email": "admin-a@example.com"}, follow_redirects=False)
    cookie = client.cookies.get("sso_flow")
    flow = jwt.decode(cookie, settings.secret_key, algorithms=["HS256"])
    return flow["st"], flow["nonce"]


async def test_callback_happy_path_mints_token_for_existing_user(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(nonce=nonce))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith(settings.public_base_url.rstrip("/") + "/sso/callback#token=")
    token = loc.split("#token=", 1)[1]
    payload = decode_access_token(token)
    assert payload is not None and int(payload["sub"]) == two_orgs["a"]["user"].id


async def test_callback_unknown_email_is_refused_not_provisioned(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(email="stranger@example.com", nonce=nonce))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=no_account" in r.headers["location"]


async def test_callback_state_mismatch_is_rejected(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    _, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(nonce=nonce))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": "forged-state"}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_callback_nonce_mismatch_is_rejected(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, _ = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(nonce="not-the-nonce"))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_callback_wrong_audience_is_rejected(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(nonce=nonce, aud="some-other-client"))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_callback_expired_token_is_rejected(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(nonce=nonce, exp_delta=-10))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=validation_failed" in r.headers["location"]


async def test_callback_unverified_email_is_rejected(client, db_session, two_orgs, monkeypatch):
    await _make_idp(db_session, two_orgs["a"]["org"].id)
    state, nonce = await _drive_login(client, monkeypatch)
    _mock_network(monkeypatch, id_token=_id_token(nonce=nonce, email_verified=False))

    r = await client.get("/api/v1/auth/sso/oidc/callback",
                         params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 303 and "sso_error=email_unverified" in r.headers["location"]


# ── admin config CRUD ────────────────────────────────────────────────────────────
async def test_config_put_encrypts_secret_and_get_redacts(client, db_session, two_orgs, auth_headers):
    body = {"protocol": "oidc", "enabled": True, "email_domain": "Example.com",
            "issuer": ISSUER, "client_id": CLIENT_ID, "client_secret": "top-secret"}
    r = await client.put("/api/v1/auth/sso/config", json=body, headers=auth_headers["a"])
    assert r.status_code == 200
    assert r.json()["client_secret"] == REDACTED          # never returned in the clear
    assert r.json()["email_domain"] == "example.com"      # normalized

    idp = await sso.idp_for_org(db_session, two_orgs["a"]["org"].id)
    assert is_encrypted(idp.client_secret)                 # stored encrypted

    g = await client.get("/api/v1/auth/sso/config", headers=auth_headers["a"])
    assert g.json()["configured"] is True and g.json()["client_secret"] == REDACTED


async def test_config_put_unchanged_secret_keeps_stored(client, db_session, two_orgs, auth_headers):
    base = {"protocol": "oidc", "enabled": True, "email_domain": "example.com",
            "issuer": ISSUER, "client_id": CLIENT_ID}
    await client.put("/api/v1/auth/sso/config", json={**base, "client_secret": "orig"},
                     headers=auth_headers["a"])
    before = (await sso.idp_for_org(db_session, two_orgs["a"]["org"].id)).client_secret
    # Re-save sending the redaction sentinel back → stored secret must be untouched.
    await client.put("/api/v1/auth/sso/config", json={**base, "client_secret": REDACTED},
                     headers=auth_headers["a"])
    await db_session.refresh(await sso.idp_for_org(db_session, two_orgs["a"]["org"].id))
    after = (await sso.idp_for_org(db_session, two_orgs["a"]["org"].id)).client_secret
    assert after == before


async def test_config_domain_collision_across_orgs_is_409(client, db_session, two_orgs, auth_headers):
    body = {"protocol": "oidc", "enabled": True, "email_domain": "shared.com",
            "issuer": ISSUER, "client_id": CLIENT_ID, "client_secret": "s"}
    r1 = await client.put("/api/v1/auth/sso/config", json=body, headers=auth_headers["a"])
    assert r1.status_code == 200
    r2 = await client.put("/api/v1/auth/sso/config", json=body, headers=auth_headers["b"])
    assert r2.status_code == 409


async def test_config_requires_authentication(client):
    assert (await client.get("/api/v1/auth/sso/config")).status_code == 401


async def test_saml_protocol_is_rejected_this_phase(client, auth_headers):
    r = await client.put("/api/v1/auth/sso/config",
                         json={"protocol": "saml", "email_domain": "x.com"},
                         headers=auth_headers["a"])
    assert r.status_code == 400
