"""Teacher sessions, rate limiting and the request checks that protect the API."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

COOKIE = "tutor_teacher"


def _sign(secret: bytes, payload: str) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def make_session(secret: bytes, hours: int) -> str:
    """A signed, expiring token for the teacher's cookie. It carries no personal data."""
    payload = f"v1.{int(time.time()) + hours * 3600}"
    return f"{payload}.{_sign(secret, payload)}"


def valid_session(secret: bytes, token: str | None) -> bool:
    try:
        version, expires, signature = (token or "").split(".")
        return (version == "v1" and int(expires) > time.time()
                and hmac.compare_digest(signature, _sign(secret, f"{version}.{expires}")))
    except ValueError:
        return False


class RateLimiter:
    """Sliding-window limits kept in memory. One process; put a shared store behind it to run several."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            if len(self._hits) > 20000:                      # never grow without bound
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True


def client_ip(request: Request) -> str:
    if request.app.state.settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def limit(request: Request, name: str, per: int, seconds: float, who: str | None = None) -> None:
    """Raise 429 when this caller has used up its allowance for `name`."""
    if not request.app.state.limiter.allow(f"{name}:{who or client_ip(request)}", per, seconds):
        raise HTTPException(429, "Too many requests. Please wait a moment and try again.")


def origin_is_allowed(request: Request) -> bool:
    """State-changing requests from a browser must come from this site (or an origin you allow). Blocks cross-site forms."""
    origin = request.headers.get("origin")
    if not origin:
        return True                                          # not a browser, or a same-origin request without the header
    own = f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"
    return origin.rstrip("/") in {own, *request.app.state.settings.allowed_origins}
