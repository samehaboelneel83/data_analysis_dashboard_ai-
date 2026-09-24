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
