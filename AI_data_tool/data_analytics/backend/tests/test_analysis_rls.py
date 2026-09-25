import pandas as pd
from sqlalchemy import select
from app.core.security import create_access_token, hash_password
from app.models.models import AnalysisResult, Dataset, Role, RowSecurityRule, User


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


async def test_post_analysis_restricted_user_gets_filtered_result_not_cached(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 999}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={}, headers=headers)

    assert resp.status_code == 200
    # The restricted result must not contain any trace of the excluded 999 value.
    assert "999" not in resp.text
    result = await db_session.execute(select(AnalysisResult).where(AnalysisResult.dataset_id == ds.id))
    assert result.scalar_one_or_none() is None  # never written to the shared cache


async def test_get_analysis_restricted_user_never_sees_unrestricted_cache(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 999}],
    )
    # Org admin computes and caches the full, unrestricted analysis first.
    post_resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={}, headers=auth_headers["a"])
    assert post_resp.status_code == 200

    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=headers)

    assert resp.status_code == 404


async def test_get_analysis_unrestricted_user_still_uses_cache(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 100}],
    )
    post_resp = await client.post(f"/api/v1/datasets/{ds.id}/analysis", json={}, headers=auth_headers["a"])
    assert post_resp.status_code == 200

    resp = await client.get(f"/api/v1/datasets/{ds.id}/analysis", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert resp.json() == post_resp.json()
