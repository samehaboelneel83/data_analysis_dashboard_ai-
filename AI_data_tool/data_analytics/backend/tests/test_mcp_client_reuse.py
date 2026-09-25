"""T8: the MCP server's `_client()` used to build a fresh DatalyticsClient (and HTTP
connection pool) on every tool call. It's now a lazily-created, thread-safe singleton
reused across calls, with `reset_client()` as a test-only escape hatch.

`mcp_server` depends on the `mcp` package, which lives in mcp_server/requirements.txt
(kept out of the main backend image on purpose — see that file). Skip cleanly if it
isn't installed in the environment running these tests.
"""
import pytest

pytest.importorskip("mcp")

import mcp_server.server as server


class _FakeClient:
    """Stand-in for DatalyticsClient: records how many times it was constructed
    without touching the network."""
    instances = 0

    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
        _FakeClient.instances += 1

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    _FakeClient.instances = 0
    monkeypatch.setenv("DATALYTICS_TOKEN", "t")
    monkeypatch.setenv("DATALYTICS_URL", "http://api/api/v1")
    monkeypatch.setattr(server, "DatalyticsClient", _FakeClient)
    server.reset_client()
    yield
    server.reset_client()


def test_client_is_a_singleton_reused_across_calls():
    c1 = server._client()
    c2 = server._client()
    assert c1 is c2
    assert _FakeClient.instances == 1


def test_client_construction_happens_exactly_once_across_many_calls():
    for _ in range(10):
        server._client()
    assert _FakeClient.instances == 1


def test_reset_client_forces_a_fresh_instance():
    c1 = server._client()
    server.reset_client()
    c2 = server._client()
    assert c1 is not c2
    assert _FakeClient.instances == 2


def test_client_raises_without_a_token(monkeypatch):
    monkeypatch.delenv("DATALYTICS_TOKEN", raising=False)
    server.reset_client()
    with pytest.raises(RuntimeError):
        server._client()
