"""4.2 / 4.3: Browse keeps saved queries and the last runs, and downloads CSV
under the connection's sensitivity."""
import sqlite3

import pytest

from app.models.models import DataSource


@pytest.fixture
def hr_db(tmp_path):
    path = tmp_path / "hr.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE dept_emp (emp_no INTEGER, dept_no TEXT, to_date TEXT);
        INSERT INTO dept_emp VALUES (1, 'd001', '9999-01-01'), (2, 'd001', '1999-01-01'), (3, 'd002', '9999-01-01');
    """)
    con.commit()
    con.close()
    return path


async def _source(db, org, path, sensitivity=None):
    src = DataSource(name="HR", type="sqlite", config={"filepath": str(path)}, org_id=org.id)
    if sensitivity:
        src.sensitivity = sensitivity
    db.add(src)
    await db.commit()
    return src


Q = "SELECT dept_no, COUNT(*) AS n FROM dept_emp WHERE to_date = '9999-01-01' GROUP BY dept_no"


@pytest.mark.asyncio
async def test_a_run_query_lands_in_history_once(client, auth_headers, db_session, two_orgs, hr_db):
    src = await _source(db_session, two_orgs["a"]["org"], hr_db)
    for _ in range(2):
        r = await client.post(f"/api/v1/data-sources/{src.id}/preview", json={"query": Q, "limit": 50},
                              headers=auth_headers["a"])
        assert r.status_code == 200, r.text
    got = (await client.get(f"/api/v1/data-sources/{src.id}/queries", headers=auth_headers["a"])).json()
    assert [h["sql"] for h in got["history"]] == [Q], "the same statement twice is one history entry"
    # browsing a table is not a query run
    await client.post(f"/api/v1/data-sources/{src.id}/preview", json={"table": "dept_emp"}, headers=auth_headers["a"])
    got = (await client.get(f"/api/v1/data-sources/{src.id}/queries", headers=auth_headers["a"])).json()
    assert len(got["history"]) == 1


@pytest.mark.asyncio
async def test_history_keeps_the_last_20(client, auth_headers, db_session, two_orgs, hr_db):
    src = await _source(db_session, two_orgs["a"]["org"], hr_db)
    for i in range(23):
        await client.post(f"/api/v1/data-sources/{src.id}/preview",
                          json={"query": f"SELECT {i} AS n", "limit": 5}, headers=auth_headers["a"])
    hist = (await client.get(f"/api/v1/data-sources/{src.id}/queries", headers=auth_headers["a"])).json()["history"]
    assert len(hist) == 20 and hist[0]["sql"] == "SELECT 22 AS n"


@pytest.mark.asyncio
async def test_save_rename_free_update_and_delete(client, auth_headers, db_session, two_orgs, hr_db):
    src = await _source(db_session, two_orgs["a"]["org"], hr_db)
    a = await client.post(f"/api/v1/data-sources/{src.id}/queries", json={"name": "Workforce", "sql": Q},
                          headers=auth_headers["a"])
    assert a.status_code == 201
    b = await client.post(f"/api/v1/data-sources/{src.id}/queries", json={"name": "Workforce", "sql": Q + " "},
                          headers=auth_headers["a"])
    assert b.json()["id"] == a.json()["id"], "saving under the same name updates it"
    saved = (await client.get(f"/api/v1/data-sources/{src.id}/queries", headers=auth_headers["a"])).json()["saved"]
    assert [s["name"] for s in saved] == ["Workforce"]
    other = await client.delete(f"/api/v1/data-sources/{src.id}/queries/{a.json()['id']}", headers=auth_headers["b"])
    assert other.status_code == 404, "another org cannot delete it"
    ok = await client.delete(f"/api/v1/data-sources/{src.id}/queries/{a.json()['id']}", headers=auth_headers["a"])
    assert ok.status_code == 204


@pytest.mark.asyncio
async def test_csv_download_and_restricted_refusal(client, auth_headers, db_session, two_orgs, hr_db):
    src = await _source(db_session, two_orgs["a"]["org"], hr_db)
    r = await client.post(f"/api/v1/data-sources/{src.id}/query-csv", json={"query": Q}, headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.content.decode("utf-8-sig").splitlines()
    assert body[0] == "dept_no,n" and "d001,1" in body
    assert r.headers["X-Truncated"] == "0"
    locked = await _source(db_session, two_orgs["a"]["org"], hr_db, sensitivity="Restricted")
    no = await client.post(f"/api/v1/data-sources/{locked.id}/query-csv", json={"query": Q}, headers=auth_headers["a"])
    assert no.status_code == 403 and "Restricted" in no.json()["detail"]


@pytest.mark.asyncio
async def test_a_missing_database_file_is_said_plainly(client, auth_headers, db_session, two_orgs, tmp_path):
    """5.3: "unable to open database file" named no file and no fix."""
    src = DataSource(name="Gone", type="sqlite", config={"filepath": str(tmp_path / "nope.db")},
                     org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    t = (await client.post(f"/api/v1/data-sources/{src.id}/test", headers=auth_headers["a"])).json()
    assert t["ok"] is False and t["error"].startswith("Database file not found at ")
    assert "edit the connection" in t["error"]
    s = await client.get(f"/api/v1/data-sources/{src.id}/schema", headers=auth_headers["a"])
    assert s.status_code == 400 and "Database file not found" in s.json()["detail"]
    assert not (tmp_path / "nope.db").exists(), "testing must not create an empty database file"
