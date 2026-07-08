"""Shared outbound URL safety checks."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_OUTBOUND_SCHEMES = {"http", "https"}


class OutboundUrlError(ValueError):
    """Raised when a server-side fetch URL is not safe to request."""


def is_disallowed_host(host: str) -> bool:
    """Return True for private, loopback, link-local, reserved, or unresolved hosts."""
    candidate = host.strip("[]")
    try:
        return _is_disallowed_ip(ipaddress.ip_address(candidate))
    except ValueError:
        pass

    lower = candidate.lower()
    if lower in {"localhost", "ip6-localhost", "ip6-loopback"}:
        return True
    if lower.endswith(".local"):
        return True

    try:
        infos = socket.getaddrinfo(candidate, None)
    except OSError:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            if _is_disallowed_ip(ipaddress.ip_address(addr)):
                return True
        except ValueError:
            continue
    return False


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_outbound_url(url: str) -> str:
    """Validate a user/provider supplied URL before server-side fetches."""
    url_clean = (url or "").strip().strip("`\"'")
    parsed = urlparse(url_clean)
    if parsed.scheme.lower() not in ALLOWED_OUTBOUND_SCHEMES:
        raise OutboundUrlError(
            f"Unsupported URL scheme: {parsed.scheme or '(empty)'}. Use http:// or https://."
        )
    host = (parsed.hostname or "").strip()
    if not host:
        raise OutboundUrlError("URL is missing a host.")
    if is_disallowed_host(host):
        raise OutboundUrlError(f"Refusing to fetch private/loopback host: {host}.")
    return url_clean


__all__ = [
    "ALLOWED_OUTBOUND_SCHEMES",
    "OutboundUrlError",
    "is_disallowed_host",
    "validate_outbound_url",
]
