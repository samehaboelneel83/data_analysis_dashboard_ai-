"""Task O2: shared result-cache backend abstraction.

One interface, two implementations, used by the widget-result LRU caches in
`direct_query.py` (via `widget_data.py`) and `widget_data.py` itself:

- `InProcessCache`: an OrderedDict-backed LRU. This is the pre-O2 behavior,
  unpacked into a reusable class. It is duck-typed on purpose -- it stores
  whatever object it is given (a plain result dict today), NOT necessarily
  bytes, so `widget_data.py` can point it at the exact same `OrderedDict`
  object its own pre-O2 tests introspect (`wd._WIDGET_DATA_CACHE`) and get
  byte-identical behavior when `settings.valkey_url` is None -- no
  serialization round-trip, no new failure mode, existing tests untouched.
  `maxsize` may be an int or a zero-arg callable (`lambda: settings.x`), so a
  test that monkeypatches the setting after construction is still honored at
  `set()` time, matching the old module-level function's behavior of reading
  `settings.widget_data_cache_maxsize` fresh on every call.

- `ValkeyCache`: a Redis-protocol client (works against real Valkey or
  fakeredis) for deployments that opt in via `settings.valkey_url`. Values
  crossing the wire are `bytes` (JSON-encoded by the caller). Keys are
  sha256-hashed before being sent -- the existing widget/DirectQuery cache
  KEYS already embed RLS expression text verbatim (load-bearing for RLS
  isolation, see widget_data._widget_data_cache_key), so hashing at this
  boundary is what keeps that raw text from ever leaving the process. On any
  connection failure it logs once and falls back to an in-process cache for a
  cooldown window -- the same circuit-breaker shape as Backend B in
  services/retrieval.py (`_circuit_open`/`_open_circuit`), sharpened here to
  an instance attribute rather than a module global so tests can construct
  independent circuits.

Because keys are hashed one-way, `delete_prefix` cannot reverse a raw prefix
into the hashed keyspace it would need to SCAN -- see `ValkeyCache.
delete_prefix`'s docstring for the one flush case it does support.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Callable

logger = logging.getLogger(__name__)


class CacheBackend:
    """Interface implemented by InProcessCache and ValkeyCache."""

    def get(self, key: str):
        raise NotImplementedError

    def set(self, key: str, value, ttl_s: int = 0) -> None:
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> None:
        raise NotImplementedError


class InProcessCache(CacheBackend):
    """LRU OrderedDict-backed cache. TTL is accepted and ignored -- every
    caller already encodes freshness into the KEY (a `now // ttl_seconds`
    bucket for DirectQuery, a file `(mtime, size)` tuple for the import path,
    `cache_epoch` for drift), so a stale entry simply becomes unaddressable
    rather than needing active expiry. That is exactly the pre-O2 behavior;
    this class does not change it.
    """

    def __init__(self, maxsize: int | Callable[[], int] = 500,
                 store: "OrderedDict | None" = None):
        self._store: "OrderedDict" = store if store is not None else OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def _resolved_maxsize(self) -> int:
        return self._maxsize() if callable(self._maxsize) else self._maxsize

    def get(self, key: str):
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)  # mark most-recently-used
                return self._store[key]
        return None

    def set(self, key: str, value, ttl_s: int = 0) -> None:
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            maxsize = self._resolved_maxsize()
            while len(self._store) > maxsize:
                self._store.popitem(last=False)  # evict least-recently-used

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            victims = [k for k in self._store if k.startswith(prefix)]
            for k in victims:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class ValkeyCache(CacheBackend):
    """Redis-protocol client cache. Construct with either `valkey_url` (a
    real `redis.Redis` client is built from it) or an already-built `client`
    (how tests inject a `fakeredis.FakeRedis` instance without a network).

    Values are opaque `bytes` in and out -- callers own JSON-encoding their
    result dicts before `set()` and decoding what `get()` returns.
    """

    def __init__(self, valkey_url: str | None = None, key_prefix: str = "wdc:",
                 fallback: CacheBackend | None = None,
                 cooldown_s: float = 300.0, client=None):
        self._prefix = key_prefix
        self._fallback = fallback if fallback is not None else InProcessCache()
        self._cooldown_s = cooldown_s
        self._circuit_opened_at: float | None = None
        self._error_logged = False
        self._lock = threading.Lock()
        if client is not None:
            self._client = client
        else:
            import redis  # local: optional dependency, only needed on this path
            self._client = redis.Redis.from_url(
                valkey_url, socket_timeout=2, socket_connect_timeout=2)

    def _hashed(self, key: str) -> str:
        return self._prefix + hashlib.sha256(
            key.encode("utf-8", "surrogatepass")).hexdigest()

    def _circuit_open(self) -> bool:
        if self._circuit_opened_at is None:
            return False
        return (time.monotonic() - self._circuit_opened_at) < self._cooldown_s

    def _open_circuit(self) -> None:
        with self._lock:
            self._circuit_opened_at = time.monotonic()
            if not self._error_logged:
                logger.exception(
                    "cache_backend: Valkey connection failed, falling back to "
                    "in-process cache for %.0fs", self._cooldown_s)
                self._error_logged = True

    def get(self, key: str):
        if self._circuit_open():
            return self._fallback.get(key)
        try:
            return self._client.get(self._hashed(key))
        except Exception:
            self._open_circuit()
            return self._fallback.get(key)

    def set(self, key: str, value, ttl_s: int = 0) -> None:
        if self._circuit_open():
            self._fallback.set(key, value, ttl_s)
            return
        try:
            hkey = self._hashed(key)
            if ttl_s and ttl_s > 0:
                self._client.set(hkey, value, ex=int(ttl_s))
            else:
                self._client.set(hkey, value)
        except Exception:
            self._open_circuit()
            self._fallback.set(key, value, ttl_s)

    def delete_prefix(self, prefix: str) -> None:
        """Hashing is one-way, so a raw `prefix` cannot be turned into the
        hashed keys that would need to be SCANned -- there is no index from
        prefix to hash. The one case this DOES support is a full flush of
        this backend's own namespace (`prefix == ""`), via SCAN over
        `key_prefix*`. Any other prefix only clears the in-process fallback
        (best effort) and is a documented limitation, not a silent bug: no
        caller in this codebase relies on a targeted Valkey-side prefix
        delete today (cache_epoch/TTL/mtime keys already make stale entries
        unaddressable without one)."""
        if prefix == "":
            if not self._circuit_open():
                try:
                    cursor = 0
                    pattern = f"{self._prefix}*".encode()
                    while True:
                        cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=500)
                        if keys:
                            self._client.delete(*keys)
                        if cursor == 0:
                            break
                except Exception:
                    self._open_circuit()
        self._fallback.delete_prefix(prefix)
