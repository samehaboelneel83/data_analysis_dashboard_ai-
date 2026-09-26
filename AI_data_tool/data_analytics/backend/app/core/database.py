from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings

#: Postgres restarts for ordinary reasons -- a minor-version upgrade, a
#: failover, a container rescheduled, the OOM killer -- and every pooled
#: connection is dead the moment it does. SQLAlchemy does not know that and
#: hands the next request a corpse.
#:
#: `pool_pre_ping` checks a connection before lending it out and silently
#: replaces a dead one, so a restart costs nobody a request. Measured against
#: a real Postgres restart with a warm pool: without pre-ping the first
#: request after the restart fails and the second already succeeds --
#: SQLAlchemy invalidates the whole pool generation once it recognises a
#: disconnect. So the cost is one failed request, not one per connection, and
#: pre-ping takes it to zero.
#:
#: The boundary: this covers a connection that died BETWEEN requests, which is
#: the restart case. A request whose connection dies WHILE it executes still
#: fails, and lands in the generic handler that quotes no exception text.
#:
#: `pool_recycle` is the same problem on a longer timer: pgbouncer, cloud load
#: balancers and firewalls drop idle connections without telling either end,
#: so the first request after a quiet period gets an already-closed socket.
#: Half an hour sits inside the common idle timeouts without churning
#: connections during normal traffic.
#:
#: `services/engines.py` has pre-ping for the CUSTOMER's database and always
#: has. This is ours -- the one every single request touches.
def utc_connect_args(url: str) -> dict:
    """Pin the database session's time zone to UTC (the async driver): text
    timestamps and `now()::text` then read as UTC too. Sent at connection
    start-up, a parameter pgbouncer tracks, so it survives pooling. The bound
    datetimes themselves are handled by `naive_params_as_utc` below."""
    if url.startswith("postgresql+asyncpg"):
        return {"server_settings": {"timezone": "UTC"}}
    return {}


def _as_utc(value):
    from datetime import datetime, timezone
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def naive_params_as_utc(parameters):
    """Every naive datetime bound to a statement, marked as the UTC it is.

    The app writes naive UTC (`datetime.utcnow()`) into `TIMESTAMPTZ`
    columns (all 105 of them). asyncpg converts a naive datetime for a
    timestamptz parameter as the PROCESS's local time, so on a server whose
    clock is not UTC every stored time moved: found live on a machine set to
    Cairo, where a dataflow run a moment ago read "3 hours ago". The Docker
    images run in UTC, which is why nobody saw it there."""
    if isinstance(parameters, dict):
        return {k: _as_utc(v) for k, v in parameters.items()}
    if isinstance(parameters, (list, tuple)):
        out = [naive_params_as_utc(p) if isinstance(p, (dict, list, tuple)) else _as_utc(p)
               for p in parameters]
        return tuple(out) if isinstance(parameters, tuple) else out
    return parameters


def pin_utc_on_connect(sync_engine):
    """The same for a synchronous (psycopg2) engine on our database: a SET
    on each new connection, which works through any pooler."""
    from sqlalchemy import event

    if sync_engine.dialect.name != "postgresql":
        return None

    @event.listens_for(sync_engine, "connect")
    def _utc(dbapi_connection, _record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("SET TIME ZONE 'UTC'")
        cur.close()
    return _utc


engine = create_async_engine(
    settings.database_url, echo=False, pool_pre_ping=True, pool_recycle=1800,
    connect_args=utc_connect_args(settings.database_url))


def utc_bound_datetimes(async_engine):
    """Attach `naive_params_as_utc` to an asyncpg engine on our database."""
    from sqlalchemy import event

    if async_engine.dialect.name != "postgresql" or async_engine.dialect.driver != "asyncpg":
        return None

    @event.listens_for(async_engine.sync_engine, "before_cursor_execute", retval=True)
    def _utc(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        return statement, naive_params_as_utc(parameters)
    return _utc


_ENGINE_UTC_HOOK = utc_bound_datetimes(engine)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
