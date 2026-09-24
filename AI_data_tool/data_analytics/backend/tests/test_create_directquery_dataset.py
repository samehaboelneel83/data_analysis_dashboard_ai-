import sqlite3

import pytest
from sqlalchemy import select
from app.models.models import DataSource, Dataset, DatasetColumn
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


async def _seed_sqlite_source(db_session, org_id, tmp_path):
    db_path = tmp_path / "source.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany("INSERT INTO sales (region, revenue) VALUES (?, ?)", [("east", 100), ("west", 50)])
    conn.commit()
    conn.close()
    src = DataSource(name="Live DB", type="sqlite", config={"filepath": str(db_path)}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def test_import_with_mode_directquery_creates_dataset_without_a_file(client, db_session, two_orgs, auth_headers, tmp_path):
    src = await _seed_sqlite_source(db_session, two_orgs["a"]["org"].id, tmp_path)

    resp = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Live Sales", "table": "sales", "mode": "directquery"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "directquery"

    result = await db_session.execute(select(Dataset).where(Dataset.id == body["id"]))
    ds = result.scalar_one()
    assert ds.mode == "directquery"
    assert ds.filename is None
    assert ds.data_source_id == src.id
    assert ds.source_table == "sales"
    assert ds.org_id == two_orgs["a"]["org"].id

    cols = await db_session.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id))
    col_names = {c.name for c in cols.scalars().all()}
    assert col_names == {"region", "revenue"}


async def test_import_default_mode_is_still_import(client, db_session, two_orgs, auth_headers, tmp_path):
    """Backward compatibility: existing callers that don't pass `mode` at all must
    keep getting the original file-materializing behavior, unchanged."""
    src = await _seed_sqlite_source(db_session, two_orgs["a"]["org"].id, tmp_path)

    resp = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Imported Sales", "table": "sales"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(Dataset).where(Dataset.id == resp.json()["id"]))
    ds = result.scalar_one()
    assert ds.mode == "import"
    assert ds.filename is not None
    assert ds.row_count == 2


async def test_directquery_dataset_is_immediately_queryable(client, db_session, two_orgs, auth_headers, tmp_path):
    """End-to-end: a dataset created via mode=directquery must work with the
    widget-data endpoint right away, with no separate activation step."""
    src = await _seed_sqlite_source(db_session, two_orgs["a"]["org"].id, tmp_path)
    create_resp = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "Live Sales", "table": "sales", "mode": "directquery"},
        headers=auth_headers["a"],
    )
    ds_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/datasets/{ds_id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    rows = {r["name"]: r["value"] for r in resp.json()["rows"]}
    assert rows == {"east": 100, "west": 50}
