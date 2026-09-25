"""Task O2: cache_backend.py -- InProcessCache and ValkeyCache against one
interface, sha256 key-hashing, connection-failure cooldown fallback, and
shared-fakeredis multi-"worker" visibility."""
import hashlib
import time

import fakeredis
import pytest

from app.services.cache_backend import InProcessCache, ValkeyCache


# ── Interface parity: both impls behave the same for basic get/set ─────────

def _both_backends():
    fake = fakeredis.FakeRedis()
    return [InProcessCache(maxsize=500), ValkeyCache(client=fake, key_prefix="wdc:")]


@pytest.mark.parametrize("backend", _both_backends())
def test_get_missing_key_returns_none(backend):
    assert backend.get("nope") is None


@pytest.mark.parametrize("backend", _both_backends())
def test_set_then_get_roundtrips(backend):
    backend.set("k1", b"hello", ttl_s=60)
    assert backend.get("k1") == b"hello"


@pytest.mark.parametrize("backend", _both_backends())
def test_overwrite_replaces_value(backend):
    backend.set("k1", b"old", ttl_s=60)
    backend.set("k1", b"new", ttl_s=60)
    assert backend.get("k1") == b"new"


# ── InProcessCache: LRU bound, dynamic maxsize ──────────────────────────────

def test_inprocess_cache_evicts_least_recently_used_beyond_maxsize():
    c = InProcessCache(maxsize=2)
    c.set("a", b"1")
    c.set("b", b"2")
    c.set("c", b"3")
    assert len(c) == 2
    assert c.get("a") is None  # evicted
    assert c.get("b") == b"2"
    assert c.get("c") == b"3"


def test_inprocess_cache_get_marks_most_recently_used():
    c = InProcessCache(maxsize=2)
    c.set("a", b"1")
    c.set("b", b"2")
    c.get("a")          # touch a -- b is now the LRU victim
    c.set("c", b"3")
    assert c.get("a") == b"1"
    assert c.get("b") is None
    assert c.get("c") == b"3"


def test_inprocess_cache_maxsize_accepts_a_callable_read_at_set_time():
    bound = {"n": 5}
    c = InProcessCache(maxsize=lambda: bound["n"])
    for i in range(5):
        c.set(str(i), b"x")
    assert len(c) == 5
    bound["n"] = 2
    c.set("new", b"y")
    assert len(c) == 2


def test_inprocess_cache_can_share_an_external_store_object():
    store = {}
    from collections import OrderedDict
    od = OrderedDict(store)
    c = InProcessCache(maxsize=500, store=od)
    c.set("k", b"v")
    assert od["k"] == b"v"   # writes are visible on the caller's own object


def test_inprocess_delete_prefix_removes_matching_keys_only():
    c = InProcessCache(maxsize=500)
    c.set("wdc:a", b"1")
    c.set("wdc:b", b"2")
    c.set("other:c", b"3")
    c.delete_prefix("wdc:")
    assert c.get("wdc:a") is None
    assert c.get("wdc:b") is None
    assert c.get("other:c") == b"3"


# ── ValkeyCache: sha256-hashed keys, no raw text on the wire ────────────────

def test_valkey_cache_keys_are_sha256_hashed_not_raw():
    fake = fakeredis.FakeRedis()
    c = ValkeyCache(client=fake, key_prefix="wdc:")
    raw_key = "org=1|rls=region == 'sensitive-east-region'|cache_epoch=3"
    c.set(raw_key, b"payload", ttl_s=60)

    stored_keys = [k.decode() for k in fake.keys("*")]
    assert len(stored_keys) == 1
    assert raw_key not in stored_keys[0]
    assert "sensitive-east-region" not in stored_keys[0]

    expected = "wdc:" + hashlib.sha256(raw_key.encode("utf-8", "surrogatepass")).hexdigest()
    assert stored_keys[0] == expected


def test_valkey_cache_get_reads_back_the_hashed_key():
    fake = fakeredis.FakeRedis()
    c = ValkeyCache(client=fake, key_prefix="wdc:")
    c.set("some-key", b"value", ttl_s=60)
    assert c.get("some-key") == b"value"


def test_valkey_cache_sets_a_ttl():
    fake = fakeredis.FakeRedis()
    c = ValkeyCache(client=fake, key_prefix="wdc:")
    c.set("k", b"v", ttl_s=60)
    hkey = "wdc:" + hashlib.sha256(b"k").hexdigest()
    ttl = fake.ttl(hkey)
    assert 0 < ttl <= 60


# ── ValkeyCache: connection-failure cooldown fallback (mirrors retrieval.py) ─

class _BoomClient:
    """A fake redis client whose every call raises, simulating a dead Valkey."""
    def get(self, *a, **k): raise ConnectionError("boom")
    def set(self, *a, **k): raise ConnectionError("boom")
    def scan(self, *a, **k): raise ConnectionError("boom")
    def delete(self, *a, **k): raise ConnectionError("boom")


def test_connection_failure_falls_back_to_in_process_cache():
    fallback = InProcessCache(maxsize=500)
    c = ValkeyCache(client=_BoomClient(), fallback=fallback, cooldown_s=300.0)

    c.set("k", b"v", ttl_s=60)         # fails against the client, lands in fallback
    assert c.get("k") == b"v"          # served from fallback


def test_cooldown_skips_the_dead_client_until_it_expires(monkeypatch):
    fallback = InProcessCache(maxsize=500)
    c = ValkeyCache(client=_BoomClient(), fallback=fallback, cooldown_s=300.0)

    calls = {"n": 0}
    real_get = _BoomClient.get
    def counting_get(self, *a, **k):
        calls["n"] += 1
        return real_get(self, *a, **k)
    monkeypatch.setattr(_BoomClient, "get", counting_get)

    c.get("k")  # 1st call: hits the client, fails, opens the circuit
    c.get("k")  # 2nd call: circuit open, must NOT touch the client again
    assert calls["n"] == 1


def test_circuit_recovers_after_cooldown_elapses(monkeypatch):
    fallback = InProcessCache(maxsize=500)
    c = ValkeyCache(client=_BoomClient(), fallback=fallback, cooldown_s=10.0)

    t = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: t["now"])

    c.get("k")               # opens the circuit at t=1000
    assert c._circuit_open() is True
    t["now"] += 11.0         # past the 10s cooldown
    assert c._circuit_open() is False


def test_error_is_logged_only_once(monkeypatch, caplog):
    import logging
    fallback = InProcessCache(maxsize=500)
    c = ValkeyCache(client=_BoomClient(), fallback=fallback, cooldown_s=0.0)

    with caplog.at_level(logging.ERROR, logger="app.services.cache_backend"):
        c.get("k")
        c.get("k")
        c.get("k")

    messages = [r for r in caplog.records if "falling back to in-process" in r.message]
    assert len(messages) == 1


# ── Two-instance shared-fakeredis visibility (simulates two workers) ───────

def test_two_valkey_cache_instances_over_the_same_server_see_each_others_entries():
    server = fakeredis.FakeServer()
    client_a = fakeredis.FakeRedis(server=server)
    client_b = fakeredis.FakeRedis(server=server)

    worker_a = ValkeyCache(client=client_a, key_prefix="wdc:")
    worker_b = ValkeyCache(client=client_b, key_prefix="wdc:")

    worker_a.set("shared-key", b"written-by-a", ttl_s=60)
    assert worker_b.get("shared-key") == b"written-by-a"


def test_two_in_process_caches_do_not_share_entries():
    """Sanity check for the contrast: InProcessCache is per-worker by
    construction -- this is exactly why Valkey exists as the optional
    shared-tier upgrade."""
    a = InProcessCache(maxsize=500)
    b = InProcessCache(maxsize=500)
    a.set("k", b"v")
    assert b.get("k") is None
