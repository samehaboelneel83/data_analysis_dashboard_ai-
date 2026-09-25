"""Per-destination export policy and the auto-disable-when-private trigger."""
import pandas as pd
import pytest

from app.models.models import ColumnSecurityRule, Dataset, Role, RowSecurityRule


async def _dataset(db, org_id, tmp_path):
    p = tmp_path / "exp.csv"
    pd.DataFrame({"region": ["N", "S"], "sales": [1.0, 2.0]}).to_csv(p, index=False)
    ds = Dataset(name="E", org_id=org_id, filename=str(p))
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


@pytest.mark.asyncio
async def test_per_format_policy_blocks_only_listed_destinations(client, auth_headers, db_session, two_orgs, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/export-policy",
                          json={"formats": ["xlsx", "tsv"]}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["export_policy"] == {"formats": ["tsv", "xlsx"]}

    # whole-table export: csv still allowed, tsv blocked
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 200
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=tsv",
                             headers=auth_headers["a"])).status_code == 403

    # widget export: csv allowed, xlsx blocked
    body = {"widget_type": "table", "config": {"columns": ["region", "sales"]}}
    ok = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=csv",
                           json=body, headers=auth_headers["a"])
    assert ok.status_code == 200
    blocked = await client.post(f"/api/v1/datasets/{ds.id}/widget-data/export?format=xlsx",
                                json=body, headers=auth_headers["a"])
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_auto_private_tracks_security_rules_live(client, auth_headers, db_session, two_orgs, tmp_path):
    """auto_private is evaluated at export time: adding a rule later closes
    exports with no policy revisit; removing it reopens them."""
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org.id, tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/export-policy",
                          json={"auto_private": True}, headers=auth_headers["a"])
    assert r.status_code == 200

    # no security rules yet: exports open
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 200

    role = Role(org_id=org.id, name="Restricted-x", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    rule = RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'N'")
    db_session.add(rule)
    await db_session.commit()

    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 403

    await db_session.delete(rule)
    await db_session.commit()
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 200


@pytest.mark.asyncio
async def test_column_rules_also_count_as_private(client, auth_headers, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org.id, tmp_path)
    await client.post(f"/api/v1/datasets/{ds.id}/export-policy",
                      json={"auto_private": True}, headers=auth_headers["a"])
    role = Role(org_id=org.id, name="Restricted-y", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["sales"]))
    await db_session.commit()
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 403


@pytest.mark.asyncio
async def test_legacy_boolean_contract_still_works(client, auth_headers, db_session, two_orgs, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=true", headers=auth_headers["a"])
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 403
    await client.post(f"/api/v1/datasets/{ds.id}/export-policy?disabled=false", headers=auth_headers["a"])
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export?format=csv",
                             headers=auth_headers["a"])).status_code == 200


@pytest.mark.asyncio
async def test_non_admin_cannot_read_or_write_policy(client, db_session, two_orgs, tmp_path, auth_headers):
    from app.core.security import create_access_token, hash_password
    from app.models.models import User
    org = two_orgs["a"]["org"]
    ds = await _dataset(db_session, org.id, tmp_path)
    role = Role(org_id=org.id, name="Viewer-z", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="viewer-z@example.com",
                password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    assert (await client.post(f"/api/v1/datasets/{ds.id}/export-policy",
                              json={"formats": ["csv"]}, headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/datasets/{ds.id}/export-policy",
                             headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_junk_formats_rejected(client, auth_headers, db_session, two_orgs, tmp_path):
    ds = await _dataset(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/export-policy",
                          json={"formats": ["pdf", "csv"]}, headers=auth_headers["a"])
    assert r.status_code == 400
