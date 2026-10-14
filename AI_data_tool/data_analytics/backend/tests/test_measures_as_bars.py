"""A bar of several measures and no category: one bar per measure, each
resolved through the widget-data endpoint's own single-measure path -- so a
row rule restricts every bar exactly as it restricts any chart."""
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, DatasetColumn, Role, RowSecurityRule, User
from app.services.multi_measure import measures_as_bars

ITEMS = {"widget_type": "bar", "calculated_columns": [], "parameters": {},
         "config": {"measures": ["q1", "q2"], "aggregation": "avg"}}


def test_only_a_bar_with_several_measures_and_no_category():
    assert measures_as_bars("bar", {"measures": ["q1", "q2"]}) == ["q1", "q2"]
    assert measures_as_bars("bar", {"measures": ["q1", "q2"], "dimension": "team"}) is None
    assert measures_as_bars("bar", {"measures": ["q1"]}) is None
    assert measures_as_bars("line", {"measures": ["q1", "q2"]}) is None


@pytest.fixture
async def scores(db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    path = tmp_path / "scores.csv"
    pd.DataFrame({"team": ["A", "A", "B"], "q1": [4, 2, 9], "q2": [5, 3, 9]}).to_csv(path, index=False)
    ds = Dataset(name="scores", org_id=org.id, mode="import", filename=str(path), row_count=3)
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("team", "categorical"), ("q1", "numeric"), ("q2", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()
    return org, ds


@pytest.mark.asyncio
async def test_each_bar_is_its_measure_s_average(client, auth_headers, scores):
    _, ds = scores
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=ITEMS, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"q1": 5.0, "q2": 17 / 3}


@pytest.mark.asyncio
async def test_a_row_rule_restricts_every_bar(client, db_session, scores):
    org, ds = scores
    role = Role(org_id=org.id, name="team A", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="a-team@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="team == 'A'"))
    await db_session.commit()
    user = (await db_session.execute(select(User).options(selectinload(User.role))
                                     .where(User.id == user.id))).scalar_one()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=ITEMS, headers=headers)
    assert r.status_code == 200, r.text
    assert {x["name"]: x["value"] for x in r.json()["rows"]} == {"q1": 3.0, "q2": 4.0}   # team B's 9s never count
