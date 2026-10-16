"""E-02 follow-up: user emails are unique whatever their letter case.

Revision 0069_users_email_ci_unique lower-cases stored addresses and adds a
unique index on lower(email); if two accounts differ only by case it refuses
and names them instead of merging or deleting anything.
`app.main._ensure_users_email_ci_unique` does the same on databases stamped at
head without running revisions (pre-Alembic / init.sql), without ever
aborting startup.
"""
import asyncio
import logging
import os

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
import app.models.models  # noqa: F401

from tests.test_alembic_migrations import _alembic_config

PREV = "0068_publishing_sharing"
REV = "0069_users_email_ci_unique"


@pytest.fixture(autouse=True)
def _isolate_migration_error(monkeypatch):
    from app import main as app_main
    monkeypatch.setattr(app_main, "_MIGRATION_ERROR", None)


@pytest.fixture
def scratch_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'email_ci.db'}"
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield url
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


async def _seed(engine, emails):
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'A'), (2, 'B')"))
        await conn.execute(text(
            "INSERT INTO roles (id, org_id, name, is_org_admin) VALUES (1, 1, 'Admin', 1), (2, 2, 'Admin', 1)"))
        for i, (org, email) in enumerate(emails, start=1):
            await conn.execute(text(
                "INSERT INTO users (id, org_id, role_id, email, password_hash, is_active) "
                "VALUES (:i, :o, :o, :e, 'x', 1)"), {"i": i, "o": org, "e": email})


async def _emails(engine):
    async with engine.connect() as conn:
        return [r[0] for r in (await conn.execute(text("SELECT email FROM users ORDER BY id"))).fetchall()]


async def _version(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()


async def _index_names(engine):
    async with engine.connect() as conn:
        # sqlite_master, not the inspector: SQLAlchemy skips reflecting
        # expression-based indexes on SQLite.
        rows = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='users'"))
        return {r[0] for r in rows}


async def test_upgrade_lower_cases_emails_and_adds_case_insensitive_unique_index(scratch_url):
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, PREV)
    engine = create_async_engine(scratch_url)
    await _seed(engine, [(1, "Mixed.Case@Example.com"), (2, "plain@example.com")])

    await asyncio.to_thread(command.upgrade, cfg, "head")

    assert await _version(engine) != PREV
    assert await _emails(engine) == ["mixed.case@example.com", "plain@example.com"]
    assert "ux_users_email_lower" in await _index_names(engine)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO users (org_id, role_id, email, password_hash, is_active) "
                "VALUES (2, 2, 'PLAIN@example.com', 'x', 1)"))

    # Idempotent, and the downgrade removes only the index.
    await asyncio.to_thread(command.downgrade, cfg, PREV)
    assert "ux_users_email_lower" not in await _index_names(engine)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert "ux_users_email_lower" in await _index_names(engine)
    await engine.dispose()


async def test_upgrade_refuses_case_duplicates_and_names_them(scratch_url):
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, PREV)
    engine = create_async_engine(scratch_url)
    seeded = [(1, "admin@datalytics.local"), (2, "ADMIN@datalytics.local"),
              (1, "Other@Example.com")]
    await _seed(engine, seeded)

    with pytest.raises(RuntimeError) as err:
        await asyncio.to_thread(command.upgrade, cfg, "head")

    msg = str(err.value)
    assert "differ only by letter case" in msg
    assert "id=1 org_id=1 email='admin@datalytics.local'" in msg
    assert "id=2 org_id=2 email='ADMIN@datalytics.local'" in msg
    assert "Other@Example.com" not in msg            # not a duplicate, not listed
    # Nothing changed: still at the previous revision, no address rewritten.
    assert await _version(engine) == PREV
    assert await _emails(engine) == [e for _, e in seeded]
    assert "ux_users_email_lower" not in await _index_names(engine)
    await engine.dispose()


async def test_the_refusal_is_not_mistaken_for_schema_drift():
    """`_run_alembic` stamps head over a 'duplicate object' failure; the
    refusal must never look like one, or the check would be skipped."""
    from app.main import _is_duplicate_schema_drift_error
    from importlib.util import module_from_spec, spec_from_file_location
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "alembic", "versions", f"{REV}.py")
    spec = spec_from_file_location("rev0069", path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    exc = RuntimeError(mod.describe_case_duplicates([(1, 1, "a@x.io"), (2, 1, "A@x.io")]))
    assert not _is_duplicate_schema_drift_error(exc)


async def _create_all_without_index(tmp_path, name):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP INDEX ux_users_email_lower"))
    return engine


async def test_startup_names_case_duplicates_and_reports_not_ready(tmp_path, monkeypatch, caplog):
    from app import main as app_main
    engine = await _create_all_without_index(tmp_path, "dupes.db")
    await _seed(engine, [(1, "boss@example.com"), (2, "Boss@Example.com")])
    monkeypatch.setattr(app_main, "engine", engine)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        await app_main._ensure_users_email_ci_unique()      # must not raise

    assert app_main._MIGRATION_ERROR == "users_email_case_duplicates"
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "'boss@example.com'" in logged and "'Boss@Example.com'" in logged
    assert await _emails(engine) == ["boss@example.com", "Boss@Example.com"]
    assert "ux_users_email_lower" not in await _index_names(engine)
    await engine.dispose()


async def test_startup_adds_the_index_on_a_clean_pre_alembic_database(tmp_path, monkeypatch):
    from app import main as app_main
    engine = await _create_all_without_index(tmp_path, "clean.db")
    await _seed(engine, [(1, "Boss@Example.com"), (2, "other@example.com")])
    monkeypatch.setattr(app_main, "engine", engine)

    await app_main._ensure_users_email_ci_unique()
    await app_main._ensure_users_email_ci_unique()          # idempotent

    assert app_main._MIGRATION_ERROR is None
    assert await _emails(engine) == ["boss@example.com", "other@example.com"]
    assert "ux_users_email_lower" in await _index_names(engine)
    await engine.dispose()


async def test_orm_schema_rejects_a_case_variant_account(db_session, two_orgs):
    """create_all (tests, fresh installs) carries the same index."""
    from app.models.models import User
    a = two_orgs["a"]
    db_session.add(User(org_id=a["org"].id, role_id=a["role"].id,
                        email="ADMIN-A@example.com", password_hash="x"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
