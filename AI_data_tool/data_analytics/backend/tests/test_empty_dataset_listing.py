"""A dataset with no rows must not break the dataset list.

Found by building an AI-proposed dashboard whose query was valid and returned
nothing. The import stores one `missing_pct` per column as
`df[col].isnull().mean() * 100`, and on an empty frame pandas returns NaN. NaN is
not valid JSON, so `GET /api/v1/datasets` raised

    ValueError: Out of range float values are not JSON compliant: nan

and returned 500 -- for the WHOLE organisation. One empty dataset, and the
Datasets page and the Ask AI scope picker both go blank for everybody, with no
clue which row caused it.

An empty query is an ordinary thing to write. It must produce an empty dataset,
not a broken tenant.
"""
import sqlite3

import pytest
from sqlalchemy import select

from app.models.models import DataSource, Dataset, DatasetColumn


async def _source_with_an_empty_table(db_session, org_id, tmp_path):
    db_path = tmp_path / "src.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE events (id INTEGER, label TEXT, amount REAL)")
    conn.commit()
    conn.close()
    src = DataSource(name="Empty", type="sqlite",
                     config={"filepath": str(db_path)}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def test_importing_an_empty_result_succeeds(client, db_session, two_orgs,
                                                  auth_headers, tmp_path):
    src = await _source_with_an_empty_table(db_session, two_orgs["a"]["org"].id, tmp_path)
    r = await client.post(f"/api/v1/data-sources/{src.id}/import",
                          json={"dataset_name": "Nothing", "table": "events",
                                "mode": "import"},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    assert r.json()["row_count"] == 0


async def test_the_dataset_list_still_loads_afterwards(client, db_session, two_orgs,
                                                       auth_headers, tmp_path):
    """The regression itself: one empty dataset used to 500 the whole list."""
    src = await _source_with_an_empty_table(db_session, two_orgs["a"]["org"].id, tmp_path)
    await client.post(f"/api/v1/data-sources/{src.id}/import",
                      json={"dataset_name": "Nothing", "table": "events", "mode": "import"},
                      headers=auth_headers["a"])

    listed = await client.get("/api/v1/datasets", headers=auth_headers["a"])

    assert listed.status_code == 200, listed.text
    assert any(d["name"] == "Nothing" for d in listed.json())


async def test_the_empty_dataset_can_be_opened(client, db_session, two_orgs,
                                               auth_headers, tmp_path):
    src = await _source_with_an_empty_table(db_session, two_orgs["a"]["org"].id, tmp_path)
    made = await client.post(f"/api/v1/data-sources/{src.id}/import",
                             json={"dataset_name": "Nothing", "table": "events",
                                   "mode": "import"},
                             headers=auth_headers["a"])
    got = await client.get(f"/api/v1/datasets/{made.json()['id']}",
                           headers=auth_headers["a"])
    assert got.status_code == 200, got.text


async def test_missing_pct_is_a_number_not_nan(client, db_session, two_orgs,
                                               auth_headers, tmp_path):
    """The stored value, not just the response. NaN in the column row is what
    made every later serialisation of it fail."""
    src = await _source_with_an_empty_table(db_session, two_orgs["a"]["org"].id, tmp_path)
    made = await client.post(f"/api/v1/data-sources/{src.id}/import",
                             json={"dataset_name": "Nothing", "table": "events",
                                   "mode": "import"},
                             headers=auth_headers["a"])
    cols = (await db_session.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == made.json()["id"])
    )).scalars().all()
    assert cols, "no columns were recorded"
    for c in cols:
        assert c.missing_pct == c.missing_pct, f"{c.name} stored NaN"
