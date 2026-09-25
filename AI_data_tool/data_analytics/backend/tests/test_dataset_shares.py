import pandas as pd
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, DatasetColumn, DatasetShare, Role, RowSecurityRule, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.flush()
    for col_name in rows[0].keys():
        dtype = "numeric" if isinstance(rows[0][col_name], (int, float)) else "string"
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col_name, dtype=dtype))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_non_admin_user(db_session, org_id, email="viewer@example.com", role_name="Viewer"):
    role = Role(org_id=org_id, name=role_name, is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(role)
    return role, user


def _headers_for(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_admin_shares_dataset_with_org_user(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 1}])
    _, target = await _seed_non_admin_user(db_session, two_orgs["a"]["org"].id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/shares", json={"user_id": target.id}, headers=auth_headers["a"])

    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == target.id
    assert body["email"] == target.email
    row = (await db_session.execute(
        select(DatasetShare).where(DatasetShare.dataset_id == ds.id, DatasetShare.user_id == target.id)
    )).scalar_one()
    assert row is not None


async def test_share_target_from_another_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 1}])
    other_org_user = two_orgs["b"]["user"]

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/shares", json={"user_id": other_org_user.id}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_share_dataset_from_another_org_returns_404(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["b"]["org"].id, [{"region": "North", "sales": 1}])
    _, target = await _seed_non_admin_user(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/shares", json={"user_id": target.id}, headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_shared_dataset_appears_flagged_in_viewers_list(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 1}])
    _, target = await _seed_non_admin_user(db_session, two_orgs["a"]["org"].id)
    await client.post(f"/api/v1/datasets/{ds.id}/shares", json={"user_id": target.id}, headers=auth_headers["a"])

    resp = await client.get("/api/v1/datasets", headers=_headers_for(target))

    assert resp.status_code == 200
    row = next(d for d in resp.json() if d["id"] == ds.id)
    assert row["shared"] is True


async def test_non_admin_cannot_create_or_delete_shares(client, db_session, two_orgs, auth_headers, tmp_path):
    """SH1 adjustment: a dataset has no owner concept, so share MANAGEMENT is
    admin-gated (mirrors row-security-rule admin gating) even though read access
    to any org dataset was already open before this feature existed."""
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 1}])
    _, non_admin = await _seed_non_admin_user(db_session, two_orgs["a"]["org"].id, email="non-admin@example.com")
    _, target = await _seed_non_admin_user(db_session, two_orgs["a"]["org"].id, email="target@example.com", role_name="Target")

    create_resp = await client.post(
        f"/api/v1/datasets/{ds.id}/shares", json={"user_id": target.id}, headers=_headers_for(non_admin),
    )
    assert create_resp.status_code == 403

    admin_share = await client.post(
        f"/api/v1/datasets/{ds.id}/shares", json={"user_id": target.id}, headers=auth_headers["a"],
    )
    share_id = admin_share.json()["id"]

    delete_resp = await client.delete(f"/api/v1/datasets/{ds.id}/shares/{share_id}", headers=_headers_for(non_admin))
    assert delete_resp.status_code == 403


async def test_unshare_revokes_the_grant(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _seed_dataset_with_file(db_session, tmp_path, two_orgs["a"]["org"].id, [{"region": "North", "sales": 1}])
    _, target = await _seed_non_admin_user(db_session, two_orgs["a"]["org"].id)
    share = (await client.post(
        f"/api/v1/datasets/{ds.id}/shares", json={"user_id": target.id}, headers=auth_headers["a"],
    )).json()

    del_resp = await client.delete(f"/api/v1/datasets/{ds.id}/shares/{share['id']}", headers=auth_headers["a"])
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/datasets/{ds.id}/shares", headers=auth_headers["a"])
    assert list_resp.json() == []

    viewer_list = await client.get("/api/v1/datasets", headers=_headers_for(target))
    row = next(d for d in viewer_list.json() if d["id"] == ds.id)
    assert row["shared"] is False


async def test_shared_viewer_reads_dataset_with_their_own_rls_identity(client, db_session, two_orgs, auth_headers, tmp_path):
    """The value-pinned proof: two users sharing the SAME restricted role each see
    only their own rows through the shared dataset -- RLS resolves per-viewer at
    the base-frame path, not per the admin who set up the share."""
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, two_orgs["a"]["org"].id,
        [{"owner_email": "alice@example.com", "sales": 100},
         {"owner_email": "bob@example.com", "sales": 200},
         {"owner_email": "alice@example.com", "sales": 50}],
    )
    role = Role(org_id=two_orgs["a"]["org"].id, name="Owner-scoped", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="`owner_email` == USEREMAIL()"))
    alice = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="alice@example.com", password_hash=hash_password("pw"))
    bob = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="bob@example.com", password_hash=hash_password("pw"))
    db_session.add_all([alice, bob])
    await db_session.commit()
    await db_session.refresh(alice)
    await db_session.refresh(bob)

    await client.post(f"/api/v1/datasets/{ds.id}/shares", json={"user_id": alice.id}, headers=auth_headers["a"])
    await client.post(f"/api/v1/datasets/{ds.id}/shares", json={"user_id": bob.id}, headers=auth_headers["a"])

    alice_resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=_headers_for(alice))
    bob_resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=_headers_for(bob))

    assert alice_resp.status_code == 200 and bob_resp.status_code == 200
    alice_body, bob_body = alice_resp.json(), bob_resp.json()
    assert alice_body["total"] == 2
    assert {row[0] for row in alice_body["rows"]} == {"alice@example.com"}
    assert bob_body["total"] == 1
    assert {row[0] for row in bob_body["rows"]} == {"bob@example.com"}
