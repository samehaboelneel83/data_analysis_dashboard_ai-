"""The same work asked for by several people at once is done once.

Ten people open the same dashboard on a huge dataset: ten identical queries
reach the server within a second, none of them has an answer in the result
cache yet, and each used to run the whole computation -- on a live source, ten
copies of the same heavy query on somebody's database.

`run(key, fn)`: the first caller for a key computes; callers that arrive while
it is running wait and are handed a copy of its result. If the leader fails,
each follower computes for itself (its error is its own to report). Nothing is
kept after the leader returns: this is not a cache, only the removal of
duplicates in flight.
"""
from __future__ import annotations

import copy
import threading

_LOCK = threading.Lock()
_FLIGHTS: dict = {}
#: A follower does not wait for ever on a leader that hangs.
WAIT_S = 300.0
#: For tests and metrics: how many calls were answered by somebody else's work.
shared_answers = 0


class _Flight:
    __slots__ = ("done", "result", "ok")

    def __init__(self):
        self.done = threading.Event()
        self.result = None
        self.ok = False


#: Across server processes (production runs several workers), with the shared
#: store configured: how long another process's computation is waited for, and
#: how often it is looked at. The waiter then runs `fn` itself -- which finds
#: the leader's answer in the shared result cache instead of computing again.
ACROSS_WAIT_S = 120.0
ACROSS_POLL_S = 0.05
_client = None
_client_for = None


def _shared():
    """The shared store's client, or None when there is none (one process, or
    no VALKEY_URL): then duplicates are removed within this process only."""
    global _client, _client_for
    from ..core.config import settings
    url = getattr(settings, "valkey_url", None) or None
    if not url:
        return None
    if _client is None or _client_for != url:
        try:
            import redis
            _client, _client_for = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2), url
        except Exception:                                   # noqa: BLE001
            return None
    return _client


def _across(key: str, fn):
    """`fn()`, but if another PROCESS is already computing `key`, wait for it
    to finish first. Any trouble with the shared store means "just compute"."""
    import os
    import time
    import uuid
    client = _shared()
    if client is None:
        return fn()
    name, mine = "sf:" + key, uuid.uuid4().hex + ":" + str(os.getpid())
    try:
        leader = bool(client.set(name, mine, nx=True, ex=int(WAIT_S)))
    except Exception:                                       # noqa: BLE001
        return fn()
    if not leader:
        global waited_across
        with _LOCK:
            waited_across += 1
        deadline = time.monotonic() + ACROSS_WAIT_S
        try:
            while time.monotonic() < deadline and client.exists(name):
                time.sleep(ACROSS_POLL_S)
        except Exception:                                   # noqa: BLE001
            pass
        return fn()
    try:
        return fn()
    finally:
        try:
            if (client.get(name) or b"").decode() == mine:
                client.delete(name)
        except Exception:                                   # noqa: BLE001
            pass


#: For tests and metrics: how many calls waited for another process's work.
waited_across = 0


def run(key, fn):
    """`fn()` -- or, when the same `key` is already being computed, a deep copy
    of that computation's result. `key` None means "never share"."""
    global shared_answers
    if key is None:
        return fn()
    work = fn
    fn = lambda: _across(key, work)                         # noqa: E731
    with _LOCK:
        flight = _FLIGHTS.get(key)
        leader = flight is None
        if leader:
            flight = _FLIGHTS[key] = _Flight()
    if not leader:
        if flight.done.wait(WAIT_S) and flight.ok:
            with _LOCK:
                shared_answers += 1
            return copy.deepcopy(flight.result)
        return fn()
    try:
        flight.result = fn()
        flight.ok = True
        return flight.result
    finally:
        with _LOCK:
            _FLIGHTS.pop(key, None)
        flight.done.set()


def key_of(*parts) -> str | None:
    """A key from anything JSON can say; None when it cannot (then nothing is shared)."""
    import hashlib
    import json
    try:
        return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    except Exception:                                       # noqa: BLE001
        return None
