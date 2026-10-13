"""A headline number's change over the period (`change_over`): resolved as
four headline numbers through the widget-data endpoint's own path, so row
rules restrict it as they restrict any chart."""
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, hash_password
from app.models.models import Dataset, DatasetColumn, Role, RowSecurityRule, User
from app.services.period_change import change_over

KPI = {"widget_type": "kpi", "calculated_columns": [], "parameters": {},
       "config": {"measure": "close", "aggregation": "avg", "change_over": "day"}}


def test_only_a_headline_with_a_date_and_a_measure():
    assert change_over("kpi", {"measure": "close", "change_over": "day"}) == "day"
    assert change_over("kpi", {"change_over": "day"}) is None
    assert change_over("bar", {"measure": "close", "change_over": "day"}) is None


@pytest.fixture
async def prices(db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    path = tmp_path / "prices.csv"
    pd.DataFrame({"day": ["2023-01-02", "2023-01-02", "2023-12-28", "2023-12-28"],
                  "member": ["A", "B", "A", "B"], "close": [40.0, 10.0, 60.0, 5.0]}).to_csv(path, index=False)
    ds = Dataset(name="prices", org_id=org.id, mode="import", filename=str(path), row_count=4)
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("day", "datetime"), ("member", "categorical"), ("close", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()
    return org, ds


@pytest.mark.asyncio
async def test_the_change_through_the_api(client, auth_headers, prices):
    _, ds = prices
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=KPI, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["change"]["from"] == 25.0 and r.json()["change"]["to"] == 32.5     # averages of both members
    assert r.json()["rows"][0]["value"] == 30.0


@pytest.mark.asyncio
async def test_a_row_rule_restricts_both_ends(client, db_session, prices):
    org, ds = prices
    role = Role(org_id=org.id, name="member A", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org.id, role_id=role.id, email="member-a@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="member == 'A'"))
    await db_session.commit()
    user = (await db_session.execute(select(User).options(selectinload(User.role))
                                     .where(User.id == user.id))).scalar_one()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=KPI, headers=headers)
    assert r.status_code == 200, r.text
    assert (r.json()["change"]["from"], r.json()["change"]["to"]) == (40.0, 60.0)       # B never counts
    assert r.json()["rows"][0]["value"] == 50.0


@pytest.mark.asyncio
async def test_the_same_change_through_duckdb(client, auth_headers, prices, monkeypatch):
    from app.core.config import settings
    from app.services import duck_agg
    from app.services.frame_cache import clear_frame_cache, write_parquet_sidecar
    from app.services.widget_data import clear_widget_data_cache
    _, ds = prices
    assert write_parquet_sidecar(ds.filename) is True
    clear_widget_data_cache(); clear_frame_cache()
    monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
    ran = {"n": 0}
    real = duck_agg.try_aggregate

    def spy(*a, **kw):
        frame, reason = real(*a, **kw)
        ran["n"] += frame is not None
        return frame, reason
    monkeypatch.setattr(duck_agg, "try_aggregate", spy)
    r = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=KPI, headers=auth_headers["a"])
    clear_widget_data_cache(); clear_frame_cache()
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["value"] == 30.0, (r.json(), ran)
