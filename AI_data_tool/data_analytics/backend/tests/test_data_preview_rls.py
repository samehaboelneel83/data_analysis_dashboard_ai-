import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_restricted_user(db_session, org_id, rule_dataset_id=None, rule_filter_expr=None):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    if rule_dataset_id is not None:
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


def _headers_for(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_data_preview_applies_rls_rule(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}, {"region": "North", "sales": 50}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=_headers_for(user),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    regions = {row[0] for row in body["rows"]}
    assert regions == {"North"}


async def test_data_preview_org_admin_sees_all_rows(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_data_preview_includes_saved_calculated_columns_when_request_sends_none(
        client, db_session, two_orgs, auth_headers, tmp_path):
    """The dashboard Data tab always posts calculated_columns: []. The dataset
    page sends the saved list. Preview must apply the dataset's own columns in
    both cases, or a formula visible on the dataset is missing on the dashboard."""
    from sqlalchemy.orm.attributes import flag_modified

    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 50}],
    )
    ds.calculated_columns = [{"name": "all_employee_count", "expression": "SUM(sales)"}]
    flag_modified(ds, "calculated_columns")
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/data-preview",
        json={"filters": [], "calculated_columns": []},
        headers=auth_headers["a"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "all_employee_count" in body["columns"]
    idx = body["columns"].index("all_employee_count")
    assert {row[idx] for row in body["rows"]} == {150}
