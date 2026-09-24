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


async def _seed_restricted_user(db_session, org_id, rule_dataset_id, rule_filter_expr):
    role = Role(org_id=org_id, name="Restricted", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(
        org_id=org_id, role_id=role.id,
        email=f"restricted-{role.id}@example.com", password_hash=hash_password("pw"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=rule_dataset_id, filter_expr=rule_filter_expr))
    await db_session.commit()
    await db_session.refresh(user)
    return role, user


async def test_filter_preview_total_and_passing_reflect_rls_restricted_set(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}, {"region": "North", "sales": 50}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/filter-preview", json={"expression": "sales > 0"}, headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2   # not 3 — the South row must not count toward total either
    assert body["passing"] == 2
