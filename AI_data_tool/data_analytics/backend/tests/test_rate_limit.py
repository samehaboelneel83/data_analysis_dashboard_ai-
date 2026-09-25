"""S5 rate limiting middleware (core/rate_limit.py): in-process token bucket,
per-key isolation, guest bucket, health exemption, and the test-mode bypass
that keeps the rest of the suite from tripping it."""
import pytest

from app.core import rate_limit as rl


@pytest.fixture(autouse=True)
def _defeat_test_bypass(monkeypatch):
    """The middleware bypasses itself under pytest by design (see
    rate_limit.is_test_mode) -- these tests exist to exercise the real
    behaviour, so they turn the bypass off and reset bucket state around
    every test."""
    monkeypatch.setattr(rl, "is_test_mode", lambda: False)
    rl.reset_buckets()
    yield
    rl.reset_buckets()


async def test_under_limit_requests_all_pass(client, monkeypatch):
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 3)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    for _ in range(3):
        resp = await client.get("/api/v1/does-not-exist-xyz")
        assert resp.status_code == 404   # reached routing, not rate-limited


async def test_over_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 2)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    for _ in range(2):
        resp = await client.get("/api/v1/does-not-exist-xyz")
        assert resp.status_code == 404
    resp = await client.get("/api/v1/does-not-exist-xyz")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


async def test_health_is_exempt(client, monkeypatch):
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    for _ in range(5):
        resp = await client.get("/health")
        assert resp.status_code == 200


async def test_per_key_isolation_different_users_have_separate_buckets(client, auth_headers, monkeypatch):
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 2)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    for _ in range(2):
        resp = await client.get("/api/v1/admin/roles", headers=auth_headers["a"])
        assert resp.status_code == 200
    exhausted = await client.get("/api/v1/admin/roles", headers=auth_headers["a"])
    assert exhausted.status_code == 429

    # Org B's admin is a distinct key (distinct user id) -- untouched by A's usage.
    still_ok = await client.get("/api/v1/admin/roles", headers=auth_headers["b"])
    assert still_ok.status_code == 200


async def test_guest_bucket_is_stricter_and_keyed_per_link(client, monkeypatch):
    monkeypatch.setattr(rl.settings, "rate_limit_guest_requests_per_window", 1)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    # Generous general bucket so only the guest tier is under test.
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1000)

    first = await client.get("/api/v1/shared/token-aaa")
    assert first.status_code != 429
    second = await client.get("/api/v1/shared/token-aaa")
    assert second.status_code == 429
    assert "Retry-After" in second.headers

    # A different share link is a different bucket -- untouched.
    other_link = await client.get("/api/v1/shared/token-bbb")
    assert other_link.status_code != 429


async def test_guest_bucket_is_keyed_per_viewer_not_just_per_link(client, auth_headers, monkeypatch):
    """Two colleagues opening the SAME share link must not share one bucket --
    that was the bug: one viewer's requests could exhaust the link's whole
    ceiling and 429 everyone else looking at it. Each authenticated viewer
    identity gets its own sub-bucket within the token."""
    monkeypatch.setattr(rl.settings, "rate_limit_guest_requests_per_window", 1)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1000)

    first = await client.get("/api/v1/shared/token-shared", headers=auth_headers["a"])
    assert first.status_code != 429
    exhausted = await client.get("/api/v1/shared/token-shared", headers=auth_headers["a"])
    assert exhausted.status_code == 429

    # Same token, different viewer identity -- independent bucket, untouched.
    still_ok = await client.get("/api/v1/shared/token-shared", headers=auth_headers["b"])
    assert still_ok.status_code != 429


async def test_embed_enumeration_from_one_ip_is_throttled_by_ip_bucket(client, monkeypatch):
    """`_embed_key`'s bucket is keyed by the token itself, so a caller minting
    a fresh garbage token on every request got a brand-new, full bucket every
    time -- unthrottled enumeration. The IP-only bucket (`_embed_ip_key`) is
    keyed at the general capacity regardless of token, so it trips after the
    IP's own budget even though every request presents a distinct token."""
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 3)
    monkeypatch.setattr(rl.settings, "rate_limit_guest_requests_per_window", 1000)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)

    statuses = []
    for i in range(4):
        resp = await client.get("/api/v1/embed/report", params={"token": f"garbage-{i}"})
        statuses.append(resp.status_code)

    assert statuses[:3].count(429) == 0
    assert statuses[3] == 429


async def test_embed_valid_token_distinct_viewers_unaffected_by_ip_budget(client, monkeypatch):
    """The IP-bucket must not punish ordinary traffic: many requests against
    ONE valid token from one IP stay within the per-token (guest-tier) bucket
    and the general IP bucket independently -- generous general capacity
    means normal single-embed usage never trips the IP guard meant for
    multi-token enumeration."""
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1000)
    monkeypatch.setattr(rl.settings, "rate_limit_guest_requests_per_window", 1000)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)

    for _ in range(5):
        resp = await client.get("/api/v1/embed/report", params={"token": "same-valid-token"})
        assert resp.status_code != 429


async def test_disabled_via_settings_never_429s(client, monkeypatch):
    monkeypatch.setattr(rl.settings, "rate_limit_enabled", False)
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    for _ in range(10):
        resp = await client.get("/api/v1/does-not-exist-xyz")
        assert resp.status_code == 404


async def test_bucket_store_is_bounded_and_evicts_lru(monkeypatch):
    """Bucket keys are attacker-influenced (bogus guest tokens, source IPs);
    a long-lived worker fielding many distinct ones must not grow the store
    without bound. Filling well past a small cap must keep the dict at or
    under cap, and a key touched most recently must survive eviction."""
    monkeypatch.setattr(rl.settings, "rate_limit_bucket_cap", 50)

    # A recently-used key, kept "warm" throughout the fill.
    rl._bucket_for("keep-me", capacity=100, window_seconds=60)

    for i in range(500):
        rl._bucket_for(f"distinct-{i}", capacity=100, window_seconds=60)
        rl._bucket_for("keep-me", capacity=100, window_seconds=60)   # stays LRU-fresh

    assert len(rl._buckets) <= 50
    assert "keep-me" in rl._buckets

    # A key that survived eviction still rate-limits correctly (fresh bucket,
    # capacity honoured), proving eviction doesn't corrupt live state.
    bucket = rl._buckets["keep-me"]
    ok, _ = bucket.consume(1.0)
    assert ok is True


async def test_disabled_in_test_mode_by_default(client, monkeypatch):
    """With the bypass restored (the normal, non-monkeypatched state), a tight
    limit never trips -- this is what keeps the rest of the backend suite
    safe from rate limiting."""
    monkeypatch.setattr(rl, "is_test_mode", lambda: True)
    monkeypatch.setattr(rl.settings, "rate_limit_requests_per_window", 1)
    monkeypatch.setattr(rl.settings, "rate_limit_window_seconds", 60)
    for _ in range(10):
        resp = await client.get("/api/v1/does-not-exist-xyz")
        assert resp.status_code == 404
