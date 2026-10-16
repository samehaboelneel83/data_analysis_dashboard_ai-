"""QA E-13: a role that may not see a column must not see the measures and
calculated columns built on it either -- their formulas name the column
("Margin % = (SUM(revenue) - SUM(cost)) / SUM(revenue) * 100") -- and the UI
must know when the reader cannot change the data model."""
import pandas as pd

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, Dataset, DatasetColumn, Report,
                               ReportCapability, Role, User)

MEASURES = [{"name": "Margin %", "expression": "(SUM(revenue) - SUM(cost)) / SUM(revenue) * 100"},
            {"name": "Revenue", "expression": "SUM(revenue)"},
            {"name": "Unit cost total", "expression": "SUM(unit_cost)"}]
CALCS = [{"name": "unit_cost", "expression": "cost / qty"},          # over the denied column
         {"name": "unit_rev", "expression": "revenue / qty"},
         {"name": "unit_margin", "expression": "unit_rev - unit_cost"}]  # through unit_cost


async def _setup(db, org, tmp_path):
    p = tmp_path / "sales.csv"
    pd.DataFrame({"region": ["EMEA"], "revenue": [10.0], "cost": [4.0], "qty": [2]}).to_csv(p, index=False)
    ds = Dataset(name="Sales", filename=str(p), org_id=org.id, mode="import",
                 measures=MEASURES, calculated_columns=CALCS)
    db.add(ds)
    await db.flush()
    for c in ("region", "revenue", "cost", "qty"):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="numeric"))
    role = Role(org_id=org.id, name="EMEA", is_org_admin=False)
    db.add(role)
    await db.flush()
    db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["cost"]))
    user = User(org_id=org.id, role_id=role.id, email="emea@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    return ds, role, {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


async def test_list_measures_hides_measures_over_denied_columns(client, db_session, two_orgs, auth_headers, tmp_path):
    ds, _, headers = await _setup(db_session, two_orgs["a"]["org"], tmp_path)
    r = await client.get(f"/api/v1/datasets/{ds.id}/measures", headers=headers)
    assert r.status_code == 200
    assert [m["name"] for m in r.json()] == ["Revenue"]
    assert "cost" not in r.text
    admin = await client.get(f"/api/v1/datasets/{ds.id}/measures", headers=auth_headers["a"])
    assert [m["name"] for m in admin.json()] == ["Margin %", "Revenue", "Unit cost total"]


async def test_dataset_get_and_calc_list_omit_calc_columns_over_denied_columns(
        client, db_session, two_orgs, auth_headers, tmp_path):
    ds, _, headers = await _setup(db_session, two_orgs["a"]["org"], tmp_path)
    detail = await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)
    assert [c["name"] for c in detail.json()["calculated_columns"]] == ["unit_rev"]
    listed = await client.get(f"/api/v1/datasets/{ds.id}/calculated-columns", headers=headers)
    assert [c["name"] for c in listed.json()] == ["unit_rev"]
    admin = await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])
    assert len(admin.json()["calculated_columns"]) == 3


async def test_saving_a_measure_keeps_the_ones_the_reader_cannot_see(client, db_session, two_orgs, tmp_path):
    ds, _, headers = await _setup(db_session, two_orgs["a"]["org"], tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/measures", headers=headers,
                          json={"name": "Qty", "expression": "SUM(qty)"})
    assert r.status_code == 200, r.text
    await db_session.refresh(ds)
    assert {m["name"] for m in ds.measures} == {"Margin %", "Revenue", "Unit cost total", "Qty"}


async def test_can_model_says_whether_the_reader_may_change_the_model(
        client, db_session, two_orgs, auth_headers, tmp_path):
    ds, role, headers = await _setup(db_session, two_orgs["a"]["org"], tmp_path)
    assert (await client.get(f"/api/v1/datasets/{ds.id}", headers=auth_headers["a"])).json()["can_model"] is True
    assert (await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)).json()["can_model"] is True
    report = Report(name="R", org_id=ds.org_id, dataset_id=ds.id)
    db_session.add(report)
    await db_session.flush()
    db_session.add(ReportCapability(report_id=report.id, role_id=role.id, level="view"))
    await db_session.commit()
    assert (await client.get(f"/api/v1/datasets/{ds.id}", headers=headers)).json()["can_model"] is False
