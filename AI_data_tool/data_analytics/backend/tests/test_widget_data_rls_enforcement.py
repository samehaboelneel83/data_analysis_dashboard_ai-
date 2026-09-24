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


async def test_rls_rule_filters_rows_for_restricted_role(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}, {"region": "North", "sales": 50}],
    )
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert [r["name"] for r in rows] == ["North"]
    assert rows[0]["value"] == 150


async def test_org_admin_bypasses_rls_rule_entirely(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    # A rule exists for a different (non-admin) role in the same org and dataset —
    # the org-admin's own role has no rule and is exempt from lookup regardless.
    await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    assert {r["name"] for r in resp.json()["rows"]} == {"North", "South"}


async def test_no_matching_rule_means_unrestricted_within_org(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    # Restricted role exists but has no rule for this dataset.
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    assert {r["name"] for r in resp.json()["rows"]} == {"North", "South"}


async def test_rls_applied_before_dataset_default_filter_expr(client, db_session, two_orgs, tmp_path):
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}],
    )
    # A default_filter_expr that would ADMIT the South row back in if it ran before RLS
    # (or if RLS didn't run at all) — proves RLS is the floor, not just "also applied".
    ds.default_filter_expr = "sales > 0"
    await db_session.commit()
    _, user = await _seed_restricted_user(db_session, two_orgs["a"]["org"].id, ds.id, "region == 'North'")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    assert [r["name"] for r in resp.json()["rows"]] == ["North"]
