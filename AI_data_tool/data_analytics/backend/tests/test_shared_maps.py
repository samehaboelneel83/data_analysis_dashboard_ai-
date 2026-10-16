"""Maps on the public surfaces: guest share links and embeds.

A logged-out guest, or a host page embedding a report, has no session. Every
map tile used to ask two signed-in-only routes for what it draws with -- the
org's basemap tiles (`GET /map-settings`) and, for a column with custom
boundaries, the shapes (`GET /boundary-sets/{id}`). Both answered 401, and the
app's global "your session expired" handler sent the guest to the login page:
a guest link to ANY dashboard with a map bounced to /login (QA 2026-10-14,
F2-55; TODO_PLAN F-01).

What the public payloads now carry instead, and the limits on it:
  * `map_settings` -- the report's ORG basemap, the same three fields the
    signed-in route returns. Never another org's.
  * the boundary shapes, through a route scoped to the link or the embed
    session, and only for a set the published report itself references: a
    column's geography classification, a map widget's `boundary_set_id`, or a
    layer's. Any other id -- even one in the same org -- is a 404, so a link
    cannot be used to read the org's other boundary files.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from jose import jwt

from app.core.security import ALGORITHM
from app.models.models import (
    BoundarySet, Dataset, DatasetColumn, OrgMapSettings, Report, ReportPage, ReportWidget, ShareLink,
)

_SQUARE = {"type": "FeatureCollection", "features": [{
    "type": "Feature", "properties": {"name": "Cairo"},
    "geometry": {"type": "Polygon", "coordinates": [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]]},
}]}


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({"region": ["Cairo", "Giza"], "amount": [10.0, 20.0]}).to_csv(p, index=False)
    return str(p)


async def _boundary_set(db, org, name):
    bs = BoundarySet(org_id=org.id, name=name, geometry=_SQUARE, key_properties=["name"], feature_count=1)
    db.add(bs)
    await db.flush()
    return bs


async def _map_report(db, org, path, *, widget_config=None):
    """A report whose one widget is a choropleth (a map)."""
    ds = Dataset(name="S", filename=path, org_id=org.id, mode="import")
    db.add(ds)
    await db.flush()
    for c in ("region", "amount"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical"))
    r = Report(name="Map R", dataset_id=ds.id, org_id=org.id)
    db.add(r)
    await db.flush()
    page = ReportPage(report_id=r.id, name="P1", position=0)
    db.add(page)
    await db.flush()
    w = ReportWidget(page_id=page.id, widget_type="geo_choropleth",
                     config=widget_config or {"category": "region", "measure": "amount", "aggregation": "sum"})
    db.add(w)
    await db.commit()
    return ds, r, w


async def _guest_token(client, headers, report_id):
    resp = await client.post(f"/api/v1/reports/{report_id}/share-links", json={"expires_days": 7},
                             headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


# ── guest share links ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_guest_payload_carries_the_orgs_basemap(client, auth_headers, db_session, two_orgs, salesfile):
    """The map tiles' settings come with the report, so the guest page never
    calls the signed-in /map-settings route (which 401s and bounced to /login)."""
    org_a, org_b = two_orgs["a"]["org"], two_orgs["b"]["org"]
    _, r, _ = await _map_report(db_session, org_a, salesfile)
    db_session.add(OrgMapSettings(org_id=org_a.id, tile_url="https://tiles.example/{z}/{x}/{y}.png",
                                  attribution="© Example"))
    db_session.add(OrgMapSettings(org_id=org_b.id, tile_url="https://other.example/{z}/{x}/{y}.png",
                                  attribution="© Other"))
    await db_session.commit()
    token = await _guest_token(client, auth_headers["a"], r.id)

    body = (await client.get(f"/api/v1/shared/{token}")).json()   # no credentials at all

    assert body["map_settings"] == {"tile_url": "https://tiles.example/{z}/{x}/{y}.png",
                                    "attribution": "© Example", "contrast_tile_url": None}


@pytest.mark.asyncio
async def test_guest_payload_map_settings_empty_when_org_has_none(client, auth_headers, db_session, two_orgs, salesfile):
    _, r, _ = await _map_report(db_session, two_orgs["a"]["org"], salesfile)
    token = await _guest_token(client, auth_headers["a"], r.id)
    body = (await client.get(f"/api/v1/shared/{token}")).json()
    assert body["map_settings"] == {"tile_url": None, "attribution": None, "contrast_tile_url": None}


@pytest.mark.asyncio
async def test_guest_can_load_a_boundary_set_the_dataset_classifies(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    ds, r, _ = await _map_report(db_session, org, salesfile)
    bs = await _boundary_set(db_session, org, "Governorates")
    ds.column_meta = {"region": {"role": "geography", "boundary_set_id": bs.id}}
    await db_session.commit()
    token = await _guest_token(client, auth_headers["a"], r.id)

    resp = await client.get(f"/api/v1/shared/{token}/boundary-sets/{bs.id}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["geometry"] == _SQUARE
    assert resp.json()["key_properties"] == ["name"]


@pytest.mark.asyncio
async def test_guest_can_load_a_boundary_set_a_widget_or_layer_names(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    widget_set = await _boundary_set(db_session, org, "Widget set")
    layer_set = await _boundary_set(db_session, org, "Layer set")
    _, r, _ = await _map_report(db_session, org, salesfile, widget_config={
        "category": "region", "measure": "amount", "boundary_set_id": widget_set.id,
        "layers": [{"id": "l1", "kind": "choropleth", "category": "region", "boundary_set_id": layer_set.id}],
    })
    token = await _guest_token(client, auth_headers["a"], r.id)

    for set_id in (widget_set.id, layer_set.id):
        resp = await client.get(f"/api/v1/shared/{token}/boundary-sets/{set_id}")
        assert resp.status_code == 200, (set_id, resp.text)


@pytest.mark.asyncio
async def test_guest_cannot_read_a_boundary_set_the_report_does_not_use(
        client, auth_headers, db_session, two_orgs, salesfile):
    """The link is not a key to the org's boundary library: a set in the SAME
    org that this report never references is a 404, like a nonexistent one."""
    org = two_orgs["a"]["org"]
    _, r, _ = await _map_report(db_session, org, salesfile)
    unrelated = await _boundary_set(db_session, org, "Not on this report")
    await db_session.commit()
    token = await _guest_token(client, auth_headers["a"], r.id)

    assert (await client.get(f"/api/v1/shared/{token}/boundary-sets/{unrelated.id}")).status_code == 404
    assert (await client.get(f"/api/v1/shared/{token}/boundary-sets/999999")).status_code == 404


@pytest.mark.asyncio
async def test_guest_cannot_read_another_orgs_boundary_set_even_if_referenced(
        client, auth_headers, db_session, two_orgs, salesfile):
    """A widget config pointing at another org's set id must not leak it."""
    foreign = await _boundary_set(db_session, two_orgs["b"]["org"], "Org B shapes")
    _, r, _ = await _map_report(db_session, two_orgs["a"]["org"], salesfile, widget_config={
        "category": "region", "measure": "amount", "boundary_set_id": foreign.id})
    token = await _guest_token(client, auth_headers["a"], r.id)

    assert (await client.get(f"/api/v1/shared/{token}/boundary-sets/{foreign.id}")).status_code == 404


@pytest.mark.asyncio
async def test_boundary_route_rejects_bogus_and_revoked_links(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    ds, r, _ = await _map_report(db_session, org, salesfile)
    bs = await _boundary_set(db_session, org, "Governorates")
    ds.column_meta = {"region": {"role": "geography", "boundary_set_id": bs.id}}
    await db_session.commit()
    token = await _guest_token(client, auth_headers["a"], r.id)

    assert (await client.get(f"/api/v1/shared/not-a-real-token/boundary-sets/{bs.id}")).status_code == 404

    link = (await db_session.execute(ShareLink.__table__.select())).first()
    await db_session.execute(ShareLink.__table__.update().where(ShareLink.id == link.id)
                             .values(revoked_at=datetime.now(timezone.utc)))
    await db_session.commit()
    assert (await client.get(f"/api/v1/shared/{token}/boundary-sets/{bs.id}")).status_code == 404


# ── embeds ───────────────────────────────────────────────────────────────────

def _host_token(secret: str, cfg_id: int) -> str:
    return jwt.encode({"cfg": cfg_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                      secret, algorithm=ALGORITHM)


async def _embed(client, headers, report_id):
    cfg = (await client.post(f"/api/v1/reports/{report_id}/embed-configs",
                             json={"name": "e", "allowed_origins": []}, headers=headers)).json()
    body = (await client.get(f"/api/v1/embed/report?token={_host_token(cfg['secret'], cfg['id'])}")).json()
    return body


@pytest.mark.asyncio
async def test_embed_payload_carries_the_orgs_basemap(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    _, r, _ = await _map_report(db_session, org, salesfile)
    db_session.add(OrgMapSettings(org_id=org.id, tile_url="https://tiles.example/{z}/{x}/{y}.png",
                                  attribution="© Example"))
    await db_session.commit()

    body = await _embed(client, auth_headers["a"], r.id)

    assert body["map_settings"]["tile_url"] == "https://tiles.example/{z}/{x}/{y}.png"


@pytest.mark.asyncio
async def test_embed_session_can_load_only_referenced_boundary_sets(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    ds, r, _ = await _map_report(db_session, org, salesfile)
    used = await _boundary_set(db_session, org, "Used")
    unused = await _boundary_set(db_session, org, "Unused")
    ds.column_meta = {"region": {"role": "geography", "boundary_set_id": used.id}}
    await db_session.commit()
    session = (await _embed(client, auth_headers["a"], r.id))["embed_session_token"]
    auth = {"Authorization": f"Bearer {session}"}

    ok = await client.get(f"/api/v1/embed/boundary-sets/{used.id}", headers=auth)
    assert ok.status_code == 200, ok.text
    assert ok.json()["geometry"] == _SQUARE
    assert (await client.get(f"/api/v1/embed/boundary-sets/{unused.id}", headers=auth)).status_code == 404
    # No session, or a session token that is not one: refused.
    assert (await client.get(f"/api/v1/embed/boundary-sets/{used.id}")).status_code == 401
    assert (await client.get(f"/api/v1/embed/boundary-sets/{used.id}",
                             headers={"Authorization": "Bearer nonsense"})).status_code == 401


@pytest.mark.asyncio
async def test_a_normal_user_token_is_not_an_embed_session(client, auth_headers, db_session, two_orgs, salesfile):
    """The embed boundary route takes ONLY an embed session, like widget-data:
    a signed-in user's own bearer token is not accepted there."""
    org = two_orgs["a"]["org"]
    ds, r, _ = await _map_report(db_session, org, salesfile)
    used = await _boundary_set(db_session, org, "Used")
    ds.column_meta = {"region": {"role": "geography", "boundary_set_id": used.id}}
    await db_session.commit()
    resp = await client.get(f"/api/v1/embed/boundary-sets/{used.id}", headers=auth_headers["a"])
    # Refused either way (no embed config in it -> the same 404 as a bad cfg,
    # exactly like /embed/widget-data); what matters is no shapes come back.
    assert resp.status_code in (401, 404), resp.text
    assert "geometry" not in resp.text
