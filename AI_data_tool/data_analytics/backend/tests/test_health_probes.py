"""Liveness and readiness probes.

The distinction these tests protect: liveness must NOT depend on Postgres, and
readiness MUST. A liveness probe that touches the database turns a brief
Postgres blip into a restart loop across every replica -- strictly worse than
the outage it was meant to detect. If someone later "improves" /health by
adding a DB check, `test_live_does_not_touch_the_database` fails.
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app import main as main_module
from app.core.config import settings
from app.main import app


async def _get(path: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get(path)


class _BrokenEngine:
    """Stands in for `main.engine` when simulating an unreachable Postgres.

    `AsyncEngine.connect` is a read-only attribute, so it cannot be patched
    directly -- the whole engine object is swapped instead.
    """

    def __init__(self, message: str = "connection refused"):
        self._message = message

    def connect(self):
        raise OSError(self._message)


class _ForbiddenEngine:
    """Fails the test outright if anything opens a connection through it."""

    def connect(self):
        raise AssertionError("liveness must not open a database connection")


class _OkEngine:
    """A reachable Postgres.

    `main.engine` is bound to `settings.database_url` at import, which under
    test is not a database anyone should be dialling: conftest overrides the
    request-scoped session, not this module-level engine. Readiness probes it
    directly, so tests that are not specifically about Postgres being down
    substitute a connection that simply succeeds -- keeping each test about
    the one dependency it names.
    """

    class _Conn:
        async def execute(self, *a, **k):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    def connect(self):
        return self._Conn()


@pytest.fixture(autouse=True)
def _healthy_baseline(monkeypatch):
    """Every test starts from: startup finished, Postgres reachable, no Valkey.

    Each test then breaks exactly one of those. Without this the class running
    first would leave its patches visible to the next -- which is precisely
    what happened while writing these.
    """
    monkeypatch.setattr(main_module, "_STARTUP_COMPLETE", True)
    monkeypatch.setattr(main_module, "engine", _OkEngine())
    monkeypatch.setattr(settings, "valkey_url", None)


class TestLiveness:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        r = await _get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_live_is_an_alias(self):
        assert (await _get("/health/live")).json() == (await _get("/health")).json()

    @pytest.mark.asyncio
    async def test_live_does_not_touch_the_database(self, monkeypatch):
        """Liveness must answer even when Postgres is unreachable."""
        monkeypatch.setattr(main_module, "engine", _ForbiddenEngine())
        assert (await _get("/health")).status_code == 200


class TestReadiness:
    @pytest.mark.asyncio
    async def test_ready_reports_postgres_ok(self):
        r = await _get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["checks"]["postgres"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unreachable_postgres_is_503(self, monkeypatch):
        monkeypatch.setattr(main_module, "engine", _BrokenEngine())
        r = await _get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["postgres"]["status"] == "down"
        assert body["checks"]["postgres"]["required"] is True

    @pytest.mark.asyncio
    async def test_failure_body_carries_no_connection_string(self, monkeypatch):
        """A DSN can carry credentials and this endpoint is unauthenticated."""
        secret = "postgresql://user:hunter2@db:5432/datalytics"
        monkeypatch.setattr(
            main_module, "engine", _BrokenEngine(f"could not connect to {secret}")
        )
        assert "hunter2" not in (await _get("/health/ready")).text

    @pytest.mark.asyncio
    async def test_not_ready_before_startup_completes(self, monkeypatch):
        monkeypatch.setattr(main_module, "_STARTUP_COMPLETE", False)
        r = await _get("/health/ready")
        assert r.status_code == 503
        assert r.json()["checks"]["migrations"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_a_failed_migration_is_not_ready(self, monkeypatch):
        """Startup finished, Postgres answers -- and the schema never reached
        head. That replica must not take traffic; it used to report ready."""
        monkeypatch.setattr(main_module, "_STARTUP_COMPLETE", True)
        monkeypatch.setattr(main_module, "_MIGRATION_ERROR", "StringDataRightTruncationError")
        r = await _get("/health/ready")
        assert r.status_code == 503
        mig = r.json()["checks"]["migrations"]
        assert mig == {"status": "failed", "required": True,
                       "error": "StringDataRightTruncationError"}
        # Liveness is unaffected, so the logs stay reachable.
        assert (await _get("/health/live")).status_code == 200


class TestValkeyIsOptional:
    @pytest.mark.asyncio
    async def test_unconfigured_valkey_is_not_a_failure(self):
        """Valkey is optional (`valkey_url` defaults to None); an install
        without it is fully ready, not partially degraded."""
        r = await _get("/health/ready")
        assert r.status_code == 200
        assert r.json()["checks"]["valkey"]["status"] == "not_configured"

    @pytest.mark.asyncio
    async def test_degraded_valkey_still_reports_ready(self, monkeypatch):
        """ValkeyCache fails soft onto an in-process cache, so a broken Valkey
        costs cache coherence, not correctness. Pulling every replica out of
        rotation over a warm cache would turn a slowdown into an outage."""
        monkeypatch.setattr(settings, "valkey_url", "redis://unreachable:6379/0")

        import app.services.widget_data as wd

        def _boom():
            raise ConnectionError("valkey unreachable")

        monkeypatch.setattr(wd, "_get_cache_backend", _boom)

        r = await _get("/health/ready")
        assert r.status_code == 200, "a degraded optional cache must not fail readiness"
        assert r.json()["status"] == "ready"
        assert r.json()["checks"]["valkey"]["status"] == "degraded"
