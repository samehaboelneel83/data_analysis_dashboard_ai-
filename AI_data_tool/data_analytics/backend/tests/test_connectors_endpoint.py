"""The connector catalog endpoint and type validation on data-source writes."""
import pytest

from app.services import connectors


@pytest.mark.asyncio
async def test_catalog_endpoint_matches_the_registry(client, auth_headers):
    """Drift guard: the endpoint the frontend renders from must enumerate exactly
    the registry — no hand-maintained second list can fall out of sync."""
    resp = await client.get("/api/v1/data-sources/connectors", headers=auth_headers["a"])
    assert resp.status_code == 200
    payload = resp.json()
    assert {c["key"] for c in payload} == {s.key for s in connectors.all_specs()}
    # a representative new connector is present with a renderable field spec
    rs = next(c for c in payload if c["key"] == "redshift")
    assert rs["category"] == "PostgreSQL-compatible"
    assert {f["name"] for f in rs["config_fields"]} >= {"host", "port", "database", "username", "password"}


@pytest.mark.asyncio
async def test_create_rejects_unknown_type(client, auth_headers):
    resp = await client.post("/api/v1/data-sources",
                             json={"name": "x", "type": "bogus", "config": {}},
                             headers=auth_headers["a"])
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_accepts_a_new_named_connector(client, auth_headers):
    resp = await client.post("/api/v1/data-sources",
                             json={"name": "Warehouse", "type": "redshift",
                                   "config": {"host": "h", "database": "d",
                                              "username": "u", "password": "p"}},
                             headers=auth_headers["a"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "redshift"


@pytest.mark.asyncio
async def test_update_rejects_unknown_type(client, auth_headers, db_session, two_orgs):
    from app.models.models import DataSource
    ds = DataSource(name="s", type="sqlite", config={"filepath": "/x.db"},
                    org_id=two_orgs["a"]["org"].id)
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    resp = await client.put(f"/api/v1/data-sources/{ds.id}",
                            json={"type": "nope"}, headers=auth_headers["a"])
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_and_generic_remain_valid_types(client, auth_headers):
    for t, cfg in [("api", {"url": "https://x.example.com"}),
                   ("generic", {"url": "sqlite:///x.db"})]:
        resp = await client.post("/api/v1/data-sources",
                                 json={"name": t, "type": t, "config": cfg},
                                 headers=auth_headers["a"])
        assert resp.status_code == 200, resp.text
