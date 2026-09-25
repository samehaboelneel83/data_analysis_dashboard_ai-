"""S5: startup enc:v1 -> enc:v2 migration for DataSource.config secrets
(services/secrets.migrate_v1_to_v2)."""
from sqlalchemy import select

from app.models.models import DataSource
from app.services import secrets


async def _make_source(db_session, org_id, password_value, type_="postgresql"):
    ds = DataSource(name="S", type=type_, org_id=org_id,
                     config={"host": "h", "username": "u", "password": password_value})
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_v1_secret_is_upgraded_to_v2(db_session, two_orgs):
    v1 = secrets.encrypt_value_v1("hunter2")
    ds = await _make_source(db_session, two_orgs["a"]["org"].id, v1)

    migrated = await secrets.migrate_v1_to_v2(db_session)

    assert migrated == 1
    await db_session.refresh(ds)
    new_value = ds.config["password"]
    assert new_value.startswith("enc:v2:")
    assert new_value != v1
    assert secrets.decrypt_value(new_value) == "hunter2"   # plaintext preserved


async def test_v2_secret_is_left_untouched(db_session, two_orgs):
    v2 = secrets.encrypt_value("s3cret")
    ds = await _make_source(db_session, two_orgs["a"]["org"].id, v2)

    migrated = await secrets.migrate_v1_to_v2(db_session)

    assert migrated == 0
    await db_session.refresh(ds)
    assert ds.config["password"] == v2


async def test_plaintext_secret_is_left_untouched(db_session, two_orgs):
    ds = await _make_source(db_session, two_orgs["a"]["org"].id, "plaintext-pw")

    migrated = await secrets.migrate_v1_to_v2(db_session)

    assert migrated == 0
    await db_session.refresh(ds)
    assert ds.config["password"] == "plaintext-pw"


async def test_undecryptable_v1_value_is_left_alone_with_a_warning(db_session, two_orgs, caplog):
    garbage = "enc:v1:not-a-real-fernet-token"
    ds = await _make_source(db_session, two_orgs["a"]["org"].id, garbage)

    import logging
    with caplog.at_level(logging.WARNING, logger="app.services.secrets"):
        migrated = await secrets.migrate_v1_to_v2(db_session)

    assert migrated == 0
    await db_session.refresh(ds)
    assert ds.config["password"] == garbage   # never corrupted or dropped
    assert any("could not decrypt" in r.message.lower() for r in caplog.records)


async def test_migration_is_idempotent_across_two_runs(db_session, two_orgs):
    v1 = secrets.encrypt_value_v1("hunter2")
    ds = await _make_source(db_session, two_orgs["a"]["org"].id, v1)

    first = await secrets.migrate_v1_to_v2(db_session)
    await db_session.refresh(ds)
    once = ds.config["password"]

    second = await secrets.migrate_v1_to_v2(db_session)
    await db_session.refresh(ds)

    assert first == 1
    assert second == 0                       # nothing left to migrate
    assert ds.config["password"] == once     # unchanged by the second run
    assert secrets.decrypt_value(once) == "hunter2"


async def test_migration_across_multiple_data_sources_counts_only_upgraded_ones(db_session, two_orgs):
    org_id = two_orgs["a"]["org"].id
    v1_ds = await _make_source(db_session, org_id, secrets.encrypt_value_v1("pw1"))
    v2_value = secrets.encrypt_value("pw2")
    v2_ds = await _make_source(db_session, org_id, v2_value)
    plain_ds = await _make_source(db_session, org_id, "pw3")

    migrated = await secrets.migrate_v1_to_v2(db_session)

    assert migrated == 1
    result = await db_session.execute(select(DataSource).where(DataSource.id == v1_ds.id))
    assert result.scalar_one().config["password"].startswith("enc:v2:")
    result = await db_session.execute(select(DataSource).where(DataSource.id == v2_ds.id))
    assert result.scalar_one().config["password"] == v2_value   # v2 untouched
    result = await db_session.execute(select(DataSource).where(DataSource.id == plain_ds.id))
    assert result.scalar_one().config["password"] == "pw3"
