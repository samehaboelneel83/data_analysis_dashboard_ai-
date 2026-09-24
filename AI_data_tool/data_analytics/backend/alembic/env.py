"""Alembic environment for Datalytics.

Builds its engine from the app's own settings (app.core.config.settings),
not from alembic.ini's sqlalchemy.url -- so the same env.py drives both
PostgreSQL in production and SQLite in tests/dev without editing config
files. ALEMBIC_DATABASE_URL, when set, overrides settings.database_url --
used to autogenerate/run revisions against a disposable scratch DB.

target_metadata is app.core.database.Base.metadata; app.models.models is
imported for its side effect of registering every ORM model on that Base
before autogenerate compares it against a database.
"""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: this runs in-process on every app
    # startup (app.main._run_alembic), not just from the `alembic` CLI.
    # fileConfig's default (True) would silently disable every logger not
    # named in alembic.ini's [loggers] section -- including app.main and
    # every other app logger -- the first time this runs, going quiet for
    # the rest of the process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Register every model on Base.metadata, then hand it to Alembic.
from app.core.database import Base  # noqa: E402
from app.models import models as _models  # noqa: E402,F401

target_metadata = Base.metadata


def _database_url() -> str:
    override = os.environ.get("ALEMBIC_DATABASE_URL")
    if override:
        return override
    from app.core.config import settings
    return settings.database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing against a DB. Not used by the
    app (startup always runs online), kept for the standard `alembic
    upgrade head --sql` workflow if anyone reaches for it."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    is_sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER a column/constraint in place; batch mode
        # recreates the table under the hood so future revisions (adding a
        # column, changing a type) work identically on SQLite and Postgres.
        render_as_batch=is_sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
