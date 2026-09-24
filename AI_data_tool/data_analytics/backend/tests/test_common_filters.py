"""Report-level common filters (gap row 358)."""
import pytest


async def _report(client, headers) -> int:
    r = await client.post("/api/v1/reports", json={"name": "Ops"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_report_starts_with_no_common_filters(client, auth_headers):
    rid = await _report(client, auth_headers["a"])
    assert (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["common_filters"] == []


@pytest.mark.asyncio
async def test_add_lists_on_the_report_and_delete_removes_it(client, auth_headers):
    rid = await _report(client, auth_headers["a"])
    r = await client.post(f"/api/v1/reports/{rid}/common-filters",
                          json={"column": "region", "op": "eq", "value": "North"},
                          headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    got = (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["common_filters"]
    assert got == [{"id": fid, "column": "region", "op": "eq", "value": "North"}]

    d = await client.delete(f"/api/v1/reports/{rid}/common-filters/{fid}", headers=auth_headers["a"])
    assert d.status_code == 204
    assert (await client.get(f"/api/v1/reports/{rid}", headers=auth_headers["a"])).json()["common_filters"] == []


@pytest.mark.asyncio
async def test_list_value_is_preserved_for_in_op(client, auth_headers):
    rid = await _report(client, auth_headers["a"])
    r = await client.post(f"/api/v1/reports/{rid}/common-filters",
                          json={"column": "region", "op": "in", "value": ["North", "South"]},
                          headers=auth_headers["a"])
    assert r.json()["value"] == ["North", "South"]


@pytest.mark.asyncio
async def test_column_required_and_op_validated(client, auth_headers):
    rid = await _report(client, auth_headers["a"])
    assert (await client.post(f"/api/v1/reports/{rid}/common-filters",
                              json={"column": "", "op": "eq"}, headers=auth_headers["a"])).status_code == 400
    assert (await client.post(f"/api/v1/reports/{rid}/common-filters",
                              json={"column": "x", "op": "bogus"}, headers=auth_headers["a"])).status_code == 400


@pytest.mark.asyncio
async def test_adding_bumps_revision(client, auth_headers):
    rid = await _report(client, auth_headers["a"])
    before = (await client.get(f"/api/v1/reports/{rid}/revision", headers=auth_headers["a"])).json()["revision"]
    await client.post(f"/api/v1/reports/{rid}/common-filters",
                      json={"column": "region", "op": "eq", "value": "N"}, headers=auth_headers["a"])
    after = (await client.get(f"/api/v1/reports/{rid}/revision", headers=auth_headers["a"])).json()["revision"]
    assert after > before


@pytest.mark.asyncio
async def test_common_filters_are_org_scoped(client, auth_headers):
    rid = await _report(client, auth_headers["a"])
    r = await client.post(f"/api/v1/reports/{rid}/common-filters",
                          json={"column": "region", "op": "eq", "value": "N"},
                          headers=auth_headers["b"])
    assert r.status_code in (403, 404)
