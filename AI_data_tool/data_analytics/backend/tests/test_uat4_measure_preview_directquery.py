"""UAT-4 (16 Oct 2026): the measure builder's Test on a live (DirectQuery)
dataset answered 404 "Dataset not found" -- the route required a file.

It now reads the live rows the way Insights does (services/analysis_frame:
row security pushed down with the query, denied columns dropped on arrival)
and evaluates the draft measure over them. When the source holds more rows
than one live read may pull, the preview would be a sample, so it refuses
with a 422 saying so rather than show an estimate as the answer.
"""
import sqlite3

import pytest

from app.core.security import create_access_token, hash_password
from app.models.models import (ColumnSecurityRule, DataSource, Dataset, DatasetColumn, Role,
                               RowSecurityRule, User)


def _db(tmp_path, rows):
    path = tmp_path / "hr.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE hr (dept TEXT, headcount REAL, salary REAL)")
    conn.executemany("INSERT INTO hr VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return str(path)


ROWS = (("Eng", 5, 90000.0), ("Eng", 3, 85000.0), ("Ops", 4, 60000.0))


async def _dq(db, org, tmp_path, rows=ROWS):
    src = DataSource(name="Live HR", type="sqlite", config={"filepath": _db(tmp_path, rows)}, org_id=org.id)
    db.add(src)
    await db.flush()
    ds = Dataset(name="HR live", org_id=org.id, mode="directquery", data_source_id=src.id, source_table="hr")
    db.add(ds)
    await db.flush()
    for c, t in (("dept", "categorical"), ("headcount", "numeric"), ("salary", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t))
    await db.commit()
    return ds


async def _restricted(db, org, ds):
    role = Role(org_id=org.id, name="ops-no-salary", is_org_admin=False)
    db.add(role)
    await db.flush()
    db.add(ColumnSecurityRule(role_id=role.id, dataset_id=ds.id, denied_columns=["salary"]))
    db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="dept == 'Ops'"))
    user = User(org_id=org.id, role_id=role.id, email="ops@example.com", password_hash=hash_password("pw"))
    db.add(user)
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id)}"}


@pytest.mark.asyncio
async def test_preview_on_a_live_dataset_evaluates_instead_of_not_found(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _dq(db_session, two_orgs["a"]["org"], tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(headcount)"}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["sample"][0]["value"] == 12

    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(headcount)", "group_by": "dept"}, headers=auth_headers["a"])
    assert {s["group"]: s["value"] for s in r.json()["sample"]} == {"Eng": 8, "Ops": 4}


@pytest.mark.asyncio
async def test_live_preview_respects_row_and_column_security(client, db_session, two_orgs, tmp_path):
    org = two_orgs["a"]["org"]
    ds = await _dq(db_session, org, tmp_path)
    headers = await _restricted(db_session, org, ds)
    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(headcount)"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["sample"][0]["value"] == 4            # Ops rows only
    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(salary)"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False                            # unknown to this reader, never 60000
    assert "60000" not in r.text and "235000" not in r.text


@pytest.mark.asyncio
async def test_live_preview_over_the_row_cap_refuses_rather_than_sampling(client, db_session, two_orgs, auth_headers,
                                                                          tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "analysis_row_cap", 2, raising=False)
    ds = await _dq(db_session, two_orgs["a"]["org"], tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(headcount)"}, headers=auth_headers["a"])
    assert r.status_code == 422, r.text
    assert "not found" not in r.text.lower()
    assert "live" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_other_org_still_not_found(client, db_session, two_orgs, auth_headers, tmp_path):
    ds = await _dq(db_session, two_orgs["a"]["org"], tmp_path)
    r = await client.post(f"/api/v1/datasets/{ds.id}/measures/preview",
                          json={"expression": "SUM(headcount)"}, headers=auth_headers["b"])
    assert r.status_code == 404
