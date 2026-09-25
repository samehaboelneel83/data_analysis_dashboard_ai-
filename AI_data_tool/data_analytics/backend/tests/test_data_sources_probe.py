"""POST /data-sources/test: try a connection's settings before saving them."""
from sqlalchemy import func, select

from app.models.models import DataSource
from app.services import secrets


async def test_probe_tries_the_settings_and_saves_nothing(client, db_session, auth_headers, two_orgs, monkeypatch):
    seen = {}

    def fake_test(cfg):
        seen.update(cfg)
        return {"ok": True}

    monkeypatch.setattr("app.routers.data_sources.test_connection", fake_test)
    before = (await db_session.execute(select(func.count()).select_from(DataSource))).scalar_one()

    resp = await client.post("/api/v1/data-sources/test", headers=auth_headers["a"],
                             json={"type": "postgresql", "config": {"host": "db", "password": "pw"}})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    assert seen["type"] == "postgresql" and seen["password"] == "pw"
    after = (await db_session.execute(select(func.count()).select_from(DataSource))).scalar_one()
    assert after == before


async def test_probe_rejects_an_unknown_connector(client, auth_headers, two_orgs):
    resp = await client.post("/api/v1/data-sources/test", headers=auth_headers["a"],
                             json={"type": "not-a-connector", "config": {}})
    assert resp.status_code == 400


async def test_probe_reuses_a_stored_secret_sent_back_redacted(client, db_session, auth_headers, two_orgs, monkeypatch):
    src = DataSource(name="S", type="postgresql", org_id=two_orgs["a"]["org"].id,
                     config=secrets.encrypt_config({"host": "db", "password": "stored-pw"}, ["password"]))
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    seen = {}
    monkeypatch.setattr("app.routers.data_sources.test_connection", lambda cfg: seen.update(cfg) or {"ok": True})

    resp = await client.post("/api/v1/data-sources/test", headers=auth_headers["a"],
                             json={"type": "postgresql", "source_id": src.id,
                                   "config": {"host": "db2", "password": secrets.REDACTED}})

    assert resp.status_code == 200, resp.text
    assert seen["password"] == "stored-pw" and seen["host"] == "db2"


async def test_probe_cannot_borrow_another_orgs_secret(client, db_session, auth_headers, two_orgs):
    src = DataSource(name="B", type="postgresql", org_id=two_orgs["b"]["org"].id, config={})
    db_session.add(src)
    await db_session.commit()
    await db_session.refresh(src)
    resp = await client.post("/api/v1/data-sources/test", headers=auth_headers["a"],
                             json={"type": "postgresql", "source_id": src.id, "config": {}})
    assert resp.status_code == 404
