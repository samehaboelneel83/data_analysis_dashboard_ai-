"""Platform super-admin: cross-org organization management + hierarchy."""
import pytest

from app.core.config import settings


@pytest.fixture
def _super(monkeypatch):
    # Org A's admin (admin-a@example.com, from the two_orgs fixture) is the super-admin.
    monkeypatch.setattr(settings, "super_admin_emails", "admin-a@example.com")


@pytest.mark.asyncio
async def test_only_a_super_admin_may_manage_organizations(client, auth_headers, two_orgs, _super):
    # Org B's admin is NOT a super-admin, so the whole surface is 403 for them.
    assert (await client.get("/api/v1/platform/organizations", headers=auth_headers["b"])).status_code == 403
    assert (await client.get("/api/v1/platform/organizations", headers=auth_headers["a"])).status_code == 200


@pytest.mark.asyncio
async def test_me_reports_super_admin_status(client, auth_headers, two_orgs, _super):
    assert (await client.get("/api/v1/auth/me", headers=auth_headers["a"])).json()["is_super_admin"] is True
    assert (await client.get("/api/v1/auth/me", headers=auth_headers["b"])).json()["is_super_admin"] is False


@pytest.mark.asyncio
async def test_create_org_provisions_an_org_and_a_working_admin(client, auth_headers, two_orgs, _super):
    r = await client.post("/api/v1/platform/organizations",
                          json={"name": "Acme", "admin_email": "boss@acme.com", "admin_password": "s3cret"},
                          headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    # the new admin can log in immediately
    login = await client.post("/api/v1/auth/login", json={"email": "boss@acme.com", "password": "s3cret"})
    assert login.status_code == 200
    # and the org shows up in the cross-org listing
    orgs = (await client.get("/api/v1/platform/organizations", headers=auth_headers["a"])).json()
    acme = next(o for o in orgs if o["name"] == "Acme")
    assert acme["user_count"] == 1 and acme["parent_org_id"] is None


@pytest.mark.asyncio
async def test_duplicate_admin_email_is_rejected(client, auth_headers, two_orgs, _super):
    r = await client.post("/api/v1/platform/organizations",
                          json={"name": "Dup", "admin_email": "admin-b@example.com", "admin_password": "pw"},
                          headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_hierarchy_set_view_and_clear(client, auth_headers, two_orgs, _super):
    a, b = two_orgs["a"]["org"].id, two_orgs["b"]["org"].id
    # make B a child of A
    r = await client.put(f"/api/v1/platform/organizations/{b}/parent",
                         json={"parent_org_id": a}, headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["parent_org_id"] == a

    tree = (await client.get("/api/v1/platform/organizations/tree", headers=auth_headers["a"])).json()
    root_a = next(n for n in tree if n["id"] == a)
    assert b in [c["id"] for c in root_a["children"]]
    assert all(n["id"] != b for n in tree)      # B is no longer a root

    # clearing makes B top-level again
    await client.put(f"/api/v1/platform/organizations/{b}/parent",
                     json={"parent_org_id": None}, headers=auth_headers["a"])
    tree2 = (await client.get("/api/v1/platform/organizations/tree", headers=auth_headers["a"])).json()
    assert any(n["id"] == b for n in tree2)


@pytest.mark.asyncio
async def test_mcp_defaults_enabled_and_can_be_toggled(client, auth_headers, two_orgs, _super):
    b = two_orgs["b"]["org"].id
    orgs = (await client.get("/api/v1/platform/organizations", headers=auth_headers["a"])).json()
    assert next(o for o in orgs if o["id"] == b)["mcp_enabled"] is True   # default on
    r = await client.put(f"/api/v1/platform/organizations/{b}/mcp",
                         json={"enabled": False}, headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["mcp_enabled"] is False
    orgs2 = (await client.get("/api/v1/platform/organizations", headers=auth_headers["a"])).json()
    assert next(o for o in orgs2 if o["id"] == b)["mcp_enabled"] is False


@pytest.mark.asyncio
async def test_deactivating_mcp_stops_that_orgs_api_keys(client, auth_headers, two_orgs, _super):
    # Org B's admin issues a key; it works, then MCP is switched off for org B.
    key = (await client.post("/api/v1/auth/api-keys", json={"name": "agent"}, headers=auth_headers["b"])).json()["key"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})).status_code == 200

    await client.put(f"/api/v1/platform/organizations/{two_orgs['b']['org'].id}/mcp",
                     json={"enabled": False}, headers=auth_headers["a"])
    # the key stops authenticating for the whole org...
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})).status_code == 403
    # ...but a normal login (JWT) is unaffected
    assert (await client.get("/api/v1/auth/me", headers=auth_headers["b"])).status_code == 200

    # reactivating restores the key
    await client.put(f"/api/v1/platform/organizations/{two_orgs['b']['org'].id}/mcp",
                     json={"enabled": True}, headers=auth_headers["a"])
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})).status_code == 200


@pytest.mark.asyncio
async def test_only_a_super_admin_can_toggle_mcp(client, auth_headers, two_orgs, _super):
    r = await client.put(f"/api/v1/platform/organizations/{two_orgs['b']['org'].id}/mcp",
                         json={"enabled": False}, headers=auth_headers["b"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cycles_and_self_parent_are_refused(client, auth_headers, two_orgs, _super):
    a, b = two_orgs["a"]["org"].id, two_orgs["b"]["org"].id
    assert (await client.put(f"/api/v1/platform/organizations/{a}/parent",
                             json={"parent_org_id": a}, headers=auth_headers["a"])).status_code == 400  # self
    await client.put(f"/api/v1/platform/organizations/{b}/parent", json={"parent_org_id": a}, headers=auth_headers["a"])
    # A -> B would close the cycle A->B->A
    assert (await client.put(f"/api/v1/platform/organizations/{a}/parent",
                             json={"parent_org_id": b}, headers=auth_headers["a"])).status_code == 400
