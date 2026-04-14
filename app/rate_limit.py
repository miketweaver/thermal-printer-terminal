"""Simple in-memory rate limiter for print form submissions."""

from collections import defaultdict
from time import time

_requests: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    """Return True if the request is within rate limits."""
    now = time()
    _requests[key] = [t for t in _requests[key] if now - t < window_seconds]
    if len(_requests[key]) >= max_requests:
        return False
    _requests[key].append(now)
    return True
