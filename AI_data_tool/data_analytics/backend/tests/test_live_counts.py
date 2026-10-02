"""4.5: a live dataset shows its row count, cached for an hour."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import DataSource, Dataset
from app.services.live_counts import STAMP, is_stale


@pytest.fixture
def hr_db(tmp_path):
    path = tmp_path / "hr.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE emp (n INTEGER); INSERT INTO emp VALUES (1),(2),(3);")
    con.commit()
    con.close()
    return path


async def _live(db, org, path):
    src = DataSource(name="HR", type="sqlite", config={"filepath": str(path)}, org_id=org.id)
    db.add(src)
    await db.flush()
    ds = Dataset(name="Current workforce", org_id=org.id, mode="directquery", data_source_id=src.id,
                 source_query="SELECT * FROM emp", row_count=0, column_meta={})
    db.add(ds)
    await db.commit()
    return ds, path


@pytest.mark.asyncio
async def test_counts_then_caches_then_recounts_when_forced(client, auth_headers, db_session, two_orgs, hr_db):
    ds, path = await _live(db_session, two_orgs["a"]["org"], hr_db)
    r = (await client.post(f"/api/v1/datasets/{ds.id}/live-count", headers=auth_headers["a"])).json()
    assert r["row_count"] == 3 and r["live"] and r["counted_at"]
    con = sqlite3.connect(path); con.execute("INSERT INTO emp VALUES (4)"); con.commit(); con.close()
    cached = (await client.post(f"/api/v1/datasets/{ds.id}/live-count", headers=auth_headers["a"])).json()
    assert cached["row_count"] == 3, "within the hour the cached count is served"
    fresh = (await client.post(f"/api/v1/datasets/{ds.id}/live-count?force=true", headers=auth_headers["a"])).json()
    assert fresh["row_count"] == 4
    listed = (await client.get("/api/v1/datasets", headers=auth_headers["a"])).json()
    assert next(d for d in listed if d["id"] == ds.id)["row_count"] == 4


@pytest.mark.asyncio
async def test_other_org_cannot_ask(client, auth_headers, db_session, two_orgs, hr_db):
    ds, _ = await _live(db_session, two_orgs["a"]["org"], hr_db)
    r = await client.post(f"/api/v1/datasets/{ds.id}/live-count", headers=auth_headers["b"])
    assert r.status_code == 404


def test_staleness():
    d = Dataset(column_meta={})
    assert is_stale(d)
    d.column_meta = {STAMP: datetime.now(timezone.utc).isoformat()}
    assert not is_stale(d)
    d.column_meta = {STAMP: (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}
    assert is_stale(d)


@pytest.mark.asyncio
async def test_certify_and_uncertify_admin_only(client, auth_headers, db_session, two_orgs, hr_db):
    """4.7: an admin marks the dataset to use; pickers read it off column_meta."""
    ds, _ = await _live(db_session, two_orgs["a"]["org"], hr_db)
    on = await client.post(f"/api/v1/datasets/{ds.id}/certify", json={"note": "HR source of truth"},
                           headers=auth_headers["a"])
    assert on.status_code == 200 and on.json()["certified"] is True
    listed = (await client.get("/api/v1/datasets", headers=auth_headers["a"])).json()
    row = next(d for d in listed if d["id"] == ds.id)
    assert row["column_meta"]["__certified__"]["note"] == "HR source of truth"
    assert "created_by" in row
    off = await client.post(f"/api/v1/datasets/{ds.id}/certify", json={"certified": False}, headers=auth_headers["a"])
    assert off.json()["certified"] is False
    other = await client.post(f"/api/v1/datasets/{ds.id}/certify", json={}, headers=auth_headers["b"])
    assert other.status_code == 404
