"""Per-locale report text overrides."""
import pytest

from app.models.models import Report


async def _report(db, org):
    r = Report(name="R", org_id=org.id)
    db.add(r)
    await db.commit()
    return r


@pytest.mark.asyncio
async def test_round_trip_and_key_hygiene(client, auth_headers, db_session, two_orgs):
    r = await _report(db_session, two_orgs["a"]["org"])
    resp = await client.put(f"/api/v1/reports/{r.id}/translations/ar",
                            json={"w12": "الإيرادات", "c9": "نص", "bogus": "x", "w12x": "y", "w13": "  "},
                            headers=auth_headers["a"])
    assert resp.status_code == 200
    # only well-formed keys with real content survive
    assert resp.json() == {"w12": "الإيرادات", "c9": "نص"}
    resp = await client.get(f"/api/v1/reports/{r.id}/translations", headers=auth_headers["a"])
    assert resp.json() == {"ar": {"w12": "الإيرادات", "c9": "نص"}}


@pytest.mark.asyncio
async def test_empty_payload_deletes_the_locale(client, auth_headers, db_session, two_orgs):
    r = await _report(db_session, two_orgs["a"]["org"])
    await client.put(f"/api/v1/reports/{r.id}/translations/fr", json={"w1": "Revenu"},
                     headers=auth_headers["a"])
    await client.put(f"/api/v1/reports/{r.id}/translations/fr", json={},
                     headers=auth_headers["a"])
    resp = await client.get(f"/api/v1/reports/{r.id}/translations", headers=auth_headers["a"])
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_locale_shape_and_org_scoping(client, auth_headers, db_session, two_orgs):
    r = await _report(db_session, two_orgs["a"]["org"])
    resp = await client.put(f"/api/v1/reports/{r.id}/translations/not_a_locale",
                            json={"w1": "x"}, headers=auth_headers["a"])
    assert resp.status_code == 400
    resp = await client.get(f"/api/v1/reports/{r.id}/translations", headers=auth_headers["b"])
    assert resp.status_code == 404
