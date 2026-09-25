"""S0: USEREMAIL()/USERID()/ORGID()/ORGNAME() must expand in ORDINARY author
expressions -- a dataset's default_filter_expr, calculated columns, measures -- not
just inside RLS rules. Before this, `apply_user_context` only ran in
`resolve_rls_expr`; `default_filter_expr` and calculated columns reached the pandas
pipeline as literal text, so `USEREMAIL()` in an author filter never resolved."""
import pandas as pd
from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, Role, User


async def _seed_dataset_with_file(db_session, tmp_path, org_id, rows, name="Test Dataset"):
    csv_path = tmp_path / f"{name.replace(' ', '_')}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    ds = Dataset(name=name, org_id=org_id, filename=str(csv_path))
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_user(db_session, org_id, email, role_name="Member"):
    role = Role(org_id=org_id, name=role_name, is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _headers_for(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def test_default_filter_expr_useremail_scopes_rows_per_viewing_user(client, db_session, two_orgs, tmp_path):
    org_id = two_orgs["a"]["org"].id
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, org_id,
        [{"owner": "alice@example.com", "sales": 100}, {"owner": "bob@example.com", "sales": 200}],
    )
    ds.default_filter_expr = "owner == USEREMAIL()"
    await db_session.commit()

    alice = await _seed_user(db_session, org_id, "alice@example.com")
    bob = await _seed_user(db_session, org_id, "bob@example.com")

    body = {"config": {"dimension": "owner", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"}

    resp_alice = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=_headers_for(alice))
    resp_bob = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=_headers_for(bob))

    assert resp_alice.status_code == 200 and resp_bob.status_code == 200
    assert [r["name"] for r in resp_alice.json()["rows"]] == ["alice@example.com"]
    assert [r["name"] for r in resp_bob.json()["rows"]] == ["bob@example.com"]


async def test_default_filter_expr_orgid_expands(client, db_session, two_orgs, tmp_path):
    org_id = two_orgs["a"]["org"].id
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, org_id,
        [{"org": org_id, "sales": 100}, {"org": org_id + 999, "sales": 200}],
    )
    ds.default_filter_expr = "org == ORGID()"
    await db_session.commit()
    user = await _seed_user(db_session, org_id, "orgid-user@example.com")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "org", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    assert [r["value"] for r in resp.json()["rows"]] == [100]


async def test_default_filter_expr_orgname_with_whitespace_still_expands(client, db_session, two_orgs, tmp_path):
    """The substitution regex tolerates `ORGNAME ( )` (whitespace before/inside
    the parens); the preload check that decides whether to bother fetching
    org_name at all must tolerate the same shape, or the token survives
    substitution unexpanded and the filter fails closed (zero rows) instead
    of matching this org."""
    org = two_orgs["a"]["org"]
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, org.id,
        [{"org_name": org.name, "sales": 100}, {"org_name": "Someone Else Inc", "sales": 200}],
    )
    ds.default_filter_expr = "org_name == ORGNAME ( )"
    await db_session.commit()
    user = await _seed_user(db_session, org.id, "orgname-ws-user@example.com")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "org_name", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    assert [r["value"] for r in resp.json()["rows"]] == [100]


async def test_default_filter_expr_orgname_expands(client, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    ds = await _seed_dataset_with_file(
        db_session, tmp_path, org.id,
        [{"org_name": org.name, "sales": 100}, {"org_name": "Someone Else Inc", "sales": 200}],
    )
    ds.default_filter_expr = "org_name == ORGNAME()"
    await db_session.commit()
    user = await _seed_user(db_session, org.id, "orgname-user@example.com")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "org_name", "measure": "sales", "aggregation": "sum"}, "widget_type": "bar"},
        headers=_headers_for(user),
    )

    assert resp.status_code == 200
    assert [r["value"] for r in resp.json()["rows"]] == [100]
