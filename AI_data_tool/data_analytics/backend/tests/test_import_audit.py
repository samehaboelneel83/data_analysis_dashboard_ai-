"""E07: who brought which data in, from where, and how much.

Exports, shares and deletes were audited; the imports themselves were not --
an org could see who downloaded a dataset but not who loaded it."""
import sqlite3

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.models import AuditLogEntry, DataSource

BODY = b"region,amount\nNorth,1\nSouth,2\n"


@pytest.fixture(autouse=True)
def _uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def _entries(db_session, action):
    return (await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.action == action)
        .order_by(AuditLogEntry.id).execution_options(populate_existing=True))).scalars().all()


def _sqlite(tmp_path, n=3):
    path = tmp_path / "src.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(n)])
    conn.commit()
    conn.close()
    return str(path)


async def test_an_upload_is_audited(client, db_session, two_orgs, auth_headers):
    r = await client.post("/api/v1/datasets", files={"file": ("sales.csv", BODY, "text/csv")},
                          data={"name": "Sales", "description": ""}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    [e] = await _entries(db_session, "dataset.upload")
    assert e.entity_id == r.json()["id"] and e.user_id == two_orgs["a"]["user"].id
    assert e.detail == "sales.csv -> 2 rows, 2 columns"


async def test_a_batch_audits_each_dataset_and_the_refusals(client, db_session, two_orgs, auth_headers):
    r = await client.post("/api/v1/datasets/batch",
                          files=[("files", ("a.csv", BODY, "text/csv")),
                                 ("files", ("empty.csv", b"a,b\n", "text/csv")),
                                 ("files", ("c.csv", b"x\n1\n", "text/csv"))],
                          data={"name": "B", "description": "", "mode": "separate"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    ups = await _entries(db_session, "dataset.upload")
    assert [e.detail.split(" ")[0] for e in ups] == ["a.csv", "c.csv"]
    [failed] = await _entries(db_session, "dataset.upload_failed")
    assert failed.detail == "1 of 3 refused: empty.csv"


async def test_a_database_import_is_audited_and_a_reimport_says_so(
        client, db_session, two_orgs, auth_headers, tmp_path):
    src = DataSource(name="Warehouse", type="sqlite", config={"filepath": _sqlite(tmp_path)},
                     org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    r = await client.post(f"/api/v1/data-sources/{src.id}/import", headers=auth_headers["a"],
                          json={"dataset_name": "T", "table": "t"})
    assert r.status_code == 200, r.text
    [e] = await _entries(db_session, "dataset.import")
    assert e.entity_id == r.json()["id"] and e.detail == "Warehouse (sqlite) t -> 3 rows"

    r2 = await client.post(f"/api/v1/data-sources/{src.id}/import", headers=auth_headers["a"],
                           json={"dataset_name": "T", "dataset_id": r.json()["id"], "query": "SELECT *\n  FROM t WHERE id < 2"})
    assert r2.status_code == 200, r2.text
    e2 = (await _entries(db_session, "dataset.reimport"))[-1]
    assert e2.detail == "Warehouse (sqlite) query: SELECT * FROM t WHERE id < 2 -> 2 rows"


async def test_a_manual_refresh_is_audited(client, db_session, two_orgs, auth_headers, tmp_path):
    src = DataSource(name="Warehouse", type="sqlite", config={"filepath": _sqlite(tmp_path, 4)},
                     org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    r = await client.post(f"/api/v1/data-sources/{src.id}/import", headers=auth_headers["a"],
                          json={"dataset_name": "T", "table": "t"})
    ds_id = r.json()["id"]
    r = await client.post(f"/api/v1/datasets/{ds_id}/refresh", headers=auth_headers["a"], json={})
    assert r.status_code == 200, r.text
    [e] = await _entries(db_session, "dataset.refresh")
    assert e.entity_id == ds_id and e.detail == "full from Warehouse -> 4 rows"


async def test_a_quota_refusal_leaves_no_imported_file(
        client, db_session, two_orgs, auth_headers, tmp_path, monkeypatch):
    """QuotaExceeded is not an HTTPException; catching only the latter left
    the refused import's CSV on disk."""
    from app.services import quotas

    async def over(*a, **k):
        raise quotas.QuotaExceeded("Storage quota reached", status_code=413, kind="storage")

    monkeypatch.setattr(quotas, "enforce_storage_quota", over)
    src = DataSource(name="W", type="sqlite", config={"filepath": _sqlite(tmp_path)},
                     org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    r = await client.post(f"/api/v1/data-sources/{src.id}/import", headers=auth_headers["a"],
                          json={"dataset_name": "T", "table": "t"})
    assert r.status_code == 413, r.text
    root = tmp_path / "uploads"
    assert not [p for p in root.rglob("*") if p.is_file()]
    assert await _entries(db_session, "dataset.import") == []
