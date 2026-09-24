"""The org basemap (MASTER_PLAN Phase 4 item 4): off by default, set by an org
admin, validated as an XYZ template, and confinable to the deployment's hosts."""
import pytest

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.models import Role, User

URL = "/api/v1/map-settings"
TILES = "https://tiles.corp.local/{z}/{x}/{y}.png"


async def _member(db_session, org_id):
    role = Role(org_id=org_id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=f"v{role.id}@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


@pytest.mark.asyncio
async def test_off_by_default(client, two_orgs, auth_headers):
    r = await client.get(URL, headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["tile_url"] is None


@pytest.mark.asyncio
async def test_an_admin_sets_it_and_every_member_reads_it_but_not_other_orgs(client, two_orgs, auth_headers, db_session):
    r = await client.put(URL, headers=auth_headers["a"], json={"tile_url": TILES, "attribution": "© GIS"})
    assert r.status_code == 200, r.text
    viewer = await _member(db_session, two_orgs["a"]["org"].id)
    assert (await client.get(URL, headers=viewer)).json()["tile_url"] == TILES
    assert (await client.get(URL, headers=auth_headers["b"])).json()["tile_url"] is None
    # Setting it is admin-only.
    denied = await client.put(URL, headers=viewer, json={"tile_url": None})
    assert denied.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("body, reason", [
    ({"tile_url": "https://tiles.corp.local/{z}/{x}.png", "attribution": "x"}, "{y} is missing"),
    ({"tile_url": "ftp://tiles/{z}/{x}/{y}", "attribution": "x"}, "http(s)"),
    ({"tile_url": TILES}, "attribution"),
])
async def test_bad_templates_are_refused_with_a_reason(client, two_orgs, auth_headers, body, reason):
    r = await client.put(URL, headers=auth_headers["a"], json=body)
    assert r.status_code == 400 and reason in r.text


@pytest.mark.asyncio
async def test_an_air_gapped_deployment_confines_the_hosts(client, two_orgs, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "map_tile_hosts", "tiles.corp.local")
    ok = await client.put(URL, headers=auth_headers["a"], json={"tile_url": TILES, "attribution": "© GIS"})
    assert ok.status_code == 200
    bad = await client.put(URL, headers=auth_headers["a"],
                           json={"tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "attribution": "© OSM"})
    assert bad.status_code == 400 and "tile.openstreetmap.org" in bad.text


@pytest.mark.asyncio
async def test_clearing_it_turns_the_basemap_off(client, two_orgs, auth_headers):
    await client.put(URL, headers=auth_headers["a"], json={"tile_url": TILES, "attribution": "© GIS"})
    r = await client.put(URL, headers=auth_headers["a"], json={"tile_url": ""})
    assert r.status_code == 200 and r.json()["tile_url"] is None
