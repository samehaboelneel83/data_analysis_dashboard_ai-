"""T5: fire-and-forget QueryRun telemetry.

The three query-execution paths (DirectQuery pushdown, the import/pandas
widget path, the agent's two executors) all call `log_query_run_sync` right
after a query actually runs. try/except-all + logger.warning: this table is
a nice-to-have training signal, not a thing a query is allowed to depend on.

T13 incident (see task-T13-report.md): the original implementation opened
its own async session via `AsyncSessionLocal` and drove it with a fresh
`asyncio.run()` per call. Two of those write points run on a worker thread
(`asyncio.to_thread`) -- `asyncio.run()` there spins up a BRAND-NEW event
loop, and `AsyncSessionLocal` is bound to the single asyncpg engine created
once at import time in `app/core/database.py`, whose connections are
loop-bound to whichever loop first touched them. A connection object used
from two different event loops corrupts mid-transaction and is left
`idle in transaction` forever (no `idle_in_transaction_session_timeout` on
this Postgres) -- and a later, unrelated request that happens to check out
that same poisoned connection gets its own commit silently swallowed inside
the zombie's still-open outer transaction: "200 OK, then 404 looking it up."
One agent SQL execution against a DirectQuery source was enough to start
this cascade in production.

The fix: this module NEVER touches the async engine, `AsyncSessionLocal`,
or any event loop, full stop. It owns a completely separate, plain
`sqlalchemy.create_engine` (psycopg2, not asyncpg) built once lazily and
reused, with `NullPool` so no connection is ever held open or reused across
calls -- there is nothing here for a zombie transaction to attach itself to.
Each call is connect -> INSERT -> commit -> close, entirely synchronous, so
it is safe to call from ANY context: a worker thread, or -- the case that
broke production -- straight out of a coroutine already running on the main
event loop. There is no more "logging silently no-ops here" call site.
"""
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_sync_engine = None
_engine_lock = threading.Lock()


def _sync_database_url(url: str) -> str:
    """`settings.database_url` is written for the app's ASYNC engine
    (`+asyncpg`, `+aiosqlite`) -- neither driver is usable from a plain sync
    `create_engine`. Swap in the sync counterpart; anything else (already a
    sync scheme, e.g. plain `sqlite://` in tests) passes through unchanged."""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + url[len("sqlite+aiosqlite://"):]
    return url


def _get_engine():
    """Lazily-created, lock-guarded singleton -- one dedicated engine for the
    process's lifetime, never the app's shared async `engine` from
    `core.database`. `NullPool`: a connection is opened for exactly one
    INSERT and closed immediately after, so there is never a pooled
    connection sitting around for a bad transaction to poison, and no
    cross-thread/cross-loop reuse is possible because nothing is reused."""
    global _sync_engine
    if _sync_engine is None:
        with _engine_lock:
            if _sync_engine is None:
                from sqlalchemy import create_engine
                from sqlalchemy.pool import NullPool

                from ..core.config import settings

                url = _sync_database_url(settings.database_url)
                _sync_engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
    return _sync_engine


def log_query_run_sync(**fields) -> None:
    """Fire-and-forget: connect, INSERT, commit, close -- entirely
    synchronous, entirely on its own dedicated engine. Never raises; a
    logging failure must never fail or slow the query it describes."""
    try:
        from ..models.models import QueryRun

        engine = _get_engine()
        with engine.begin() as conn:
            conn.execute(QueryRun.__table__.insert().values(**fields))
    except Exception:
        logger.warning("query_run logging failed", exc_info=True)


#: Two renders of the same link, by the same client, this close together are
#: one visit. A share page's fetch fires again on a component remount (React
#: StrictMode double-invokes effects in development), on a retried request and
#: on a double-click, and each repeat used to be counted as a separate view --
#: a link opened once reported "2 views", which quietly overstates the reach of
#: every link someone shared. A reload a minute later is a real second visit
#: and still counts.
_SHARE_ACCESS_DEDUPE_S = 10


def log_share_access_sync(**fields) -> None:
    """S4: same fire-and-forget contract as `log_query_run_sync` above, for
    ShareLinkAccess rows -- a guest link's render must never fail, slow down,
    or 500 because its access log couldn't be written.

    The one exception to "just insert": a repeat of the SAME render inside
    `_SHARE_ACCESS_DEDUPE_S` is dropped, because the owner reads these rows as
    a count of visits. The extra SELECT is on an indexed column and still
    inside the same never-raises envelope.
    """
    try:
        from ..models.models import ShareLinkAccess

        table = ShareLinkAccess.__table__
        engine = _get_engine()
        with engine.begin() as conn:
            if _share_access_is_repeat(conn, table, fields):
                return
            conn.execute(table.insert().values(**fields))
    except Exception:
        logger.warning("share_link_access logging failed", exc_info=True)


def _share_access_is_repeat(conn, table, fields) -> bool:
    """Whether an identical access row was written moments ago.

    "Identical" is link + viewer + ip_hash + user_agent: everything that
    identifies WHO is looking. `None` is matched as NULL rather than compared
    with `=`, which in SQL is never true and would defeat the whole check for
    anonymous visitors -- the common case for a guest link.
    """
    from sqlalchemy import select as sa_select

    cutoff = datetime.utcnow() - timedelta(seconds=_SHARE_ACCESS_DEDUPE_S)
    where = [table.c.ts >= cutoff]
    for col in ("share_link_id", "viewer_user_id", "ip_hash", "user_agent"):
        value = fields.get(col)
        where.append(table.c[col].is_(None) if value is None else table.c[col] == value)
    return conn.execute(sa_select(table.c.id).where(*where).limit(1)).first() is not None


def log_delivery_sync(**fields) -> None:
    """T3: same fire-and-forget contract as the loggers above, for Delivery
    rows -- a scheduled report send or an alert evaluation must never fail,
    slow down, or lose its outcome because this log write couldn't happen."""
    try:
        from ..models.models import Delivery

        engine = _get_engine()
        with engine.begin() as conn:
            conn.execute(Delivery.__table__.insert().values(**fields))
    except Exception:
        logger.warning("delivery logging failed", exc_info=True)
