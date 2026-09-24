"""Per-report viewer capability levels: view / edit / data, enforced server-side."""
import pandas as pd
import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, DatasetColumn, Report, ReportCapability, Role, User


async def _member(db, org_id, level_role_name):
    role = Role(org_id=org_id, name=level_role_name, is_org_admin=False)
    db.add(role)
    await db.flush()
    user = User(org_id=org_id, role_id=role.id,
                email=f"{level_role_name}-{role.id}@ex.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    return role, user


def _hdr(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}


async def _report(db, org_id, dataset_id=None):
    r = Report(name="R", org_id=org_id, dataset_id=dataset_id)
    db.add(r)
    await db.flush()
    return r


async def _dataset(db, org_id, tmp_path):
    p = tmp_path / "c.csv"
    pd.DataFrame({"region": ["N", "S"], "sales": [1.0, 2.0]}).to_csv(p, index=False)
    ds = Dataset(name="D", org_id=org_id, filename=str(p))
    db.add(ds)
    await db.flush()
    db.add(DatasetColumn(dataset_id=ds.id, name="region", dtype="categorical"))
    db.add(DatasetColumn(dataset_id=ds.id, name="sales", dtype="numeric"))
    return ds


@pytest.mark.asyncio
async def test_unowned_report_is_view_not_a_studio(client, auth_headers, db_session, two_orgs):
    """No author and no capability rows: a member may open it, not it.
    The old default of 'data' is why a View share still showed Edit mode."""
    org = two_orgs["a"]["org"]
    _, user = await _member(db_session, org.id, "unrestricted")
    r = await _report(db_session, org.id)
    await db_session.commit()

    resp = await client.get(f"/api/v1/reports/{r.id}", headers=_hdr(user))
    assert resp.json()["my_capability"] == "view"
    assert (await client.post(f"/api/v1/reports/{r.id}/pages",
            json={"name": "P2", "position": 1}, headers=_hdr(user))).status_code == 403


@pytest.mark.asyncio
async def test_view_level_cannot_mutate_the_report(client, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    role, user = await _member(db_session, org.id, "viewer")
    r = await _report(db_session, org.id)
    db_session.add(ReportCapability(report_id=r.id, role_id=role.id, level="view"))
    await db_session.commit()

    assert (await client.get(f"/api/v1/reports/{r.id}", headers=_hdr(user))).json()["my_capability"] == "view"
    # every structural mutation is refused
    assert (await client.post(f"/api/v1/reports/{r.id}/pages",
            json={"name": "P2", "position": 1}, headers=_hdr(user))).status_code == 403
    assert (await client.patch(f"/api/v1/reports/{r.id}",
            json={"name": "renamed"}, headers=_hdr(user))).status_code == 403
    assert (await client.delete(f"/api/v1/reports/{r.id}", headers=_hdr(user))).status_code == 403


@pytest.mark.asyncio
async def test_edit_level_can_edit_structure_but_not_data(client, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    role, user = await _member(db_session, org.id, "editor")
    ds = await _dataset(db_session, org.id, tmp_path)
    r = await _report(db_session, org.id, dataset_id=ds.id)
    db_session.add(ReportCapability(report_id=r.id, role_id=role.id, level="edit"))
    await db_session.commit()

    # structural edit: allowed
    assert (await client.post(f"/api/v1/reports/{r.id}/pages",
            json={"name": "P2", "position": 1}, headers=_hdr(user))).status_code == 201
    # data-model edit: refused (needs 'data')
    assert (await client.put(f"/api/v1/datasets/{ds.id}/calculated-columns",
            json={"name": "profit", "expression": "sales * 2"}, headers=_hdr(user))).status_code == 403
    assert (await client.post(f"/api/v1/datasets/{ds.id}/measures",
            json={"name": "m", "expression": "SUM(sales)"}, headers=_hdr(user))).status_code == 403


@pytest.mark.asyncio
async def test_data_level_can_edit_the_data_model(client, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    role, user = await _member(db_session, org.id, "datauser")
    ds = await _dataset(db_session, org.id, tmp_path)
    r = await _report(db_session, org.id, dataset_id=ds.id)
    db_session.add(ReportCapability(report_id=r.id, role_id=role.id, level="data"))
    await db_session.commit()

    assert (await client.put(f"/api/v1/datasets/{ds.id}/calculated-columns",
            json={"name": "profit", "expression": "sales * 2"}, headers=_hdr(user))).status_code == 200


@pytest.mark.asyncio
async def test_admin_is_always_data_level(client, auth_headers, db_session, two_orgs):
    """An admin cannot be locked out even by an explicit restriction row."""
    org = two_orgs["a"]["org"]
    admin_role_id = two_orgs["a"]["role"].id
    r = await _report(db_session, org.id)
    db_session.add(ReportCapability(report_id=r.id, role_id=admin_role_id, level="view"))
    await db_session.commit()

    resp = await client.get(f"/api/v1/reports/{r.id}", headers=auth_headers["a"])
    assert resp.json()["my_capability"] == "data"
    assert (await client.post(f"/api/v1/reports/{r.id}/pages",
            json={"name": "P2", "position": 1}, headers=auth_headers["a"])).status_code == 201


@pytest.mark.asyncio
async def test_capability_admin_endpoints(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    role, member = await _member(db_session, org.id, "team")
    r = await _report(db_session, org.id)
    await db_session.commit()

    # set the team role to view-only
    resp = await client.put(f"/api/v1/reports/{r.id}/capabilities",
                            json={"levels": {str(role.id): "view"}}, headers=auth_headers["a"])
    assert resp.status_code == 200
    assert resp.json()["levels"] == {str(role.id): "view"}
    # read back
    got = await client.get(f"/api/v1/reports/{r.id}/capabilities", headers=auth_headers["a"])
    assert got.json()["levels"] == {str(role.id): "view"}
    # the member now sees view
    assert (await client.get(f"/api/v1/reports/{r.id}", headers=_hdr(member))).json()["my_capability"] == "view"
    # 'data' is the default and is stored as no-restriction
    resp = await client.put(f"/api/v1/reports/{r.id}/capabilities",
                            json={"levels": {str(role.id): "data"}}, headers=auth_headers["a"])
    assert resp.json()["levels"] == {}


@pytest.mark.asyncio
async def test_non_admin_cannot_touch_capabilities(client, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    _, member = await _member(db_session, org.id, "plain")
    r = await _report(db_session, org.id)
    await db_session.commit()
    assert (await client.get(f"/api/v1/reports/{r.id}/capabilities", headers=_hdr(member))).status_code == 403
    assert (await client.put(f"/api/v1/reports/{r.id}/capabilities",
            json={"levels": {}}, headers=_hdr(member))).status_code == 403


@pytest.mark.asyncio
async def test_invalid_level_and_foreign_role_rejected(client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    role, _ = await _member(db_session, org.id, "x")
    r = await _report(db_session, org.id)
    await db_session.commit()
    assert (await client.put(f"/api/v1/reports/{r.id}/capabilities",
            json={"levels": {str(role.id): "superuser"}}, headers=auth_headers["a"])).status_code == 400
    assert (await client.put(f"/api/v1/reports/{r.id}/capabilities",
            json={"levels": {"999999": "view"}}, headers=auth_headers["a"])).status_code == 400
