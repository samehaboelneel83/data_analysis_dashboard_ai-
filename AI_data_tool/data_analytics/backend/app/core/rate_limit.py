"""In-process token-bucket rate limiting middleware (S5).

No Valkey/Redis in this stack, so limiting is per-worker and honest about it:
each uvicorn worker enforces its own buckets in memory, so the effective
ceiling scales with worker count. Documented, not hidden -- see
`settings.rate_limit_*`.

Two tiers, keyed differently:
  * general authenticated/anonymous traffic -- keyed by user id, decoded
    straight off the bearer token (no DB hit, so the check stays cheap) or by
    client IP when there is none.
  * guest/share routes (`/api/v1/shared/{token}...`) -- a stricter, separate
    bucket per (share link, viewer) -- the token in the path plus whichever
    viewer identity `_guest_key` can find (authenticated user id, else client
    IP) -- because a guest link is handed to people outside the org and
    deserves its own ceiling independent of however busy the rest of the app
    is, AND because one link is routinely opened by several distinct viewers
    at once, who must not share a single bucket with each other.

`/health` is exempt (used by liveness probes, must never 429).

Bypassed entirely while pytest is running (`PYTEST_CURRENT_TEST`), because the
rest of the suite reuses one client identity across hundreds of requests in a
single process and must not trip this. The rate-limit tests defeat the bypass
explicitly via `is_test_mode`, which they monkeypatch.
"""
from __future__ import annotations

import os
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import settings
from .security import decode_access_token

EXEMPT_PATHS = {"/health"}
GUEST_PREFIX = "/api/v1/shared/"
# Task E1: the embed surface has no login either, so it gets the same stricter,
# separate-from-general-traffic tier as guest share links (settings.rate_limit_
# guest_requests_per_window) -- reused rather than a third setting, since the
# threat model (unauthenticated, externally-distributed credential) is the same.
EMBED_PREFIX = "/api/v1/embed/"


class TokenBucket:
    """Continuous refill, not fixed windows -- capacity tokens available at
    once, refilled evenly at `refill_per_sec` so a burst right at a window
    boundary can't double an allowance."""
    __slots__ = ("capacity", "tokens", "refill_per_sec", "last")

    def __init__(self, capacity: float, refill_per_sec: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_per_sec = refill_per_sec
        self.last = time.monotonic()

    def consume(self, n: float = 1.0) -> tuple[bool, float]:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill_per_sec)
        self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True, 0.0
        deficit = n - self.tokens
        retry_after = deficit / self.refill_per_sec if self.refill_per_sec > 0 else 1.0
        return False, retry_after


# Per-worker, process-lifetime bucket store. Keys are attacker-influenced
# (share tokens, source IPs), so left completely unbounded a long-lived worker
# fielding many distinct bogus guest tokens/IPs would grow this dict forever.
# Bounded by settings.rate_limit_bucket_cap: once full, `_evict_lru` drops the
# least-recently-used entries (their `.last` timestamp) to make room -- an
# evicted key that comes back simply starts a fresh, full bucket, which is a
# harmless one-time freebie, not a correctness issue.
_buckets: dict[str, TokenBucket] = {}


def reset_buckets() -> None:
    """Test hook: clear all bucket state between tests."""
    _buckets.clear()


def is_test_mode() -> bool:
    """True while running under pytest. A free function (not inlined) so tests
    can monkeypatch it to exercise the real limiting behaviour."""
    return "PYTEST_CURRENT_TEST" in os.environ


def _evict_lru(cap: int) -> None:
    """Drop the least-recently-used buckets until the store is back under cap.
    Called only on insert of a new key, so the common case (an existing key
    being reused) never pays this cost."""
    if len(_buckets) < cap:
        return
    # Evict down to 90% of cap so this doesn't re-trigger on every single
    # insert once the store is at capacity.
    target = max(1, int(cap * 0.9))
    oldest_first = sorted(_buckets.items(), key=lambda kv: kv[1].last)
    for key, _ in oldest_first[: len(_buckets) - target]:
        _buckets.pop(key, None)


def _bucket_for(key: str, capacity: int, window_seconds: int) -> TokenBucket:
    refill = capacity / window_seconds if window_seconds > 0 else float(capacity)
    bucket = _buckets.get(key)
    if bucket is None or bucket.capacity != capacity:
        if bucket is None:
            _evict_lru(settings.rate_limit_bucket_cap)
        bucket = TokenBucket(capacity, refill)
        _buckets[key] = bucket
    return bucket


def _session_sub(request: Request) -> str | None:
    """The logged-in user id, from the bearer header or (T6) the browser's
    session cookie -- without the cookie, every browser user would fall back
    to a per-IP bucket and a whole office behind one NAT would share one."""
    from .security import SESSION_COOKIE
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    payload = decode_access_token(token)
    return str(payload["sub"]) if payload and payload.get("sub") else None


def _client_key(request: Request) -> str:
    sub = _session_sub(request)
    if sub:
        return f"user:{sub}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def _guest_key(path: str, request: Request) -> str:
    """Bucket per (share token, viewer) rather than per share token alone --
    a link handed to a team is one token but many viewers, and one shared
    bucket meant the whole team fought over a single ceiling (six colleagues
    opening a twelve-widget report inside the same minute could 429 each
    other out). Viewer identity mirrors `_client_key`: an authenticated
    caller's user id off the bearer token when there is one (a share link
    opened while logged in, or an embed carrying its own auth), else client
    IP -- the same signal already used to separate general traffic, just
    scoped inside this token's own bucket instead of across the whole app."""
    token = path[len(GUEST_PREFIX):].split("/", 1)[0]
    sub = _session_sub(request)
    viewer = f"user:{sub}" if sub else f"ip:{request.client.host if request.client else 'unknown'}"
    return f"guest:{token or 'unknown'}:{viewer}"


def _embed_key(request: Request) -> str:
    """Bucket per (embed credential, viewer). The credential rides differently
    on the embed surface's two routes -- the host JWT as a `token` query param
    on `GET /embed/report`, the internal session JWT as a bearer header on
    `POST /embed/widget-data/{id}` -- so both are checked; whichever is
    present keys the bucket, falling back to client IP alone (still a real
    bucket, just coarser) when neither is."""
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    ip = request.client.host if request.client else "unknown"
    return f"embed:{token or 'unknown'}:{ip}"


def _embed_ip_key(request: Request) -> str:
    """IP-only bucket for the embed surface, consumed ALONGSIDE (not instead
    of) `_embed_key`'s per-(credential, viewer) bucket. That bucket is keyed
    by the token itself, so a caller minting a fresh garbage token on every
    request -- probing `GET /embed/report?token=...` for a valid one -- gets
    a brand-new, full bucket every single time and is never actually
    throttled; worse, each distinct bogus token churns the LRU bucket store.
    This bucket ignores the token entirely and caps by IP alone, at the
    general (not guest) capacity -- generous enough that one IP's ordinary
    multi-viewer traffic on a handful of valid embeds never trips it, tight
    enough that a sweep of garbage tokens from that IP does."""
    ip = request.client.host if request.client else "unknown"
    return f"embed-ip:{ip}"


async def rate_limit_middleware(request: Request, call_next):
    if not settings.rate_limit_enabled or is_test_mode():
        return await call_next(request)

    path = request.url.path
    if path in EXEMPT_PATHS:
        return await call_next(request)

    if path.startswith(GUEST_PREFIX):
        key = _guest_key(path, request)
        capacity = settings.rate_limit_guest_requests_per_window
    elif path.startswith(EMBED_PREFIX):
        # Both buckets must pass: the IP-only one first, since it's the one
        # that actually catches a garbage-token enumeration sweep (see
        # _embed_ip_key) -- the per-(token, ip) bucket below still applies on
        # top, unchanged, for a legitimate credential's own ceiling.
        ip_bucket = _bucket_for(_embed_ip_key(request),
                                settings.rate_limit_requests_per_window,
                                settings.rate_limit_window_seconds)
        ip_ok, ip_retry_after = ip_bucket.consume(1.0)
        if not ip_ok:
            wait_s = max(1, int(ip_retry_after) + 1)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again shortly."},
                headers={"Retry-After": str(wait_s)},
            )
        key = _embed_key(request)
        capacity = settings.rate_limit_guest_requests_per_window
    else:
        key = _client_key(request)
        capacity = settings.rate_limit_requests_per_window

    bucket = _bucket_for(key, capacity, settings.rate_limit_window_seconds)
    ok, retry_after = bucket.consume(1.0)
    if not ok:
        wait_s = max(1, int(retry_after) + 1)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again shortly."},
            headers={"Retry-After": str(wait_s)},
        )
    return await call_next(request)
