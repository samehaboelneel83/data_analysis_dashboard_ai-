"""SSRF guard: metadata endpoints always blocked; private ranges by policy."""
import pytest

from app.core.config import settings
from app.services import net_guard
from app.services.net_guard import BlockedHostError, assert_host_allowed


@pytest.fixture
def _resolve(monkeypatch):
    """Make host→IP deterministic without real DNS."""
    def resolver(mapping):
        def fake(host, *a, **k):
            ip = mapping.get(host, host)
            return [(0, 0, 0, "", (ip, 0))]
        monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake)
    return resolver


def test_metadata_ip_literal_always_blocked():
    with pytest.raises(BlockedHostError):
        assert_host_allowed("169.254.169.254")
    with pytest.raises(BlockedHostError):
        assert_host_allowed("fd00:ec2::254")


def test_hostname_resolving_to_metadata_blocked(_resolve):
    _resolve({"evil.example.com": "169.254.169.254"})
    with pytest.raises(BlockedHostError):
        assert_host_allowed("evil.example.com")


def test_link_local_always_blocked(_resolve):
    _resolve({"h": "169.254.10.10"})
    with pytest.raises(BlockedHostError):
        assert_host_allowed("h")


def test_private_allowed_by_default_blocked_when_disabled(_resolve, monkeypatch):
    _resolve({"db.internal": "10.1.2.3"})
    monkeypatch.setattr(settings, "connector_allow_private_hosts", True)
    assert_host_allowed("db.internal")  # default: allowed (dev/sandbox)
    monkeypatch.setattr(settings, "connector_allow_private_hosts", False)
    with pytest.raises(BlockedHostError):
        assert_host_allowed("db.internal")


def test_loopback_blocked_only_under_strict_policy(_resolve, monkeypatch):
    _resolve({"localhost": "127.0.0.1"})
    monkeypatch.setattr(settings, "connector_allow_private_hosts", True)
    assert_host_allowed("localhost")
    monkeypatch.setattr(settings, "connector_allow_private_hosts", False)
    with pytest.raises(BlockedHostError):
        assert_host_allowed("localhost")


def test_public_host_allowed_either_way(_resolve, monkeypatch):
    _resolve({"warehouse.example.com": "93.184.216.34"})
    for allow in (True, False):
        monkeypatch.setattr(settings, "connector_allow_private_hosts", allow)
        assert_host_allowed("warehouse.example.com")  # never raises


def test_no_host_is_allowed():
    assert_host_allowed(None)
    assert_host_allowed("")


def test_build_url_blocks_metadata_host():
    from app.services import connectors
    with pytest.raises(BlockedHostError):
        connectors.build_url({"type": "postgresql", "host": "169.254.169.254",
                              "database": "d", "username": "u", "password": "p"})
