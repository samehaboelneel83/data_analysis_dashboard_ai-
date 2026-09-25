import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


async def test_malformed_stored_rls_rule_hides_all_rows_not_all_of_them(client, db_session, two_orgs, tmp_path):
    csv_path = tmp_path / "d.csv"
    pd.DataFrame([{"region": "North", "sales": 100}, {"region": "South", "sales": 200}]).to_csv(csv_path, index=False)
    ds = Dataset(name="D", org_id=two_orgs["a"]["org"].id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.flush()

    role = Role(org_id=two_orgs["a"]["org"].id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="restricted-fc@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    # Bypass admin-time validation by inserting the malformed rule directly at the ORM
    # level, simulating a rule that was valid when authored but broke later (e.g. the
    # column it referenced was removed by a dataset re-upload).
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="nonexistent_column_xyz > 5"))
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json()["rows"] == []
