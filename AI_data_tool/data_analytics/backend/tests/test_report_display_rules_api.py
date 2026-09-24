import pytest

from app.models.models import Report


@pytest.mark.asyncio
async def test_new_report_defaults_to_no_display_rules(client, auth_headers):
    created = await client.post("/api/v1/reports", json={"name": "R"}, headers=auth_headers["a"])

    assert created.status_code == 201
    assert created.json()["display_rules"] == []


@pytest.mark.asyncio
async def test_report_display_rules_round_trip_through_patch(client, auth_headers):
    created = await client.post("/api/v1/reports", json={"name": "R"}, headers=auth_headers["a"])
    report_id = created.json()["id"]
    rules = [{"id": "r1", "kind": "value_map", "target": "mark", "any_category": True,
              "mappings": [{"value": "US", "color": "#6c8fff"}]}]

    patched = await client.patch(f"/api/v1/reports/{report_id}", json={"display_rules": rules},
                                 headers=auth_headers["a"])

    assert patched.status_code == 200
    assert patched.json()["display_rules"] == rules
    fetched = await client.get(f"/api/v1/reports/{report_id}", headers=auth_headers["a"])
    assert fetched.json()["display_rules"] == rules


@pytest.mark.asyncio
async def test_editing_display_rules_bumps_the_report_revision(client, auth_headers):
    """A report-level rule restyles every page, so another open session must be told.
    Asserting persistence alongside the bump is what keeps this test non-vacuous: the
    revision moves on ANY patch, so a bump alone would prove nothing about display_rules."""
    created = await client.post("/api/v1/reports", json={"name": "R"}, headers=auth_headers["a"])
    report_id = created.json()["id"]
    before = created.json()["revision"]
    rules = [{"id": "r1", "kind": "expression", "target": "background",
              "expression": "value > 1000", "style": {"background": "#fee2e2"}}]

    patched = await client.patch(f"/api/v1/reports/{report_id}",
                                 json={"display_rules": rules}, headers=auth_headers["a"])

    assert patched.status_code == 200
    assert patched.json()["display_rules"] == rules
    assert patched.json()["revision"] > before
