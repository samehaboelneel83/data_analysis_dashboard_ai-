"""E14: limits every API process shares, through Valkey when there is one.

Against a real redis-server (Valkey speaks the same protocol) started for the
test; skipped where there is none. "Another process" is modelled the way it
differs in production: a fresh client and empty per-process state -- the
in-process buckets and counters are cleared between the two halves, so only
what is in Valkey carries over.
"""
import asyncio
import shutil
import socket
import subprocess
import time

import pytest

from app.core import rate_limit as rl
from app.core import shared_limits as sl
from app.core.config import settings
from app.services import quotas

pytestmark = pytest.mark.skipif(shutil.which("redis-server") is None, reason="no redis-server")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def valkey():
    port = _free_port()
    proc = subprocess.Popen(["redis-server", "--port", str(port), "--save", "", "--appendonly", "no"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"redis://127.0.0.1:{port}/0"
    proc.terminate()
    proc.wait(5)


@pytest.fixture(autouse=True)
def _shared(valkey, monkeypatch):
    monkeypatch.setattr(settings, "valkey_url", valkey)
    monkeypatch.setattr(rl, "is_test_mode", lambda: False)
    sl.reset()
    rl.reset_buckets()
    quotas.reset_concurrent_counts()
    import redis
    redis.Redis.from_url(valkey).flushdb()
    yield
    sl.reset()
    rl.reset_buckets()


def another_process():
    """What a second API process has: no client yet, no local state."""
    sl.reset()
    rl.reset_buckets()
    quotas.reset_concurrent_counts()


class TestBuckets:
    async def test_the_ceiling_is_shared_across_processes(self):
        assert (await sl.consume_token("user:1", 3, 60))[0] is True
        assert (await sl.consume_token("user:1", 3, 60))[0] is True
        another_process()
        assert (await sl.consume_token("user:1", 3, 60))[0] is True
        ok, retry = await sl.consume_token("user:1", 3, 60)
        assert ok is False and 0 < retry <= 20

    async def test_keys_are_separate_and_refill(self):
        for _ in range(2):
            assert (await sl.consume_token("user:1", 2, 1))[0]
        assert (await sl.consume_token("user:1", 2, 1))[0] is False
        assert (await sl.consume_token("user:2", 2, 1))[0] is True
        await asyncio.sleep(0.6)                   # 2 tokens a second
        assert (await sl.consume_token("user:1", 2, 1))[0] is True

    async def test_no_two_callers_take_the_last_token(self):
        results = await asyncio.gather(*[sl.consume_token("burst", 5, 60) for _ in range(20)])
        assert sum(ok for ok, _ in results) == 5


class TestTheMiddleware:
    async def test_a_second_process_does_not_grant_a_fresh_allowance(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "rate_limit_requests_per_window", 2)
        monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
        for _ in range(2):
            assert (await client.get("/api/v1/admin/roles", headers=auth_headers["a"])).status_code == 200
        another_process()
        r = await client.get("/api/v1/admin/roles", headers=auth_headers["a"])
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


class TestAskSlots:
    async def test_one_slot_is_one_slot_in_every_process(self):
        assert await sl.acquire_slot("asks:1", 1) is True
        another_process()
        assert await sl.acquire_slot("asks:1", 1) is False
        await sl.release_slot("asks:1")
        assert await sl.acquire_slot("asks:1", 1) is True

    async def test_a_release_never_goes_below_zero(self):
        await sl.release_slot("asks:9")
        assert await sl.acquire_slot("asks:9", 1) is True
        assert await sl.acquire_slot("asks:9", 1) is False

    async def test_the_ask_gate_uses_it(self, db_session, two_orgs):
        from app.models.models import Quota
        org = two_orgs["a"]["org"]
        db_session.add(Quota(org_id=org.id, max_concurrent_asks=1))
        await db_session.commit()
        quotas.invalidate_quota_cache()
        async with quotas.concurrent_ask_slot(db_session, org.id):
            another_process()
            with pytest.raises(quotas.QuotaExceeded):
                async with quotas.concurrent_ask_slot(db_session, org.id):
                    pass
        async with quotas.concurrent_ask_slot(db_session, org.id):
            pass                                    # released on the way out


class TestWhenValkeyIsDown:
    async def test_everything_falls_back_to_this_process(self, client, monkeypatch):
        monkeypatch.setattr(settings, "valkey_url", f"redis://127.0.0.1:{_free_port()}/0")
        sl.reset()
        assert await sl.consume_token("k", 1, 60) is None
        assert await sl.acquire_slot("k", 1) is None
        # And it stops trying for a while: the next call does not wait on a
        # connection at all.
        t0 = time.monotonic()
        assert await sl.consume_token("k", 1, 60) is None
        assert time.monotonic() - t0 < 0.05
        monkeypatch.setattr(settings, "rate_limit_requests_per_window", 1)
        assert (await client.get("/api/v1/does-not-exist-xyz")).status_code == 404
        assert (await client.get("/api/v1/does-not-exist-xyz")).status_code == 429
