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
engine = create_async_engine(
    settings.database_url, echo=False, pool_pre_ping=True, pool_recycle=1800)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
