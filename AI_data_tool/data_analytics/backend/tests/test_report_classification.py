"""Sensitivity labels on reports (gap row 470)."""
import pytest

from app.services.pdf_export import build_report_pdf


async def _make_report(client, headers) -> int:
    r = await client.post("/api/v1/reports", json={"name": "Q4 numbers"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_report_starts_unclassified(client, auth_headers):
    rid = await _make_report(client, auth_headers["a"])
    r = await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])
    assert r.json()["classification"] is None


@pytest.mark.asyncio
async def test_set_and_read_a_label(client, auth_headers):
    rid = await _make_report(client, auth_headers["a"])
    r = await client.put(f"/api/v1/reports/{rid}/classification",
                         json={"label": "Confidential"}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["classification"] == "Confidential"
    # persisted and echoed on the plain GET
    assert (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["classification"] == "Confidential"


@pytest.mark.asyncio
async def test_changing_the_label_replaces_it_and_clearing_removes_it(client, auth_headers):
    rid = await _make_report(client, auth_headers["a"])
    await client.put(f"/api/v1/reports/{rid}/classification", json={"label": "Internal"}, headers=auth_headers["a"])
    await client.put(f"/api/v1/reports/{rid}/classification", json={"label": "Restricted"}, headers=auth_headers["a"])
    assert (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["classification"] == "Restricted"
    await client.put(f"/api/v1/reports/{rid}/classification", json={"label": ""}, headers=auth_headers["a"])
    assert (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["classification"] is None


@pytest.mark.asyncio
async def test_unknown_label_is_rejected(client, auth_headers):
    rid = await _make_report(client, auth_headers["a"])
    r = await client.put(f"/api/v1/reports/{rid}/classification",
                         json={"label": "TopSecret"}, headers=auth_headers["a"])
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_setting_a_label_bumps_the_revision(client, auth_headers):
    rid = await _make_report(client, auth_headers["a"])
    before = (await client.get(f"/api/v1/reports/{rid}/revision", headers=auth_headers["a"])).json()["revision"]
    await client.put(f"/api/v1/reports/{rid}/classification", json={"label": "Public"}, headers=auth_headers["a"])
    after = (await client.get(f"/api/v1/reports/{rid}/revision", headers=auth_headers["a"])).json()["revision"]
    assert after > before


@pytest.mark.asyncio
async def test_classification_is_org_scoped(client, auth_headers):
    rid = await _make_report(client, auth_headers["a"])
    r = await client.put(f"/api/v1/reports/{rid}/classification",
                         json={"label": "Public"}, headers=auth_headers["b"])
    assert r.status_code in (403, 404)


def test_pdf_cover_stamps_the_label():
    # The label has to travel on the document itself, so it must reach the bytes.
    plain = build_report_pdf("R", None, [])
    stamped = build_report_pdf("R", None, [], classification="Restricted")
    assert stamped[:4] == b"%PDF"
    assert len(stamped) != len(plain)  # the banner changed the rendered output
