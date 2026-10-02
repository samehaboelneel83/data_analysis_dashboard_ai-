"""HR re-test 2026-10-01: every model widget fitted on the live workforce
dataset, but saving a model (for the Score widget) was refused as
"import-mode datasets only". Training now reads the secured live frame."""
import sqlite3

import pytest

from app.models.models import DataSource, Dataset, DatasetColumn


@pytest.mark.asyncio
async def test_a_model_trains_on_a_live_dataset(client, auth_headers, db_session, two_orgs, tmp_path):
    org_id = two_orgs["a"]["org"].id
    path = tmp_path / "live_hr.db"
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE staff (title TEXT, dept TEXT, salary REAL)")
    rows = []
    for i in range(300):
        title = ["Engineer", "Senior Staff", "Staff"][i % 3]
        dept = ["Sales", "Development"][i % 2]
        salary = {"Engineer": 60000, "Senior Staff": 80000, "Staff": 67000}[title] + (i % 7) * 100
        rows.append((title, dept, salary))
    con.executemany("INSERT INTO staff VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()
    src = DataSource(name="Live HR", type="sqlite", org_id=org_id, config={"filepath": str(path)})
    db_session.add(src)
    await db_session.flush()
    ds = Dataset(name="Live staff", org_id=org_id, mode="directquery",
                 data_source_id=src.id, source_table="staff")
    db_session.add(ds)
    await db_session.flush()
    for c, t in (("title", "categorical"), ("dept", "categorical"), ("salary", "numeric")):
        db_session.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db_session.commit()

    r = await client.post(f"/api/v1/datasets/{ds.id}/prediction-models",
                          json={"name": "Salary model", "target": "salary",
                                "predictors": ["title", "dept"]},
                          headers=auth_headers["a"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["target"] == "salary" and body["task"] == "regression"
    assert body["score"] is not None and body["score"] > 0.9
