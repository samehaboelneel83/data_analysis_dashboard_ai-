"""Does this application survive its own database restarting?

Postgres restarts for ordinary reasons — a minor-version upgrade, a failover, a
container rescheduled, the OOM killer. Every connection already in the pool is
dead the moment it does, and SQLAlchemy does not know that: it hands the next
request a corpse, which fails.

Measured against a real Postgres restart with a warm pool, two engines
identical but for this setting: the plain engine's first request after the
restart raised `InterfaceError`, its second succeeded, and the pre-ping
engine never failed at all. SQLAlchemy invalidates the whole pool generation
once it recognises a disconnect, so the cost of not having this is one failed
request rather than one per pooled connection — and pre-ping takes it to zero.

The boundary this does NOT cover: a request whose connection dies while it is
executing. Nothing in a pool can rescue that; it fails, and lands in the
generic handler that quotes no exception text.

`services/engines.py` already does this for the CUSTOMER's database. This is
about ours — the one every single request touches.

`pool_recycle` is the same problem on a longer timer: pgbouncer, cloud load
balancers and firewalls drop idle connections without telling either end, so
the first request after a quiet period gets a socket that is already closed.
"""
from app.core import database


def test_the_app_pool_checks_a_connection_before_lending_it_out():
    """`_pre_ping` is the only exposed form of the setting; SQLAlchemy keeps no
    public accessor for it."""
    pool = database.engine.pool
    assert getattr(pool, "_pre_ping", False) is True, (
        "the app's own engine hands out pooled connections without checking "
        "them, so a database restart costs one failed request per stale "
        "connection -- after the database is healthy again")


def test_the_app_pool_retires_connections_before_a_proxy_drops_them():
    pool = database.engine.pool
    recycle = getattr(pool, "_recycle", -1)
    assert recycle is not None and recycle > 0, (
        "connections are kept for ever, so the first request after an idle "
        "period can get a socket a proxy has already closed")
    # Half an hour is comfortably inside the common idle timeouts (pgbouncer's
    # server_idle_timeout, most cloud load balancers) without churning
    # connections during normal traffic.
    assert recycle <= 3600


def test_the_customer_engines_still_do_the_same():
    """The setting this file exists to add to OUR engine was already on theirs.

    Pinned together so the two cannot drift apart again: it would be a strange
    system that protected the customer's database from a restart and not its
    own."""
    import inspect

    from app.services import engines

    src = inspect.getsource(engines)
    assert "pool_pre_ping" in src
