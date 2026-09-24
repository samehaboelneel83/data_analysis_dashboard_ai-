import sqlite3

import pytest

from app.models.models import DataSource, Dataset, DatasetColumn, RowSecurityRule, Role, User
from app.core.security import create_access_token, hash_password
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


async def _seed_data_source(db_session, org_id, name="Live DB", type_="sqlite", config=None):
    src = DataSource(name=name, type=type_, config=config or {}, org_id=org_id)
    db_session.add(src)
    await db_session.flush()
    return src


def _seed_sqlite_sales_db(tmp_path, rows=(("east", 100), ("east", 50), ("west", 30))):
    db_path = tmp_path / "sales.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany("INSERT INTO sales (region, revenue) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()
    return str(db_path)


async def _seed_directquery_dataset(db_session, org_id, data_source_id, source_table="sales",
                                     columns=("region", "revenue")):
    ds = Dataset(
        name="DQ Dataset", org_id=org_id, mode="directquery",
        data_source_id=data_source_id, source_table=source_table,
    )
    db_session.add(ds)
    await db_session.flush()
    for col in columns:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype="string"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_data_preview_directquery_returns_rows(client, db_session, two_orgs, auth_headers, tmp_path):
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)

    resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=auth_headers["a"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["region", "revenue"]
    assert body["total"] == 3


async def test_data_preview_directquery_applies_rls(client, db_session, two_orgs, tmp_path):
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)
    role = Role(org_id=org_id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'east'"))
    user = User(org_id=org_id, role_id=role.id, email="viewer@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(f"/api/v1/datasets/{ds.id}/data-preview", json={}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["total"] == 2
