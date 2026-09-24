from sqlalchemy import text


async def test_db_session_fixture_creates_tables_and_queries(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_client_fixture_hits_the_real_app(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
