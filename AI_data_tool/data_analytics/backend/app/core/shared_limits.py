"""Limits shared by every API process, through Valkey when there is one (E14).

The rate limiter's buckets and the AI concurrent-ask counter lived in each
process's memory, so a deployment of N API processes allowed N times the
configured ceiling, and one person could hold a slot in every process. With
`settings.valkey_url` set (the same Valkey the result cache can use), both
live there instead, and the ceiling is the configured one whichever process
a request lands on.

Honest failure: no Valkey configured, or Valkey unreachable, and every call
here answers None -- the caller falls back to its per-process state, as
before. A dead Valkey never turns into 429s or refused questions; after a
failure the shared path is skipped for a cooldown, so a down Valkey costs one
timeout, not one per request.

The bucket is the same continuous-refill token bucket as the in-process one,
run as one Lua script so concurrent processes cannot both take the last
token; its clock is Valkey's (TIME), so processes with drifting clocks agree.
"""
from __future__ import annotations

import asyncio
import logging
import time
import weakref

from .config import settings

log = logging.getLogger(__name__)

_COOLDOWN_S = 30.0
#: One async client per event loop (a connection belongs to the loop that
#: opened it; tests, and anything that runs its own loop, get their own).
_clients: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_down_until = 0.0

#: KEYS[1] bucket; ARGV capacity, refill per second, ttl ms.
#: Returns {1|0, retry-after seconds as text}.
_BUCKET = """
local cap = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local b = redis.call('HMGET', KEYS[1], 'tokens', 'last')
local tokens = tonumber(b[1]) or cap
local last = tonumber(b[2]) or now
tokens = math.min(cap, tokens + math.max(0, now - last) * rate)
local ok, retry = 0, 0
if tokens >= 1 then tokens = tokens - 1; ok = 1
elseif rate > 0 then retry = (1 - tokens) / rate else retry = 1 end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'last', tostring(now))
redis.call('PEXPIRE', KEYS[1], ARGV[3])
return {ok, tostring(retry)}
"""

#: KEYS[1] counter; ARGV limit, ttl s. Returns 1 when a slot was taken.
_ACQUIRE = """
local n = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
if n > tonumber(ARGV[1]) then redis.call('DECR', KEYS[1]); return 0 end
return 1
"""

_RELEASE = """
local n = redis.call('DECR', KEYS[1])
if n < 0 then redis.call('SET', KEYS[1], 0) end
return n
"""


def _get_client():
    """The async client, or None when there is no Valkey or it is cooling off."""
    url = settings.valkey_url
    if not url or time.monotonic() < _down_until:
        return None
    loop = asyncio.get_running_loop()
    cached = _clients.get(loop)
    if cached is None or cached[0] != url:
        import redis.asyncio as aioredis  # optional dependency, only on this path
        cached = (url, aioredis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1))
        _clients[loop] = cached
    return cached[1]


def _failed(what: str) -> None:
    global _down_until
    if time.monotonic() >= _down_until:
        log.warning("shared limits: Valkey unavailable for %s; using per-process limits for %.0fs",
                    what, _COOLDOWN_S)
    _down_until = time.monotonic() + _COOLDOWN_S


def reset() -> None:
    """Test hook: forget the clients and any cooldown."""
    global _down_until
    _clients.clear()
    _down_until = 0.0


async def consume_token(key: str, capacity: int, window_seconds: int) -> tuple[bool, float] | None:
    """Take one token from the shared bucket `key`; None when not shared."""
    client = _get_client()
    if client is None:
        return None
    rate = capacity / window_seconds if window_seconds > 0 else float(capacity)
    try:
        ok, retry = await client.eval(_BUCKET, 1, f"dl:rl:{key}", capacity, rate,
                                      int(max(window_seconds, 1) * 2000))
    except Exception:                               # noqa: BLE001 -- any failure: fall back
        _failed("rate limits")
        return None
    return bool(int(ok)), float(retry)


async def acquire_slot(key: str, limit: int, ttl_s: int = 900) -> bool | None:
    """Take one of `limit` shared slots; None when not shared. The TTL bounds
    a slot leaked by a process that died holding it."""
    client = _get_client()
    if client is None:
        return None
    try:
        return bool(int(await client.eval(_ACQUIRE, 1, f"dl:slot:{key}", limit, ttl_s)))
    except Exception:                               # noqa: BLE001
        _failed("concurrency slots")
        return None


async def release_slot(key: str) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        await client.eval(_RELEASE, 1, f"dl:slot:{key}")
    except Exception:                               # noqa: BLE001
        _failed("concurrency slots")
