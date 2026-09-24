"""Phase 7.6: the semantic layer as an API -- a notebook gets the governed frame,
through an API key acting as its user."""
import pandas as pd
import pytest

from app.core.api_keys import generate
from app.core.security import hash_password
from app.models.models import (ApiKey, ColumnSecurityRule, Dataset, DatasetColumn, Role,
                               RowSecurityRule, User)


@pytest.fixture
def salesfile(tmp_path):
    p = tmp_path / "s.csv"
    pd.DataFrame({"region": ["US", "US", "EU", "EU"], "product": ["a", "b", "a", "b"],
                  "amount": [10.0, 20.0, 40.0, 30.0], "email": ["x@a", "y@a", "z@a", "w@a"],
                  "salary": [1, 2, 3, 4]}).to_csv(p, index=False)
    return str(p)


async def _ds(db, org, path, meta=None):
    ds = Dataset(name="Sales", filename=path, org_id=org.id, mode="import", column_meta=meta or {},
                 measures=[{"name": "Share", "expression": "SUM(amount) / TOTAL(SUM(amount))"}])
    db.add(ds)
    await db.flush()
    for c, sem in (("region", None), ("product", None), ("amount", None), ("email", "email"), ("salary", None)):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="categorical", semantic_type=sem))
    await db.commit()
    return ds


async def _restricted_key(db, org, ds):
    """A non-admin whose role sees only US rows and not `salary`, with an API key."""
    role = Role(org_id=org.id, name="analyst", is_org_admin=False)
    db.add(role)
    await db.flush()
    db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="`region` == 'US'"))
    db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["salary"]))
    user = User(org_id=org.id, role_id=role.id, email="nb@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    ds.created_by = None  # an unowned dataset stays readable to members (fixture convention)
    full, prefix, key_hash = generate()
    db.add(ApiKey(org_id=org.id, user_id=user.id, name="notebook", prefix=prefix, key_hash=key_hash))
    await db.commit()
    return {"Authorization": f"Bearer {full}"}


@pytest.mark.asyncio
async def test_a_notebook_key_gets_its_users_governed_frame(client, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    ds = await _ds(db_session, org, salesfile)
    h = await _restricted_key(db_session, org, ds)
    cat = (await client.get("/api/v1/semantic/datasets", headers=h)).json()["datasets"]
    mine = next(d for d in cat if d["id"] == ds.id)
    assert "salary" not in [c["name"] for c in mine["columns"]] and mine["measures"][0]["name"] == "Share"
    rows = (await client.get(f"/api/v1/semantic/datasets/{ds.id}/rows", headers=h)).json()
    assert rows["total_rows"] == 2 and "salary" not in rows["columns"]
    q = (await client.post("/api/v1/semantic/query", headers=h, json={
        "dataset_id": ds.id, "dimensions": ["product"],
        "measures": ["Share", {"column": "amount", "agg": "sum"}]})).json()
    got = {r[0]: r for r in q["rows"]}
    assert q["columns"] == ["product", "rows", "Share", "sum_amount"]
    assert got["a"][3] == 10.0 and got["b"][2] == pytest.approx(20 / 30)
    r = await client.post("/api/v1/semantic/query", headers=h, json={
        "dataset_id": ds.id, "dimensions": ["salary"], "measures": []})
    assert r.status_code == 400 and "not available to you" in r.json()["detail"]


@pytest.mark.asyncio
async def test_policy_and_sensitivity_hold_on_the_api(client, auth_headers, db_session, two_orgs, salesfile):
    org = two_orgs["a"]["org"]
    ds = await _ds(db_session, org, salesfile, meta={"__sensitivity__": "Confidential"})
    rows = (await client.get(f"/api/v1/semantic/datasets/{ds.id}/rows?format=json", headers=auth_headers["a"])).json()
    assert "email" not in rows["columns"]          # personal data redacted
    csv = await client.get(f"/api/v1/semantic/datasets/{ds.id}/rows?format=csv", headers=auth_headers["a"])
    assert csv.status_code == 200 and "amount" in csv.text
    ds2 = await _ds(db_session, org, salesfile, meta={"__exports_disabled__": True})
    blocked = await client.get(f"/api/v1/semantic/datasets/{ds2.id}/rows", headers=auth_headers["a"])
    assert blocked.status_code == 403 and "API is an export" in blocked.json()["detail"]
    assert (await client.get(f"/api/v1/semantic/datasets/{ds.id}/rows", headers=auth_headers["b"])).status_code == 404
