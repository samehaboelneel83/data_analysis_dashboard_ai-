"""S5 admin_audit trail: security-relevant admin mutations write rows with
actor/action/target, the list endpoint is admin-gated and org-scoped, and
list+filter works."""
import pandas as pd
from sqlalchemy import select

from app.models.models import AdminAudit, Dataset


async def _seed_dataset(db_session, org_id, name="Rule Dataset"):
    csv_path_rows = [{"region": "North", "sales": 100}]
    ds = Dataset(name=name, org_id=org_id, mode="directquery", source_table="sales")
    db_session.add(ds)
    await db_session.flush()
    from app.models.models import DatasetColumn
    db_session.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="string"))
    db_session.add(DatasetColumn(dataset_id=ds.id, name="sales", dtype="number"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_row_security_rule_create_writes_an_audit_row(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200

    rows = (await db_session.execute(
        select(AdminAudit).where(AdminAudit.org_id == two_orgs["a"]["org"].id)
    )).scalars().all()
    matches = [r for r in rows if r.action == "row_security_rule.create"]
    assert len(matches) == 1
    assert matches[0].actor_email == "admin-a@example.com"
    assert matches[0].target == f"dataset:{ds.id}"
    assert matches[0].detail == "region == 'North'"


async def test_row_security_rule_delete_writes_an_audit_row(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)
    created = await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )
    rule_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/admin/row-security-rules/{rule_id}", headers=auth_headers["a"])
    assert resp.status_code == 204

    rows = (await db_session.execute(
        select(AdminAudit).where(AdminAudit.org_id == two_orgs["a"]["org"].id, AdminAudit.action == "row_security_rule.delete")
    )).scalars().all()
    assert len(rows) == 1


async def test_export_policy_change_writes_an_audit_row(client, db_session, two_orgs, auth_headers, tmp_path):
    path = tmp_path / "t.csv"
    pd.DataFrame({"a": [1, 2]}).to_csv(path, index=False)
    ds = Dataset(name="T", filename=str(path), org_id=two_orgs["a"]["org"].id, mode="import")
    db_session.add(ds)
    await db_session.commit()

    resp = await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true", headers=auth_headers["a"])
    assert resp.status_code == 200

    rows = (await db_session.execute(
        select(AdminAudit).where(AdminAudit.org_id == two_orgs["a"]["org"].id, AdminAudit.action == "export_policy.set")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].target == f"dataset:{ds.id}"


async def test_api_key_create_and_revoke_write_audit_rows(client, db_session, two_orgs, auth_headers):
    created = await client.post("/api/v1/auth/api-keys", json={"name": "ci-key"}, headers=auth_headers["a"])
    assert created.status_code == 201
    key_id = created.json()["id"]

    revoked = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=auth_headers["a"])
    assert revoked.status_code == 204

    rows = (await db_session.execute(
        select(AdminAudit).where(AdminAudit.org_id == two_orgs["a"]["org"].id)
    )).scalars().all()
    actions = {r.action for r in rows}
    assert "api_key.create" in actions
    assert "api_key.revoke" in actions


async def test_non_admin_cannot_read_the_admin_audit_endpoint(client, db_session, two_orgs):
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User

    non_admin_role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
    db_session.add(non_admin_role)
    await db_session.flush()
    non_admin = User(org_id=two_orgs["a"]["org"].id, role_id=non_admin_role.id,
                      email="viewer@example.com", password_hash=hash_password("pw"))
    db_session.add(non_admin)
    await db_session.commit()
    await db_session.refresh(non_admin)

    token = create_access_token(non_admin.id, non_admin.org_id)
    resp = await client.get("/api/v1/admin/admin-audit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (401, 403)


async def test_list_and_filter_admin_audit(client, db_session, two_orgs, auth_headers):
    ds = await _seed_dataset(db_session, two_orgs["a"]["org"].id)
    await client.post(
        "/api/v1/admin/row-security-rules",
        json={"role_id": two_orgs["a"]["role"].id, "dataset_id": ds.id, "filter_expr": "region == 'North'"},
        headers=auth_headers["a"],
    )
    await client.post("/api/v1/auth/api-keys", json={"name": "ci-key"}, headers=auth_headers["a"])

    all_rows = (await client.get("/api/v1/admin/admin-audit", headers=auth_headers["a"])).json()
    assert len(all_rows) >= 2

    filtered = (await client.get(
        "/api/v1/admin/admin-audit?action=row_security_rule.create", headers=auth_headers["a"])).json()
    assert len(filtered) == 1
    assert filtered[0]["action"] == "row_security_rule.create"

    by_target = (await client.get(
        f"/api/v1/admin/admin-audit?q=dataset:{ds.id}", headers=auth_headers["a"])).json()
    assert len(by_target) == 1

    # Org isolation: org B sees nothing of org A's audit trail.
    log_b = (await client.get("/api/v1/admin/admin-audit", headers=auth_headers["b"])).json()
    assert log_b == []
