"""HR evaluation 2026-10-01, Phase 2: governance.

2.2 a connection's label is a floor for every dataset read from it.
2.4 a Confidential dataset starts with exports switched off while governed.
2.5 a dataset can be shared with a role or an org unit, view-only or edit.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.capability import can_read_dataset, require_dataset_capability
from app.core.security import create_access_token
from app.models.models import (DataSource, Dataset, DatasetGroupShare, OrgUnit, Role,
                               User, UserOrgUnit)
from app.services.sensitivity import apply_confidential_export_default, dataset_effective


async def _member(db, org_id, email, role_name="HR managers"):
    role = Role(org_id=org_id, name=role_name, is_org_admin=False)
    db.add(role)
    await db.flush()
    u = User(org_id=org_id, role_id=role.id, email=email, password_hash="x")
    db.add(u)
    await db.flush()
    await db.refresh(u, ["role"])
    return u, role


async def _dataset(db, org_id, owner_id, src_id=None, name="Current workforce"):
    ds = Dataset(name=name, org_id=org_id, filename=None, mode="directquery",
                 data_source_id=src_id, created_by=owner_id, row_count=0, col_count=0, file_size=0)
    db.add(ds)
    await db.flush()
    return ds


@pytest.mark.asyncio
async def test_connection_label_is_a_floor(db_session, two_orgs):
    org = two_orgs["a"]["org"].id
    src = DataSource(name="Employees", type="postgresql", org_id=org, sensitivity="Confidential")
    db_session.add(src)
    await db_session.flush()
    ds = await _dataset(db_session, org, two_orgs["a"]["user"].id, src.id)
    label, why = await dataset_effective(db_session, ds.id)
    assert label == "Confidential" and "Employees" in why[0]
    assert await apply_confidential_export_default(db_session, ds) is True
    assert ds.column_meta["__exports_disabled__"]["auto_private"] is True
    # an explicit policy is never overwritten
    assert await apply_confidential_export_default(db_session, ds) is False


@pytest.mark.asyncio
async def test_role_share_opens_read_and_view_blocks_authoring(db_session, two_orgs):
    org = two_orgs["a"]["org"].id
    ds = await _dataset(db_session, org, two_orgs["a"]["user"].id)
    member, role = await _member(db_session, org, "mgr@example.com")
    assert not await can_read_dataset(db_session, member, ds.id)
    db_session.add(DatasetGroupShare(org_id=org, dataset_id=ds.id, role_id=role.id, level="view"))
    await db_session.flush()
    assert await can_read_dataset(db_session, member, ds.id)
    with pytest.raises(HTTPException) as e:
        await require_dataset_capability(db_session, member, ds.id, "data")
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_org_unit_share_reaches_people_placed_below_it(db_session, two_orgs):
    org = two_orgs["a"]["org"].id
    ds = await _dataset(db_session, org, two_orgs["a"]["user"].id)
    hr = OrgUnit(org_id=org, name="HR", level_name="Department", match_value="HR")
    db_session.add(hr)
    await db_session.flush()
    payroll = OrgUnit(org_id=org, name="Payroll", level_name="Team", match_value="Payroll", parent_id=hr.id)
    db_session.add(payroll)
    await db_session.flush()
    member, _ = await _member(db_session, org, "payroll@example.com", "Payroll staff")
    db_session.add(UserOrgUnit(user_id=member.id, org_unit_id=payroll.id))
    db_session.add(DatasetGroupShare(org_id=org, dataset_id=ds.id, org_unit_id=hr.id, level="edit"))
    await db_session.flush()
    assert await can_read_dataset(db_session, member, ds.id)
    await require_dataset_capability(db_session, member, ds.id, "data")   # edit share: allowed


@pytest.mark.asyncio
async def test_share_api_by_role(client, db_session, two_orgs, auth_headers):
    org = two_orgs["a"]["org"].id
    ds = await _dataset(db_session, org, two_orgs["a"]["user"].id)
    _, role = await _member(db_session, org, "m2@example.com")
    await db_session.commit()
    r = await client.post(f"/api/v1/datasets/{ds.id}/shares",
                          json={"role_id": role.id, "level": "view"}, headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "role" and r.json()["name"] == "HR managers"
    lst = (await client.get(f"/api/v1/datasets/{ds.id}/shares", headers=auth_headers["a"])).json()
    assert any(x["kind"] == "role" and x["level"] == "view" for x in lst)
    gid = next(x["id"] for x in lst if x["kind"] == "role")
    d = await client.delete(f"/api/v1/datasets/{ds.id}/group-shares/{gid}", headers=auth_headers["a"])
    assert d.status_code == 204
