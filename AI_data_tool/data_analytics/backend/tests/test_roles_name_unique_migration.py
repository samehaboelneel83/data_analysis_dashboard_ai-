"""E-15: revision 0070_roles_org_name_unique and its startup twin rename
duplicate role names within an org (oldest keeps the name, nothing merged or
deleted) and add a unique (org_id, lower(name)) index."""
import asyncio
import os

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
import app.models.models  # noqa: F401
from tests.test_alembic_migrations import _alembic_config

PREV = "0069_users_email_ci_unique"


@pytest.fixture(autouse=True)
def _isolate_migration_error(monkeypatch):
    from app import main as app_main
    monkeypatch.setattr(app_main, "_MIGRATION_ERROR", None)


@pytest.fixture
def scratch_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'roles.db'}"
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield url
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


ROLES = [(1, 1, "QA E Role"), (2, 1, "qa e role "), (3, 1, "QA E Role (2)"), (4, 1, "Analyst"),
         (5, 2, "QA E Role"), (6, 1, "QA E ROLE")]


async def _seed(engine):
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'A'), (2, 'B')"))
        for i, org, name in ROLES:
            await conn.execute(text("INSERT INTO roles (id, org_id, name, is_org_admin) VALUES (:i, :o, :n, 0)"),
                               {"i": i, "o": org, "n": name})
        await conn.execute(text("INSERT INTO users (org_id, role_id, email, password_hash, is_active) "
                                "VALUES (1, 2, 'u@example.com', 'x', 1)"))


async def _names(engine):
    async with engine.connect() as conn:
        return dict((await conn.execute(text("SELECT id, name FROM roles ORDER BY id"))).fetchall())


async def _assert_renamed_and_enforced(engine):
    assert await _names(engine) == {1: "QA E Role", 2: "qa e role (3)", 3: "QA E Role (2)", 4: "Analyst",
                                    5: "QA E Role", 6: "QA E ROLE (4)"}
    async with engine.connect() as conn:       # the user kept its (renamed) role
        assert (await conn.execute(text("SELECT role_id FROM users"))).scalar_one() == 2
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO roles (org_id, name, is_org_admin) VALUES (1, 'analyst', 0)"))
    async with engine.begin() as conn:         # another org may reuse it
        await conn.execute(text("INSERT INTO roles (org_id, name, is_org_admin) VALUES (2, 'analyst', 0)"))


async def test_upgrade_renames_duplicates_and_adds_the_index(scratch_url):
    cfg = _alembic_config()
    await asyncio.to_thread(command.upgrade, cfg, PREV)
    engine = create_async_engine(scratch_url)
    await _seed(engine)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await _assert_renamed_and_enforced(engine)
    await asyncio.to_thread(command.downgrade, cfg, PREV)
    await asyncio.to_thread(command.upgrade, cfg, "head")       # re-run: no-op
    await engine.dispose()


async def test_startup_does_the_same_for_a_database_stamped_at_head(tmp_path, monkeypatch):
    from app import main as app_main
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'stamped.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed(engine)
    monkeypatch.setattr(app_main, "engine", engine)
    await app_main._ensure_roles_name_unique()
    await app_main._ensure_roles_name_unique()                   # idempotent
    assert app_main._MIGRATION_ERROR is None
    await _assert_renamed_and_enforced(engine)
    await engine.dispose()
