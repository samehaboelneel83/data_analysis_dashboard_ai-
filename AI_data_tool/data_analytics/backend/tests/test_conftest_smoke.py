from sqlalchemy import text


async def test_db_session_fixture_creates_tables_and_queries(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_client_fixture_hits_the_real_app(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_suite_uses_its_own_duckdb_metadata_cache(tmp_path_factory):
    """B-13: the suite must never open the live backend's metadata cache file
    (a DuckDB file lock held by pytest made live syncs 500/409/hang)."""
    import os

    from app.core.config import Settings, settings
    from app.services.metadata import cache

    path = settings.duckdb_cache_path
    assert path != Settings.model_fields["duckdb_cache_path"].default
    assert os.path.realpath(path).startswith(
        os.path.realpath(str(tmp_path_factory.getbasetemp()))
    )
    assert cache.get_cache().path == path
