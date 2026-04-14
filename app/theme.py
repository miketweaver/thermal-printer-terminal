"""DNS resolution and callsign helpers for the Thermal Printer Terminal."""

import re
import socket
import time as _time

# ITU amateur callsign regex — covers all international prefix formats.
_CALLSIGN_RE = re.compile(
    r'^('
    r'[A-Z]{1,2}\d{1,2}[A-Z]{1,4}'
    r'|'
    r'\d[A-Z]{1,2}\d[A-Z]{1,4}'
    r')(?=[-.]|$)',
    re.IGNORECASE,
)

_dns_cache: dict[str, tuple[str, float]] = {}
_DNS_TTL = 600  # 10 minutes — mesh nodes come and go


def resolve_hostname(ip: str) -> str:
    """Reverse-DNS an IP to a hostname, with a 10-min TTL cache."""
    now = _time.monotonic()
    if ip in _dns_cache:
        val, ts = _dns_cache[ip]
        if now - ts < _DNS_TTL:
            return val
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        if hostname and hostname != ip:
            _dns_cache[ip] = (hostname, now)
            return hostname
    except (socket.herror, socket.gaierror, OSError):
        pass
    _dns_cache[ip] = ('', now)
    return ''


def resolve_client_display(ip: str) -> str:
    """Format client IP with its mesh hostname for display."""
    hostname = resolve_hostname(ip)
    if hostname:
        return f'{ip} ({hostname})'
    return ip


def callsign_from_hostname(ip: str) -> str:
    """Try to extract a callsign from the reverse DNS hostname."""
    hostname = resolve_hostname(ip)
    if hostname:
        m = _CALLSIGN_RE.match(hostname)
        if m:
            return m.group(1).upper()
    return ''
