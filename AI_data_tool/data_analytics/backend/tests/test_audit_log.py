"""The audit log: append-only, org-scoped, admin-readable."""
import pytest
from sqlalchemy import select

from app.models.models import AuditLogEntry, Dataset


async def _entries(db, org_id):
    return (await db.execute(
        select(AuditLogEntry).where(AuditLogEntry.org_id == org_id)
    )).scalars().all()


@pytest.mark.asyncio
async def test_creating_and_deleting_a_report_are_recorded(client, auth_headers, db_session, two_orgs):
    r = await client.post("/api/v1/reports", json={"name": "Audited"}, headers=auth_headers["a"])
    rid = r.json()["id"]
    await client.delete(f"/api/v1/reports/{rid}", headers=auth_headers["a"])

    entries = await _entries(db_session, two_orgs["a"]["org"].id)
    actions = [(e.action, e.entity_id) for e in entries]
    assert ("report.create", rid) in actions
    assert ("report.delete", rid) in actions
    # The email is denormalised so the trail outlives the user row.
    assert all(e.user_email == "admin-a@example.com" for e in entries)


@pytest.mark.asyncio
async def test_a_rolled_back_action_leaves_no_entry(client, auth_headers, db_session, two_orgs):
    """The log must never claim something happened that did not: deleting a report in
    another org 404s before the mutation, so no entry may exist either."""
    r = await client.post("/api/v1/reports", json={"name": "Mine"}, headers=auth_headers["a"])
    rid = r.json()["id"]

    resp = await client.delete(f"/api/v1/reports/{rid}", headers=auth_headers["b"])
    assert resp.status_code == 404

    entries_b = await _entries(db_session, two_orgs["b"]["org"].id)
    assert entries_b == []


@pytest.mark.asyncio
async def test_the_log_is_admin_only_and_org_scoped(client, auth_headers, two_orgs):
    await client.post("/api/v1/reports", json={"name": "A's report"}, headers=auth_headers["a"])

    log_a = (await client.get("/api/v1/admin/audit-log", headers=auth_headers["a"])).json()
    log_b = (await client.get("/api/v1/admin/audit-log", headers=auth_headers["b"])).json()
    assert any(e["action"] == "report.create" for e in log_a)
    # Org B sees none of org A's activity -- asserted from B's side, the stronger claim.
    assert all(e["action"] != "report.create" or e["detail"] != "A's report" for e in log_b)
    assert log_b == []


@pytest.mark.asyncio
async def test_a_whole_table_export_is_recorded(client, auth_headers, db_session, two_orgs, tmp_path):
    """Exports move data out of the org boundary, which is exactly what an audit trail
    exists to answer questions about."""
    import pandas as pd
    path = tmp_path / "t.csv"
    pd.DataFrame({"a": [1, 2]}).to_csv(path, index=False)
    ds = Dataset(name="T", filename=str(path), org_id=two_orgs["a"]["org"].id, mode="import")
    db_session.add(ds)
    await db_session.commit()

    await client.get(f"/api/v1/datasets/{ds.id}/export", headers=auth_headers["a"])

    entries = await _entries(db_session, two_orgs["a"]["org"].id)
    export = [e for e in entries if e.action == "dataset.export"]
    assert len(export) == 1
    assert export[0].entity_id == ds.id
    assert "2 rows" in export[0].detail


async def _details(db, org_id, action):
    return [e.detail for e in await _entries(db, org_id) if e.action == action]


@pytest.mark.asyncio
async def test_an_org_quota_is_written_in_words_without_none(client, auth_headers, db_session, two_orgs, monkeypatch):
    """AD-18: 'queries=None asks=None storage_mb=None…' read as code."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "super_admin_emails", "admin-a@example.com")
    org_b = two_orgs["b"]["org"].id
    r = await client.put(f"/api/v1/platform/organizations/{org_b}/quota",
                         json={"max_queries_per_day": 500}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    [detail] = await _details(db_session, two_orgs["a"]["org"].id, "platform.set_org_quota")
    assert "None" not in detail and "=" not in detail
    assert "Daily queries: 500" in detail and "AI asks per day: no limit" in detail


@pytest.mark.asyncio
async def test_share_changes_name_who_not_a_grant_id(client, auth_headers, db_session, two_orgs):
    from app.models.models import Role
    role = Role(org_id=two_orgs["a"]["org"].id, name="Sales", is_org_admin=False)
    db_session.add(role)
    await db_session.commit()
    rid = (await client.post("/api/v1/reports", json={"name": "Shared"}, headers=auth_headers["a"])).json()["id"]
    g = await client.post(f"/api/v1/reports/{rid}/grants", json={"role_id": role.id, "level": "view"},
                          headers=auth_headers["a"])
    assert g.status_code == 201, g.text
    gid = g.json()["id"]
    await client.patch(f"/api/v1/reports/{rid}/grants/{gid}", json={"can_export": False}, headers=auth_headers["a"])
    await client.delete(f"/api/v1/reports/{rid}/grants/{gid}", headers=auth_headers["a"])
    org = two_orgs["a"]["org"].id
    [changed] = await _details(db_session, org, "report.share_change")
    [removed] = await _details(db_session, org, "report.unshare")
    for d in (changed, removed):
        assert "grant:" not in d and "role Sales" in d
    assert "no downloads" in changed
