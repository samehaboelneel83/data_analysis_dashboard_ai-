"""3.13: "Your access, and why" names the row and column rules on the report's data."""
import pandas as pd
import pytest

from app.models.models import (ColumnSecurityRule, Dataset, Organization, Report, Role,
                               RowSecurityRule, User)
from app.routers.authz import _report_data_rules


@pytest.fixture
async def world(db_session, tmp_path):
    p = tmp_path / "emp.csv"
    pd.DataFrame({"dept": ["d001"], "salary": [1]}).to_csv(p, index=False)
    org = Organization(name="HR Co")
    db_session.add(org)
    await db_session.flush()
    role = Role(name="Dept manager", org_id=org.id)
    admin = Role(name="Admin", org_id=org.id, is_org_admin=True)
    db_session.add_all([role, admin])
    await db_session.flush()
    mgr = User(email="m@hr.co", password_hash="x", org_id=org.id, role_id=role.id)
    mgr.role = role
    boss = User(email="b@hr.co", password_hash="x", org_id=org.id, role_id=admin.id)
    boss.role = admin
    ds = Dataset(name="Current workforce", org_id=org.id, mode="import", filename=str(p))
    open_ds = Dataset(name="Departments", org_id=org.id, mode="import", filename=str(p))
    db_session.add_all([mgr, boss, ds, open_ds])
    await db_session.flush()
    rep = Report(name="Headcount", org_id=org.id, dataset_id=ds.id, additional_dataset_ids=[open_ds.id])
    db_session.add(rep)
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="owner == USEREMAIL()"))
    db_session.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["salary"]))
    await db_session.commit()
    return {"mgr": mgr, "boss": boss, "rep": rep, "ds": ds}


@pytest.mark.asyncio
async def test_rules_listed_with_the_resolved_filter(db_session, world):
    got = await _report_data_rules(db_session, world["mgr"], world["rep"], "view", "Shared with your role.")
    assert got["allowed"] is True
    assert len(got["rules"]) == 1, "the dataset with no rule is not listed"
    r = got["rules"][0]
    assert r["dataset_name"] == "Current workforce"
    assert r["row_rule"] == "owner == USEREMAIL()"
    assert "m@hr.co" in r["row_rule_for_you"]
    assert r["hidden_columns"] == ["salary"]
    assert "Dept manager" in got["reason"]


@pytest.mark.asyncio
async def test_admin_sees_everything_and_is_told_so(db_session, world):
    got = await _report_data_rules(db_session, world["boss"], world["rep"], "data", "Admin.")
    assert got["rules"] == [] and "every row and every column" in got["reason"]


@pytest.mark.asyncio
async def test_no_access_no_rules(db_session, world):
    got = await _report_data_rules(db_session, world["mgr"], world["rep"], "none", "Not shared.")
    assert got["allowed"] is False and got["rules"] == []
