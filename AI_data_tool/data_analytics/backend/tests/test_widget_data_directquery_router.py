import sqlite3

import pytest

from app.models.models import DataSource, Dataset, DatasetColumn, Role, RowSecurityRule, User
from app.core.security import create_access_token, hash_password
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    # The DirectQuery cache key includes data_source_id (a small per-test
    # autoincrement int, not globally unique across the test run) and
    # source_table (often "sales" across many tests here) -- without clearing
    # between tests, an earlier test's cache entry could collide with a later
    # one's key and leak stale data across unrelated tests.
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
                                     columns=("region", "revenue"), calculated_columns=None,
                                     default_filter_expr=None):
    ds = Dataset(
        name="DQ Dataset", org_id=org_id, mode="directquery",
        data_source_id=data_source_id, source_table=source_table,
        calculated_columns=calculated_columns or [], default_filter_expr=default_filter_expr,
    )
    db_session.add(ds)
    await db_session.flush()
    for col in columns:
        db_session.add(DatasetColumn(dataset_id=ds.id, name=col, dtype="string"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def _seed_viewer(db_session, org_id, email):
    """A non-admin role + user, returning both the Role (so a RowSecurityRule can be
    attached to it) and bearer auth headers for that user."""
    role = Role(org_id=org_id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=org_id, role_id=role.id, email=email, password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}
    return role, headers


async def test_directquery_widget_non_admin_with_no_rule_sees_all_org_data(client, db_session, two_orgs, tmp_path):
    """Phase 2 lifts the Phase 1 admin-only restriction now that RLS pushdown exists.
    No rule for (role, dataset) means unrestricted within the org, matching import
    mode's resolve_rls_expr semantics exactly."""
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)
    _, headers = await _seed_viewer(db_session, org_id, "viewer-no-rule@example.com")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "widget_type": "bar"},
        headers=headers,
    )

    assert resp.status_code == 200
    rows = {r["name"] for r in resp.json()["rows"]}
    assert rows == {"east", "west"}


async def test_directquery_widget_non_admin_with_rule_sees_only_matching_rows(client, db_session, two_orgs, tmp_path):
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)
    role, headers = await _seed_viewer(db_session, org_id, "viewer-with-rule@example.com")
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="region == 'east'"))
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "widget_type": "bar"},
        headers=headers,
    )

    assert resp.status_code == 200
    rows = {r["name"] for r in resp.json()["rows"]}
    assert rows == {"east"}


async def test_directquery_widget_org_admin_bypasses_rls_rule(client, db_session, two_orgs, auth_headers, tmp_path):
    """An org-admin role bypasses RLS entirely (resolve_rls_expr returns None for
    is_org_admin roles), even if some OTHER role has a restrictive rule on this
    dataset -- the admin must still see every row."""
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)
    other_role = Role(org_id=org_id, name="Restricted Viewer", is_org_admin=False)
    db_session.add(other_role)
    await db_session.flush()
    db_session.add(RowSecurityRule(role_id=other_role.id, dataset_id=ds.id, filter_expr="region == 'east'"))
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    rows = {r["name"] for r in resp.json()["rows"]}
    assert rows == {"east", "west"}


async def test_directquery_widget_untranslatable_rls_rule_returns_400_not_data(client, db_session, two_orgs, tmp_path):
    """Fail-closed at the HTTP layer: an untranslatable rule must surface as an
    error, never as a 200 with unfiltered (potentially over-exposed) data."""
    org_id = two_orgs["a"]["org"].id
    db_path = _seed_sqlite_sales_db(tmp_path)
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)
    role, headers = await _seed_viewer(db_session, org_id, "viewer-bad-rule@example.com")
    db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="SUM(revenue) > 100"))
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue"}, "widget_type": "bar"},
        headers=headers,
    )

    assert resp.status_code == 400


async def test_directquery_widget_cross_org_data_source_returns_404(client, db_session, two_orgs, auth_headers):
    src_b = await _seed_data_source(db_session, two_orgs["b"]["org"].id)
    # A dataset owned by org A but whose data_source_id points at org B's source.
    ds = await _seed_directquery_dataset(db_session, two_orgs["a"]["org"].id, src_b.id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_directquery_widget_rejects_calculated_columns(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    src = await _seed_data_source(db_session, org_id)
    ds = await _seed_directquery_dataset(
        db_session, org_id, src.id, calculated_columns=[{"name": "x", "expression": "1"}],
    )

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_directquery_widget_rejects_default_filter_expr(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    src = await _seed_data_source(db_session, org_id)
    ds = await _seed_directquery_dataset(db_session, org_id, src.id, default_filter_expr="revenue > 0")

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_directquery_widget_cache_ttl_zero_always_fetches_fresh_data(client, db_session, two_orgs, auth_headers, tmp_path):
    db_path = _seed_sqlite_sales_db(tmp_path, rows=[("east", 100)])
    org_id = two_orgs["a"]["org"].id
    src = await _seed_data_source(db_session, org_id, config={"filepath": db_path})
    src.cache_ttl_seconds = 0
    await db_session.commit()
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)
    body = {"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "widget_type": "bar"}

    first = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert first.json()["rows"][0]["value"] == 100

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE sales SET revenue = 999 WHERE region = 'east'")
    conn.commit()
    conn.close()

    second = await client.post(f"/api/v1/datasets/{ds.id}/widget-data", json=body, headers=auth_headers["a"])
    assert second.json()["rows"][0]["value"] == 999  # cache_ttl_seconds=0 means always fresh


async def test_directquery_widget_end_to_end_returns_aggregated_series(client, db_session, two_orgs, auth_headers, tmp_path):
    db_path = tmp_path / "router_e2e.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany(
        "INSERT INTO sales (region, revenue) VALUES (?, ?)",
        [("east", 100), ("east", 50), ("west", 30)],
    )
    conn.commit()
    conn.close()

    org_id = two_orgs["a"]["org"].id
    src = await _seed_data_source(db_session, org_id, config={"filepath": str(db_path)})
    ds = await _seed_directquery_dataset(db_session, org_id, src.id)

    resp = await client.post(
        f"/api/v1/datasets/{ds.id}/widget-data",
        json={"config": {"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "widget_type": "bar"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    body = resp.json()
    rows = {r["name"]: r["value"] for r in body["rows"]}
    assert rows == {"east": 150, "west": 30}
    assert body["total"] == 3
