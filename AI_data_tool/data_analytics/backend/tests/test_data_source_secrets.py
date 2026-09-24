"""Data-source secrets are encrypted at rest and redacted on the wire."""
import pytest
from sqlalchemy import select

from app.models.models import DataSource
from app.services import secrets


def _cfg(pw="topsecret"):
    return {"host": "db.internal", "database": "d", "username": "u", "password": pw}


@pytest.mark.asyncio
async def test_create_stores_ciphertext_and_returns_a_redaction(client, auth_headers, db_session):
    r = await client.post("/api/v1/data-sources",
                          json={"name": "PG", "type": "postgresql", "config": _cfg()},
                          headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    # the wire never carries the secret
    assert r.json()["config"]["password"] == secrets.REDACTED
    # the row holds ciphertext, not the plaintext
    ds = (await db_session.execute(select(DataSource).where(DataSource.id == r.json()["id"]))).scalar_one()
    assert secrets.is_encrypted(ds.config["password"])
    assert ds.config["password"] != "topsecret"
    assert ds.config["host"] == "db.internal"      # non-secret fields untouched


@pytest.mark.asyncio
async def test_list_and_get_redact_the_secret(client, auth_headers):
    rid = (await client.post("/api/v1/data-sources",
                             json={"name": "PG", "type": "postgresql", "config": _cfg()},
                             headers=auth_headers["a"])).json()["id"]
    got = await client.get(f"/api/v1/data-sources/{rid}", headers=auth_headers["a"])
    assert got.json()["config"]["password"] == secrets.REDACTED
    lst = await client.get("/api/v1/data-sources", headers=auth_headers["a"])
    assert all(d["config"].get("password") in (None, secrets.REDACTED) for d in lst.json())


@pytest.mark.asyncio
async def test_update_with_the_sentinel_keeps_the_stored_secret(client, auth_headers, db_session):
    rid = (await client.post("/api/v1/data-sources",
                             json={"name": "PG", "type": "postgresql", "config": _cfg("orig")},
                             headers=auth_headers["a"])).json()["id"]
    stored_before = (await db_session.execute(select(DataSource).where(DataSource.id == rid))).scalar_one().config["password"]

    # The UI round-trips the redaction sentinel for an unchanged secret.
    cfg = _cfg(secrets.REDACTED)
    cfg["host"] = "changed.internal"
    await client.put(f"/api/v1/data-sources/{rid}", json={"config": cfg}, headers=auth_headers["a"])

    db_session.expire_all()
    row = (await db_session.execute(select(DataSource).where(DataSource.id == rid))).scalar_one()
    assert row.config["password"] == stored_before          # secret preserved verbatim
    assert secrets.decrypt_value(row.config["password"]) == "orig"
    assert row.config["host"] == "changed.internal"         # the real edit applied


@pytest.mark.asyncio
async def test_update_with_a_new_password_re_encrypts(client, auth_headers, db_session):
    rid = (await client.post("/api/v1/data-sources",
                             json={"name": "PG", "type": "postgresql", "config": _cfg("orig")},
                             headers=auth_headers["a"])).json()["id"]
    await client.put(f"/api/v1/data-sources/{rid}",
                     json={"config": _cfg("rotated")}, headers=auth_headers["a"])
    db_session.expire_all()
    row = (await db_session.execute(select(DataSource).where(DataSource.id == rid))).scalar_one()
    assert secrets.is_encrypted(row.config["password"])
    assert secrets.decrypt_value(row.config["password"]) == "rotated"
