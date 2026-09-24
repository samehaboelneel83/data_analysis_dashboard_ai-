"""SSRF guard for outbound data-source connections.

Broadening the connector catalog multiplies the places a user-supplied host or
URL reaches an outbound connection. The worst vector is a connection aimed at a
cloud instance-metadata endpoint (169.254.169.254 etc.), which can hand back
temporary cloud credentials — so those are blocked ALWAYS. Private/loopback/
reserved ranges are blocked only when `connector_allow_private_hosts` is False;
it defaults True so local/sandbox/dev databases and the sqlite demo keep working
(operators tighten it in production).
"""
from __future__ import annotations

import ipaddress
import socket

from ..core.config import settings

# Instance-metadata / link-local endpoints — blocked regardless of settings.
_METADATA_IPS = {
    "169.254.169.254",   # AWS / Azure / GCP IMDS
    "169.254.170.2",     # AWS ECS task metadata
    "100.100.100.200",   # Alibaba Cloud
    "fd00:ec2::254",     # AWS IMDS over IPv6
}


class BlockedHostError(ValueError):
    """Raised when a connection target is refused by the SSRF guard."""


def _resolved_ips(host: str) -> list[ipaddress._BaseAddress]:
    out: list[ipaddress._BaseAddress] = []
    # A literal IP: use it directly (getaddrinfo would too, but be explicit).
    try:
        out.append(ipaddress.ip_address(host))
        return out
    except ValueError:
        pass
    for family, _t, _p, _c, sockaddr in socket.getaddrinfo(host, None):
        try:
            out.append(ipaddress.ip_address(sockaddr[0]))
        except ValueError:
            continue
    return out


def assert_host_allowed(host: str | None) -> None:
    """Refuse a host that resolves to a metadata endpoint (always) or, when
    private hosts are disallowed, to a private/loopback/reserved address. A
    missing host (sqlite file, in-memory) is allowed."""
    if not host:
        return
    if host in _METADATA_IPS:
        raise BlockedHostError(f"Refusing to connect to the metadata endpoint {host}")
    try:
        ips = _resolved_ips(host)
    except socket.gaierror:
        # Unresolvable host: let the driver surface the real connection error
        # rather than masking it as a guard failure.
        return
    allow_private = getattr(settings, "connector_allow_private_hosts", True)
    for ip in ips:
        if str(ip) in _METADATA_IPS or ip.is_link_local:
            raise BlockedHostError(
                f"Refusing to connect to the link-local/metadata address {ip} (from host '{host}')")
        if not allow_private and (ip.is_private or ip.is_loopback or ip.is_reserved
                                  or ip.is_multicast or ip.is_unspecified):
            raise BlockedHostError(
                f"Host '{host}' resolves to a non-public address {ip}; blocked by policy")
