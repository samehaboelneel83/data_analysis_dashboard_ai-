"""T1: Alembic adopted alongside the existing create_all/_migrate path.

Covers the four scenarios app.main._run_alembic has to get right without
ever bricking startup:
  - a brand-new database: `upgrade head` builds the same tables create_all
    would.
  - an existing pre-Alembic database (app tables, no alembic_version):
    adoption stamps 0001_baseline instead of running any DDL.
  - re-running is idempotent (no error, no duplicate work).
  - a broken Alembic step (bad revision, unreachable DB, ...) is logged and
    swallowed -- create_all/_migrate still run right after it.
"""
import asyncio
import logging
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
import app.models.models  # noqa: F401  -- registers every table on Base.metadata

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _isolate_migration_error(monkeypatch):
    """_run_alembic records failures in a module global that /health/ready
    reads; a test that forces a failure must not leave every later readiness
    test answering 503."""
    from app import main as app_main
    monkeypatch.setattr(app_main, "_MIGRATION_ERROR", None)


def _alembic_config() -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return cfg


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: set(sa_inspect(sync_conn).get_table_names()))


async def _table_columns(engine) -> set[tuple[str, str]]:
    """Every (table, column) pair -- the comparison table names alone missed:
    a migration that creates the table but forgets a column matched."""
    async with engine.connect() as conn:
        def _read(sync_conn):
            insp = sa_inspect(sync_conn)
            return {(t, c["name"]) for t in insp.get_table_names()
                    for c in insp.get_columns(t)}
        return await conn.run_sync(_read)


@pytest.fixture
def scratch_url(tmp_path):
    """A sqlite file URL, and ALEMBIC_DATABASE_URL pointed at it for the
    duration of the test -- env.py reads that override in preference to
    settings.database_url, so this is how a test steers Alembic at a
    throwaway file without touching real app config."""
    db_path = tmp_path / "scratch.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        yield url
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


class TestFreshDatabase:
    async def test_upgrade_head_matches_create_all_tables(self, tmp_path, scratch_url):
        create_all_engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'create_all.db'}"
        )
        async with create_all_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        create_all_tables = await _table_names(create_all_engine)
        await create_all_engine.dispose()

        await asyncio.to_thread(command.upgrade, _alembic_config(), "head")

        alembic_engine = create_async_engine(scratch_url)
        alembic_tables = await _table_names(alembic_engine)
        await alembic_engine.dispose()

        assert alembic_tables - {"alembic_version"} == create_all_tables

    async def test_upgrade_head_matches_create_all_columns(self, tmp_path, scratch_url):
        create_all_engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'create_all_cols.db'}")
        async with create_all_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        expected = await _table_columns(create_all_engine)
        await create_all_engine.dispose()

        await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
        alembic_engine = create_async_engine(scratch_url)
        actual = await _table_columns(alembic_engine)
        await alembic_engine.dispose()

        actual = {tc for tc in actual if tc[0] != "alembic_version"}
        assert actual == expected, (
            f"missing from alembic: {sorted(expected - actual)}; "
            f"extra in alembic: {sorted(actual - expected)}")

    async def test_downgrade_to_base_and_back_is_clean(self, tmp_path, scratch_url):
        """Every revision's downgrade() has to run, on SQLite, in batch mode
        where it alters a table. Nothing exercised them before.

        Note this exercises SQLite's batch-mode downgrade path only -- the
        Postgres downgrade() bodies (plain ALTER, no batch rewrite) are
        unexercised by this suite (see the spec's follow-up list, item 16)."""
        cfg = _alembic_config()
        await asyncio.to_thread(command.upgrade, cfg, "head")
        await asyncio.to_thread(command.downgrade, cfg, "base")
        engine = create_async_engine(scratch_url)
        after_down = await _table_names(engine)
        await engine.dispose()
        assert after_down <= {"alembic_version"}, sorted(after_down)

        await asyncio.to_thread(command.upgrade, cfg, "head")
        engine = create_async_engine(scratch_url)
        after_up = await _table_names(engine)
        assert "datasets" in after_up
        # Table names alone missed a column a downgrade's batch rewrite drops
        # and the matching upgrade never puts back -- compare every
        # (table, column) pair against a fresh create_all(), the same
        # comparison test_upgrade_head_matches_create_all_columns makes for a
        # plain upgrade, now also made across a down-then-up round trip.
        after_up_cols = await _table_columns(engine)
        await engine.dispose()
        after_up_cols = {tc for tc in after_up_cols if tc[0] != "alembic_version"}

        create_all_engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'create_all_roundtrip.db'}")
        async with create_all_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        expected_cols = await _table_columns(create_all_engine)
        await create_all_engine.dispose()

        assert after_up_cols == expected_cols, (
            f"missing after the round trip: {sorted(expected_cols - after_up_cols)}; "
            f"extra after the round trip: {sorted(after_up_cols - expected_cols)}")


class TestAdoption:
    async def test_stamp_adopts_existing_db_without_altering_it(self, tmp_path, scratch_url):
        # Simulate a pre-T1 database: tables exist (via create_all, same as
        # every deployed DB before this task), no alembic_version table.
        pre_existing_engine = create_async_engine(scratch_url)
        async with pre_existing_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables_before = await _table_names(pre_existing_engine)
        assert "alembic_version" not in tables_before

        await asyncio.to_thread(command.stamp, _alembic_config(), "0001_baseline")

        tables_after = await _table_names(pre_existing_engine)
        # Only the version-tracking table appears; nothing else changed.
        assert tables_after - {"alembic_version"} == tables_before
        assert "alembic_version" in tables_after

        async with pre_existing_engine.connect() as conn:
            row = (await conn.execute(
                __import__("sqlalchemy").text("SELECT version_num FROM alembic_version")
            )).scalar_one()
        assert row == "0001_baseline"
        await pre_existing_engine.dispose()

    async def test_double_stamp_is_idempotent(self, tmp_path, scratch_url):
        engine = create_async_engine(scratch_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await asyncio.to_thread(command.stamp, _alembic_config(), "0001_baseline")
        await asyncio.to_thread(command.stamp, _alembic_config(), "0001_baseline")  # must not raise

        async with engine.connect() as conn:
            count = (await conn.execute(
                __import__("sqlalchemy").text("SELECT COUNT(*) FROM alembic_version")
            )).scalar_one()
        assert count == 1
        await engine.dispose()

    async def test_double_upgrade_head_is_idempotent(self, scratch_url):
        await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
        await asyncio.to_thread(command.upgrade, _alembic_config(), "head")  # must not raise


class TestStartupResilience:
    async def test_run_alembic_survives_a_broken_step(self, tmp_path, monkeypatch, caplog):
        from app import main as app_main

        # Point _run_alembic's inspection connection at a reachable scratch
        # DB (real startup uses settings.database_url, i.e. Postgres, which
        # isn't up in this test) so the failure under test is the Alembic
        # step itself, not an unrelated connection error.
        test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scratch.db'}")
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(app_main, "engine", test_engine)

        def _boom(*args, **kwargs):
            raise RuntimeError("bad revision")

        monkeypatch.setattr("alembic.command.upgrade", _boom)
        monkeypatch.setattr("alembic.command.stamp", _boom)

        with caplog.at_level(logging.ERROR, logger="app.main"):
            await app_main._run_alembic()  # must not raise

        assert any("alembic startup migration failed" in r.message for r in caplog.records)
        # Logged AND recorded: readiness must see it (gap: it used to be
        # swallowed, and the replica reported ready on an unmigrated schema).
        assert app_main._MIGRATION_ERROR == "RuntimeError"
        await test_engine.dispose()

    async def test_a_run_that_leaves_the_db_off_head_is_recorded(self, tmp_path, monkeypatch):
        """No exception, wrong result: the stamp lands on an older revision.
        Verified against the script head, not inferred from 'nothing raised'."""
        from app import main as app_main

        db_path = tmp_path / "offhead.db"
        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(app_main, "engine", test_engine)
        os.environ["ALEMBIC_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        try:
            real_stamp = command.stamp
            monkeypatch.setattr("alembic.command.stamp",
                                lambda cfg, _rev: real_stamp(cfg, "0001_baseline"))
            await app_main._run_alembic()
            assert app_main._MIGRATION_ERROR == "revision_mismatch"
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
            await test_engine.dispose()


class TestAdoptionStampsHead:
    async def test_second_boot_upgrade_succeeds_after_adoption(self, tmp_path, scratch_url):
        """Regression (final review, High): adoption must stamp HEAD, not the
        baseline. Stamping 0001 while the same boot's create_all provisions
        0002+'s tables made the next boot's `upgrade head` die on
        DuplicateTable forever, orphaning every future revision."""
        engine = create_async_engine(scratch_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Boot 1: adopt (what _run_alembic does on a pre-alembic DB).
        await asyncio.to_thread(command.stamp, _alembic_config(), "head")

        # Boot 2: upgrade head must be a clean no-op, not DuplicateTable.
        await asyncio.to_thread(command.upgrade, _alembic_config(), "head")

        async with engine.connect() as conn:
            version = (await conn.execute(
                __import__("sqlalchemy").text("SELECT version_num FROM alembic_version")
            )).scalar_one()
        await engine.dispose()

        # The stored version is the chain head, not the baseline.
        from alembic.script import ScriptDirectory
        head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
        assert version == head
        assert version != "0001_baseline"


class TestSelfHeal:
    async def test_upgrade_head_self_heals_on_duplicate_table_drift(self, tmp_path, monkeypatch):
        """Simulated drift: a DB that's already at head-equivalence (via
        create_all) but whose alembic_version is pinned behind. `upgrade
        head` then tries to re-run later revisions' DDL (e.g. 0002's
        `create_table('deliveries')`) against tables that already exist --
        a genuine DuplicateTable-class error -- which must self-heal by
        stamping head instead of leaving the DB wedged forever."""
        from app import main as app_main
        from sqlalchemy import text as sa_text

        db_path = tmp_path / "drift.db"
        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(app_main, "engine", test_engine)

        os.environ["ALEMBIC_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        try:
            # Pin the version marker behind head, as an old adoption boot would.
            await asyncio.to_thread(command.stamp, _alembic_config(), "0001_baseline")

            await app_main._run_alembic()  # must not raise; must self-heal
            assert app_main._MIGRATION_ERROR is None  # healed means ready

            async with test_engine.connect() as conn:
                version = (await conn.execute(
                    sa_text("SELECT version_num FROM alembic_version")
                )).scalar_one()
            from alembic.script import ScriptDirectory
            head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
            assert version == head
            assert version != "0001_baseline"
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
            await test_engine.dispose()

    async def test_non_duplicate_failure_does_not_stamp(self, tmp_path, monkeypatch):
        """A genuinely broken revision (not a duplicate-object error) must
        NOT be self-healed -- it keeps today's log-and-continue, and stamp
        is never called."""
        from app import main as app_main
        from sqlalchemy import text as sa_text

        db_path = tmp_path / "broken.db"
        test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(app_main, "engine", test_engine)

        os.environ["ALEMBIC_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        try:
            await asyncio.to_thread(command.stamp, _alembic_config(), "0001_baseline")

            stamp_calls = []
            real_stamp = command.stamp

            def _spy_stamp(*args, **kwargs):
                stamp_calls.append((args, kwargs))
                return real_stamp(*args, **kwargs)

            def _boom(*args, **kwargs):
                raise RuntimeError("bad revision, not a duplicate anything")

            monkeypatch.setattr("alembic.command.upgrade", _boom)
            monkeypatch.setattr("alembic.command.stamp", _spy_stamp)

            # (Not asserting on caplog here: the preceding real `command.stamp`
            # call above runs Alembic's own `fileConfig`, which replaces the
            # root logger's handlers -- including pytest's caplog handler --
            # as an unrelated side effect. The "log-and-continue" behavior
            # itself is already pinned by TestStartupResilience above; this
            # test's job is to prove self-heal does NOT trigger here.)
            await app_main._run_alembic()  # must not raise

            assert stamp_calls == []

            async with test_engine.connect() as conn:
                version = (await conn.execute(
                    sa_text("SELECT version_num FROM alembic_version")
                )).scalar_one()
            assert version == "0001_baseline"  # untouched
        finally:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
            await test_engine.dispose()


class TestRevisionIdLengths:
    async def test_every_revision_id_fits_alembic_version_column(self):
        """alembic_version.version_num is VARCHAR(32). SQLite ignores varchar
        lengths so the test suite can't catch an oversized id -- live Postgres
        rejects it with StringDataRightTruncation and the stamp/upgrade dies
        (found on the live DB with '0003_agent_feedback_and_eval_runs', 33
        chars). Pin every id to <= 32 here, where Postgres can't be fooled."""
        from alembic.script import ScriptDirectory
        script = ScriptDirectory.from_config(_alembic_config())
        for rev in script.walk_revisions():
            assert len(rev.revision) <= 32, (
                f"revision id {rev.revision!r} is {len(rev.revision)} chars; "
                "alembic_version.version_num is VARCHAR(32)")
