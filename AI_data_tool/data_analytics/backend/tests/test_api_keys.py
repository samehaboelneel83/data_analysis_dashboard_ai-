"""Machine API keys: durable bearer credentials that authenticate as their user."""
import pytest

from app.core import api_keys


# ── unit: key format + hashing ────────────────────────────────────────────────

def test_generate_produces_a_prefixed_key_and_a_matching_hash():
    full, prefix, h = api_keys.generate()
    assert full.startswith("dk_") and api_keys.looks_like_api_key(full)
    assert api_keys.prefix_of(full) == prefix
    assert api_keys.verify(full, h) is True
    assert api_keys.verify(full + "x", h) is False   # any tamper fails


def test_a_login_jwt_is_not_mistaken_for_an_api_key():
    assert not api_keys.looks_like_api_key("eyJhbGciOi.something.sig")
    assert api_keys.prefix_of("not-a-key") is None


# ── end to end: issue, use, list, revoke ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_key_authenticates_like_a_login_token(client, auth_headers):
    r = await client.post("/api/v1/auth/api-keys", json={"name": "agent"}, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    key = r.json()["key"]
    assert key.startswith("dk_")

    # the key works as a bearer token on a normal endpoint...
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
    assert me.status_code == 200
    # ...as the SAME user who issued it
    who = await client.get("/api/v1/auth/me", headers=auth_headers["a"])
    assert me.json()["id"] == who.json()["id"]


@pytest.mark.asyncio
async def test_the_secret_is_shown_once_and_never_listed(client, auth_headers):
    created = (await client.post("/api/v1/auth/api-keys", json={"name": "k"}, headers=auth_headers["a"])).json()
    listed = (await client.get("/api/v1/auth/api-keys", headers=auth_headers["a"])).json()
    row = next(k for k in listed if k["id"] == created["id"])
    assert "key" not in row and "key_hash" not in row      # only metadata is listable
    assert row["prefix"] == created["prefix"]


@pytest.mark.asyncio
async def test_revoking_a_key_stops_it_working(client, auth_headers):
    created = (await client.post("/api/v1/auth/api-keys", json={"name": "k"}, headers=auth_headers["a"])).json()
    key = created["key"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})).status_code == 200

    d = await client.delete(f"/api/v1/auth/api-keys/{created['id']}", headers=auth_headers["a"])
    assert d.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})).status_code == 401


@pytest.mark.asyncio
async def test_a_bogus_key_is_rejected(client):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dk_deadbeef.notreal"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_keys_are_owner_scoped(client, auth_headers):
    created = (await client.post("/api/v1/auth/api-keys", json={"name": "a-key"}, headers=auth_headers["a"])).json()
    # org B's admin cannot see org A's key nor revoke it
    b_list = (await client.get("/api/v1/auth/api-keys", headers=auth_headers["b"])).json()
    assert all(k["id"] != created["id"] for k in b_list)
    d = await client.delete(f"/api/v1/auth/api-keys/{created['id']}", headers=auth_headers["b"])
    assert d.status_code == 404
