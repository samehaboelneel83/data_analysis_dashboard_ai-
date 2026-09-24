"""Per-role page visibility, enforced server-side."""
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import Role, User


async def _viewer(db, org, role_name="viewers"):
    role = Role(org_id=org.id, name=role_name, is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{role_name}@example.com",
                password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    return role, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def _two_page_report(client, headers):
    r = await client.post("/api/v1/reports", json={"name": "Vis"}, headers=headers)
    rid = r.json()["id"]
    await client.post(f"/api/v1/reports/{rid}/pages", json={"name": "Secret", "position": 1}, headers=headers)
    # 0014: an authored dashboard is a private draft, and these tests are about
    # what OTHER viewers see of its pages -- so the fixture publishes it. Page
    # visibility then filters the published payload per role, which is exactly
    # the claim being pinned; draft privacy has its own suite
    # (test_publish_and_grants).
    await client.post(f"/api/v1/reports/{rid}/publish", json={"published": True},
                      headers=headers)
    pages = (await client.get(f"/api/v1/reports/{rid}", headers=headers)).json()["pages"]
    return rid, pages


@pytest.mark.asyncio
async def test_a_restricted_page_is_absent_for_the_wrong_role(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    rid, pages = await _two_page_report(client, auth_headers["a"])
    secret = next(p for p in pages if p["name"] == "Secret")

    allowed_role, _ = await _viewer(db_session, org, "allowed")
    _, outsider_headers = await _viewer(db_session, org, "outsiders")

    await client.put(f"/api/v1/reports/{rid}/pages/{secret['id']}/visibility",
                     json={"role_ids": [allowed_role.id]}, headers=auth_headers["a"])

    seen = (await client.get(f"/api/v1/reports/{rid}", headers=outsider_headers)).json()
    # ABSENT from the payload -- not flagged hidden. The page's widget configs must
    # never be serialised to a viewer the restriction excludes.
    assert [p["name"] for p in seen["pages"]] == ["Page 1"]


@pytest.mark.asyncio
async def test_the_allowed_role_and_admins_still_see_it(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    rid, pages = await _two_page_report(client, auth_headers["a"])
    secret = next(p for p in pages if p["name"] == "Secret")
    allowed_role, allowed_headers = await _viewer(db_session, org, "allowed2")

    await client.put(f"/api/v1/reports/{rid}/pages/{secret['id']}/visibility",
                     json={"role_ids": [allowed_role.id]}, headers=auth_headers["a"])

    assert "Secret" in [p["name"] for p in
                        (await client.get(f"/api/v1/reports/{rid}", headers=allowed_headers)).json()["pages"]]
    # The admin is exempt: an admin locked out of a page could not administer the
    # restriction that locked them out.
    assert "Secret" in [p["name"] for p in
                        (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["pages"]]


@pytest.mark.asyncio
async def test_clearing_the_restriction_restores_everyone(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    rid, pages = await _two_page_report(client, auth_headers["a"])
    secret = next(p for p in pages if p["name"] == "Secret")
    allowed_role, _ = await _viewer(db_session, org, "allowed3")
    _, outsider_headers = await _viewer(db_session, org, "outsiders3")

    await client.put(f"/api/v1/reports/{rid}/pages/{secret['id']}/visibility",
                     json={"role_ids": [allowed_role.id]}, headers=auth_headers["a"])
    await client.put(f"/api/v1/reports/{rid}/pages/{secret['id']}/visibility",
                     json={"role_ids": []}, headers=auth_headers["a"])

    assert "Secret" in [p["name"] for p in
                        (await client.get(f"/api/v1/reports/{rid}", headers=outsider_headers)).json()["pages"]]


@pytest.mark.asyncio
async def test_a_foreign_orgs_role_id_is_rejected(client, auth_headers, db_session, two_orgs):
    """Smuggling another org's role id into the restriction would be meaningless at
    best and confusing at worst; it is rejected at the door."""
    rid, pages = await _two_page_report(client, auth_headers["a"])
    secret = next(p for p in pages if p["name"] == "Secret")
    foreign_role, _ = await _viewer(db_session, two_orgs["b"]["org"], "foreign")

    r = await client.put(f"/api/v1/reports/{rid}/pages/{secret['id']}/visibility",
                         json={"role_ids": [foreign_role.id]}, headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_roles_lite_lists_only_the_callers_org(client, auth_headers, db_session, two_orgs):
    await _viewer(db_session, two_orgs["a"]["org"], "a-role")
    listed_b = (await client.get("/api/v1/reports/roles/lite", headers=auth_headers["b"])).json()
    assert all(r["name"] != "a-role" for r in listed_b)
