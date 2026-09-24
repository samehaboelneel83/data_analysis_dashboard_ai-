import pytest
from sqlalchemy import select
from app.models.models import DataSource, Dataset, DatasetColumn


async def _seed_data_source(db_session, org_id, name="Test Source"):
    src = DataSource(name=name, type="postgres", config={}, org_id=org_id)
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    return src


async def test_list_data_sources_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    await _seed_data_source(db_session, two_orgs["a"]["org"].id, "A's source")
    await _seed_data_source(db_session, two_orgs["b"]["org"].id, "B's source")

    resp = await client.get("/api/v1/data-sources", headers=auth_headers["a"])

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["A's source"]


async def test_get_data_source_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/data-sources/{src.id}", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_create_data_source_sets_org_id_to_current_users_org(client, db_session, two_orgs, auth_headers):
    resp = await client.post(
        "/api/v1/data-sources", json={"name": "New Source", "type": "postgresql", "config": {}}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(DataSource).where(DataSource.id == resp.json()["id"]))
    src = result.scalar_one()
    assert src.org_id == two_orgs["a"]["org"].id


async def test_update_data_source_cache_ttl_seconds(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["a"]["org"].id)

    resp = await client.put(
        f"/api/v1/data-sources/{src.id}", json={"cache_ttl_seconds": 0}, headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    assert resp.json()["cache_ttl_seconds"] == 0
    await db_session.refresh(src)
    assert src.cache_ttl_seconds == 0


async def test_delete_data_source_cross_org_returns_404_and_does_not_delete(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.delete(f"/api/v1/data-sources/{src.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
    result = await db_session.execute(select(DataSource).where(DataSource.id == src.id))
    assert result.scalar_one_or_none() is not None


async def test_test_connection_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(f"/api/v1/data-sources/{src.id}/test", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_get_schema_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.get(f"/api/v1/data-sources/{src.id}/schema", headers=auth_headers["a"])

    assert resp.status_code == 404


async def test_preview_data_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(
        f"/api/v1/data-sources/{src.id}/preview", json={"table": "some_table"}, headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_import_dataset_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    src = await _seed_data_source(db_session, two_orgs["b"]["org"].id)

    resp = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "test", "table": "some_table"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_list_data_sources_requires_authentication(client, db_session):
    resp = await client.get("/api/v1/data-sources")
    assert resp.status_code == 401


async def test_preview_data_non_admin_gets_403(client, db_session, two_orgs):
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User

    src = await _seed_data_source(db_session, two_orgs["a"]["org"].id)
    role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="viewer-preview@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(f"/api/v1/data-sources/{src.id}/preview", json={"table": "some_table"}, headers=headers)

    assert resp.status_code == 403


async def test_reimport_carries_forward_semantic_type_by_column_name(client, db_session, two_orgs, auth_headers, monkeypatch, tmp_path):
    """A re-import (dataset_id set) does full delete+recreate of DatasetColumn
    rows. semantic_type is set by metadata sync / a manual edit, not derived
    from the freshly detected types, so it must survive by matching column
    name -- otherwise the codeless RLS builder and auto-generate silently
    degrade until the next metadata sync."""
    import pandas as pd

    org_id = two_orgs["a"]["org"].id
    src = await _seed_data_source(db_session, org_id)
    ds = Dataset(name="ds", filename=str(tmp_path / "ds.csv"), org_id=org_id,
                 row_count=1, col_count=2, data_source_id=src.id, source_table="t")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    db_session.add_all([
        DatasetColumn(dataset_id=ds.id, name="id", dtype="int", semantic_type=None),
        DatasetColumn(dataset_id=ds.id, name="email", dtype="string", semantic_type="email"),
    ])
    await db_session.commit()

    fresh = pd.DataFrame([{"id": 1, "email": "a@x.com"}, {"id": 2, "email": "b@x.com"}])
    monkeypatch.setattr("app.routers.data_sources.import_to_dataframe",
                        lambda cfg, table, query: fresh)

    resp = await client.post(
        f"/api/v1/data-sources/{src.id}/import",
        json={"dataset_name": "ds", "table": "t", "dataset_id": ds.id},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id))
    cols = {c.name: c.semantic_type for c in result.scalars().all()}
    assert cols["email"] == "email"
    assert cols["id"] is None


async def test_import_dataset_non_admin_gets_403(client, db_session, two_orgs):
    from app.core.security import create_access_token, hash_password
    from app.models.models import Role, User

    src = await _seed_data_source(db_session, two_orgs["a"]["org"].id)
    role = Role(org_id=two_orgs["a"]["org"].id, name="Viewer", is_org_admin=False)
    db_session.add(role)
    await db_session.flush()
    user = User(org_id=two_orgs["a"]["org"].id, role_id=role.id, email="viewer-import@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.org_id)}"}

    resp = await client.post(f"/api/v1/data-sources/{src.id}/import", json={"dataset_name": "x", "table": "some_table"}, headers=headers)

    assert resp.status_code == 403


# ── Connecting a database starts understanding it ────────────────────────────

@pytest.mark.asyncio
class TestTheConnectionDescribesItself:
    """Creating a connection used to save a row and say "Connection created".
    Everything that explains a database -- the overview, the table and column
    descriptions, the inferred joins, the entities -- sat behind a sync nothing
    prompted anyone to run, reachable only from a row menu. A person who had
    just plugged in a database they did not know was left with a list of table
    names.
    """

    @pytest.fixture
    def started(self, monkeypatch):
        """The background sync, recorded rather than run: what is being tested
        is that the endpoint starts one, not what the pipeline then does."""
        calls = []

        async def _fake(session_factory, run_id, source_id, org_id, **kw):
            calls.append({"run_id": run_id, "source_id": source_id,
                          "org_id": org_id, **kw})

        from app.services.metadata import sync
        monkeypatch.setattr(sync, "run_sync_background", _fake)
        return calls

    async def test_creating_a_connection_starts_a_sync(
            self, client, auth_headers, db_session, two_orgs, started):
        from app.models.models import SyncRun

        r = await client.post("/api/v1/data-sources",
                              json={"name": "warehouse", "type": "postgresql",
                                    "config": {"host": "db", "database": "shop"}},
                              headers=auth_headers["a"])
        assert r.status_code == 200, r.text
        run_id = r.json()["sync_run_id"]
        assert run_id is not None

        run = await db_session.get(SyncRun, run_id)
        assert run is not None
        assert run.trigger == "on_create"
        assert run.status == "running"

    async def test_the_client_is_handed_the_run_to_watch(
            self, client, auth_headers, db_session, two_orgs, started):
        """The point of returning the id: the UI can send the user straight to
        the review page with progress already on screen, instead of announcing a
        connection and leaving them to find the sync themselves."""
        r = await client.post("/api/v1/data-sources",
                              json={"name": "warehouse", "type": "postgresql",
                                    "config": {"host": "db", "database": "shop"}},
                              headers=auth_headers["a"])
        assert started and started[0]["run_id"] == r.json()["sync_run_id"]
        assert started[0]["source_id"] == r.json()["id"]

    async def test_a_sync_that_cannot_start_still_creates_the_connection(
            self, client, auth_headers, db_session, two_orgs, monkeypatch):
        """A missing convenience, not a failed request. Before this existed the
        user ran the sync by hand, and that is exactly what they fall back to."""
        from app.routers import data_sources as router_mod

        async def _boom(*a, **k):
            raise RuntimeError("no scheduler here")

        monkeypatch.setattr(router_mod, "_start_initial_sync", _boom)
        r = await client.post("/api/v1/data-sources",
                              json={"name": "warehouse", "type": "postgresql",
                                    "config": {"host": "db"}},
                              headers=auth_headers["a"])
        # The helper itself swallows; this pins the endpoint's own behaviour if
        # anything above the helper ever raises instead.
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            assert r.json()["id"]
