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


def run(key, fn):
    """`fn()` -- or, when the same `key` is already being computed, a deep copy
    of that computation's result. `key` None means "never share"."""
    global shared_answers
    if key is None:
        return fn()
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
